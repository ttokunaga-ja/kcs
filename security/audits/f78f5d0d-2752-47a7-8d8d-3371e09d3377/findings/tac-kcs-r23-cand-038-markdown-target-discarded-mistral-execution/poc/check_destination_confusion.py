#!/usr/bin/env python3
"""Local/offline source invariant check for KCS-R23-CAND-038.

This probe reads the pinned KCS source revision through `git show`. It does not
send traffic, execute KCS, read secrets, or contact a provider. The check models
the configuration-to-dispatch invariant: target fields accepted from tools.toml
must either be rejected or survive into the runtime dispatcher.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

REV = "0e19f3c6489da458e93a982a333c308d92d0a0ae"
REQUIRED_ACCEPTED_FIELDS = {"kind", "cmd", "args", "url", "model", "auth"}
DROPPED_TARGET_FIELDS = {"kind", "cmd", "args", "url"}


def repo_root() -> pathlib.Path:
    env = os.environ.get("KCS_REPO")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    current = pathlib.Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    print("error: set KCS_REPO to a checkout containing the target revision", file=sys.stderr)
    sys.exit(2)


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def source(repo: pathlib.Path, rel: str) -> str:
    return git(repo, "show", f"{REV}:{rel}")


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"[-] {message}", file=sys.stderr)
        sys.exit(1)
    print(f"[+] {message}")


def block_between(text: str, start: str, end: str) -> str:
    start_idx = text.index(start)
    end_idx = text.index(end, start_idx)
    return text[start_idx:end_idx]


def main() -> int:
    repo = repo_root()
    head = git(repo, "rev-parse", "HEAD").strip()
    require(head == REV, f"checked target revision {REV}")

    tool_lock = source(repo, "crates/kcs-adapter/src/tool_lock.rs")
    catalog = source(repo, "crates/kcs-adapter/src/catalog.rs")
    mistral = source(repo, "crates/kcs-adapter/src/mistral_ocr.rs")
    cli = source(repo, "crates/kcs-cli/src/main.rs")

    fields_match = re.search(r"const TOOLS_ENTRY_FIELDS: &\[&str\] = &\[(.*?)\];", tool_lock, re.S)
    require(fields_match is not None, "found TOOLS_ENTRY_FIELDS")
    accepted_fields = set(re.findall(r'"([a-z_]+)"', fields_match.group(1)))
    require(REQUIRED_ACCEPTED_FIELDS.issubset(accepted_fields),
            "tools.toml accepts kind/cmd/args/url/model/auth fields")

    struct_block = block_between(tool_lock, "pub struct DeclaredAdapter", "}\n\n/// R13-2: locate")
    require(all(f"pub {field}: Option<String>" in struct_block for field in ["tool_id", "model", "auth"]),
            "DeclaredAdapter retains only tool_id/model/auth")
    require(all(f"pub {field}:" not in struct_block for field in DROPPED_TARGET_FIELDS),
            "DeclaredAdapter has no kind/cmd/args/url fields")

    projection = block_between(tool_lock, "pub fn declared_adapter_for_role", "}\n\n/// R13-2: process-global")
    projection_reads = set(re.findall(r'\.get\("([^"]+)"\)', projection))
    require({"model", "auth"}.issubset(projection_reads),
            "declared_adapter_for_role copies model/auth")
    require(projection_reads.isdisjoint(DROPPED_TARGET_FIELDS),
            "declared_adapter_for_role never copies kind/cmd/args/url")

    require("register_declared_adapters(map);" in cli and "declared_adapter_for_role(&value, role)" in cli,
            "CLI registers the lossy DeclaredAdapter projection")

    run_body = block_between(catalog, "pub fn run_standard_online_markdownize", "}\n\n/// R13-2: the configured")
    require("EnvMistralOcrClient::new()" in run_body,
            "production markdown path constructs EnvMistralOcrClient")
    require("declared_markdown_model()" in run_body,
            "production markdown path consults only the declared model")
    require("declared_markdown_url" not in catalog and "declared_markdown_cmd" not in catalog,
            "catalog has no declared target dispatcher")

    require('std::env::var("MISTRAL_API_BASE")' in mistral and '"https://api.mistral.ai"' in mistral,
            "Mistral client chooses ambient/default base URL")
    require('resolve_role_api_key("markdown", "MISTRAL_API_KEY")' in mistral,
            "Mistral client resolves the retained markdown auth secret")
    require('/v1/ocr' in mistral and 'set("Authorization", &format!("Bearer {api_key}"))' in mistral,
            "document bytes are sent in a bearer-authenticated OCR request")

    preview = block_between(cli, "fn index_preview_json", "}\n\n#[derive(Debug, Default)]")
    require("network_transmission_policy" in preview and "adapter_execution_mode" in preview,
            "preview exposes generic network/mode fields")
    require("MISTRAL_API_BASE" not in preview and "cmd" not in preview and "url" not in preview,
            "preview does not disclose declared versus effective recipient")

    synthetic_declared_url = "http://127.0.0.1:18080/private-ocr"
    effective_default = "https://api.mistral.ai"
    print(f"[+] synthetic declared url {synthetic_declared_url} is not projected into runtime")
    print(f"[+] effective default recipient remains {effective_default} unless ambient base is set")
    print("result: vulnerable destination-confusion invariant is present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
