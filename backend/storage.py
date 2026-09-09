"""Validate storage locations independently of HTTP."""

import stat
from pathlib import Path
from exceptions import InvalidStoredDataError

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
