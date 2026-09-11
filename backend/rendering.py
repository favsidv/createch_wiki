"""Convert stored article data into frontend response models."""

import markdown2

from article import StoredArticle
from models import Article

def build_article_response(article: StoredArticle) -> Article:
    """Render the Markdown body and attach already validated metadata.

    Parameters
    ----------
    article : StoredArticle
        Article loaded or saved by the storage layer.

    Returns
    -------
    Article
        Frontend response containing HTML and the original Markdown.

    Notes
    -----
    Raw HTML is escaped rather than executed by the frontend.
    Metadata is never passed to the Markdown renderer.
    """
    return Article(
        name=article.identifier.replace("_", " "),
        articleUrl=article.identifier,
        content=markdown2.markdown(article.source, safe_mode="escape"),
        source=article.source,
        **article.metadata.model_dump(),
    )