"""Read Markdown articles through a minimal FastAPI endpoint."""

import os
from pathlib import Path

import markdown2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ARTICLES_DIR = Path(os.environ.get(
    "WIKI_CONTENT_DIR", Path(__file__).resolve().parent.parent / "content"
)).resolve() / "articles"


class Article(BaseModel):
    """Return a display name, identifier, rendered HTML and Markdown."""

    name: str
    articleUrl: str
    content: str
    source: str


app = FastAPI(title="Wiki API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


@app.get("/article/{article_identifier}", response_model=Article)
def read_article(article_identifier: str) -> Article:
    """Read a Markdown file and return its content.

    Parameters
    ----------
    article_identifier : str
        Article filename without its Markdown extension.

    Returns
    -------
    Article
        Article identifier, HTML and original Markdown.

    Raises
    ------
    HTTPException
        If the identifier is unsafe, the article is absent, or storage
        cannot be read.
    """
    try:
        if not ARTICLES_DIR.is_dir():
            raise HTTPException(status_code=500, detail="Article storage is unavailable")
        article_path = ARTICLES_DIR / f"{article_identifier}.md"
        markdown_source = article_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    except (PermissionError, NotADirectoryError, IsADirectoryError, UnicodeError):
        raise HTTPException(status_code=500, detail="Article storage is unavailable")
    return Article(
        name=article_identifier.replace("_", " "), articleUrl=article_identifier,
        content=markdown2.markdown(markdown_source, safe_mode="escape"),
        source=markdown_source,
    )

@app.get("/", response_model=dict[str, str])
def read_api_root() -> dict[str, str]:
    """Return a welcome message without checking storage availability.

    Returns
    -------
    dict of str to str
        API welcome message.
    """
    return {"message": "It works!!!"}
