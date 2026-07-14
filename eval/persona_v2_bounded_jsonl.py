"""Fail-closed bounded canonical-JSONL reader for persona-PC v2 shards.

The caller supplies a separately authenticated declared body length and shard
descriptor.  This primitive validates all configurable bounds before the
first body read, consumes exactly the declared bytes, parses records with a
bounded pending-line buffer, and verifies the descriptor over the exact body.

Successful loading proves only byte-boundary, canonical-encoding, row-order,
and descriptor integrity.  It grants no G0, solver, source-plan, rendering,
filesystem-write, history, evaluation, or publication authority.
"""

from __future__ import annotations

import codecs
import hashlib
import hmac
import json
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


HARD_MAX_BODY_BYTES = 16 * 2**20
HARD_MAX_ROW_BYTES_INCLUDING_LF = 64 * 2**10
HARD_MAX_ROWS = 65_536
READ_CHUNK_BYTES = 64 * 2**10

DESCRIPTOR_FIELDS = frozenset(
    {
        "body_sha256",
        "first_key",
        "last_key",
        "row_count",
    }
)


class PersonaV2BoundedJsonlError(ValueError):
    """Raised when a declared JSONL shard is unsafe or non-canonical."""


def _require_integer(value, *, name, minimum, maximum):
    if type(value) is not int:
        raise PersonaV2BoundedJsonlError(f"{name} must be an exact integer")
    if not minimum <= value <= maximum:
        raise PersonaV2BoundedJsonlError(
            f"{name} must be in {minimum}..{maximum}"
        )


def _require_string(value, *, name):
    if type(value) is not str or not value:
        raise PersonaV2BoundedJsonlError(f"{name} must be a non-empty string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise PersonaV2BoundedJsonlError(f"{name} must be valid UTF-8") from None
    if len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        raise PersonaV2BoundedJsonlError(f"{name} exceeds the shared string cap")
    if unicodedata.normalize("NFC", value) != value:
        raise PersonaV2BoundedJsonlError(f"{name} must be NFC")
    return encoded


def _require_sha256(value):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PersonaV2BoundedJsonlError(
            "descriptor body_sha256 must be 64 lowercase hexadecimal characters"
        )


def _validate_descriptor(descriptor, *, max_rows):
    if type(descriptor) is not dict or set(descriptor) != DESCRIPTOR_FIELDS:
        raise PersonaV2BoundedJsonlError(
            "shard descriptor fields differ from the exact schema"
        )
    _require_integer(
        descriptor["row_count"],
        name="descriptor row_count",
        minimum=1,
        maximum=max_rows,
    )
    first = _require_string(descriptor["first_key"], name="descriptor first_key")
    last = _require_string(descriptor["last_key"], name="descriptor last_key")
    _require_sha256(descriptor["body_sha256"])
    if descriptor["row_count"] == 1:
        if first != last:
            raise PersonaV2BoundedJsonlError(
                "single-row descriptor first_key and last_key must match"
            )
    elif first >= last:
        raise PersonaV2BoundedJsonlError(
            "multi-row descriptor keys must be in strict UTF-8 byte order"
        )


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PersonaV2BoundedJsonlError(
                f"canonical JSONL row contains duplicate object key {key!r}"
            )
        value[key] = item
    return value


def _reject_float(token):
    raise PersonaV2BoundedJsonlError(
        f"canonical JSONL rows must not contain floating-point token {token!r}"
    )


def _reject_constant(token):
    raise PersonaV2BoundedJsonlError(
        f"canonical JSONL rows must not contain non-JSON constant {token!r}"
    )


def _parse_row(raw, *, row_number, key_field, max_row_bytes_including_lf):
    label = f"canonical JSONL row {row_number}"
    if not raw:
        raise PersonaV2BoundedJsonlError(f"{label} must not be blank")
    if raw.startswith(codecs.BOM_UTF8):
        raise PersonaV2BoundedJsonlError(f"{label} must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise PersonaV2BoundedJsonlError(f"{label} must be valid UTF-8") from None
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2BoundedJsonlError:
        raise
    except (RecursionError, ValueError, json.JSONDecodeError) as error:
        raise PersonaV2BoundedJsonlError(f"{label} is not strict JSON") from error
    if type(value) is not dict:
        raise PersonaV2BoundedJsonlError(f"{label} top level must be an object")
    try:
        canonical = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_row_bytes_including_lf - 1,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2BoundedJsonlError(str(error)) from error
    if not hmac.compare_digest(raw, canonical):
        raise PersonaV2BoundedJsonlError(
            f"{label} is valid JSON but not exact compact sorted canonical bytes"
        )
    if key_field not in value:
        raise PersonaV2BoundedJsonlError(
            f"{label} is missing sort-key field {key_field!r}"
        )
    key_bytes = _require_string(
        value[key_field],
        name=f"{label} sort key",
    )
    return value, key_bytes


def load_declared_canonical_jsonl(
    reader,
    *,
    declared_body_bytes,
    descriptor,
    key_field,
    max_body_bytes,
    max_row_bytes_including_lf,
    max_rows,
):
    """Load one declared JSONL shard without reading into a following frame.

    Row order is the strict lexicographic order of each key's UTF-8 bytes.
    Every successful row includes its LF in the configured per-row byte cap.
    The returned tuple is detached parsed data, not an authority receipt.
    """

    # Validate the entire caller-controlled envelope before the first read.
    _require_integer(
        max_body_bytes,
        name="maximum body bytes",
        minimum=1,
        maximum=HARD_MAX_BODY_BYTES,
    )
    _require_integer(
        max_row_bytes_including_lf,
        name="maximum row bytes including LF",
        minimum=3,
        maximum=HARD_MAX_ROW_BYTES_INCLUDING_LF,
    )
    _require_integer(
        max_rows,
        name="maximum row count",
        minimum=1,
        maximum=HARD_MAX_ROWS,
    )
    _require_integer(
        declared_body_bytes,
        name="declared body bytes",
        minimum=1,
        maximum=HARD_MAX_BODY_BYTES,
    )
    if declared_body_bytes > max_body_bytes:
        raise PersonaV2BoundedJsonlError(
            "declared body length exceeds the selected shard cap"
        )
    _require_string(key_field, name="sort-key field")
    _validate_descriptor(descriptor, max_rows=max_rows)
    read = getattr(reader, "read", None)
    if not callable(read):
        raise PersonaV2BoundedJsonlError("JSONL reader must expose read(size)")

    digest = hashlib.sha256()
    pending = bytearray()
    rows = []
    first_key_bytes = None
    previous_key_bytes = None
    last_key_bytes = None
    remaining = declared_body_bytes

    while remaining:
        requested = min(remaining, READ_CHUNK_BYTES, max_row_bytes_including_lf)
        try:
            chunk = read(requested)
        except Exception as error:
            raise PersonaV2BoundedJsonlError("JSONL body read failed") from error
        if type(chunk) is not bytes:
            raise PersonaV2BoundedJsonlError(
                "JSONL reader must return exact bytes"
            )
        if len(chunk) > requested or len(chunk) > remaining:
            raise PersonaV2BoundedJsonlError(
                "JSONL reader returned more than the requested body boundary"
            )
        if not chunk:
            raise PersonaV2BoundedJsonlError(
                "JSONL body ended before its declared body length"
            )
        if b"\r" in chunk:
            raise PersonaV2BoundedJsonlError(
                "canonical JSONL must not contain CR or CRLF bytes"
            )
        digest.update(chunk)
        remaining -= len(chunk)

        start = 0
        while True:
            newline = chunk.find(b"\n", start)
            if newline < 0:
                fragment = chunk[start:]
                if len(pending) + len(fragment) >= max_row_bytes_including_lf:
                    raise PersonaV2BoundedJsonlError(
                        "canonical JSONL row exceeds its LF-inclusive byte cap"
                    )
                pending.extend(fragment)
                break

            fragment = chunk[start:newline]
            if len(pending) + len(fragment) + 1 > max_row_bytes_including_lf:
                raise PersonaV2BoundedJsonlError(
                    "canonical JSONL row exceeds its LF-inclusive byte cap"
                )
            pending.extend(fragment)
            if len(rows) >= descriptor["row_count"] or len(rows) >= max_rows:
                raise PersonaV2BoundedJsonlError(
                    "canonical JSONL contains more rows than its declared bound"
                )
            row_number = len(rows) + 1
            value, key_bytes = _parse_row(
                bytes(pending),
                row_number=row_number,
                key_field=key_field,
                max_row_bytes_including_lf=max_row_bytes_including_lf,
            )
            pending.clear()
            if previous_key_bytes is not None and key_bytes <= previous_key_bytes:
                raise PersonaV2BoundedJsonlError(
                    "canonical JSONL sort keys must be unique and strictly increasing"
                )
            if first_key_bytes is None:
                first_key_bytes = key_bytes
            previous_key_bytes = key_bytes
            last_key_bytes = key_bytes
            rows.append(value)
            start = newline + 1

    if pending:
        raise PersonaV2BoundedJsonlError(
            "canonical JSONL final row must terminate with LF"
        )
    if len(rows) != descriptor["row_count"]:
        raise PersonaV2BoundedJsonlError("descriptor row_count mismatch")
    expected_first = descriptor["first_key"].encode("utf-8", "strict")
    expected_last = descriptor["last_key"].encode("utf-8", "strict")
    if first_key_bytes != expected_first:
        raise PersonaV2BoundedJsonlError("descriptor first_key mismatch")
    if last_key_bytes != expected_last:
        raise PersonaV2BoundedJsonlError("descriptor last_key mismatch")
    if not hmac.compare_digest(
        digest.hexdigest(), descriptor["body_sha256"]
    ):
        raise PersonaV2BoundedJsonlError("descriptor body_sha256 mismatch")
    return tuple(rows)
