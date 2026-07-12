#!/usr/bin/env python3
"""Offline probe for KCS Gemini embedding numeric-domain validation.

The vulnerable KCS path accepts JSON numbers, narrows them to f32, checks only
the vector width, and later treats the bytes as cosine vectors. This synthetic
probe models that invariant with a small dimension so it can run without KCS,
sqlite-vec, credentials, or a network call.
"""

from __future__ import annotations

import math
import struct


DIMENSIONS = 4
F32_MAX = 3.4028234663852886e38


def rust_f64_to_f32(value: float) -> float:
    """Model Rust's f64-to-f32 cast for the finite values used in this probe."""

    if math.isnan(value):
        return math.nan
    if value > F32_MAX:
        return math.inf
    if value < -F32_MAX:
        return -math.inf
    return struct.unpack("<f", struct.pack("<f", value))[0]


def parse_like_vulnerable_adapter(response: dict, expected_count: int) -> list[list[float]]:
    embeddings = response.get("embeddings")
    if not isinstance(embeddings, list):
        raise ValueError("embedding response missing embeddings")
    if len(embeddings) != expected_count:
        raise ValueError("embedding response count does not match request")

    out: list[list[float]] = []
    for embedding in embeddings:
        values = embedding.get("values") if isinstance(embedding, dict) else None
        if not isinstance(values, list):
            raise ValueError("embedding missing values")
        vector: list[float] = []
        for raw_value in values:
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise ValueError("embedding values must be numeric")
            vector.append(rust_f64_to_f32(float(raw_value)))
        if len(vector) != DIMENSIONS:
            raise ValueError(
                f"embedding dimension mismatch: expected {DIMENSIONS}, got {len(vector)}"
            )
        out.append(vector)
    return out


def hardened_validate(vector: list[float]) -> None:
    if any(not math.isfinite(component) for component in vector):
        raise ValueError("vector component is not finite after f32 narrowing")
    norm_sq = sum(component * component for component in vector)
    if not math.isfinite(norm_sq) or norm_sq <= 0.0:
        raise ValueError("vector norm must be positive and finite")


def cosine_distance_or_null(lhs: list[float], rhs: list[float]) -> float | None:
    if any(not math.isfinite(component) for component in lhs + rhs):
        return None
    lhs_norm = math.sqrt(sum(component * component for component in lhs))
    rhs_norm = math.sqrt(sum(component * component for component in rhs))
    if lhs_norm == 0.0 or rhs_norm == 0.0:
        return None
    similarity = sum(a * b for a, b in zip(lhs, rhs)) / (lhs_norm * rhs_norm)
    if not math.isfinite(similarity):
        return None
    return 1.0 - similarity


def show_case(name: str, response: dict, stored_basis: list[float]) -> None:
    vector = parse_like_vulnerable_adapter(response, expected_count=1)[0]
    distance = cosine_distance_or_null(vector, stored_basis)
    print(f"[{name}] vulnerable parser accepted: yes")
    print(f"[{name}] first f32 component: {vector[0]!r}")
    print(f"[{name}] all components finite after cast: {all(math.isfinite(x) for x in vector)}")
    print(f"[{name}] squared norm: {sum(x * x for x in vector)!r}")
    print(f"[{name}] cosine distance result: {distance if distance is not None else 'NULL'}")
    try:
        hardened_validate(vector)
    except ValueError as exc:
        print(f"[{name}] hardened validator: rejected ({exc})")
    else:
        print(f"[{name}] hardened validator: accepted")


def main() -> None:
    basis = [1.0, 0.0, 0.0, 0.0]
    overflow_source = 3.5e38
    print(f"[overflow] source f64 finite: {math.isfinite(overflow_source)}")
    show_case(
        "overflow",
        {"embeddings": [{"values": [overflow_source, 0.0, 0.0, 0.0]}]},
        basis,
    )
    show_case("zero", {"embeddings": [{"values": [0.0, 0.0, 0.0, 0.0]}]}, basis)
    show_case("control", {"embeddings": [{"values": basis}]}, basis)


if __name__ == "__main__":
    main()
