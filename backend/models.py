"""Define the article request and response contracts."""

from pydantic import BaseModel, Field, ConfigDict

class ArticleBase(BaseModel):
    """Define the display name and URL identifier shared by articles."""

    name: str
    articleUrl: str


class ArticleInfo(ArticleBase):
    """Define list information independently of the detailed article."""


class ArticleMetadata(BaseModel):
    """Define optional metadata with empty values when fields are omitted."""

    model_config = ConfigDict(strict=True)

    author: str = Field(default="", description="Name of the author", examples=["Léa"])
    tags: list[str] = Field(
        default_factory=list,
        description="Keywords describing the article",
        examples=[["Python", "Web"]],
    )
    category: str = Field(default="", description="Article category", examples=["Programming"])


class Article(ArticleBase, ArticleMetadata):
    """Return metadata, rendered HTML and the original Markdown body."""

    content: str = Field(description="Article content rendered as HTML")
    source: str = Field(description="Original Markdown without metadata")


class NewArticle(ArticleMetadata):
    """Receive a name, Markdown body and optional metadata for creation."""

    name: str
    content: str = Field(description="Article content written in Markdown")


class ArticleUpdate(BaseModel):
    """Receive required replacement Markdown for an existing article."""

    model_config = ConfigDict(strict=True)
    content: str


class ErrorResponse(BaseModel):
    """Describe an application error returned by the HTTP layer."""

    detail: str
