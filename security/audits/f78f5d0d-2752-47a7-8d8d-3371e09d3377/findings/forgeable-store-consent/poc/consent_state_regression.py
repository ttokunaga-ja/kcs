#!/usr/bin/env python3
"""Harmless offline regression for portable, self-asserted KCS consent state.

This models the exact acceptance predicates in the confirmed revision.  It
does not invoke KCS, load credentials, create sockets, or contact a service.
All synthetic state is created below a temporary directory and removed on
exit.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


ORIGIN_SCOPE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
FORGED_SCOPE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
RECEIVER_SCOPE_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAX"
TOOL_ID = "synthetic.embedding.adapter"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def make_store(
    root: Path,
    scope_id: str,
    *,
    asserted_root: str,
    asserted_actor: str,
) -> Path:
    kcs_dir = root / ".kcs"
    kcs_dir.mkdir(parents=True)
    write_json(
        kcs_dir / "scope.json",
        {
            "kcs_format_version": "0.1.0",
            "scope_id": scope_id,
            "scope_path": asserted_root,
        },
    )
    write_jsonl(
        kcs_dir / "approvals.jsonl",
        [
            {
                "scope_id": scope_id,
                "tool_id": TOOL_ID,
                "execution_mode": "online_api",
                "network_opt_in": True,
                # These provenance-looking fields are ignored by the reader.
                "root_path": asserted_root,
                "actor": asserted_actor,
                "approved_at": "1900-01-01T00:00:00Z",
                "approval_method": "approve",
            }
        ],
    )
    write_jsonl(
        kcs_dir / "secrets-approved.jsonl",
        [
            {
                "scope_id": scope_id,
                "approval_method": "send_secrets",
                "actor": asserted_actor,
                "approved_at": "1900-01-01T00:00:00Z",
            }
        ],
    )
    return kcs_dir


def read_scope_id(kcs_dir: Path) -> str:
    return json.loads((kcs_dir / "scope.json").read_text(encoding="utf-8"))["scope_id"]


def rows(path: Path) -> Iterable[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    parsed: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def current_network_reader(kcs_dir: Path, tool_id: str) -> bool:
    """Mirror approval_row_present_in_kcs_dir at main.rs:6362-6378."""
    expected_scope_id = read_scope_id(kcs_dir)
    return any(
        row.get("scope_id") == expected_scope_id
        and row.get("tool_id") == tool_id
        and row.get("execution_mode") == "online_api"
        and row.get("network_opt_in") is True
        for row in rows(kcs_dir / "approvals.jsonl")
    )


def current_secret_reader(kcs_dir: Path) -> bool:
    """Mirror secrets_send_approved at main.rs:10543-10555."""
    expected_scope_id = read_scope_id(kcs_dir)
    return any(
        row.get("scope_id") == expected_scope_id
        and row.get("approval_method") == "send_secrets"
        for row in rows(kcs_dir / "secrets-approved.jsonl")
    )


def trusted_local_reader(
    local_grants: set[tuple[str, str, str, str]],
    root: Path,
    kcs_dir: Path,
    tool_id: str,
    operation: str,
) -> bool:
    """Regression oracle: authority comes from protected device-local state."""
    key = (str(root.resolve()), read_scope_id(kcs_dir), tool_id, operation)
    return key in local_grants


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kcs-consent-regression-") as tmp:
        base = Path(tmp)

        origin_root = base / "trusted-origin"
        origin = make_store(
            origin_root,
            ORIGIN_SCOPE_ID,
            asserted_root=str(origin_root),
            asserted_actor="trusted-operator",
        )

        # Existing negative control: copying only a row into another scope fails
        # because its receiving scope_id differs.
        receiver_root = base / "different-scope"
        receiver = make_store(
            receiver_root,
            RECEIVER_SCOPE_ID,
            asserted_root=str(receiver_root),
            asserted_actor="trusted-operator",
        )
        shutil.copyfile(origin / "approvals.jsonl", receiver / "approvals.jsonl")
        shutil.copyfile(
            origin / "secrets-approved.jsonl", receiver / "secrets-approved.jsonl"
        )

        # Whole-store replay: scope.json and both rows move together, so the
        # self-comparison still succeeds at a different canonical root.
        copied_root = base / "adopted-copy"
        copied = copied_root / ".kcs"
        shutil.copytree(origin, copied)

        # Preseeded forgery: a contributor can choose both the scope identity and
        # the matching unsigned rows, including arbitrary provenance fields.
        forged_root = base / "preseeded-forgery"
        forged = make_store(
            forged_root,
            FORGED_SCOPE_ID,
            asserted_root="/asserted/by/archive/contributor",
            asserted_actor="archive-contributor",
        )

        foreign_network = current_network_reader(receiver, TOOL_ID)
        foreign_secrets = current_secret_reader(receiver)
        copied_network = current_network_reader(copied, TOOL_ID)
        copied_secrets = current_secret_reader(copied)
        forged_network = current_network_reader(forged, TOOL_ID)
        forged_secrets = current_secret_reader(forged)

        assert not foreign_network and not foreign_secrets
        assert copied_network and copied_secrets
        assert forged_network and forged_secrets

        # A protected device-local grant is deliberately bound to the canonical
        # origin root. Replaying the store or inventing a new store cannot create
        # another entry in this authority domain.
        local_grants = {
            (str(origin_root.resolve()), ORIGIN_SCOPE_ID, TOOL_ID, "network"),
            (str(origin_root.resolve()), ORIGIN_SCOPE_ID, TOOL_ID, "send_secrets"),
        }
        fixed_origin = trusted_local_reader(
            local_grants, origin_root, origin, TOOL_ID, "network"
        )
        fixed_copy = trusted_local_reader(
            local_grants, copied_root, copied, TOOL_ID, "network"
        )
        fixed_forgery = trusted_local_reader(
            local_grants, forged_root, forged, TOOL_ID, "network"
        )
        assert fixed_origin and not fixed_copy and not fixed_forgery

        print(
            "[+] foreign-row negative control: "
            f"network={foreign_network} secrets={foreign_secrets}"
        )
        print(
            "[!] copied whole-store replay: "
            f"network={copied_network} secrets={copied_secrets}"
        )
        print(
            "[!] preseeded same-store forgery: "
            f"network={forged_network} secrets={forged_secrets}"
        )
        print(
            "[+] fixed provenance oracle: "
            f"origin={fixed_origin} copied={fixed_copy} forged={fixed_forgery}"
        )
        print("[+] no KCS binary, adapter, service, socket, or credential was used")


if __name__ == "__main__":
    main()
