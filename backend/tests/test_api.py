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

    def test_identifier_and_path_validation(self):
        """Reject unsafe identifiers and symbolic links."""
        self.assertEqual(self.client.get('/article/a..b').status_code, 400)
        self.assertEqual(self.client.get('/article/a%00b').status_code, 400)
        target = self.root / 'private.md'
        target.write_text('Private')
        (self.articles / 'Linked.md').symlink_to(target)
        self.assertEqual(self.client.get('/article/Linked').status_code, 400)

    def test_response_model(self):
        """Describe source and HTML in the API response model."""
        fields = self.client.get('/openapi.json').json()['components']['schemas']['Article']['properties']
        self.assertTrue({'name', 'articleUrl', 'source', 'content'} <= set(fields))

    def test_configurable_storage(self):
        """Resolve storage from the environment in a fresh process."""
        environment = dict(os.environ, WIKI_CONTENT_DIR=str(self.root))
        result = subprocess.run([sys.executable, '-B', '-c', 'from config import paths; print(paths.articles)'], cwd=Path(__file__).resolve().parents[1], env=environment, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), str(self.articles.resolve()))


if __name__ == '__main__':
    unittest.main()
