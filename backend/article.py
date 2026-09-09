"""Validate and store Markdown articles independently of HTTP."""

from dataclasses import dataclass
from pathlib import Path
from config import paths
from exceptions import ArticleNotFoundError, InvalidArticleExtensionError, InvalidArticleIdentifierError, InvalidArticlePathError
from storage import require_directory, validate_storage_file

@dataclass(frozen=True)
class StoredArticle:
    """Keep an article identifier and its original Markdown body."""

    identifier: str
    source: str

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
    """Read an article from its validated filesystem path.

    Parameters
    ----------
    article_identifier : str
        Identifier of the requested article.

    Returns
    -------
    StoredArticle
        Markdown without HTML rendering.

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
    return StoredArticle(article_identifier, source)


def read_article(article_identifier: str) -> StoredArticle:
    """Read an article from Markdown storage.

    Parameters
    ----------
    article_identifier : str
        Identifier of the requested article.

    Returns
    -------
    StoredArticle
        Article content.

    Raises
    ------
    ArticleNotFoundError
        If the article does not exist.
    """
    return _read_article(article_identifier)
