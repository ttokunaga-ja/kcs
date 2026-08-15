"""Bounded no-follow filesystem observations for Rust persona artifacts.

The content root is only filesystem evidence.  It never claims Kio contents,
history replay, or artifact semantic validity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata

from . import persona_artifacts

CONTENT_ROOT_SCHEMA = "kio.persona.filesystem-content-root/v2"
FILESYSTEM_ATTESTATION_SCHEMA = "kio.persona.filesystem-attestation/v2"
FILESYSTEM_COVERAGE = "filesystem_structure_and_file_bytes_only"
HARD_MAX_ENTRIES = 250_000
HARD_MAX_DIRECT_ENTRIES = 16_384
HARD_MAX_FILES = 200_000
HARD_MAX_DIRECTORIES = 50_000
HARD_MAX_TOTAL_FILE_BYTES = 8 * 1024 * 1024 * 1024
HARD_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
HARD_MAX_DEPTH = 32
HARD_MAX_RELATIVE_PATH_BYTES = 4096
HARD_MAX_COMPONENTS = 64
HARD_MAX_READ_SIZE = 16 * 1024 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")

class PersonaHistoryAttestationError(RuntimeError):
    pass

@dataclass(frozen=True)
class AttestationLimits:
    max_entries: int = HARD_MAX_ENTRIES
    max_direct_entries: int = HARD_MAX_DIRECT_ENTRIES
    max_files: int = HARD_MAX_FILES
    max_directories: int = HARD_MAX_DIRECTORIES
    max_total_file_bytes: int = HARD_MAX_TOTAL_FILE_BYTES
    max_file_bytes: int = HARD_MAX_FILE_BYTES
    max_depth: int = HARD_MAX_DEPTH
    max_relative_path_bytes: int = HARD_MAX_RELATIVE_PATH_BYTES
    max_components: int = HARD_MAX_COMPONENTS
    read_size: int = 1024 * 1024
    def __post_init__(self):
        caps = {"max_entries": HARD_MAX_ENTRIES, "max_direct_entries": HARD_MAX_DIRECT_ENTRIES, "max_files": HARD_MAX_FILES, "max_directories": HARD_MAX_DIRECTORIES, "max_total_file_bytes": HARD_MAX_TOTAL_FILE_BYTES, "max_file_bytes": HARD_MAX_FILE_BYTES, "max_depth": HARD_MAX_DEPTH, "max_relative_path_bytes": HARD_MAX_RELATIVE_PATH_BYTES, "max_components": HARD_MAX_COMPONENTS, "read_size": HARD_MAX_READ_SIZE}
        for name, cap in caps.items():
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= cap:
                raise PersonaHistoryAttestationError(f"{name} is outside hard bounds")
        if self.max_files > self.max_entries or self.max_directories > self.max_entries or self.max_file_bytes > self.max_total_file_bytes or self.read_size < 512:
            raise PersonaHistoryAttestationError("attestation limits are inconsistent")

DEFAULT_LIMITS = AttestationLimits()

@dataclass(frozen=True)
class DirectoryContentRoot:
    schema: str
    schema_version: int
    coverage: str
    directory_device: int
    directory_inode: int
    directory_nlink: int
    descendant_directories: int
    regular_files: int
    total_file_bytes: int
    maximum_depth: int
    content_root_sha256: str

def _stable(metadata: os.stat_result):
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink, metadata.st_size, getattr(metadata, "st_mtime_ns", 0), getattr(metadata, "st_ctime_ns", 0))

def _flags(directory: bool) -> int:
    required = ("O_CLOEXEC", "O_NOFOLLOW") + (("O_DIRECTORY",) if directory else ("O_NONBLOCK",))
    flags = os.O_RDONLY
    for name in required:
        value = getattr(os, name, None)
        if type(value) is not int or value == 0:
            raise PersonaHistoryAttestationError(f"safe-open flag unavailable: {name}")
        flags |= value
    return flags

def _component(name: str):
    if not isinstance(name, str) or not name or name in (".", "..") or "/" in name or "\x00" in name or unicodedata.normalize("NFC", name) != name or len(name.encode()) > 255:
        raise PersonaHistoryAttestationError("runtime entry is not a portable component")

def _file(parent: int, name: str, expected: os.stat_result, limits: AttestationLimits):
    if expected.st_nlink != 1 or expected.st_size < 0 or expected.st_size > limits.max_file_bytes:
        raise PersonaHistoryAttestationError("runtime file link count or size is invalid")
    try:
        fd = os.open(name, _flags(False), dir_fd=parent)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or _stable(opened) != _stable(expected):
            raise PersonaHistoryAttestationError("runtime file changed while opening")
        digest, total = hashlib.sha256(), 0
        while total < expected.st_size:
            block = os.read(fd, min(limits.read_size, expected.st_size - total))
            if not block: break
            total += len(block); digest.update(block)
        after = os.fstat(fd); named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if total != expected.st_size or _stable(after) != _stable(opened) or _stable(named) != _stable(after):
            raise PersonaHistoryAttestationError("runtime file changed while reading")
        return total, digest.digest()
    except OSError as error:
        raise PersonaHistoryAttestationError("cannot read runtime file safely") from error
    finally:
        try: os.close(fd)
        except (OSError, UnboundLocalError): pass

def _merkle(rows):
    digest = hashlib.sha256(b"kio.persona.filesystem-directory-merkle/v2\0" + len(rows).to_bytes(8, "big"))
    for name, kind, size, child in sorted(rows):
        digest.update(kind); digest.update(len(name).to_bytes(2, "big")); digest.update(name)
        if kind == b"F": digest.update(size.to_bytes(8, "big"))
        digest.update(child)
    return digest.digest()


def _open_absolute_directory(path: Path) -> tuple[int, os.stat_result]:
    """Bind every existing absolute-path component through no-follow handles."""
    if not path.is_absolute() or path.anchor != "/":
        raise PersonaHistoryAttestationError("runtime root must be an absolute POSIX path")
    descriptor = -1
    try:
        descriptor = os.open(path.anchor, _flags(True))
        for component in path.parts[1:]:
            before = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise PersonaHistoryAttestationError("runtime root component is not a directory")
            child = os.open(component, _flags(True), dir_fd=descriptor)
            try:
                if _stable(os.fstat(child)) != _stable(before):
                    raise PersonaHistoryAttestationError("runtime root component changed while opening")
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise PersonaHistoryAttestationError("runtime root is not a directory")
        return descriptor, metadata
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise PersonaHistoryAttestationError("cannot open runtime root safely") from error

def walk_directory_content_root(path: os.PathLike[str] | str, *, limits: AttestationLimits = DEFAULT_LIMITS) -> DirectoryContentRoot:
    """Walk a stable same-device tree, rejecting links, replacements and bounds."""
    if type(limits) is not AttestationLimits or os.name == "nt":
        raise PersonaHistoryAttestationError("handle-relative attestation is unavailable")
    supplied = Path(os.fspath(path))
    if not supplied.is_absolute() or Path(os.path.normpath(supplied)) != supplied:
        raise PersonaHistoryAttestationError("runtime root path must be absolute and lexically normalized")
    root = supplied
    rootfd, opened = _open_absolute_directory(root)
    seen = {(opened.st_dev, opened.st_ino)}; counts = {"entries": 0, "files": 0, "dirs": 0, "bytes": 0, "depth": 0}
    def visit(fd: int, depth: int, path_bytes: int):
        start = os.fstat(fd); rows = []; direct = 0; folds = set()
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    direct += 1; _component(entry.name)
                    if direct > limits.max_direct_entries: raise PersonaHistoryAttestationError("runtime directory exceeds direct-entry bound")
                    folded = entry.name.casefold().encode();
                    if folded in folds: raise PersonaHistoryAttestationError("runtime directory has case-insensitive collision")
                    folds.add(folded); name = entry.name.encode(); child_depth = depth + 1; child_path = path_bytes + (1 if path_bytes else 0) + len(name)
                    if child_depth > limits.max_depth or child_depth > limits.max_components or child_path > limits.max_relative_path_bytes: raise PersonaHistoryAttestationError("runtime tree exceeds path bound")
                    counts["entries"] += 1
                    if counts["entries"] > limits.max_entries: raise PersonaHistoryAttestationError("runtime tree exceeds entry bound")
                    metadata = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                    inode = (metadata.st_dev, metadata.st_ino)
                    if metadata.st_dev != opened.st_dev or inode in seen: raise PersonaHistoryAttestationError("runtime tree crosses device or reuses inode")
                    seen.add(inode); counts["depth"] = max(counts["depth"], child_depth)
                    if stat.S_ISDIR(metadata.st_mode):
                        counts["dirs"] += 1
                        if counts["dirs"] > limits.max_directories: raise PersonaHistoryAttestationError("runtime tree exceeds directory bound")
                        child = os.open(entry.name, _flags(True), dir_fd=fd)
                        try:
                            child_stat = os.fstat(child)
                            if _stable(child_stat) != _stable(metadata): raise PersonaHistoryAttestationError("runtime directory changed while opening")
                            root_digest = visit(child, child_depth, child_path)
                            if _stable(os.fstat(child)) != _stable(child_stat) or _stable(os.stat(entry.name, dir_fd=fd, follow_symlinks=False)) != _stable(child_stat): raise PersonaHistoryAttestationError("runtime directory changed while scanning")
                        finally: os.close(child)
                        rows.append((name, b"D", 0, root_digest))
                    elif stat.S_ISREG(metadata.st_mode):
                        counts["files"] += 1; counts["bytes"] += metadata.st_size
                        if counts["files"] > limits.max_files or counts["bytes"] > limits.max_total_file_bytes: raise PersonaHistoryAttestationError("runtime tree exceeds file or byte bound")
                        size, digest = _file(fd, entry.name, metadata, limits); rows.append((name, b"F", size, digest))
                    else: raise PersonaHistoryAttestationError("runtime entry is a link or special file")
            if _stable(os.fstat(fd)) != _stable(start): raise PersonaHistoryAttestationError("runtime directory changed during traversal")
            return _merkle(rows)
        except OSError as error:
            raise PersonaHistoryAttestationError("cannot traverse runtime directory safely") from error
    try:
        digest = visit(rootfd, 0, 0)
        if _stable(os.fstat(rootfd)) != _stable(opened) or _stable(root.lstat()) != _stable(opened): raise PersonaHistoryAttestationError("runtime root changed during traversal")
        return DirectoryContentRoot(CONTENT_ROOT_SCHEMA, 2, FILESYSTEM_COVERAGE, opened.st_dev, opened.st_ino, opened.st_nlink, counts["dirs"], counts["files"], counts["bytes"], counts["depth"], "sha256:" + digest.hex())
    finally: os.close(rootfd)

def build_filesystem_attestation(*, bundle: object, root_binding_sha256: str, directory: os.PathLike[str] | str, limits: AttestationLimits = DEFAULT_LIMITS) -> dict[str, object]:
    """Bind an opaque directory observation to supplied Rust artifact identities."""
    try: fields = {name: getattr(bundle, name) for name in ("fixture_id", "profile", "plan_digest", "plan_sha256", "schedule_sha256", "render_sha256")}
    except AttributeError as error: raise PersonaHistoryAttestationError("artifact bundle is invalid") from error
    if (
        fields["fixture_id"] != persona_artifacts.FIXTURE_ID
        or fields["profile"] not in {"tiny", "pilot", "full"}
        or any(type(fields[name]) is not str for name in fields)
        or any(_DIGEST.fullmatch(fields[name]) is None for name in ("plan_digest", "plan_sha256", "schedule_sha256", "render_sha256"))
        or fields["plan_digest"] != fields["plan_sha256"]
        or _DIGEST.fullmatch(root_binding_sha256 or "") is None
    ):
        raise PersonaHistoryAttestationError("artifact binding digest is invalid")
    supplied = Path(os.fspath(directory))
    content = walk_directory_content_root(supplied, limits=limits)
    return {"schema": FILESYSTEM_ATTESTATION_SCHEMA, "schema_version": 2, **fields, "root_binding_sha256": root_binding_sha256, "directory": str(supplied), "content_root": content.__dict__, "claims": {"actual_kio_evidence": False, "history_ready": False}}
