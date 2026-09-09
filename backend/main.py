"""Expose article routes and translate storage exceptions into HTTP."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Never
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import article
from exceptions import (ArticleNotFoundError, InvalidArticleIdentifierError, InvalidArticlePathError, InvalidStoredDataError)
from models import (Article, ErrorResponse)
import markdown2

def build_article_response(article: article.StoredArticle) -> Article:
    """Render Markdown and build an article response.

    Parameters
    ----------
    article : article.StoredArticle
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
    )



app = FastAPI(title="Wiki API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid article data"},
    404: {"model": ErrorResponse, "description": "Article not found"},

    500: {"model": ErrorResponse, "description": "Storage is unavailable or invalid"},
}

def _build_storage_exception() -> HTTPException:
    """Build a public exception for a storage failure.

    Returns
    -------
    HTTPException
        HTTP 500 exception without private filesystem details.

    Notes
    -----
    The caller must raise the returned exception.
    """
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Wiki storage is unavailable",
    )


@contextmanager
def _translate_storage_exceptions() -> Iterator[None]:
    """Translate exceptions from an operation into HTTP errors.

    Yields
    ------
    None
        Control to the route while its application operation runs.

    Raises
    ------
    HTTPException
        If validation fails, an article is missing or already exists,
        or a storage operation fails.

    Notes
    -----
    Storage functions contain no FastAPI imports. This boundary keeps
    HTTP decisions in main.py and shares the same mapping across routes.
    """
    try:
        yield
    except InvalidArticleIdentifierError:
        raise HTTPException(status_code=400, detail="Invalid article identifier")
    except InvalidArticlePathError:
        raise HTTPException(status_code=400, detail="Invalid article path")
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    except InvalidStoredDataError:
        raise HTTPException(status_code=500, detail="Stored wiki data is invalid")
    except (
        FileNotFoundError,
        NotADirectoryError,
        IsADirectoryError,
        PermissionError,
        UnicodeError,
    ):
        raise _build_storage_exception()




@app.get("/article", response_model=None, include_in_schema=False)
@app.get("/article/", response_model=None, responses={400: _ERROR_RESPONSES[400]})
def reject_missing_article_identifier() -> Never:
    """Reject a request that does not specify an article identifier.

    Raises
    ------
    HTTPException
        Always raised with HTTP 400.
    """
    raise HTTPException(status_code=400, detail="An article identifier is required")


@app.get("/article/{article_identifier}", response_model=Article, responses=_ERROR_RESPONSES)
def read_article(article_identifier: str) -> Article:
    """Read an article with its rendered Markdown.

    Parameters
    ----------
    article_identifier : str
        Article filename without its Markdown extension.

    Returns
    -------
    Article
        Metadata, HTML content and original Markdown body.

    Raises
    ------
    HTTPException
        If the identifier is invalid, the article is missing or storage
        cannot be read.
    """
    with _translate_storage_exceptions():
        stored_article = article.read_article(article_identifier)
        return build_article_response(stored_article)


@app.get("/", response_model=dict[str, str])
def read_api_root() -> dict[str, str]:
    """Return a welcome message without checking storage availability.

    Returns
    -------
    dict of str to str
        API welcome message.
    """
    return {"message": "It works!!!"}
