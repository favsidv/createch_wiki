"""Define application exceptions without any HTTP dependency."""

class InvalidArticleIdentifierError(ValueError):
    """Indicate that an article identifier is invalid."""

class InvalidArticlePathError(ValueError):
    """Indicate that an article file is outside the allowed location."""

class InvalidArticleExtensionError(InvalidArticlePathError):
    """Indicate that an article does not have the Markdown extension."""

class InvalidArticleContentError(ValueError):
    """Indicate that an article name or Markdown body is invalid."""

class ArticleNotFoundError(FileNotFoundError):
    """Indicate that a requested article is absent from valid storage."""

class InvalidStoredDataError(ValueError):
    """Indicate that stored JSON or a storage file is invalid."""

class InvalidCommentError(ValueError):
    """Indicate that a comment contains invalid text."""