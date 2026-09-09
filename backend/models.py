"""Define the article response contract."""

from pydantic import BaseModel

class Article(BaseModel):
    """Return a display name, identifier, rendered HTML and Markdown."""

    name: str
    articleUrl: str
    content: str
    source: str
