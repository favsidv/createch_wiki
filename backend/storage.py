"""Provide locked file access and atomic replacement on macOS and Linux."""

import fcntl
import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from exceptions import InvalidStoredDataError

_thread_lock = RLock()


def require_directory(directory: Path) -> None:
    """Require an existing directory.

    Parameters
    ----------
    directory : pathlib.Path
        Storage directory to check.

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    NotADirectoryError
        If the path exists but is not a directory.
    """
    if not stat.S_ISDIR(directory.stat().st_mode):
        raise NotADirectoryError("Storage location is not a directory")


def validate_storage_file(path: Path) -> None:
    """Accept a regular file or an unused filename, without following links.

    Parameters
    ----------
    path : pathlib.Path
        Existing or future storage file.

    Raises
    ------
    InvalidStoredDataError
        If the path is a symbolic link or another special file.
    """
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise InvalidStoredDataError("Storage files must be regular files")


@contextmanager
def storage_lock(directory: Path) -> Iterator[None]:
    """Serialize access across server threads and worker processes.

    Parameters
    ----------
    directory : pathlib.Path
        Shared storage root containing the lock file.

    Yields
    ------
    None
        Control while the storage lock is held.

    Notes
    -----
    The directory must exist. The advisory lock coordinates this backend,
    not external programs editing files without taking the same lock.
    """
    require_directory(directory)
    with _thread_lock:
        lock_path = directory / ".wiki.lock"
        validate_storage_file(lock_path)
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _replace_file(path: Path, content: bytes) -> None:
    """Replace one file using a fully written temporary file.

    Parameters
    ----------
    path : pathlib.Path
        Destination file.
    content : bytes
        Complete new file contents.
    """
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".wiki-", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_files(changes: Mapping[Path, bytes | None]) -> None:
    """Apply file changes and restore previous contents on an exception.

    Parameters
    ----------
    changes : mapping of pathlib.Path to bytes or None
        New contents, or None to remove a file.

    Notes
    -----
    Call while holding the storage lock. Each replacement is atomic.
    The group is not a crash-safe transaction; rollback can also fail
    if the underlying storage becomes unavailable.
    """
    previous = {}
    for path in changes:
        validate_storage_file(path)
        try:
            previous[path] = path.read_bytes()
        except FileNotFoundError:
            previous[path] = None

    applied = []
    try:
        for path, content in changes.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _replace_file(path, content)
            applied.append(path)
    except Exception:
        # Restore completed changes, then propagate the original failure.
        for path in reversed(applied):
            if previous[path] is None:
                path.unlink(missing_ok=True)
            else:
                _replace_file(path, previous[path])
        raise
