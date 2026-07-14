"""Strict helpers shared by post-policy persona-PC v2 artifacts.

The original envelope/topology/problem/policy artifacts intentionally keep
their own validators and hashes frozen.  New input-closure sidecars use this
module so that their plain-value, Unicode, integer, depth, and in-memory byte
rules cannot drift.  This is not an external artifact loader: a framed reader
that checks the declared body length before reading remains a separate G0
requirement.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata


MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096
MAX_INTEGER_BITS = 127
MAX_INTEGER_MAGNITUDE = 2**MAX_INTEGER_BITS - 1


class PersonaV2ArtifactError(ValueError):
    """Raised when a post-policy v2 artifact is not strict canonical JSON."""


def validate_plain_value(
    value,
    *,
    label,
    depth=0,
    max_depth=MAX_CANONICAL_DEPTH,
    max_string_bytes=MAX_CANONICAL_STRING_BYTES,
    max_integer=MAX_INTEGER_MAGNITUDE,
):
    """Validate JSON-like values without accepting Python equality aliases.

    Null, floats, tuples, mapping/list subclasses, negative integers, invalid
    UTF-8, and non-NFC strings are deliberately unavailable to these planning
    artifacts.  Exact built-in ``bool`` remains distinct from ``int``.
    """

    if type(label) is not str or not label:
        raise PersonaV2ArtifactError("artifact label must be a non-empty string")
    if type(max_depth) is not int or max_depth < 0:
        raise PersonaV2ArtifactError("canonical depth cap must be a non-negative integer")
    if max_depth > MAX_CANONICAL_DEPTH:
        raise PersonaV2ArtifactError("canonical depth cap cannot exceed the shared limit")
    if type(max_string_bytes) is not int or max_string_bytes <= 0:
        raise PersonaV2ArtifactError("canonical string cap must be a positive integer")
    if max_string_bytes > MAX_CANONICAL_STRING_BYTES:
        raise PersonaV2ArtifactError("canonical string cap cannot exceed the shared limit")
    if type(max_integer) is not int or max_integer < 0:
        raise PersonaV2ArtifactError("canonical integer cap must be a non-negative integer")
    if max_integer > MAX_INTEGER_MAGNITUDE:
        raise PersonaV2ArtifactError("canonical integer cap cannot exceed the shared limit")
    if type(depth) is not int or depth < 0:
        raise PersonaV2ArtifactError(f"{label} depth must be a non-negative integer")
    if depth > max_depth:
        raise PersonaV2ArtifactError(f"{label} exceeds canonical nesting depth")
    if type(value) is bool:
        return
    if type(value) is int:
        if value < 0 or value > max_integer:
            raise PersonaV2ArtifactError(
                f"{label} integer exceeds checked non-negative range"
            )
        return
    if type(value) is str:
        try:
            encoded = value.encode("utf-8", "strict")
        except UnicodeEncodeError:
            raise PersonaV2ArtifactError(
                f"{label} strings must be valid UTF-8"
            ) from None
        if len(encoded) > max_string_bytes:
            raise PersonaV2ArtifactError(f"{label} string exceeds byte bound")
        if unicodedata.normalize("NFC", value) != value:
            raise PersonaV2ArtifactError(f"{label} strings must be NFC")
        return
    if type(value) is list:
        for item in value:
            validate_plain_value(
                item,
                label=label,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_integer=max_integer,
            )
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PersonaV2ArtifactError(f"{label} object keys must be strings")
            validate_plain_value(
                key,
                label=label,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_integer=max_integer,
            )
            validate_plain_value(
                item,
                label=label,
                depth=depth + 1,
                max_depth=max_depth,
                max_string_bytes=max_string_bytes,
                max_integer=max_integer,
            )
        return
    raise PersonaV2ArtifactError(
        f"unsupported {label} value type: {type(value).__name__}"
    )


def canonical_json_bytes(value, *, label, max_bytes):
    """Return sorted compact UTF-8 JSON after strict in-memory validation."""

    if type(max_bytes) is not int or max_bytes <= 0:
        raise PersonaV2ArtifactError("artifact byte cap must be a positive integer")
    validate_plain_value(value, label=label)
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", "strict")
    if len(raw) > max_bytes:
        raise PersonaV2ArtifactError(f"{label} exceeds canonical byte cap")
    return raw


def validate_exact_regeneration(value, *, builder, label, max_bytes):
    """Reject any value that is not byte-identical to a fresh deterministic build."""

    if type(value) is not dict:
        raise PersonaV2ArtifactError(f"{label} must be an object")
    if not callable(builder):
        raise PersonaV2ArtifactError("artifact builder must be callable")
    actual = canonical_json_bytes(value, label=label, max_bytes=max_bytes)
    expected_value = builder()
    if type(expected_value) is not dict:
        raise PersonaV2ArtifactError("artifact builder must return an object")
    expected = canonical_json_bytes(
        expected_value,
        label=label,
        max_bytes=max_bytes,
    )
    if actual != expected:
        raise PersonaV2ArtifactError(
            f"{label} differs from canonical deterministic regeneration"
        )
    return True


def canonical_sha256(value, *, builder, label, max_bytes):
    """Validate an exact artifact and hash only its canonical body bytes."""

    if value is None:
        value = builder()
    validate_exact_regeneration(
        value,
        builder=builder,
        label=label,
        max_bytes=max_bytes,
    )
    return hashlib.sha256(
        canonical_json_bytes(value, label=label, max_bytes=max_bytes)
    ).hexdigest()
