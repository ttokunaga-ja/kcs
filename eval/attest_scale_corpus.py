#!/usr/bin/env python3
"""Attest the generated scale corpus against KCS's current search predicates.

The important count is not ``COUNT(*) FROM chunks``.  It is the set that the
production search path can serve at each scope's HEAD: a non-placeholder
chunk, associated with the current chunking configuration, whose
``(raw_hash, tool_profile_hash, gen)`` identity occurs in HEAD tree entries.
"""

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_scale_corpus as generator  # noqa: E402
import scale_fixture_spec as spec  # noqa: E402


MAX_HEAD_BYTES = 256
MAX_CONFIG_BYTES = 1024 * 1024
MAX_SCOPE_BYTES = 64 * 1024
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
REQUIRED_TABLES = {
    "chunks",
    "chunk_config_generations",
    "embeddings",
    "tree_entries",
    "chunk_fts",
}
OPTIONAL_TABLES = {
    "chunk_fts_docsize",
    "chunk_vec_rowids",
    "scopes",
}
MAX_EXPECTED_SCOPE_CHUNKS = max(
    profile["files_per_scope"] * profile["sections_per_file"]
    for profile in spec.PROFILES.values()
)


class ScaleAttestationError(RuntimeError):
    pass


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _regular_file_bytes(path, maximum, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ScaleAttestationError(f"{label} is missing: {path}") from exc
    if not generator._is_plain_regular_file(metadata):
        raise ScaleAttestationError(f"{label} must be a plain regular file: {path}")
    if metadata.st_size > maximum:
        raise ScaleAttestationError(
            f"{label} exceeds {maximum} bytes: {path} ({metadata.st_size})"
        )
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ScaleAttestationError(f"{label} grew while being read: {path}")
    return data


def _read_json(path, maximum, label):
    raw = _regular_file_bytes(path, maximum, label)
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScaleAttestationError(f"{label} is invalid JSON: {path}: {exc}") from exc


def _write_json_atomic(path, value):
    data = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def _prefixed_hash(digest):
    return digest if digest.startswith("sha256:") else f"sha256:{digest}"


def _canonical(path):
    try:
        return str(Path(path).resolve(strict=True))
    except OSError as exc:
        raise ScaleAttestationError(f"cannot canonicalize path {path}: {exc}") from exc


def _lexical_absolute(path):
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _validate_report_path(root, out):
    official = root / spec.ATTESTATION_NAME
    canonical_root = Path(_canonical(root))

    missing_components = []
    existing_parent = out.parent
    while generator._optional_lstat(existing_parent) is None:
        if existing_parent == existing_parent.parent:
            raise ScaleAttestationError(
                f"cannot find an existing output ancestor: {out.parent}"
            )
        missing_components.append(existing_parent.name)
        existing_parent = existing_parent.parent
    canonical_parent = Path(_canonical(existing_parent)).joinpath(
        *reversed(missing_components)
    )
    canonical_out = canonical_parent / out.name
    canonical_official = canonical_root / spec.ATTESTATION_NAME

    try:
        out.relative_to(root)
    except ValueError:
        lexical_inside = False
    else:
        lexical_inside = True
    try:
        canonical_out.relative_to(canonical_root)
    except ValueError:
        canonical_inside = False
    else:
        canonical_inside = True

    if lexical_inside and (out != official or canonical_out != canonical_official):
        raise ScaleAttestationError(
            f"attestation output inside the owned corpus must be {official}: {out}"
        )
    if not lexical_inside and canonical_inside:
        raise ScaleAttestationError(
            f"external attestation path resolves inside the owned corpus: {out}"
        )
    return canonical_out


def _bounded_child_names(path, expected_count, label):
    """Read at most the exact expected child count plus one overflow sentinel."""
    children = list(itertools.islice(path.iterdir(), expected_count + 1))
    if len(children) > expected_count:
        raise ScaleAttestationError(
            f"{label} contains more than {expected_count} entries: {path}"
        )
    return {child.name for child in children}


def _require_plain_directory(path, label, allow_missing=False):
    metadata = generator._optional_lstat(path)
    if metadata is None:
        if allow_missing:
            return False
        raise ScaleAttestationError(f"{label} is missing: {path}")
    if not generator._is_plain_directory(metadata):
        raise ScaleAttestationError(f"{label} must be a plain directory: {path}")
    return True


def verify_source_files(root, manifest, allow_kcs=True):
    """Verify every source byte and reject unmanifested scope entries."""
    expected_total = 0
    for scope in manifest["scopes"]:
        scope_dir = root / scope["name"]
        _require_plain_directory(scope_dir, "scope directory")
        expected_names = {entry["path"] for entry in scope["files"]}
        if allow_kcs:
            expected_names.add(".kcs")
        actual_names = _bounded_child_names(
            scope_dir, len(expected_names), "scale scope"
        )
        unknown = sorted(actual_names - expected_names)
        missing = sorted(
            {entry["path"] for entry in scope["files"]} - actual_names
        )
        if unknown:
            raise ScaleAttestationError(
                f"scope contains unmanifested entries ({scope['name']}): "
                + ", ".join(unknown)
            )
        if missing:
            raise ScaleAttestationError(
                f"scope is missing source files ({scope['name']}): "
                + ", ".join(missing)
            )
        for entry in scope["files"]:
            path = scope_dir / entry["path"]
            data = _regular_file_bytes(path, entry["bytes"], "scale source file")
            if len(data) != entry["bytes"] or _sha256(data) != entry["raw_sha256"]:
                raise ScaleAttestationError(f"scale source file digest mismatch: {path}")
            expected_total += 1
    if expected_total != manifest["shape"]["expected_files"]:
        raise ScaleAttestationError("verified source file count differs from manifest shape")
    return expected_total


def _read_head(kcs_dir):
    raw = _regular_file_bytes(kcs_dir / "HEAD", MAX_HEAD_BYTES, "scope HEAD")
    try:
        head = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ScaleAttestationError(f"scope HEAD is not ASCII: {kcs_dir / 'HEAD'}") from exc
    if not HASH_RE.fullmatch(head):
        raise ScaleAttestationError(f"scope HEAD is not a SHA-256 commit: {head!r}")
    return head, raw


def _read_scope_id(kcs_dir):
    value = _read_json(kcs_dir / "scope.json", MAX_SCOPE_BYTES, "scope identity")
    if not isinstance(value, dict):
        raise ScaleAttestationError("scope.json must be an object")
    scope_id = value.get("scope_id")
    if not isinstance(scope_id, str) or not ULID_RE.fullmatch(scope_id):
        raise ScaleAttestationError("scope.json scope_id is not a valid ULID")
    return scope_id


def _read_chunking_config(kcs_dir):
    path = kcs_dir / "config.toml"
    raw = _regular_file_bytes(path, MAX_CONFIG_BYTES, "scope config")
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ScaleAttestationError(f"scope config is invalid TOML: {path}: {exc}") from exc
    chunking = value.get("chunking", {})
    if not isinstance(chunking, dict):
        raise ScaleAttestationError(f"scope [chunking] must be a table: {path}")
    strategy = chunking.get("strategy", "heading")
    max_chars = chunking.get("max_chars", 6000)
    if strategy != spec.CHUNKING_STRATEGY or max_chars != spec.CHUNKING_MAX_CHARS:
        raise ScaleAttestationError(
            f"scope chunking config differs from scale contract: {path} "
            f"(strategy={strategy!r}, max_chars={max_chars!r})"
        )
    return {
        "strategy": strategy,
        "max_chars": max_chars,
        "chunking_config_hash": spec.CHUNKING_CONFIG_HASH,
    }


def _ensure_empty_runtime_tree(path, label):
    if not _require_plain_directory(path, label, allow_missing=True):
        return
    if next(path.rglob("*"), None) is not None:
        raise ScaleAttestationError(f"fresh scale scope has {label} entries: {path}")


def _open_read_only(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ScaleAttestationError(f"scope SQLite index is missing: {path}") from exc
    if not generator._is_plain_regular_file(metadata):
        raise ScaleAttestationError(
            f"scope SQLite index must be a plain regular file: {path}"
        )
    try:
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ScaleAttestationError(f"cannot open scope SQLite index: {path}: {exc}") from exc


def materialize_current_eligible(
    conn,
    head,
    chunking_config_hash,
    max_chunk_rowid=None,
    max_association_rowid=None,
    maximum_rows=MAX_EXPECTED_SCOPE_CHUNKS + 1,
):
    """Materialize exactly the production HEAD/current-config chunk predicate."""
    if (
        not isinstance(maximum_rows, int)
        or isinstance(maximum_rows, bool)
        or maximum_rows <= 0
    ):
        raise ScaleAttestationError("eligible-row materialization limit must be positive")
    if max_chunk_rowid is None:
        max_chunk_rowid = conn.execute(
            "SELECT COALESCE(MAX(rowid), 0) FROM chunks"
        ).fetchone()[0]
    if max_association_rowid is None:
        max_association_rowid = conn.execute(
            "SELECT COALESCE(MAX(association_rowid), 0) "
            "FROM chunk_config_generations"
        ).fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS temp.scale_current_eligible")
    conn.execute(
        "CREATE TEMP TABLE scale_current_eligible ("
        "rowid INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE, "
        "raw_hash TEXT NOT NULL, text_hash TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO scale_current_eligible(rowid, chunk_id, raw_hash, text_hash) "
        "SELECT c.rowid, c.chunk_id, c.raw_hash, c.text_hash "
        "FROM chunks c "
        "WHERE c.first_seen_commit IS NOT NULL "
        "AND c.rowid <= ?1 "
        "AND EXISTS ("
        "  SELECT 1 FROM chunk_config_generations cg "
        "  WHERE cg.chunk_id = c.chunk_id "
        "  AND cg.chunking_config_hash = ?2 "
        "  AND cg.association_rowid <= ?3"
        ") "
        "AND EXISTS ("
        "  SELECT 1 FROM tree_entries te "
        "  WHERE te.commit_hash = ?4 "
        "  AND te.raw_hash = c.raw_hash "
        "  AND te.tool_profile_hash = c.tool_profile_hash "
        "  AND te.gen = c.gen"
        ") "
        "LIMIT ?5",
        (
            max_chunk_rowid,
            chunking_config_hash,
            max_association_rowid,
            head,
            maximum_rows,
        ),
    )
    return int(max_chunk_rowid), int(max_association_rowid)


def _table_names(conn):
    names = tuple(sorted(REQUIRED_TABLES | OPTIONAL_TABLES))
    placeholders = ", ".join("?" for _ in names)
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type IN ('table', 'view') "
            f"AND name IN ({placeholders}) LIMIT ?",
            (*names, len(names) + 1),
        )
    }


def _head_tree_rows(conn, head, expected_entries):
    rows = conn.execute(
        "SELECT path, raw_hash, tool_profile_hash, gen "
        "FROM tree_entries WHERE commit_hash = ?1 ORDER BY path LIMIT ?2",
        (head, expected_entries + 1),
    ).fetchall()
    if len(rows) > expected_entries:
        raise ScaleAttestationError(
            f"HEAD has more than {expected_entries} projected tree entries"
        )
    return rows


def _fts_coverage(conn):
    # Every generated chunk deliberately contains the token `scale`.  MATCH
    # therefore tests index membership for the whole eligible set without
    # walking hundreds of millions of trigram instances at the full profile.
    matched = conn.execute(
        "SELECT COUNT(*) FROM chunk_fts f "
        "JOIN scale_current_eligible eligible ON eligible.rowid = f.rowid "
        "WHERE chunk_fts MATCH 'scale'"
    ).fetchone()[0]
    # FTS5's docsize shadow table has one row per indexed document and is a
    # cheap exact structural cross-check; unlike SELECT COUNT(*) on an
    # external-content FTS table, it does not merely echo `chunks` content.
    docsize = conn.execute(
        "SELECT COUNT(*) FROM scale_current_eligible eligible "
        "JOIN chunk_fts_docsize d ON d.id = eligible.rowid"
    ).fetchone()[0]
    return int(matched), int(docsize)


def attest_scope(root, scope_manifest):
    scope_dir = root / scope_manifest["name"]
    _require_plain_directory(scope_dir, "scope directory")
    kcs_dir = scope_dir / ".kcs"
    _require_plain_directory(kcs_dir, "scope .kcs directory")
    purge_dir = kcs_dir / "purge"
    _require_plain_directory(purge_dir, "scope purge directory", allow_missing=True)
    purge_journal = kcs_dir / "purge" / "in-progress.json"
    if generator._optional_lstat(purge_journal) is not None:
        raise ScaleAttestationError(f"scope has an in-progress purge: {purge_journal}")
    _ensure_empty_runtime_tree(kcs_dir / "tombstones", "tombstones")
    _ensure_empty_runtime_tree(kcs_dir / "purge" / "erase-receipts", "erase receipts")

    head, head_raw_before = _read_head(kcs_dir)
    scope_id = _read_scope_id(kcs_dir)
    chunking = _read_chunking_config(kcs_dir)
    _require_plain_directory(kcs_dir / "index", "scope index directory")
    db_path = kcs_dir / "index" / "sqlite.db"
    conn = _open_read_only(db_path)
    try:
        tables = _table_names(conn)
        missing_tables = sorted(REQUIRED_TABLES - tables)
        if missing_tables:
            raise ScaleAttestationError(
                f"scope index is missing required tables ({scope_manifest['name']}): "
                + ", ".join(missing_tables)
            )
        if "chunk_fts_docsize" not in tables:
            raise ScaleAttestationError("scope FTS index lacks chunk_fts_docsize")

        tree_rows = _head_tree_rows(
            conn, head, scope_manifest["expected_files"]
        )
        if not tree_rows:
            raise ScaleAttestationError(
                "HEAD has no projected tree_entries; prepare must stop at "
                "`kcs index` and must not append a separate `kcs snapshot`"
            )
        expected_tree = {
            entry["path"]: _prefixed_hash(entry["raw_sha256"])
            for entry in scope_manifest["files"]
        }
        actual_tree = {row[0]: row[1] for row in tree_rows}
        if actual_tree != expected_tree:
            raise ScaleAttestationError(
                f"HEAD tree differs from source manifest: {scope_manifest['name']}"
            )
        if any(
            not isinstance(tool_hash, str)
            or not HASH_RE.fullmatch(tool_hash)
            or not isinstance(generation, int)
            or generation < 0
            for _, _, tool_hash, generation in tree_rows
        ):
            raise ScaleAttestationError(
                f"HEAD tree has invalid normalized identities: {scope_manifest['name']}"
            )

        physical_chunks = int(
            conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        )
        max_chunk_rowid, max_association_rowid = materialize_current_eligible(
            conn,
            head,
            chunking["chunking_config_hash"],
            maximum_rows=scope_manifest["expected_current_chunks"] + 1,
        )
        current_chunks = int(
            conn.execute("SELECT COUNT(*) FROM scale_current_eligible").fetchone()[0]
        )
        if current_chunks != scope_manifest["expected_current_chunks"]:
            raise ScaleAttestationError(
                f"eligible chunk count mismatch ({scope_manifest['name']}): "
                f"expected {scope_manifest['expected_current_chunks']}, got {current_chunks}"
            )
        chunks_by_raw = {
            raw_hash: int(count)
            for raw_hash, count in conn.execute(
                "SELECT raw_hash, COUNT(*) FROM scale_current_eligible "
                "GROUP BY raw_hash"
            )
        }
        expected_by_raw = {
            _prefixed_hash(entry["raw_sha256"]): entry["expected_chunks"]
            for entry in scope_manifest["files"]
        }
        if chunks_by_raw != expected_by_raw:
            raise ScaleAttestationError(
                f"per-file eligible chunk counts mismatch: {scope_manifest['name']}"
            )

        fts_matched, fts_docsize = _fts_coverage(conn)
        if fts_matched != current_chunks or fts_docsize != current_chunks:
            raise ScaleAttestationError(
                f"FTS coverage mismatch ({scope_manifest['name']}): "
                f"eligible={current_chunks}, match={fts_matched}, docsize={fts_docsize}"
            )
        embedded_chunks = int(
            conn.execute(
                "SELECT COUNT(*) FROM scale_current_eligible eligible "
                "WHERE EXISTS ("
                "  SELECT 1 FROM embeddings e "
                "  WHERE e.target_type = 'chunk' "
                "  AND e.target_id = eligible.text_hash"
                ")"
            ).fetchone()[0]
        )
        vector_shadow_rows = None
        if "chunk_vec_rowids" in tables:
            vector_shadow_rows = int(
                conn.execute("SELECT COUNT(*) FROM chunk_vec_rowids").fetchone()[0]
            )
    except sqlite3.Error as exc:
        raise ScaleAttestationError(
            f"SQLite attestation failed ({scope_manifest['name']}): {exc}"
        ) from exc
    finally:
        conn.close()

    _, head_raw_after = _read_head(kcs_dir)
    if head_raw_after != head_raw_before:
        raise ScaleAttestationError(f"scope HEAD changed during attestation: {scope_dir}")
    return {
        "name": scope_manifest["name"],
        "scope_id": scope_id,
        "root_path": _canonical(scope_dir),
        "head": head,
        "chunking": chunking,
        "source_files": scope_manifest["expected_files"],
        "head_tree_entries": len(tree_rows),
        "physical_chunks": physical_chunks,
        "current_eligible_chunks": current_chunks,
        "historical_or_ineligible_chunks": physical_chunks - current_chunks,
        "fts_match_sentinel": "scale",
        "fts_matched_current_chunks": fts_matched,
        "fts_docsize_current_chunks": fts_docsize,
        "embedded_current_chunks": embedded_chunks,
        "chunk_vec_shadow_rows": vector_shadow_rows,
        "max_chunk_rowid": max_chunk_rowid,
        "max_association_rowid": max_association_rowid,
    }


def attest_registry(root, scope_reports):
    if len(scope_reports) != len(spec.SCOPES):
        raise ScaleAttestationError(
            f"scale attestation requires exactly {len(spec.SCOPES)} scope reports"
        )
    device_dir = root / spec.DEVICE_DIR_NAME
    data_dir = device_dir / "data"
    kcs_data_dir = data_dir / "kcs"
    _require_plain_directory(device_dir, "isolated device directory")
    _require_plain_directory(data_dir, "isolated device data directory")
    _require_plain_directory(kcs_data_dir, "isolated device KCS directory")
    path = kcs_data_dir / "scope-registry.sqlite"
    conn = _open_read_only(path)
    try:
        tables = _table_names(conn)
        if "scopes" not in tables:
            raise ScaleAttestationError("isolated scope registry lacks scopes table")
        all_rows = conn.execute(
            "SELECT scope_id, kcs_path, root_path, "
            "participates_in_global_search, indexed FROM scopes LIMIT 21"
        ).fetchall()
    except sqlite3.Error as exc:
        raise ScaleAttestationError(f"scope registry attestation failed: {exc}") from exc
    finally:
        conn.close()
    if len(all_rows) != len(scope_reports):
        raise ScaleAttestationError(
            f"isolated registry row count mismatch: expected {len(scope_reports)}, "
            f"got {len(all_rows)}"
        )
    expected = {
        report["scope_id"]: (
            _canonical(Path(report["root_path"]) / ".kcs"),
            report["root_path"],
        )
        for report in scope_reports
    }
    if len(expected) != len(scope_reports):
        raise ScaleAttestationError("scope ids are not unique across the 20 scopes")
    actual = {}
    for scope_id, kcs_path, root_path, participates, indexed in all_rows:
        if participates != 1 or indexed != 1:
            raise ScaleAttestationError(
                f"registry scope is not an indexed global participant: {scope_id}"
            )
        actual[scope_id] = (_canonical(kcs_path), _canonical(root_path))
    if actual != expected:
        raise ScaleAttestationError("isolated scope registry paths/ids differ from scopes")
    return {
        "path": _canonical(path),
        "rows": len(all_rows),
        "indexed_global_participants": len(all_rows),
    }


def attest_corpus(corpus_dir):
    try:
        root, owner, manifest = generator.load_owned_manifest(corpus_dir)
        source_files = verify_source_files(root, manifest, allow_kcs=True)
    except generator.ScaleGenerationError as exc:
        raise ScaleAttestationError(str(exc)) from exc
    scope_reports = [
        attest_scope(root, scope_manifest)
        for scope_manifest in manifest["scopes"]
    ]
    registry = attest_registry(root, scope_reports)
    current_chunks = sum(
        report["current_eligible_chunks"] for report in scope_reports
    )
    fts_chunks = sum(
        report["fts_matched_current_chunks"] for report in scope_reports
    )
    expected_chunks = manifest["shape"]["expected_current_chunks"]
    if current_chunks != expected_chunks or fts_chunks != expected_chunks:
        raise ScaleAttestationError(
            f"collection chunk total mismatch: expected {expected_chunks}, "
            f"eligible={current_chunks}, fts={fts_chunks}"
        )
    minimum = manifest["shape"]["minimum_current_chunks"]
    if current_chunks < minimum:
        raise ScaleAttestationError(
            f"scale threshold not met: expected at least {minimum}, got {current_chunks}"
        )
    manifest_raw = _regular_file_bytes(
        root / spec.MANIFEST_NAME,
        generator.MAX_MANIFEST_BYTES,
        "scale manifest",
    )
    return {
        "schema_version": spec.SCHEMA_VERSION,
        "passed": True,
        "fixture_id": spec.FIXTURE_ID,
        "query_workload_id": spec.QUERY_WORKLOAD_ID,
        "profile": owner["profile"],
        "manifest_sha256": _sha256(manifest_raw),
        "content_root_sha256": manifest["content_root_sha256"],
        "totals": {
            "scopes": len(scope_reports),
            "source_files": source_files,
            "physical_chunks": sum(r["physical_chunks"] for r in scope_reports),
            "current_eligible_chunks": current_chunks,
            "fts_matched_current_chunks": fts_chunks,
            "embedded_current_chunks": sum(
                r["embedded_current_chunks"] for r in scope_reports
            ),
            "minimum_current_chunks": minimum,
        },
        "registry": registry,
        "scopes": scope_reports,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Attest a prepared KCS scale corpus"
    )
    parser.add_argument("--corpus", required=True, help="scale collection root")
    parser.add_argument(
        "--out",
        help="attestation JSON (default: <corpus>/scale-attestation.json)",
    )
    args = parser.parse_args(argv)
    try:
        root = _lexical_absolute(args.corpus)
        out = _lexical_absolute(args.out) if args.out else root / spec.ATTESTATION_NAME
        out = _validate_report_path(root, out)
        with generator.fixture_lock(root):
            report = attest_corpus(root)
            _write_json_atomic(out, report)
    except (
        OSError,
        ValueError,
        generator.ScaleGenerationError,
        ScaleAttestationError,
    ) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    totals = report["totals"]
    print(
        "[ok] scale attestation passed: "
        f"profile={report['profile']} scopes={totals['scopes']} "
        f"files={totals['source_files']} "
        f"current_chunks={totals['current_eligible_chunks']} "
        f"fts_chunks={totals['fts_matched_current_chunks']}"
    )
    print(f"     report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
