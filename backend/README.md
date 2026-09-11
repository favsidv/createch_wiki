# [Wiki backend](https://github.com/favsidv/createch_wiki)

This folder contains the backend of a wiki built with FastAPI, Python exceptions, Markdown and JSON storage.

## Running the backend

From this folder (`backend/`), run:

```bash
uv sync
uv run fastapi dev
```

The API listens on `http://127.0.0.1:8000`. Its interactive documentation is available at `/docs`, and its OpenAPI schema at `/openapi.json`.

By default, data is stored in the `content/` folder at the repository root.  Both `content/` and `content/articles/` must exist. The configuration does not depend on the working directory from which the server is started. To use a different storage location, set `WIKI_CONTENT_DIR` to the directory containing the `articles/` folder:

```bash
WIKI_CONTENT_DIR=/absolute/path/to/content uv run fastapi dev
```

The backend creates the trash folder when the first article is deleted. `comments.json` is created when the first comment is posted. Missing content directories are not silently created when an article is read.

## Project structure

| File | Responsibility |
| --- | --- |
| `main.py` | Routes, response models and translation of exceptions into HTTP errors |
| `article.py` | Identifier and path validation, creation, reading, editing and trash operations |
| `metadata.py` | JSON validation and serialization, and reading legacy headers |
| `comments.py` | Validation and persistence of site-wide comments |
| `storage.py` | Locking, file replacement and recovery after failures |
| `models.py` | Pydantic contracts for articles, metadata, updates and comments |
| `exceptions.py` | Application exceptions independent of FastAPI |
| `rendering.py` | Markdown-to-HTML conversion and construction of `Article` responses |
| `config.py` | Storage paths and size limits |
| `tests/test_api.py` | HTTP contract checks using temporary storage |

Validation and storage operations raise Python exceptions. They do not depend on `HTTPException`. `main.py` catches these exceptions through `_translate_storage_exceptions()` and selects the HTTP status. This context manager runs the route's code at the `yield` point and catches any resulting exceptions. Routes therefore share the same HTTP error translation. There is no application logging or explicit exception chaining with `from exc`.

`ArticleInfo` remains separate from `Article` so the list response can evolve  without automatically adding its future fields to detailed responses.

## HTTP contract

| Method | Path | Result |
| --- | --- | --- |
| GET | `/` | Welcome message |
| GET | `/list` | Alphabetical list of active articles |
| GET | `/article/` | `400`: missing identifier |
| GET | `/article/{article_identifier}` | Article, HTML, Markdown and metadata |
| POST | `/create` | Created article, status `201` |
| POST | `/article/{article_identifier}/edit` | Updated article |
| GET | `/article/{article_identifier}/delete` | Move to trash, `{"deleted": true}` |
| GET | `/comments` | Comments from oldest to newest |
| POST | `/comments` | Created comment, status `201` |

The OpenAPI parameter name is `article_identifier`. Actual URLs remain those expected by the frontend, such as `/article/Robotique`. The JSON fields `name`, `articleUrl`, `author`, `tags`, `category`, `content` and `source` are preserved.

Application errors use `{"detail": "..."}`. Type errors and missing required fields detected by FastAPI/Pydantic return status `422` with the native error list in `detail`, which the frontend also handles. A missing article returns `404`, an identifier already in use returns `409`, invalid input returns `400` and missing or corrupt storage returns `500`. Other unexpected system errors are handled by the server; their response body is not guaranteed to be JSON.

## Articles and metadata

The frontend tutorial and README describe two different storage formats. New writes follow `BACKEND_TUTORIALS.md`:

```text
content/
├── articles/
│   ├── My_article.md
│   └── My_article.json
├── comments.json
├── .wiki.lock
└── trash/
```

The Markdown file contains only the article body. The JSON file contains an object:

```json
{
  "author": "Léa",
  "tags": ["Python", "Web"],
  "category": "Programming"
}
```

Omitted metadata fields default to `""` for the author, `[]` for tags and `""` for the category. Articles without a JSON file remain readable. An existing but invalid JSON file causes an error rather than hiding the problem or overwriting its data.

For compatibility with the README and older articles, a recognizable JSON object on the first line of the Markdown file is still supported. A companion
JSON file takes precedence. Reads do not modify files; an edit migrates a legacy header into the companion file.

Creation accepts a name of 1 to 50 characters after trimming surrounding whitespace, a non-blank Markdown body of up to 100,000 characters and optional
metadata. Whitespace in the name becomes underscores in the identifier. A collision with an existing Markdown or JSON file returns `409`; creation never replaces an existing article.

An edit may contain only the author, category or tags. `model_dump(exclude_unset=True)` preserves omitted fields. An empty value clears the metadata field; `null` is not accepted for article metadata. Markdown content may be omitted, but cannot be replaced with `null` or whitespace-only text. Metadata-only edits do not rewrite the Markdown file, except when migrating a legacy header.

Older names containing spaces remain accessible through their actual identifiers. The frontend should reuse `articleUrl` rather than reconstructing the identifier from the display name.

## Comments

Comments belong to the entire site. Their content remains plain text, even when it contains HTML characters. The frontend must display it as text. A missing, empty or `null` author is stored as an empty string. Content must not be blank and is limited to 10,000 characters.

Each comment receives a server-generated UUID. The JSON file preserves insertion order across restarts. A corrupt file is never replaced with an empty list.

## Trash

Deletion logically moves the Markdown file and its optional JSON file to `content/trash/`, replacing any previous copy with the same name as specified by the tutorial. The backend writes the destination copies, then removes the source files, restoring changes if a handled failure occurs. This is not permanent deletion.

`GET .../delete` is retained for frontend compatibility. Since this operation changes state, a future contract should use `DELETE` with appropriate access controls. The current response includes `Cache-Control: no-store`; this does not prevent a client from prefetching the request.

## *(The following is made entirely by AI, both README and the codes. This in order to be most effective and to speed tests)*
## Storage and deployment limitations

Locking combines `RLock` and `fcntl.flock` on macOS and Linux. All operations in this backend are coordinated across threads and processes using the same
directory. This utility does not support Windows. The lock is global: it prioritizes consistency over throughput and does not protect against external tools that ignore it.

Each file is written to a temporary file, synchronized and then moved into place. If an operation affecting multiple files fails, completed changes are
restored when storage conditions allow it. However, an abrupt interruption between replacements can leave a Markdown/JSON pair inconsistent: this is not
a durable transaction. A database would be preferable for high concurrency or transactional guarantees.

Storage must be managed by trusted users. Symbolic links and special files are rejected for data files, but these checks are not a complete defense against a malicious local process modifying paths concurrently.

Rendering uses markdown2's HTML-escaping mode. The original Markdown remains intact; raw HTML is not executed. This setting deliberately changes how older articles containing raw HTML are rendered.

The API is intended for a local workshop: it has no authentication, and CORS allows all origins so the frontend can be opened directly. Before exposing it publicly, add access controls and configure the allowed origins.

## Tests

From `backend/`, using the project environment:

```bash
uv run python -B -m unittest discover -s tests -v
```

Tests use temporary directories. They cover the creation, reading, editing and trash workflow; compatibility with older articles; invalid JSON; omitted
and cleared values; duplicates; comment persistence in a fresh process; concurrent access; symbolic links; HTTP responses; and recovery after a write failure.
