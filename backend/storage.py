"""Provide locked file access and atomic replacement on macOS and Linux."""

import fcntl
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
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
    """Write complete bytes to the destination file.

    Parameters
    ----------
    path : pathlib.Path
        File to write.
    content : bytes
        New file contents.
    """
    path.write_bytes(content)


def write_files(changes: Mapping[Path, bytes | None]) -> None:
    """Apply prepared file changes without group rollback.

    Parameters
    ----------
    changes : mapping of pathlib.Path to bytes or None
        New file contents, or None to remove a file.

    Notes
    -----
    The caller owns the storage access boundary. A multi-file operation
    is not transactional at this stage.
    """
    for path, content in changes.items():
        validate_storage_file(path)
        if content is None:
            path.unlink(missing_ok=True)
        else:
            _replace_file(path, content)
