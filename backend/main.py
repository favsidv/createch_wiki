from collections.abc import Iterator
from contextlib import contextmanager
from typing import Never

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

import article
import comments
from exceptions import (
    ArticleNotFoundError,
    InvalidArticleContentError,
    InvalidArticleIdentifierError,
    InvalidArticlePathError,
    InvalidCommentError,
    InvalidStoredDataError,
)
from models import (
    Article,
    ArticleInfo,
    ArticleUpdate,
    Comment,
    DeleteResult,
    ErrorResponse,
    NewArticle,
    NewComment,
)
from rendering import build_article_response

app = FastAPI(title="Wiki API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid article or comment data"},
    404: {"model": ErrorResponse, "description": "Article not found"},
    409: {"model": ErrorResponse, "description": "Article already exists"},
    500: {"model": ErrorResponse, "description": "Storage is unavailable or invalid"},
}

def _build_storage_exception() -> HTTPException:
    """Build a public exception for a storage failure.

    Returns
    -------
    HTTPException
        HTTP 500 exception

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
        If validation fails, an article is missing or already exists, or a storage operation fails.

    Notes
    -----
    Storage functions contain no FastAPI imports. This boundary keeps HTTP decisions in main.py and shares the same mapping across routes.  Just to be clear, AI MADE THAT. Didn't know about @contentmanager
    """
    try:
        yield
    except InvalidArticleIdentifierError:
        raise HTTPException(status_code=400, detail="Invalid article identifier")
    except InvalidArticlePathError:
        raise HTTPException(status_code=400, detail="Invalid article path")
    except InvalidArticleContentError:
        raise HTTPException(status_code=400, detail="Invalid article name, content or metadata")
    except InvalidCommentError:
        raise HTTPException(status_code=400, detail="Invalid comment content or author")
    except ArticleNotFoundError:
        raise HTTPException(status_code=404, detail="Article not found")
    except FileExistsError:
        raise HTTPException(status_code=409, detail="An article with this identifier already exists")
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

@app.get("/list", response_model=list[ArticleInfo], responses={500: ERROR_RESPONSES[500]})
def list_articles() -> list[ArticleInfo]:
    """List active articles in alphabetical order.

    Returns
    -------
    list of ArticleInfo
        Display names and identifiers, without content or metadata.

    Raises
    ------
    HTTPException
        If article storage cannot be listed.
    """
    with _translate_storage_exceptions():
        identifiers = article.list_article_identifiers()
    return [ArticleInfo(name=identifier.replace("_", " "), articleUrl=identifier) for identifier in identifiers]

@app.get("/article", response_model=None, include_in_schema=False)
@app.get("/article/", response_model=None, responses={400: ERROR_RESPONSES[400]})
def reject_missing_article_identifier() -> Never:
    """Reject a request that does not specify an article identifier.

    Raises
    ------
    HTTPException
        Always raised with HTTP 400.
    """
    raise HTTPException(status_code=400, detail="An article identifier is required")

@app.get("/article/{article_identifier}", response_model=Article, responses=ERROR_RESPONSES)
def read_article(article_identifier: str) -> Article:
    """Read an article with its metadata and rendered Markdown.

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
        If the identifier is invalid, the article is missing or storage cannot be read.
    """
    with _translate_storage_exceptions():
        stored_article = article.read_article(article_identifier)
        return build_article_response(stored_article)

@app.post("/create", response_model=Article, status_code=201, responses=ERROR_RESPONSES)
def create_article(article_request: NewArticle) -> Article:
    """Create an article and return the resource expected by the frontend.

    Parameters
    ----------
    article_request : NewArticle
        Display name, Markdown body and optional metadata.

    Returns
    -------
    Article
        Created article with its generated URL identifier.

    Raises
    ------
    HTTPException
        If the request is invalid, the identifier already exists or storage cannot be written.
    """
    with _translate_storage_exceptions():
        stored_article = article.create_article(article_request)
        return build_article_response(stored_article)

@app.post("/article/{article_identifier}/edit", response_model=Article, responses=ERROR_RESPONSES)
def update_article(article_identifier: str, article_update: ArticleUpdate) -> Article:
    """Update supplied article fields and preserve omitted values.

    Parameters
    ----------
    article_identifier : str
        Existing article identifier.
    article_update : ArticleUpdate
        Replacement Markdown or metadata fields.

    Returns
    -------
    Article
        Saved article with updated metadata and rendered content.

    Raises
    ------
    HTTPException
        If supplied data is invalid, the article is missing or storage cannot be updated.
    """
    with _translate_storage_exceptions():
        stored_article = article.update_article(article_identifier, article_update)
        return build_article_response(stored_article)

@app.get("/article/{article_identifier}/delete", response_model=DeleteResult, responses=ERROR_RESPONSES)
def delete_article(article_identifier: str, response: Response) -> DeleteResult:
    """Move an article and its metadata to trash.

    Parameters
    ----------
    article_identifier : str
        Existing article identifier.
    response : fastapi.Response
        Response receiving cache-control headers.

    Returns
    -------
    DeleteResult
        Confirmation that the article was removed from active storage.

    Raises
    ------
    HTTPException
        If the article is missing or the move fails.

    Notes
    -----
    GET is retained to match the supplied frontend contract. This route changes state and must not be prefetched or cached by clients.
    """
    with _translate_storage_exceptions():
        article.delete_article(article_identifier)
    response.headers["Cache-Control"] = "no-store"
    return DeleteResult(deleted=True)

@app.get("/comments", response_model=list[Comment], responses={500: ERROR_RESPONSES[500]})
def list_comments() -> list[Comment]:
    """Return site-wide comments from oldest to newest.

    Returns
    -------
    list of Comment
        Stored comments, or an empty list before the first comment.

    Raises
    ------
    HTTPException
        If comment storage is unavailable or invalid.
    """
    with _translate_storage_exceptions():
        return comments.list_comments()

@app.post("/comments", response_model=Comment, status_code=201, responses={
    400: ERROR_RESPONSES[400],
    500: ERROR_RESPONSES[500],
})
def create_comment(comment_request: NewComment) -> Comment:
    """Create a persistent plain-text comment with a unique identifier.

    Parameters
    ----------
    comment_request : NewComment
        Content and optional author supplied by the frontend.

    Returns
    -------
    Comment
        Saved comment with a server-generated UUID.

    Raises
    ------
    HTTPException
        If the comment is invalid or cannot be saved.
    """
    with _translate_storage_exceptions():
        return comments.create_comment(comment_request)

@app.get("/", response_model=dict[str, str])
def read_api_root() -> dict[str, str]:
    """Return a welcome message without checking storage availability.

    Returns
    -------
    dict of str to str
        API welcome message.
    """
    return {"message": "Hi Paul! Glad to have you onboard!"}