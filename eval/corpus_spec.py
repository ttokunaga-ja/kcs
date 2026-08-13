"""Frozen metadata for the Rust-owned synthetic evaluation corpus.

Corpus bytes and the corpus manifest are generated only by ``kio-eval
generate-corpus`` from ``corpus-fixture.json``.  Python retains this small
metadata view for history replay and independent diagnostic oracles; it must
not render documents or synthesize filler content.
"""

import json
import os


HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_FIXTURE_NAME = "corpus-fixture.json"
CORPUS_MANIFEST_NAME = "corpus-manifest.json"
HISTORY_MANIFEST_NAME = "history-manifest.json"


def _load_fixture():
    with open(os.path.join(HERE, CORPUS_FIXTURE_NAME), encoding="utf-8") as handle:
        return json.load(handle)


def _load_history():
    with open(os.path.join(HERE, HISTORY_MANIFEST_NAME), encoding="utf-8") as handle:
        return json.load(handle)


_FIXTURE = _load_fixture()
_MANIFEST = _FIXTURE["manifest"]
_HISTORY_MANIFEST = _load_history()
SEED = _MANIFEST["seed"]
SCOPES = _MANIFEST["scopes"]
# Anchor metadata only: content rendering deliberately has no Python source.
ANCHORS = [entry for entry in _MANIFEST["files"] if entry["anchor"]]
_ANCHOR_BY_KEY = {(entry["scope"], entry["file"]): entry for entry in ANCHORS}


def anchor_manifest_entry(anchor):
    """Return a standalone manifest view for legacy diagnostic callers."""
    return {
        key: anchor[key]
        for key in ("scope", "file", "kind", "anchor", "role", "sections", "raw_sha256")
    }


def anchor_by_key(scope, file_):
    return _ANCHOR_BY_KEY.get((scope, file_))


_HISTORY_OPERATION_FIELDS = {
    "renames": ("renamed", ("scope", "old_file", "new_file")),
    "edits": ("edited", ("scope", "file", "old_value", "new_value")),
    "deletes": ("deleted", ("scope", "file")),
}
HISTORY = {
    operation: [
        {field: entry[field] for field in fields}
        for entry in _HISTORY_MANIFEST[manifest_key]
    ]
    for operation, (manifest_key, fields) in _HISTORY_OPERATION_FIELDS.items()
}
