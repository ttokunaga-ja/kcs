"""Bounded canonical-body reader for persona-PC v2 planning artifacts.

The external frame header and schema dispatcher are intentionally not defined
here.  A caller must first obtain a declared body length and expected digest
from a separately authenticated frame/manifest, then call this primitive.  It
validates the declared length before the first body read, reads exactly that
many bytes, verifies the digest, rejects non-canonical JSON, and returns a
detached plain object.

This closes a reusable read-boundary gap but grants no G0, solver, source-plan,
filesystem, write, or history authority.  A bounded frame-header reader and an
exact schema/cap dispatcher remain separate requirements.
"""

from __future__ import annotations

import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


MAX_SUPPORTED_BODY_BYTES = 16 * 2**20


class PersonaV2BoundedBodyError(ValueError):
    """Raised when a declared artifact body is unsafe or non-canonical."""


def _require_label(label):
    if type(label) is not str or not label:
        raise PersonaV2BoundedBodyError("body label must be a non-empty string")
    try:
        encoded = label.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise PersonaV2BoundedBodyError("body label must be valid UTF-8") from None
    if len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        raise PersonaV2BoundedBodyError("body label exceeds shared string cap")


def _require_length(value, *, name, allow_zero, maximum):
    if type(value) is not int:
        raise PersonaV2BoundedBodyError(f"{name} must be an exact integer")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= maximum:
        raise PersonaV2BoundedBodyError(
            f"{name} must be in {minimum}..{maximum}"
        )


def _require_sha256(value):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PersonaV2BoundedBodyError(
            "expected body SHA-256 must be 64 lowercase hexadecimal characters"
        )


def read_declared_body(
    reader,
    *,
    declared_body_bytes,
    max_body_bytes,
    label,
):
    """Read exactly one already-declared body without consuming a next frame.

    The declared length and caller-selected artifact cap are checked before the
    first invocation of ``reader.read``.  Readers that return more bytes than
    requested, non-bytes, or EOF before the declared boundary are rejected.
    """

    _require_label(label)
    _require_length(
        max_body_bytes,
        name="maximum body bytes",
        allow_zero=False,
        maximum=MAX_SUPPORTED_BODY_BYTES,
    )
    _require_length(
        declared_body_bytes,
        name="declared body bytes",
        allow_zero=False,
        maximum=MAX_SUPPORTED_BODY_BYTES,
    )
    if declared_body_bytes > max_body_bytes:
        raise PersonaV2BoundedBodyError(
            f"{label} declared body length exceeds artifact cap"
        )
    read = getattr(reader, "read", None)
    if not callable(read):
        raise PersonaV2BoundedBodyError(f"{label} reader must expose read(size)")

    remaining = declared_body_bytes
    offset = 0
    body = bytearray(declared_body_bytes)
    while remaining:
        try:
            chunk = read(remaining)
        except Exception as error:
            raise PersonaV2BoundedBodyError(f"{label} body read failed") from error
        if type(chunk) is not bytes:
            raise PersonaV2BoundedBodyError(
                f"{label} reader must return exact bytes"
            )
        if len(chunk) > remaining:
            raise PersonaV2BoundedBodyError(
                f"{label} reader returned more than the requested body boundary"
            )
        if not chunk:
            raise PersonaV2BoundedBodyError(
                f"{label} ended before its declared body length"
            )
        body[offset : offset + len(chunk)] = chunk
        offset += len(chunk)
        remaining -= len(chunk)
    return bytes(body)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PersonaV2BoundedBodyError(
                f"canonical body contains duplicate object key {key!r}"
            )
        value[key] = item
    return value


def _reject_float(token):
    raise PersonaV2BoundedBodyError(
        f"canonical body must not contain floating-point token {token!r}"
    )


def _reject_constant(token):
    raise PersonaV2BoundedBodyError(
        f"canonical body must not contain non-JSON constant {token!r}"
    )


def load_declared_canonical_object(
    reader,
    *,
    declared_body_bytes,
    max_body_bytes,
    expected_sha256,
    label,
):
    """Read, digest-check, parse, and canonicality-check one object body."""

    _require_sha256(expected_sha256)
    body = read_declared_body(
        reader,
        declared_body_bytes=declared_body_bytes,
        max_body_bytes=max_body_bytes,
        label=label,
    )
    actual_sha256 = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise PersonaV2BoundedBodyError(f"{label} body SHA-256 mismatch")
    try:
        text = body.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise PersonaV2BoundedBodyError(f"{label} body must be valid UTF-8") from None
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2BoundedBodyError:
        raise
    except (RecursionError, ValueError, json.JSONDecodeError) as error:
        raise PersonaV2BoundedBodyError(f"{label} body is not strict JSON") from error
    if type(value) is not dict:
        raise PersonaV2BoundedBodyError(f"{label} top level must be an object")
    try:
        canonical = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_body_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2BoundedBodyError(str(error)) from error
    if not hmac.compare_digest(body, canonical):
        raise PersonaV2BoundedBodyError(
            f"{label} body is valid JSON but not exact canonical bytes"
        )
    return value
