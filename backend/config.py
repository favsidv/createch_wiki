"""Define storage locations independently of the working directory."""

import os
from dataclasses import dataclass
from pathlib import Path

MAX_ARTICLE_NAME_LENGTH = 50
MAX_ARTICLE_CONTENT_LENGTH = 100_000


@dataclass(frozen=True)
class StoragePaths:
    """Group the directories and files used by the wiki.

    Parameters
    ----------
    root : pathlib.Path
        Directory containing articles, comments and trash.
    """

    root: Path

    @property
    def articles(self) -> Path:
        """Return the directory containing active articles."""
        return self.root / "articles"

    @property
    def trash(self) -> Path:
        """Return the directory containing deleted articles."""
        return self.root / "trash"


paths = StoragePaths(
    Path(os.environ.get(
        "WIKI_CONTENT_DIR",
        Path(__file__).resolve().parent.parent / "content",
    )).resolve()
)
