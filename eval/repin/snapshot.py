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
import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(".")
sys.path.insert(0, str(ROOT))


def artifacts() -> list[tuple[str, str]]:
    """(module, zero-arg builder) を宣言順に集める。**正本を選ばない。**

    「どれが正本の builder か」を当てにいく版は 3 回続けて外した — 最初の builder
    だと仮定して per-persona の 3 モジュールを落とし、`ARTIFACT_KIND = "` を条件に
    して複数行で書いているモジュールを落とし、`overlay_reservation_layout` では
    origin suite を掴んで byte cap で落ちた。そのたびに「解けない残件」に見えて
    いたが、実際は測っていないだけだった。

    当てる必要が無い。**引数を取らない builder を全部測ればよい。** 対応の採用条件
    (bytes が前後で一致し、`old` が repo に実在する) が正本でないものを自動的に
    弾く — どこにも pin されていない出力は `old` が repo に無いので採られない。
    選別を推測から検査へ移すのが要点で、余分に組む時間は誤りを見逃す代償より安い。
    """
    found = []
    for path in sorted((ROOT / "eval").glob("persona_v2_*.py")):
        source = path.read_text(encoding="utf-8")
        for builder in re.findall(r"^def (build_[a-z0-9_]+)\(", source, re.M):
            found.append((path.stem, builder))
    return found


def callable_with_no_arguments(function) -> bool:
    """引数なしで呼べるかを署名で判定する。

    `\\(\\s*\\)` という正規表現で「引数を取らない」を判定していた版は、
    **既定値付きの引数を持つ builder** を取りこぼした
    (`build_device_lane_compositor(envelope_value=None)` は引数なしで呼べる)。
    ソースの見た目で当てるのをやめ、署名に訊く。
    """
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return all(
        parameter.default is not inspect.Parameter.empty
        or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        for parameter in parameters
    )


def persona_argument(function) -> bool:
    """persona_id 1 つだけを取る builder か。

    引数なしで呼べる builder しか測らない版は、**per-persona builder を丸ごと
    落としていた**。`build_fact_graph(persona_id)` の pin は 19 件 (p02-p20) が
    バイト数そのままで digest だけ動いた状態、つまり改名以外に理由の無い
    未再 pin のまま残っていた。しかもテストは最初の不一致で fail-fast するので、
    19 件が 2 件のエラーとして見えていた。
    """
    try:
        parameters = list(inspect.signature(function).parameters.values())
    except (TypeError, ValueError):
        return False
    required = [p for p in parameters if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(required) == 1 and "persona" in required[0].name


def canonical_bytes(module, value) -> bytes:
    """モジュール自身のハッシャで測る。無ければ共通の正準化に落とす。

    `canonical_json_bytes` を公開していないモジュールがある (`corpus_input_closure_v3`
    は `corpus_input_closure_v3_candidate_bytes` という名前で持つ)。名前を当てにいく
    より、共通の正準化に落として**採用条件に判定させる**ほうが安全である — 正準化を
    取り違えていれば digest はどこにも pin されておらず、`old` が repo に無いので
    その対応は採られない。byte cap は測るだけなので効かせない。
    """
    if hasattr(module, "canonical_json_bytes"):
        return module.canonical_json_bytes(value)
    common = importlib.import_module("eval.persona_v2_artifact_common")
    return common.canonical_json_bytes(value, label="snapshot", max_bytes=1 << 30)


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
        key = f"{module_name}::{builder}"
        try:
            module = importlib.import_module(f"eval.{module_name}")
            if args.allow_fail and hasattr(module, "_fail"):
                module._fail = lambda *a, **k: None
            function = getattr(module, builder)
            if callable_with_no_arguments(function):
                raw = canonical_bytes(module, function())
            elif persona_argument(function):
                # per-persona builder は persona ごとに 1 件として記録する。
                envelope = importlib.import_module("eval.persona_v2_contract")
                for persona in envelope.PERSONA_IDS:
                    try:
                        one = canonical_bytes(module, function(persona))
                    except Exception as error:
                        result[f"{key}[{persona}]"] = {
                            "error": f"{type(error).__name__}: {error}"[:200]}
                        continue
                    result[f"{key}[{persona}]"] = {
                        "bytes": len(one),
                        "sha256": hashlib.sha256(one).hexdigest(),
                    }
                print(f"  {key}[*]: {len(envelope.PERSONA_IDS)} personas",
                      file=sys.stderr, flush=True)
                continue
            else:
                continue
        except Exception as error:
            result[key] = {"error": f"{type(error).__name__}: {error}"[:200]}
            print(f"  [skip] {key}: {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        result[key] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        print(f"  {key}: {len(raw)} bytes", file=sys.stderr, flush=True)

    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = sum(1 for v in result.values() if "sha256" in v)
    print(f"\n[ok] {ok}/{len(result)} artifacts -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
