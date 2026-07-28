#!/usr/bin/env python3
"""各 artifact を組んで (bytes, sha256) を記録する。改名の前後で 1 回ずつ走らせる。

## なぜこの形なのか

前の試みは「pin が落ちた → そのモジュールに書かれている 64 桁のどれかが古い値だ
ろう」と**推測**して差し替え、無関係な上流 pin を潰した。推測が入る余地を無くす。

同じ artifact を改名の前後で組めば、`digest_before -> digest_after` は
**同一の builder の出力どうしの対応**として決まる。どの pin がどの値を保持して
いるかを知る必要はない — 改名前の値がそこに書かれていたことは、改名前にテストが
通っていた事実が保証している。

`--allow-fail` は改名後の側でだけ使う。改名前は pin が揃っているので不要であり、
「pin を黙らせないと組めない」こと自体が改名前ツリーの異常を意味する。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(".")
sys.path.insert(0, str(ROOT))


def artifacts() -> list[tuple[str, str]]:
    """(module, zero-arg builder) を宣言順に集める。"""
    found = []
    for path in sorted((ROOT / "eval").glob("persona_v2_*.py")):
        if path.stem.endswith("_validator"):
            continue
        source = path.read_text(encoding="utf-8")
        if 'ARTIFACT_KIND = "' not in source:
            continue
        builders = re.findall(r"^def (build_[a-z0-9_]+)\(\s*\)\s*:", source, re.M)
        if builders:
            found.append((path.stem, builders[0]))
    return found


def silence_all() -> None:
    """全 persona_v2 モジュールの pin 検査を黙らせる。改名後の側でのみ使う。"""
    for path in sorted((ROOT / "eval").glob("persona_v2_*.py")):
        try:
            module = importlib.import_module(f"eval.{path.stem}")
        except Exception:
            continue
        if hasattr(module, "_fail"):
            module._fail = lambda *a, **k: None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-fail", action="store_true")
    args = parser.parse_args()

    if args.allow_fail:
        silence_all()

    result: dict[str, dict] = {}
    for module_name, builder in artifacts():
        try:
            module = importlib.import_module(f"eval.{module_name}")
            if args.allow_fail and hasattr(module, "_fail"):
                module._fail = lambda *a, **k: None
            raw = module.canonical_json_bytes(getattr(module, builder)())
        except Exception as error:
            result[module_name] = {"error": f"{type(error).__name__}: {error}"[:200]}
            print(f"  [skip] {module_name}: {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        result[module_name] = {
            "builder": builder,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        print(f"  {module_name}: {len(raw)} bytes", file=sys.stderr, flush=True)

    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = sum(1 for v in result.values() if "sha256" in v)
    print(f"\n[ok] {ok}/{len(result)} artifacts -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
