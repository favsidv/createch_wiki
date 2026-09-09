"""Verify the backend features implemented at this stage."""

import json
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import main

class WikiTests(unittest.TestCase):
    """Check HTTP contracts against isolated temporary storage."""

    def setUp(self):
        """Initialize a private article directory and HTTP client."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.articles = self.root / 'articles'
        self.articles.mkdir()
        replacement = patch.object(main, 'ARTICLES_DIR', self.articles)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def create(self, **changes):
        """Create an article with optional test-specific fields."""
        payload = {'name': 'My article', 'content': '# Title\n\nBody\n'}
        payload.update(changes)
        return self.client.post('/create', json=payload)

    def test_root(self):
        """Return the API welcome message."""
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_article_reading(self):
        """Read existing files and distinguish empty from absent content."""
        (self.articles / 'Example.md').write_text('# Example')
        result = self.client.get('/article/Example')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['source'], '# Example')
        (self.articles / 'Empty.md').write_text('')
        self.assertEqual(self.client.get('/article/Empty').json()['source'], '')
        self.assertEqual(self.client.get('/article/Missing').status_code, 404)

    def test_html_rendering(self):
        """Render Markdown while preserving the original source."""
        (self.articles / 'Example.md').write_text('# Example')
        result = self.client.get('/article/Example').json()
        self.assertIn('<h1>Example</h1>', result['content'])
        self.assertEqual(result['source'], '# Example')


if __name__ == '__main__':
    unittest.main()
