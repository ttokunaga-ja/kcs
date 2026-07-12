#!/usr/bin/env python3
"""Bounded, in-memory regression model for Gemini response handling.

This harness does not open sockets or read credentials.  It exercises the
ordering a repaired client should preserve: finish a byte-capped read within a
deadline, then decode JSON, then apply response-shape checks.
"""

import io
import json
import queue
import threading
import time


MAX_RESPONSE_BYTES = 160
READ_DEADLINE_SECONDS = 0.020


class ResponseTooLarge(Exception):
    pass


class ResponseDeadlineExceeded(Exception):
    pass


class SemanticViolation(Exception):
    pass


class DelayedReader:
    """An in-memory reader whose first read completes after a bounded delay."""

    def __init__(self, body, first_read_delay):
        self._inner = io.BytesIO(body)
        self._first_read_delay = first_read_delay
        self._delayed = False

    def read(self, size=-1):
        if not self._delayed:
            self._delayed = True
            time.sleep(self._first_read_delay)
        return self._inner.read(size)


def read_capped(reader, max_bytes):
    """Read at most max_bytes + 1 so overflow is detected before JSON decode."""

    body = bytearray()
    while True:
        remaining_probe = max_bytes + 1 - len(body)
        chunk = reader.read(min(64, remaining_probe))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLarge(
                "decoded response exceeds {} bytes".format(max_bytes)
            )


def read_capped_with_deadline(reader, max_bytes, timeout_seconds):
    """Bound total read time without allowing timed-out work to reach parsing."""

    outcomes = queue.Queue(maxsize=1)

    def worker():
        try:
            outcomes.put((True, read_capped(reader, max_bytes)))
        except Exception as error:  # Preserve the exact test failure.
            outcomes.put((False, error))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise ResponseDeadlineExceeded(
            "response read exceeded {:.0f} ms".format(timeout_seconds * 1000)
        )

    succeeded, value = outcomes.get_nowait()
    if not succeeded:
        raise value
    return value


def validate_one_two_dimensional_embedding(document):
    if not isinstance(document, dict):
        raise SemanticViolation("response must be an object")
    embeddings = document.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != 1:
        raise SemanticViolation("expected exactly one embedding")
    embedding = embeddings[0]
    if not isinstance(embedding, dict):
        raise SemanticViolation("embedding must be an object")
    values = embedding.get("values")
    if not isinstance(values, list) or len(values) != 2:
        raise SemanticViolation("expected exactly two values")
    if not all(type(value) in (int, float) for value in values):
        raise SemanticViolation("embedding values must be numeric")
    return values


def bounded_decode(reader, semantic_check, timeout_seconds=READ_DEADLINE_SECONDS):
    body = read_capped_with_deadline(reader, MAX_RESPONSE_BYTES, timeout_seconds)
    document = json.loads(body)
    return semantic_check(document)


def expect(exception_type, operation):
    try:
        operation()
    except exception_type:
        return
    except Exception as error:
        raise AssertionError(
            "expected {}, got {}".format(exception_type.__name__, type(error).__name__)
        ) from error
    raise AssertionError("expected {}".format(exception_type.__name__))


def main():
    valid = b'{"embeddings":[{"values":[0.1,0.2]}]}'

    semantic_calls = []

    def marked_semantic_check(document):
        semantic_calls.append(True)
        return validate_one_two_dimensional_embedding(document)

    exact_limit = valid + b" " * (MAX_RESPONSE_BYTES - len(valid))
    assert len(exact_limit) == MAX_RESPONSE_BYTES
    assert bounded_decode(
        io.BytesIO(exact_limit), marked_semantic_check
    ) == [0.1, 0.2]
    assert semantic_calls == [True]
    print("[PASS] exact-limit response accepted, then passed semantic validation")

    semantic_calls.clear()
    oversized = json.dumps(
        {
            "embeddings": [{"values": [0.1, 0.2]}],
            "irrelevant_padding": "x" * MAX_RESPONSE_BYTES,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(oversized) > MAX_RESPONSE_BYTES
    expect(
        ResponseTooLarge,
        lambda: bounded_decode(io.BytesIO(oversized), marked_semantic_check),
    )
    assert semantic_calls == []
    print("[PASS] oversized response rejected before semantic validation")

    semantic_calls.clear()
    expect(
        ResponseDeadlineExceeded,
        lambda: bounded_decode(
            DelayedReader(valid, first_read_delay=0.100),
            marked_semantic_check,
        ),
    )
    assert semantic_calls == []
    print("[PASS] delayed response rejected by 20 ms deadline before semantic validation")

    semantic_calls.clear()
    wrong_width = b'{"embeddings":[{"values":[0.1,0.2,0.3]}]}'
    expect(
        SemanticViolation,
        lambda: bounded_decode(io.BytesIO(wrong_width), marked_semantic_check),
    )
    assert semantic_calls == [True]
    print("[PASS] wrong-width vector rejected after transport bounds")

    print("[PASS] 4 bounded in-memory regressions; no network or credentials used")


if __name__ == "__main__":
    main()
