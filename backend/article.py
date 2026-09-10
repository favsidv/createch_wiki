"""Manage article validation, Markdown files, metadata and trash."""

from dataclasses import dataclass
from pathlib import Path

from config import MAX_ARTICLE_CONTENT_LENGTH, MAX_ARTICLE_NAME_LENGTH, paths
from exceptions import (
    ArticleNotFoundError,
    InvalidArticleContentError,
    InvalidArticleExtensionError,
    InvalidArticleIdentifierError,
    InvalidArticlePathError,
)
from metadata import read_article_metadata, serialize_metadata
from models import ArticleMetadata, ArticleUpdate, NewArticle
from storage import require_directory, storage_lock, validate_storage_file, write_files


@dataclass(frozen=True)
class StoredArticle:
    """Keep an article identifier, Markdown body and validated metadata."""

    identifier: str
    source: str
    metadata: ArticleMetadata
    has_legacy_header: bool = False


def validate_article_identifier(article_identifier: str) -> None:
    """Validate an article identifier without accessing the filesystem.

    Parameters
    ----------
    article_identifier : str
        Article filename without its Markdown extension.

    Raises
    ------
    InvalidArticleIdentifierError
        If the identifier is blank, unsafe or not valid UTF-8 text.
    """
    if (
        not article_identifier.strip()
        or any(fragment in article_identifier for fragment in ("/", "\\", ".."))
        or any(ord(character) < 32 or ord(character) == 127 for character in article_identifier)
    ):
        raise InvalidArticleIdentifierError("Invalid article identifier")
    try:
        encoded_identifier = article_identifier.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidArticleIdentifierError("Article identifier must be valid UTF-8")
    if len(encoded_identifier) > 250:
        raise InvalidArticleIdentifierError("Article identifier is too long")


def validate_article_path(article_path: Path) -> None:
    """Validate the article location, extension and file type.

    Parameters
    ----------
    article_path : pathlib.Path
        Existing or future Markdown article path.

    Raises
    ------
    InvalidArticlePathError
        If the path is outside storage or is a symbolic link.
    InvalidArticleExtensionError
        If the extension is not .md.
    FileNotFoundError
        If the articles directory is missing.
    NotADirectoryError
        If article storage is not a directory.

    Notes
    -----
    The file itself may be absent so creation can use this validation.
    """
    # Resolve the storage directory and ensure it exists.
    storage_directory = paths.articles.resolve(strict=True)
    require_directory(storage_directory)
    if article_path.is_symlink() or article_path.resolve().parent != storage_directory:
        raise InvalidArticlePathError("Invalid article path")
    if article_path.suffix != ".md":
        raise InvalidArticleExtensionError("Article extension must be .md")
    validate_storage_file(article_path)


def get_article_path(article_identifier: str) -> Path:
    """Build and validate the path to an article file.

    Parameters
    ----------
    article_identifier : str
        Article filename without its Markdown extension.

    Returns
    -------
    pathlib.Path
        Validated path to an existing or future article.

    Raises
    ------
    InvalidArticleIdentifierError
        If the identifier is invalid.
    InvalidArticlePathError
        If the path is invalid.
    """
    validate_article_identifier(article_identifier)
    article_path = paths.articles / f"{article_identifier}.md"
    validate_article_path(article_path)
    return article_path


def _read_article(article_identifier: str) -> StoredArticle:
    """Read an article while the caller holds the storage lock.

    Parameters
    ----------
    article_identifier : str
        Identifier of the requested article.

    Returns
    -------
    StoredArticle
        Markdown and metadata without HTML rendering.

    Raises
    ------
    ArticleNotFoundError
        If the article is missing from an existing directory.
    """
    article_path = get_article_path(article_identifier)
    try:
        source = article_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        require_directory(paths.articles)
        raise ArticleNotFoundError("Article not found")
    metadata, source, has_header = read_article_metadata(article_path.with_suffix(".json"), source)
    return StoredArticle(article_identifier, source, metadata, has_header)


def read_article(article_identifier: str) -> StoredArticle:
    """Read an article and its optional metadata under the storage lock.

    Parameters
    ----------
    article_identifier : str
        Identifier of the requested article.

    Returns
    -------
    StoredArticle
        Article content and metadata.

    Raises
    ------
    ArticleNotFoundError
        If the article does not exist.
    """
    with storage_lock(paths.root):
        return _read_article(article_identifier)


def list_article_identifiers() -> list[str]:
    """List readable article identifiers in alphabetical order.

    Returns
    -------
    list of str
        Identifiers excluding directories, links and non-Markdown files.

    Raises
    ------
    FileNotFoundError
        If the article directory is absent.
    """
    with storage_lock(paths.root):
        require_directory(paths.articles)
        identifiers = []
        for article_path in paths.articles.iterdir():
            if article_path.suffix != ".md" or article_path.is_symlink() or not article_path.is_file():
                continue
            try:
                validate_article_identifier(article_path.stem)
            except InvalidArticleIdentifierError:
                continue
            identifiers.append(article_path.stem)
        return sorted(identifiers, key=lambda identifier: (identifier.casefold(), identifier))


def _validate_content(content: str | None) -> str:
    """Validate Markdown supplied for creation or replacement.

    Parameters
    ----------
    content : str or None
        Proposed Markdown body.

    Returns
    -------
    str
        Validated Markdown, preserving its original whitespace.

    Raises
    ------
    InvalidArticleContentError
        If content is null, blank, too long or cannot be encoded.
    """
    if content is None or not content.strip():
        raise InvalidArticleContentError("Article content must not be empty")
    if len(content) > MAX_ARTICLE_CONTENT_LENGTH:
        raise InvalidArticleContentError("Article content exceeds 100000 characters")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidArticleContentError("Article content must be valid UTF-8")
    return content


def _metadata_bytes(metadata: ArticleMetadata) -> bytes:
    """Encode client metadata and reject unencodable text.

    Parameters
    ----------
    metadata : ArticleMetadata
        Metadata supplied by a client.

    Returns
    -------
    bytes
        UTF-8 JSON contents.

    Raises
    ------
    InvalidArticleContentError
        If metadata contains invalid Unicode.
    """
    try:
        return serialize_metadata(metadata)
    except UnicodeEncodeError:
        raise InvalidArticleContentError("Article metadata must be valid UTF-8")


def create_article(article_request: NewArticle) -> StoredArticle:
    """Create separate Markdown and JSON files without replacing articles.

    Parameters
    ----------
    article_request : NewArticle
        Name, Markdown body and optional metadata.

    Returns
    -------
    StoredArticle
        Newly saved article.

    Raises
    ------
    InvalidArticleContentError
        If the name or content is invalid.
    FileExistsError
        If either destination file already exists.
    """
    name = article_request.name.strip()
    if not 1 <= len(name) <= MAX_ARTICLE_NAME_LENGTH:
        raise InvalidArticleContentError("Article name must contain between 1 and 50 characters")
    _validate_content(article_request.content)
    identifier = "_".join(name.split())
    metadata = ArticleMetadata.model_validate(article_request.model_dump())
    serialized_metadata = _metadata_bytes(metadata)
    with storage_lock(paths.root):
        article_path = get_article_path(identifier)
        metadata_path = article_path.with_suffix(".json")
        if article_path.exists() or metadata_path.exists() or metadata_path.is_symlink():
            raise FileExistsError("An article with this identifier already exists")
        write_files({
            article_path: article_request.content.encode("utf-8"),
            metadata_path: serialized_metadata,
        })
    return StoredArticle(identifier, article_request.content, metadata)


def update_article(article_identifier: str, article_update: ArticleUpdate) -> StoredArticle:
    """Update supplied fields and preserve omitted fields.

    Parameters
    ----------
    article_identifier : str
        Identifier of the existing article.
    article_update : ArticleUpdate
        Replacement content and metadata fields, all omittable.

    Returns
    -------
    StoredArticle
        Article after the requested changes.

    Raises
    ------
    ArticleNotFoundError
        If the article is absent.
    InvalidArticleContentError
        If supplied content or metadata cannot be saved.

    Notes
    -----
    Empty metadata clears a field. Legacy JSON headers are migrated to
    companion files on update. Metadata-only edits keep the Markdown
    file unchanged unless it contains a legacy header.
    """
    with storage_lock(paths.root):
        current = _read_article(article_identifier)
        supplied = article_update.model_dump(exclude_unset=True)
        source = current.source
        if "content" in supplied:
            source = _validate_content(article_update.content)
        metadata_values = current.metadata.model_dump()
        metadata_values.update({key: value for key, value in supplied.items() if key != "content"})
        metadata = ArticleMetadata.model_validate(metadata_values)
        serialized_metadata = _metadata_bytes(metadata)
        article_path = get_article_path(article_identifier)
        changes = {}
        if "content" in supplied or current.has_legacy_header:
            changes[article_path] = source.encode("utf-8")
        if any(key != "content" for key in supplied) or current.has_legacy_header:
            changes[article_path.with_suffix(".json")] = serialized_metadata
        write_files(changes)
        return StoredArticle(article_identifier, source, metadata)
