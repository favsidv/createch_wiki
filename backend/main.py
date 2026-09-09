"""Expose the initial FastAPI application."""

from fastapi import FastAPI

app = FastAPI(title="Wiki API")

@app.get("/", response_model=dict[str, str])
def read_api_root() -> dict[str, str]:
    """Return a welcome message without checking storage availability.

    Returns
    -------
    dict of str to str
        API welcome message.
    """
    return {"message": "It works!!!"}
