#!/usr/bin/env python3
"""Static regression probe for KCS-R23-CAND-039.

The probe reads a KCS source checkout and verifies the vulnerable source shape
for the embedding adapter target/model drift. It does not execute adapters,
read secrets, or send network traffic.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


def read_source(root: pathlib.Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"[-] could not read {relative}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[-] {message}")
    print(f"[+] {message}")


def extract_struct(source: str, name: str) -> str:
    match = re.search(rf"pub struct {re.escape(name)}\s*\{{(?P<body>.*?)\n\}}", source, re.S)
    if not match:
        raise SystemExit(f"[-] could not find struct {name}")
    return match.group("body")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        required=True,
        help="path to a KCS checkout at the reviewed revision",
    )
    args = parser.parse_args()

    root = pathlib.Path(args.source_root)
    tool_lock = read_source(root, "crates/kcs-adapter/src/tool_lock.rs")
    catalog = read_source(root, "crates/kcs-adapter/src/catalog.rs")
    gemini = read_source(root, "crates/kcs-adapter/src/gemini_embedding.rs")

    accepted_fields = ["kind", "cmd", "args", "url", "model", "auth"]
    require(
        all(f'"{field}"' in tool_lock for field in accepted_fields),
        "accepted embedding declaration fields include kind/cmd/args/url/model/auth",
    )

    declared_adapter = extract_struct(tool_lock, "DeclaredAdapter")
    require(
        "pub model:" in declared_adapter
        and "pub auth:" in declared_adapter
        and "pub url:" not in declared_adapter
        and "pub kind:" not in declared_adapter
        and "pub cmd:" not in declared_adapter
        and "pub args:" not in declared_adapter,
        "DeclaredAdapter keeps model/auth but not destination execution fields",
    )

    require(
        'registered_declared_adapter("embedding")' in catalog
        and ".and_then(|declared| declared.auth)" in catalog
        and "real_embedding_activation(" in catalog,
        "declared embedding auth activates real execution",
    )

    require(
        "AdoptedEmbeddingExecution::Real => GeminiEmbeddingAdapter::default().embed(request)"
        in catalog,
        "real embedding execution dispatches GeminiEmbeddingAdapter::default()",
    )

    require(
        'std::env::var("GEMINI_API_BASE")' in gemini
        and '"https://generativelanguage.googleapis.com"' in gemini,
        "Gemini client chooses GEMINI_API_BASE or Google's default, not the declared URL",
    )

    require(
        '"x-goog-api-key"' in gemini
        and "item.text.clone().unwrap_or_default()" in gemini
        and ":batchEmbedContents" in gemini,
        "Gemini embed sink sends x-goog-api-key and item text",
    )

    print(
        "[+] vulnerable pattern confirmed: accepted embedding target/model can drift to fixed Gemini execution"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
