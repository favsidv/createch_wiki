"""Read and serialize companion JSON metadata."""

import json
from pathlib import Path
from exceptions import InvalidStoredDataError
from models import ArticleMetadata
from storage import validate_storage_file
from pydantic import ValidationError

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



def read_article_metadata(metadata_path: Path, markdown_source: str) -> tuple[ArticleMetadata, str, bool]:
    """Read optional metadata without changing the Markdown body.

    Parameters
    ----------
    metadata_path : pathlib.Path
        Companion JSON file, which may be absent.
    markdown_source : str
        Original Markdown content.

    Returns
    -------
    ArticleMetadata
        Validated metadata, with defaults for absent fields.
    str
        Unchanged Markdown body.
    bool
        False, since inline headers are not interpreted at this stage.

    Raises
    ------
    InvalidStoredDataError
        If stored JSON or metadata types are invalid.
    """
    validate_storage_file(metadata_path)
    try:
        serialized_metadata = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ArticleMetadata(), markdown_source, False
    try:
        value = json.loads(serialized_metadata)
    except json.JSONDecodeError:
        raise InvalidStoredDataError("Stored article metadata is not valid JSON")
    return _validate_metadata(value), markdown_source, False

def serialize_metadata(metadata: ArticleMetadata) -> bytes:
    """Encode metadata as a readable UTF-8 JSON object.

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
