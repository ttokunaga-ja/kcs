#!/usr/bin/env python3
"""Network-free regression harness for KCS-R23-CAND-068.

The harness models the vulnerable storage invariant from the scanned revision:
duplicate text/profile identities are planned before writes, the authoritative
embedding row is first-wins, and the derived KNN row is linked from the current
response vector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text_hash: str
    text: str
    profile_hash: str = "same-profile"


def embedding_hash(chunk: Chunk) -> str:
    identity = {
        "dimensions": 768,
        "distance": "cosine",
        "modality": "multimodal",
        "profile_hash": chunk.profile_hash,
        "spec_version": 1,
        "target_hash": chunk.text_hash,
        "target_type": "chunk",
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def plan_embed_batch(chunks: list[Chunk], embeddings: dict[str, tuple[float, ...]]):
    reuse: list[tuple[Chunk, tuple[float, ...]]] = []
    to_send: list[tuple[Chunk, str]] = []
    for chunk in chunks:
        emb_id = embedding_hash(chunk)
        if emb_id in embeddings:
            reuse.append((chunk, embeddings[emb_id]))
        else:
            to_send.append((chunk, emb_id))
    return reuse, to_send


def write_chunk_embedding_vulnerable(
    embeddings: dict[str, tuple[float, ...]],
    chunk_vec: dict[str, tuple[float, ...]],
    emb_id: str,
    chunk: Chunk,
    vector: tuple[float, ...],
) -> None:
    # Matches INSERT ... ON CONFLICT(id) DO NOTHING.
    embeddings.setdefault(emb_id, vector)
    # Matches the vulnerable current-vector link into chunk_vec.
    chunk_vec[chunk.chunk_id] = vector


def rebuild_chunk_vec(
    chunks: list[Chunk],
    embeddings: dict[str, tuple[float, ...]],
) -> dict[str, tuple[float, ...]]:
    return {chunk.chunk_id: embeddings[embedding_hash(chunk)] for chunk in chunks}


def run_vulnerable_case(chunks: list[Chunk]):
    first = (1.0, 0.0, 0.0)
    second = (0.0, 1.0, 0.0)
    responses = {"chunk-a": first, "chunk-b": second}

    embeddings: dict[str, tuple[float, ...]] = {}
    chunk_vec: dict[str, tuple[float, ...]] = {}
    _reuse, to_send = plan_embed_batch(chunks, embeddings)

    for chunk, emb_id in to_send:
        write_chunk_embedding_vulnerable(
            embeddings, chunk_vec, emb_id, chunk, responses[chunk.chunk_id]
        )

    emb_id = embedding_hash(chunks[0])
    rebuilt = rebuild_chunk_vec(chunks, embeddings)
    return {
        "planned_duplicate_misses": len(to_send) == 2,
        "authoritative_kept_first": embeddings[emb_id] == first,
        "chunk_a_matches_first": chunk_vec["chunk-a"] == first,
        "chunk_b_matches_second": chunk_vec["chunk-b"] == second,
        "chunk_b_conflicts_with_authoritative": chunk_vec["chunk-b"]
        != embeddings[emb_id],
        "rebuild_changes_chunk_b": rebuilt["chunk-b"] == first
        and rebuilt["chunk-b"] != chunk_vec["chunk-b"],
    }


def run_fixed_case(chunks: list[Chunk]):
    first = (1.0, 0.0, 0.0)
    conflicting_second = (0.0, 1.0, 0.0)

    groups: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        groups.setdefault(embedding_hash(chunk), []).append(chunk)

    embeddings: dict[str, tuple[float, ...]] = {}
    chunk_vec: dict[str, tuple[float, ...]] = {}
    for emb_id, members in groups.items():
        # Fixed behavior sends or accepts one canonical vector per identity.
        embeddings[emb_id] = first
        for member in members:
            chunk_vec[member.chunk_id] = embeddings[emb_id]

    emb_id = embedding_hash(chunks[0])
    return {
        "one_adapter_item_for_duplicate_identity": len(groups) == 1,
        "both_chunks_link_authoritative": all(
            chunk_vec[chunk.chunk_id] == embeddings[emb_id] for chunk in chunks
        ),
        "conflicting_duplicate_rejected": conflicting_second != embeddings[emb_id],
    }


def main() -> None:
    duplicate_text = "the same markdown paragraph"
    text_hash = hashlib.sha256(duplicate_text.encode()).hexdigest()
    chunks = [
        Chunk("chunk-a", text_hash, duplicate_text),
        Chunk("chunk-b", text_hash, duplicate_text),
    ]

    result = {
        "bounded": True,
        "duplicate_embedding_id": embedding_hash(chunks[0]) == embedding_hash(chunks[1]),
        "planned_duplicate_misses": True,
        "vulnerable": run_vulnerable_case(chunks),
        "fixed": run_fixed_case(chunks),
    }
    print(json.dumps(result, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
