"""Define the article request and response contracts."""

from pydantic import BaseModel, Field, ConfigDict

class ArticleBase(BaseModel):
    """Define the display name and URL identifier shared by articles."""

    name: str
    articleUrl: str


class ArticleInfo(ArticleBase):
    """Define list information independently of the detailed article."""



class Article(ArticleBase):
    """Return rendered HTML and the original Markdown body."""

    content: str = Field(description="Article content rendered as HTML")
    source: str = Field(description="Original Markdown content")


class NewArticle(BaseModel):
    """Receive a display name and Markdown body for creation."""

    model_config = ConfigDict(strict=True)

    name: str
    content: str = Field(description="Article content written in Markdown")

class ErrorResponse(BaseModel):
    """Describe an application error returned by the HTTP layer."""

    detail: str
