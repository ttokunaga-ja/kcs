#!/usr/bin/env python3
"""Atomic, descriptor-bound persona ownership leases for corpus production."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

if __package__ in (None, ""):
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[1]))

from eval import persona_fixture_spec as spec
from eval.scaffold_persona_skill_corpus import (
    ScaffoldError,
    _FILE_NOFOLLOW,
    _absolute_lexical,
    _open_directory_at,
    _open_existing_root,
    _read_text_at,
    _validate_regular_file,
    _write_new_json_at,
    scope_control_id,
)


LEASE_FILE = "lease.json"
LOCK_FILE = ".lease.lock"
RECOVERY_LOG = "lease-recovery.jsonl"
_SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _persona_slug(persona_id: str) -> str:
    for persona in spec.PERSONAS:
        slug = f"{persona['id']}-{persona['role']}"
        if persona_id in (persona["id"], slug):
            return slug
    raise ScaffoldError(f"unknown persona: {persona_id}")


def _validate_session(session: str) -> None:
    if not _SESSION.fullmatch(session):
        raise ScaffoldError(
            "session must be 1-128 ASCII letters, digits, dot, underscore, colon, or hyphen"
        )


def _open_control(root: Path, persona_id: str) -> tuple[int, int, int, str]:
    root = _absolute_lexical(root)
    slug = _persona_slug(persona_id)
    root_descriptor = _open_existing_root(root)
    try:
        persona = _open_directory_at(root_descriptor, slug, slug)
        try:
            control = _open_directory_at(persona, "_production", f"{slug}/_production")
        except BaseException:
            os.close(persona)
            raise
    except BaseException:
        os.close(root_descriptor)
        raise
    return root_descriptor, persona, control, slug


def _scope_path(slug: str, scope_path: str) -> str:
    persona = next(row for row in spec.PERSONAS if f"{row['id']}-{row['role']}" == slug)
    if scope_path not in spec.all_scope_paths(persona):
        raise ScaffoldError(f"scope is not authoritative for {slug}: {scope_path}")
    return scope_path


def _open_scope_control(root: Path, persona_id: str, scope_path: str) -> tuple[int, int, int, int, str, str]:
    root_descriptor, persona, control, slug = _open_control(root, persona_id)
    try:
        scope_path = _scope_path(slug, scope_path)
        scopes = _open_directory_at(control, "scopes", f"{slug}/_production/scopes")
        try:
            scope_id = scope_control_id(scope_path)
            scope_control = _open_directory_at(scopes, scope_id, f"{slug}/_production/scopes/{scope_id}")
        except BaseException:
            os.close(scopes)
            raise
        os.close(scopes)
    except BaseException:
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)
        raise
    return root_descriptor, persona, control, scope_control, slug, scope_path


@contextlib.contextmanager
def _lease_guard(control: int, slug: str):
    try:
        descriptor = os.open(
            LOCK_FILE, os.O_RDWR | _FILE_NOFOLLOW, dir_fd=control
        )
    except OSError as error:
        raise ScaffoldError(f"cannot open lease guard for {slug}: {error}") from error
    try:
        _validate_regular_file(os.fstat(descriptor), f"{slug}/_production/{LOCK_FILE}")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_lease(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "release_token_sha256"}


def _read_lease_locked(control: int, slug: str) -> dict[str, object]:
    try:
        payload = json.loads(
            _read_text_at(control, LEASE_FILE, f"{slug}/_production/{LEASE_FILE}")
        )
    except ValueError as error:
        raise ScaffoldError(f"invalid persona lease: {slug}") from error
    if (
        payload.get("schema_version") != 1
        or payload.get("persona") != slug
        or not isinstance(payload.get("session"), str)
        or not isinstance(payload.get("release_token_sha256"), str)
    ):
        raise ScaffoldError(f"invalid persona lease: {slug}")
    return payload


def _require_parent_lease_locked(control: int, slug: str, parent_session: str) -> None:
    _validate_session(parent_session)
    lease = _read_lease_locked(control, slug)
    if lease["session"] != parent_session:
        raise ScaffoldError(f"active parent persona lease does not match for {slug}")


def _active_scope_leases_locked(control: int, slug: str) -> list[str]:
    """Return authoritative scopes still assigned under a parent lease guard."""
    persona = next(row for row in spec.PERSONAS if f"{row['id']}-{row['role']}" == slug)
    scopes = _open_directory_at(control, "scopes", f"{slug}/_production/scopes")
    try:
        active: list[str] = []
        for scope_path in spec.all_scope_paths(persona):
            scope_id = scope_control_id(scope_path)
            scope_control = _open_directory_at(scopes, scope_id, f"{slug}/_production/scopes/{scope_id}")
            try:
                if os.stat(LEASE_FILE, dir_fd=scope_control, follow_symlinks=False):
                    _read_scope_lease_locked(scope_control, slug, scope_path)
                    active.append(scope_path)
            except FileNotFoundError:
                pass
            finally:
                os.close(scope_control)
        return active
    finally:
        os.close(scopes)


def _read_scope_lease_locked(scope_control: int, slug: str, scope_path: str) -> dict[str, object]:
    scope_id = scope_control_id(scope_path)
    label = f"{slug}/_production/scopes/{scope_id}/{LEASE_FILE}"
    try:
        payload = json.loads(_read_text_at(scope_control, LEASE_FILE, label))
    except ValueError as error:
        raise ScaffoldError(f"invalid scope lease: {slug}/{scope_path}") from error
    if (
        payload.get("schema_version") != 1
        or payload.get("persona") != slug
        or payload.get("scope_path") != scope_path
        or payload.get("scope_id") != scope_id
        or not isinstance(payload.get("parent_session"), str)
        or not isinstance(payload.get("worker_session"), str)
        or not isinstance(payload.get("release_token_sha256"), str)
    ):
        raise ScaffoldError(f"invalid scope lease: {slug}/{scope_path}")
    return payload


def _append_recovery_locked(control: int, slug: str, payload: object) -> None:
    label = f"{slug}/_production/{RECOVERY_LOG}"
    try:
        descriptor = os.open(
            RECOVERY_LOG, os.O_WRONLY | os.O_APPEND | _FILE_NOFOLLOW, dir_fd=control
        )
    except OSError as error:
        raise ScaffoldError(f"cannot open recovery log {label}: {error}") from error
    try:
        _validate_regular_file(os.fstat(descriptor), label)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        os.write(descriptor, line.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_scope_recovery_locked(scope_control: int, slug: str, scope_path: str, payload: object) -> None:
    scope_id = scope_control_id(scope_path)
    _append_recovery_locked(scope_control, f"{slug}/scopes/{scope_id}", payload)


def claim(root: Path, persona_id: str, session: str, owner: str | None) -> dict[str, object]:
    _validate_session(session)
    root_descriptor, persona, control, slug = _open_control(root, persona_id)
    try:
        with _lease_guard(control, slug):
            release_token = secrets.token_urlsafe(32)
            payload = {
                "schema_version": 1,
                "persona": slug,
                "session": session,
                "owner_label": owner,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "release_token_sha256": _token_hash(release_token),
            }
            _write_new_json_at(
                control, LEASE_FILE, payload, f"{slug}/_production/{LEASE_FILE}"
            )
            public = _public_lease(payload)
            public["release_token"] = release_token
            return public
    finally:
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def read_lease(root: Path, persona_id: str) -> dict[str, object]:
    root_descriptor, persona, control, slug = _open_control(root, persona_id)
    try:
        with _lease_guard(control, slug):
            return _public_lease(_read_lease_locked(control, slug))
    finally:
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def release(root: Path, persona_id: str, token: str) -> dict[str, object]:
    if not token:
        raise ScaffoldError("release token must not be empty")
    root_descriptor, persona, control, slug = _open_control(root, persona_id)
    try:
        with _lease_guard(control, slug):
            payload = _read_lease_locked(control, slug)
            if not hmac.compare_digest(
                payload["release_token_sha256"], _token_hash(token)
            ):
                raise ScaffoldError(f"release token mismatch for {slug}")
            active_scopes = _active_scope_leases_locked(control, slug)
            if active_scopes:
                raise ScaffoldError(f"cannot release parent persona lease with active scopes: {active_scopes}")
            os.unlink(LEASE_FILE, dir_fd=control)
            os.fsync(control)
            return _public_lease(payload)
    finally:
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def recover(
    root: Path, persona_id: str, expected_session: str, reason: str
) -> dict[str, object]:
    _validate_session(expected_session)
    if not reason.strip():
        raise ScaffoldError("recovery reason must not be empty")
    root_descriptor, persona, control, slug = _open_control(root, persona_id)
    try:
        with _lease_guard(control, slug):
            payload = _read_lease_locked(control, slug)
            if payload.get("session") != expected_session:
                raise ScaffoldError(f"lease session changed for {slug}; recovery refused")
            active_scopes = _active_scope_leases_locked(control, slug)
            if active_scopes:
                raise ScaffoldError(f"cannot recover parent persona lease with active scopes: {active_scopes}")
            receipt = {
                "schema_version": 1,
                "action": "forced-recovery",
                "recovered_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason.strip(),
                "lease": _public_lease(payload),
            }
            _append_recovery_locked(control, slug, receipt)
            os.unlink(LEASE_FILE, dir_fd=control)
            os.fsync(control)
            return receipt
    finally:
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def scope_claim(
    root: Path,
    persona_id: str,
    scope_path: str,
    parent_session: str,
    worker_session: str,
    owner: str | None,
) -> dict[str, object]:
    _validate_session(worker_session)
    root_descriptor, persona, control, scope_control, slug, scope_path = _open_scope_control(root, persona_id, scope_path)
    try:
        with _lease_guard(control, slug):
            _require_parent_lease_locked(control, slug, parent_session)
            with _lease_guard(scope_control, f"{slug}/{scope_path}"):
                token = secrets.token_urlsafe(32)
                payload = {
                    "schema_version": 1,
                    "persona": slug,
                    "scope_path": scope_path,
                    "scope_id": scope_control_id(scope_path),
                    "parent_session": parent_session,
                    "worker_session": worker_session,
                    "owner_label": owner,
                    "claimed_at": datetime.now(timezone.utc).isoformat(),
                    "release_token_sha256": _token_hash(token),
                }
                _write_new_json_at(scope_control, LEASE_FILE, payload, f"{slug}/{scope_path}/{LEASE_FILE}")
                public = _public_lease(payload)
                public["release_token"] = token
                return public
    finally:
        os.close(scope_control)
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def read_scope_lease(root: Path, persona_id: str, scope_path: str) -> dict[str, object]:
    root_descriptor, persona, control, scope_control, slug, scope_path = _open_scope_control(root, persona_id, scope_path)
    try:
        with _lease_guard(scope_control, f"{slug}/{scope_path}"):
            return _public_lease(_read_scope_lease_locked(scope_control, slug, scope_path))
    finally:
        os.close(scope_control)
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def scope_release(root: Path, persona_id: str, scope_path: str, parent_session: str, token: str) -> dict[str, object]:
    if not token:
        raise ScaffoldError("release token must not be empty")
    root_descriptor, persona, control, scope_control, slug, scope_path = _open_scope_control(root, persona_id, scope_path)
    try:
        with _lease_guard(control, slug):
            _require_parent_lease_locked(control, slug, parent_session)
            with _lease_guard(scope_control, f"{slug}/{scope_path}"):
                payload = _read_scope_lease_locked(scope_control, slug, scope_path)
                if payload["parent_session"] != parent_session or not hmac.compare_digest(payload["release_token_sha256"], _token_hash(token)):
                    raise ScaffoldError(f"release token or parent session mismatch for {slug}/{scope_path}")
                os.unlink(LEASE_FILE, dir_fd=scope_control)
                os.fsync(scope_control)
                return _public_lease(payload)
    finally:
        os.close(scope_control)
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def scope_recover(root: Path, persona_id: str, scope_path: str, parent_session: str, expected_worker_session: str, reason: str) -> dict[str, object]:
    _validate_session(expected_worker_session)
    if not reason.strip():
        raise ScaffoldError("recovery reason must not be empty")
    root_descriptor, persona, control, scope_control, slug, scope_path = _open_scope_control(root, persona_id, scope_path)
    try:
        with _lease_guard(control, slug):
            _require_parent_lease_locked(control, slug, parent_session)
            with _lease_guard(scope_control, f"{slug}/{scope_path}"):
                payload = _read_scope_lease_locked(scope_control, slug, scope_path)
                if payload["parent_session"] != parent_session or payload["worker_session"] != expected_worker_session:
                    raise ScaffoldError(f"scope lease changed for {slug}/{scope_path}; recovery refused")
                receipt = {"schema_version": 1, "action": "forced-recovery", "recovered_at": datetime.now(timezone.utc).isoformat(), "reason": reason.strip(), "lease": _public_lease(payload)}
                _append_scope_recovery_locked(scope_control, slug, scope_path, receipt)
                os.unlink(LEASE_FILE, dir_fd=scope_control)
                os.fsync(scope_control)
                return receipt
    finally:
        os.close(scope_control)
        os.close(control)
        os.close(persona)
        os.close(root_descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage parent persona leases and child scope-worker leases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("claim", "show", "release", "recover", "scope-claim", "scope-show", "scope-release", "scope-recover"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", type=Path, required=True)
        subparser.add_argument("--persona", required=True, help="p01 or full persona slug")
        if command in ("scope-claim", "scope-show", "scope-release", "scope-recover"):
            subparser.add_argument("--scope", required=True, help="exact authoritative relative scope path")
        if command == "claim":
            subparser.add_argument("--session", required=True)
            subparser.add_argument("--owner", help="non-secret human/session label")
        elif command == "release":
            subparser.add_argument("--token", required=True)
        elif command == "recover":
            subparser.add_argument("--expected-session", required=True)
            subparser.add_argument("--reason", required=True)
        elif command == "scope-claim":
            subparser.add_argument("--parent-session", required=True)
            subparser.add_argument("--worker-session", required=True)
            subparser.add_argument("--owner", help="non-secret worker label")
        elif command == "scope-release":
            subparser.add_argument("--parent-session", required=True)
            subparser.add_argument("--token", required=True)
        elif command == "scope-recover":
            subparser.add_argument("--parent-session", required=True)
            subparser.add_argument("--expected-worker-session", required=True)
            subparser.add_argument("--reason", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "claim":
            payload = claim(args.root, args.persona, args.session, args.owner)
        elif args.command == "show":
            payload = read_lease(args.root, args.persona)
        elif args.command == "release":
            payload = release(args.root, args.persona, args.token)
        elif args.command == "scope-claim":
            payload = scope_claim(args.root, args.persona, args.scope, args.parent_session, args.worker_session, args.owner)
        elif args.command == "scope-show":
            payload = read_scope_lease(args.root, args.persona, args.scope)
        elif args.command == "scope-release":
            payload = scope_release(args.root, args.persona, args.scope, args.parent_session, args.token)
        elif args.command == "scope-recover":
            payload = scope_recover(args.root, args.persona, args.scope, args.parent_session, args.expected_worker_session, args.reason)
        else:
            payload = recover(
                args.root, args.persona, args.expected_session, args.reason
            )
    except (OSError, ScaffoldError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
