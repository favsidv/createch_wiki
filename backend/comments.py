"""Store site-wide plain-text comments in a JSON file."""

import json

from pydantic import TypeAdapter, ValidationError

from config import paths
from exceptions import InvalidStoredDataError
from models import Comment
from storage import storage_lock, validate_storage_file

_comment_list = TypeAdapter(list[Comment])


def _read_comments() -> list[Comment]:
    """Read comments while the caller holds the storage lock.

    Returns
    -------
    list of Comment
        Comments in stored order, or an empty list when no file exists.

    Raises
    ------
    InvalidStoredDataError
        If the JSON file or its comment records are invalid.
    """
    validate_storage_file(paths.comments)
    try:
        source = paths.comments.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        comments = _comment_list.validate_python(json.loads(source))
    except (json.JSONDecodeError, ValidationError):
        raise InvalidStoredDataError("Stored comments are invalid")
    if len({comment.id for comment in comments}) != len(comments):
        raise InvalidStoredDataError("Stored comment identifiers are duplicated")
    return comments


def list_comments() -> list[Comment]:
    """Read all site-wide comments in insertion order.

    Returns
    -------
    list of Comment
        Comments from oldest to newest.
    """
    with storage_lock(paths.root):
        return _read_comments()
