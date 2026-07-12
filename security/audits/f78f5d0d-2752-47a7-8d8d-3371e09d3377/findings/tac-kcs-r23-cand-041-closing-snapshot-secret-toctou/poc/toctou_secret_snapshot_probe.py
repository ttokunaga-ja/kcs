#!/usr/bin/env python3
"""Synthetic regression probe for KCS-R23-CAND-041.

The probe models the preview-to-closing-snapshot interleaving with temporary
files only. It intentionally does not invoke KCS, touch a .kcs store, or read
real credentials.
"""

from pathlib import Path
import tempfile


TIER_A_NAMES = {".env", ".env.local", ".npmrc"}
TIER_A_SUFFIXES = (".pem", ".key", ".p12")


def is_tier_a_name(name: str) -> bool:
    return name in TIER_A_NAMES or name.endswith(TIER_A_SUFFIXES)


def preview_exclusions(scope: Path) -> set[str]:
    return {path.name for path in scope.iterdir() if is_tier_a_name(path.name)}


def vulnerable_closing_archive(scope: Path, excluded: set[str]) -> list[str]:
    archived = []
    for path in sorted(scope.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        if path.name in excluded:
            continue
        archived.append(path.name)
    return archived


def fixed_last_use_exclusions(scope: Path) -> set[str]:
    return {path.name for path in scope.iterdir() if is_tier_a_name(path.name)}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kcs-cand-041-") as tmp:
        scope = Path(tmp)
        (scope / "notes.md").write_text("ordinary archive content\n", encoding="utf-8")
        (scope / "present.pem").write_text(
            "synthetic preview-time secret\n", encoding="utf-8"
        )

        excluded = preview_exclusions(scope)
        print("[+] created synthetic scope")
        print(f"[+] preview excluded names: {sorted(excluded)!r}")

        introduced = scope / ".env"
        introduced.write_text("SYNTHETIC_TOKEN=not-a-real-secret\n", encoding="utf-8")
        print(f"[+] introduced Tier-A name after preview: {introduced.name}")

        vulnerable_archive = vulnerable_closing_archive(scope, excluded)
        print(f"[+] vulnerable closing snapshot would archive: {vulnerable_archive!r}")

        if ".env" not in vulnerable_archive:
            print("[-] model did not reproduce the stale-exclusion admission")
            return 1

        print("[!] stale exclusion admitted newly introduced Tier-A file: .env")

        fixed_excluded = fixed_last_use_exclusions(scope)
        print(f"[+] fixed last-use classification would exclude: {sorted(fixed_excluded)!r}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
