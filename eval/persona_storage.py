"""Small filesystem primitives retained for streaming persona artifacts.

Persona plans, workspace ownership, and canonical artifact publication are now
Rust-only concerns. This module exposes only generic no-replace and plain-entry
operations used by ``persona_streaming_storage``.
"""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import stat
import sys
import tempfile


WINDOWS_REPARSE_POINT_ATTRIBUTE = 0x400
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004


class PersonaStorageError(RuntimeError):
    """Raised when a streaming storage operation cannot fail closed."""


def _is_windows_reparse_point(metadata: os.stat_result) -> bool:
    return bool(
        (getattr(metadata, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT_ATTRIBUTE)
        or getattr(metadata, "st_reparse_tag", 0)
    )


def is_plain_directory_metadata(metadata: os.stat_result) -> bool:
    """Whether metadata is a real directory rather than a link/reparse entry."""
    return stat.S_ISDIR(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def is_plain_regular_file_metadata(metadata: os.stat_result) -> bool:
    """Whether metadata is a real regular file rather than a link/reparse entry."""
    return stat.S_ISREG(metadata.st_mode) and not _is_windows_reparse_point(metadata)


def _optional_lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _absolute_lexical(path: os.PathLike[str] | str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    # Darwin exposes these two system-owned compatibility aliases as symlinks.
    # Normalize only the fixed platform aliases; all caller-controlled links
    # remain rejected by the component walk below.
    if sys.platform == "darwin":
        for alias, physical in ((Path("/var"), Path("/private/var")), (Path("/tmp"), Path("/private/tmp"))):
            if absolute == alias or alias in absolute.parents:
                try:
                    if (alias.parent / os.readlink(alias)).resolve() == physical:
                        return physical.joinpath(*absolute.relative_to(alias).parts)
                except OSError:
                    pass
    return absolute


def _validate_existing_directory_chain(path: Path) -> None:
    """Reject existing symlink, file, or special components without resolving."""
    current = Path(path.anchor)
    metadata = _optional_lstat(current)
    if metadata is None or not is_plain_directory_metadata(metadata):
        raise PersonaStorageError(f"filesystem anchor is not a plain directory: {current}")
    for component in path.parts[1:]:
        current /= component
        metadata = _optional_lstat(current)
        if metadata is None:
            return
        if not is_plain_directory_metadata(metadata):
            raise PersonaStorageError(f"path component must be a plain directory: {current}")


def _same_file_identity(path: Path, expected: os.stat_result) -> bool:
    current = _optional_lstat(path)
    return bool(
        current is not None
        and (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino)
    )


def _open_plain_directory(path: Path) -> tuple[int, os.stat_result]:
    """Open a directory and bind its descriptor to the lexical path identity."""
    apparent = _optional_lstat(path)
    if apparent is None or not is_plain_directory_metadata(apparent):
        raise PersonaStorageError(f"directory is not plain: {path}")
    if os.name == "nt":  # pragma: no cover - Windows CI
        return -1, apparent
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PersonaStorageError(f"cannot safely open directory: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not is_plain_directory_metadata(opened) or not _same_file_identity(path, opened):
            raise PersonaStorageError(f"directory changed while opening: {path}")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - Windows CI
        return
    descriptor, _ = _open_plain_directory(path)
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise PersonaStorageError(f"cannot sync directory: {path}") from exc
    finally:
        os.close(descriptor)


def _raise_rename_error(result: int, source: str, destination: str) -> None:
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise FileExistsError(error_number, "atomic destination already exists", destination)
    raise OSError(error_number, os.strerror(error_number), f"{source} -> {destination}")


def _require_noreplace_directory_support() -> None:
    """Fail before writing a stage if atomic sibling no-replace is unavailable."""
    if sys.platform == "darwin":
        if not hasattr(ctypes.CDLL(None), "renameatx_np"):
            raise PersonaStorageError("Darwin lacks atomic no-replace publication")
        return
    if sys.platform.startswith("linux"):
        if getattr(ctypes.CDLL(None), "renameat2", None) is None:
            raise PersonaStorageError("libc lacks atomic no-replace publication")
        return
    if os.name == "nt":
        return
    raise PersonaStorageError("platform lacks atomic no-replace directory publication support")


def _rename_directory_noreplace(
    parent_descriptor: int, parent_path: Path, source_name: str, destination_name: str
) -> None:
    """Atomically rename a sibling entry without replacing an existing target."""
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        function = ctypes.CDLL(None, use_errno=True).renameatx_np
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        ctypes.set_errno(0)
        _raise_rename_error(function(parent_descriptor, source, parent_descriptor, destination, _RENAME_EXCL), source_name, destination_name)
        return
    if sys.platform.startswith("linux"):
        function = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
        if function is None:
            raise PersonaStorageError("libc lacks atomic no-replace publication")
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        ctypes.set_errno(0)
        _raise_rename_error(function(parent_descriptor, source, parent_descriptor, destination, _RENAME_NOREPLACE), source_name, destination_name)
        return
    if os.name == "nt":  # pragma: no cover - Windows CI
        os.rename(parent_path / source_name, parent_path / destination_name)
        return
    raise PersonaStorageError("platform lacks atomic no-replace directory publication support")


def atomic_write_file(
    path: os.PathLike[str] | str, data: bytes, *, mode: int = 0o600
) -> None:
    """Durably publish ``data`` once, retaining a failed temporary as evidence."""
    if not isinstance(data, bytes):
        raise TypeError("atomic_write_file data must be bytes")
    target = _absolute_lexical(path)
    _validate_existing_directory_chain(target.parent)
    if _optional_lstat(target) is not None:
        raise PersonaStorageError(f"refusing to replace existing path: {target}")
    _require_noreplace_directory_support()
    parent_descriptor, opened_parent = _open_plain_directory(target.parent)
    descriptor = -1
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        temporary_metadata = os.fstat(descriptor)
        if not is_plain_regular_file_metadata(temporary_metadata):
            raise PersonaStorageError(f"atomic temporary is not regular: {temporary}")
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        else:  # pragma: no cover - Windows CI
            os.chmod(temporary, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not _same_file_identity(target.parent, opened_parent):
            raise PersonaStorageError(f"file parent changed during publication: {target.parent}")
        if not _same_file_identity(temporary, temporary_metadata):
            raise PersonaStorageError(f"atomic temporary changed during publication: {temporary}")
        try:
            _rename_directory_noreplace(parent_descriptor, target.parent, temporary.name, target.name)
        except FileExistsError as exc:
            raise PersonaStorageError(f"file target appeared during no-replace publication: {target}") from exc
        try:
            published = target.lstat()
        except FileNotFoundError as exc:
            raise PersonaStorageError(
                f"file parent changed after publication: {target.parent}"
            ) from exc
        if not is_plain_regular_file_metadata(published) or (published.st_dev, published.st_ino) != (temporary_metadata.st_dev, temporary_metadata.st_ino):
            raise PersonaStorageError(f"published file identity changed unexpectedly: {target}")
        if not _same_file_identity(target.parent, opened_parent):
            raise PersonaStorageError(f"file parent changed after publication: {target.parent}")
        if parent_descriptor >= 0:
            os.fsync(parent_descriptor)
        _fsync_directory(target.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
