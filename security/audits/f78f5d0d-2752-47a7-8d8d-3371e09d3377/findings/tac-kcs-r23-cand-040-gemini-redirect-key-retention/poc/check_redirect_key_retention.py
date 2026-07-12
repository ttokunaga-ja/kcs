#!/usr/bin/env python3
import argparse
import os
from pathlib import Path


def read(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"[fail] missing required file: {path}")
    return path.read_text(encoding="utf-8")


def find_ureq_src(explicit: str | None) -> Path:
    if explicit:
        src = Path(explicit)
        if (src / "unit.rs").exists() and (src / "agent.rs").exists():
            return src
        raise SystemExit(f"[fail] UREQ_SRC does not look like ureq src: {src}")

    roots = []
    cargo_home = os.environ.get("CARGO_HOME")
    if cargo_home:
        roots.append(Path(cargo_home) / "registry" / "src")
    roots.append(Path.home() / ".cargo" / "registry" / "src")

    for root in roots:
        if not root.exists():
            continue
        for src in root.glob("*/ureq-2.12.1/src"):
            if (src / "unit.rs").exists() and (src / "agent.rs").exists():
                return src
    raise SystemExit("[fail] could not locate ureq-2.12.1/src; pass UREQ_SRC")


def require(condition: bool, ok_message: str, fail_message: str) -> None:
    if not condition:
        raise SystemExit(f"[fail] {fail_message}")
    print(f"[ok] {ok_message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--ureq-src")
    args = parser.parse_args()

    source_root = Path(args.source_root)
    gemini = read(source_root / "crates/kcs-adapter/src/gemini_embedding.rs")
    lock = read(source_root / "Cargo.lock")
    cargo_toml = read(source_root / "Cargo.toml")
    ureq_src = find_ureq_src(args.ureq_src)
    lib_rs = read(ureq_src / "lib.rs")
    agent_rs = read(ureq_src / "agent.rs")
    unit_rs = read(ureq_src / "unit.rs")

    require(
        'ureq::post(&format!' in gemini
        and '.set("x-goog-api-key", &api_key)' in gemini
        and ".send_json(" in gemini,
        "KCS attaches the Gemini secret as x-goog-api-key on ureq::post",
        "Gemini request no longer matches the vulnerable top-level ureq::post pattern",
    )
    require(
        'ureq = { version = "2", features = ["json"] }' in cargo_toml
        and 'name = "ureq"' in lock
        and 'version = "2.12.1"' in lock,
        "repository lockfile pins ureq 2.12.1",
        "workspace no longer selects the inspected ureq 2.12.1 dependency",
    )
    require(
        "AgentBuilder::new().build()" in lib_rs
        and "pub fn post(path: &str) -> Request" in lib_rs
        and 'request("POST", path)' in lib_rs,
        "top-level ureq::post uses a default agent",
        "ureq top-level post no longer uses the inspected default-agent path",
    )
    require(
        "redirects: 5" in agent_rs
        and "redirect_auth_headers: RedirectAuthHeaders::Never" in agent_rs,
        "default ureq agent enables redirects",
        "ureq default redirect configuration changed",
    )
    require(
        "url.join(location)" in unit_rs
        and '301 | 302 | 303' in unit_rs
        and 'Payload::Empty.into_read()' in unit_rs,
        "redirect code accepts Location without same-origin enforcement",
        "ureq redirect join or POST-to-GET behavior changed",
    )
    require(
        '!h.is_name("content-length")' in unit_rs
        and '!h.is_name("cookie")' in unit_rs
        and '!h.is_name("authorization")' in unit_rs
        and "x-goog-api-key" not in unit_rs,
        "redirect reconstruction strips authorization/cookie but not x-goog-api-key",
        "ureq now explicitly strips the Gemini custom key header or changed header filtering",
    )
    print("[vulnerable] custom Gemini key header survives the locked redirect path")


if __name__ == "__main__":
    main()
