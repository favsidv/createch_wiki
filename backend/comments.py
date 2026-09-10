"""Store site-wide plain-text comments in a JSON file."""

import json
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError

from config import MAX_COMMENT_CONTENT_LENGTH, paths
from exceptions import InvalidCommentError, InvalidStoredDataError
from models import Comment, NewComment
from storage import storage_lock, validate_storage_file, write_files

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


def create_comment(comment_request: NewComment) -> Comment:
    """Validate and persist a comment with a server-generated UUID.

    Parameters
    ----------
    comment_request : NewComment
        Plain-text content and an optional author.

    Returns
    -------
    Comment
        Stored comment, using an empty author for anonymous users.

    Raises
    ------
    InvalidCommentError
        If the content is blank, too long or contains invalid Unicode.
    """
    content = comment_request.content.strip()
    if not content or len(content) > MAX_COMMENT_CONTENT_LENGTH:
        raise InvalidCommentError("Comment content must contain between 1 and 10000 characters")
    comment = Comment(id=str(uuid4()), author=(comment_request.author or "").strip(), content=content)
    try:
        comment.model_dump_json().encode("utf-8")
        content.encode("utf-8")
        comment.author.encode("utf-8")
    except (UnicodeEncodeError, ValueError):
        raise InvalidCommentError("Comment text must be valid UTF-8")
    with storage_lock(paths.root):
        comments = _read_comments()
        # Appending under the lock preserves order and prevents lost writes.
        comments.append(comment)
        serialized = json.dumps([entry.model_dump() for entry in comments], ensure_ascii=False, indent=2)
        write_files({paths.comments: (serialized + "\n").encode("utf-8")})
    return comment
