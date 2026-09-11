"""Read companion JSON metadata and older inline metadata headers."""

import json
from pathlib import Path

from pydantic import ValidationError

from exceptions import InvalidStoredDataError
from models import ArticleMetadata
from storage import validate_storage_file

def _validate_metadata(value: object) -> ArticleMetadata:
    """Validate stored metadata and report malformed data.

    Parameters
    ----------
    value : object
        Parsed JSON value.

    Returns
    -------
    ArticleMetadata
        Validated metadata with defaults for missing fields.

    Raises
    ------
    InvalidStoredDataError
        If the value is not an object with valid metadata fields.
    """
    try:
        return ArticleMetadata.model_validate(value)
    except ValidationError:
        raise InvalidStoredDataError("Stored article metadata is invalid")

def read_article_metadata(
    metadata_path: Path,
    markdown_source: str,
) -> tuple[ArticleMetadata, str, bool]:
    """Read metadata and separate any legacy header from the Markdown. Mostly made by AI.

    Parameters
    ----------
    metadata_path : pathlib.Path
        Companion JSON file, which may be absent.
    markdown_source : str
        Stored Markdown, possibly containing a legacy JSON header.

    Returns
    -------
    ArticleMetadata
        Metadata from the companion file, legacy header or defaults.
    str
        Markdown body without a recognized legacy header.
    bool
        Whether the Markdown contained a legacy header.

    Raises
    ------
    InvalidStoredDataError
        If stored metadata is malformed or the JSON path is unsafe.

    Notes
    -----
    A companion file takes precedence over inline metadata. Reading
    never migrates or rewrites an existing article.
    """
    validate_storage_file(metadata_path)
    try:
        serialized_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        serialized_metadata = None

    first_line, separator, remaining_source = markdown_source.partition("\n")
    try:
        inline_metadata = json.loads(first_line)
    except json.JSONDecodeError:
        inline_metadata = None
    has_header = isinstance(inline_metadata, dict) and any(
        field in inline_metadata for field in ArticleMetadata.model_fields
    )
    body = remaining_source if has_header and separator else markdown_source
    if has_header and not separator:
        body = ""

    if serialized_metadata is not None:
        try:
            metadata_value = json.loads(serialized_metadata)
        except json.JSONDecodeError:
            raise InvalidStoredDataError("Stored article metadata is not valid JSON")
        return _validate_metadata(metadata_value), body, has_header
    if has_header:
        return _validate_metadata(inline_metadata), body, True
    return ArticleMetadata(), markdown_source, False

def serialize_metadata(metadata: ArticleMetadata) -> bytes:
    """Encode metadata as a readable UTF-8 JSON object. Made by AI.

    Parameters
    ----------
    metadata : ArticleMetadata
        Validated article metadata.

    Returns
    -------
    bytes
        JSON ready to write to the companion file.
    """
    return (json.dumps(metadata.model_dump(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")