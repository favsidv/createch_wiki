"""Define the article request and response contracts."""

from pydantic import BaseModel, Field

class ArticleBase(BaseModel):
    """Define the display name and URL identifier shared by articles."""

    name: str
    articleUrl: str





class Article(ArticleBase):
    """Return rendered HTML and the original Markdown body."""

    content: str = Field(description="Article content rendered as HTML")
    source: str = Field(description="Original Markdown content")

class ErrorResponse(BaseModel):
    """Describe an application error returned by the HTTP layer."""

    detail: str
