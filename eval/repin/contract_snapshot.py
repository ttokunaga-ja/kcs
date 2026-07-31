#!/usr/bin/env python3
"""renderer / validator contract を組んで (bytes, sha256) を記録する。

`snapshot.py` はこれらを丸ごと取りこぼしていた。理由は 2 つある:

- 契約モジュールは `persona_v2_*_validator.py` を「validator のテスト用モジュール」
  だと思って除外していたが、実際には **正本の生産者** である
  (`persona_v2_text_validator` が contributor-text の validator contract を作る)。
- 契約モジュールは `ARTIFACT_KIND` ではなく `CONTRACT_KIND` を宣言し、builder も
  `build_*_suite_descriptor` ではなく `build_renderer_contract` である。

正準化はモジュールごとに違う (raw-image-media だけ terminal-LF 付き ASCII) ので、
**そのモジュール自身の `*_contract_sha256()` で測る**。共通ハッシャで測ると
raw-image-media だけ静かに別の値になる。

生産者の一覧は `PAIR_SPECS` から取る — レジストリ自身が正本として持っている表を
読むので、こちらでモジュール名を綴り直す必要がない。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path


def silence_all(root: Path) -> None:
    """全 persona_v2 モジュールの pin 検査を黙らせる。改名後の側でのみ使う。"""
    for path in sorted((root / "eval").glob("persona_v2_*.py")):
        try:
            module = importlib.import_module(f"eval.{path.stem}")
        except Exception:
            continue
        if hasattr(module, "_fail"):
            module._fail = lambda *a, **k: None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--allow-fail", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.root.resolve()))
    if args.allow_fail:
        silence_all(args.root)

    registry = importlib.import_module(
        "eval.persona_v2_format_implementation_registry"
    )
    if args.allow_fail:
        silence_all(args.root)  # レジストリ取り込みで新たに載ったものも黙らせる

    result: dict[str, dict] = {}
    for pair_id, _, renderer, validator in registry.PAIR_SPECS:
        for role, module, builder, hasher in (
            ("renderer", renderer, "build_renderer_contract", "renderer_contract_sha256"),
            ("validator", validator, "build_validator_contract", "validator_contract_sha256"),
        ):
            binding_id = f"{pair_id}-{role}-contract"
            try:
                value = getattr(module, builder)()
                digest = getattr(module, hasher)(value)
                # bytes は共通ハッシャの長さではなくレジストリが pin している
                # `canonical_bytes` と同じ意味でなければ番人にならない。契約側の
                # `canonical_json_bytes` は正準化の違いをそのまま反映する。
                size = len(module.canonical_json_bytes(value))
            except Exception as error:
                result[binding_id] = {"error": f"{type(error).__name__}: {error}"[:200]}
                print(f"  [skip] {binding_id}: {type(error).__name__}",
                      file=sys.stderr, flush=True)
                continue
            if digest != hashlib.sha256(
                module.canonical_json_bytes(value)
            ).hexdigest():
                # 正準化が 2 通りあるモジュールの取り違えを検出する。
                print(f"  [warn] {binding_id}: hasher disagrees with canonical bytes",
                      file=sys.stderr, flush=True)
            result[binding_id] = {
                "module": module.__name__.rsplit(".", 1)[-1],
                "builder": builder,
                "bytes": size,
                "sha256": digest,
            }
            print(f"  {binding_id}: {size} bytes", file=sys.stderr, flush=True)

    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    ok = sum(1 for v in result.values() if "sha256" in v)
    print(f"\n[ok] {ok}/{len(result)} contracts -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
