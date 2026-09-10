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
import article
from config import StoragePaths
from models import ArticleMetadata

class WikiTests(unittest.TestCase):
    """Check HTTP contracts against isolated temporary storage."""

    def setUp(self):
        """Initialize a private article directory and HTTP client."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.articles = self.root / 'articles'
        self.articles.mkdir()
        self.paths = StoragePaths(self.root)
        for module in (article,):
            replacement = patch.object(module, 'paths', self.paths)
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

    def test_storage_errors_remain_http_independent(self):
        """Raise a Python exception in storage and translate it in HTTP."""
        from exceptions import ArticleNotFoundError
        with self.assertRaises(ArticleNotFoundError):
            article.read_article('Missing')
        self.assertEqual(self.client.get('/article/').status_code, 400)
        self.articles.rmdir()
        self.assertEqual(self.client.get('/article/Missing').status_code, 500)

    def test_renderer_does_not_read_storage(self):
        """Render a stored article object without creating a file."""
        from rendering import build_article_response
        record = article.StoredArticle('Example', '# Example', ArticleMetadata())
        self.assertIn('<h1>Example</h1>', build_article_response(record).content)

    def test_article_listing(self):
        """Sort active Markdown and exclude other filesystem entries."""
        (self.articles / 'b.md').write_text('# B')
        (self.articles / 'A.md').write_text('# A')
        (self.articles / 'image.jpg').write_bytes(b'')
        (self.articles / 'folder.md').mkdir()
        self.assertEqual([item['articleUrl'] for item in self.client.get('/list').json()], ['A', 'b'])

    def test_creation_and_duplicate(self):
        """Create a readable article and reject invalid or duplicate input."""
        result = self.create()
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(self.client.get('/article/My_article').json(), result.json())
        self.assertEqual(self.create().status_code, 409)
        for payload in ({'name': ''}, {'content': '  '}, {'name': '../private'}, {'content': 'x' * 100001}):
            self.assertEqual(self.create(**payload).status_code, 400)
        self.assertEqual(self.client.post('/create', json={}).status_code, 422)

    def test_concurrent_creation(self):
        """Allow one successful creation for a shared article name."""
        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(lambda _: self.create().status_code, range(4)))
        self.assertEqual(sorted(statuses), [201, 409, 409, 409])

    def test_worker_process_coordination(self):
        """Prevent two workers from creating the same article."""
        environment = dict(os.environ, WIKI_CONTENT_DIR=str(self.root))
        program = "from article import create_article; from models import NewArticle; create_article(NewArticle(name='Workers', content='# Worker'))"
        processes = [subprocess.Popen([sys.executable, '-B', '-c', program], cwd=Path(__file__).resolve().parents[1], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
        statuses = []
        for process in processes:
            process.communicate(timeout=20)
            statuses.append(process.returncode)
        self.assertEqual(statuses.count(0), 1)
        self.assertEqual(self.client.get('/article/Workers').status_code, 200)

    def test_atomic_replacement_failure(self):
        """Keep the previous file when replacement cannot complete."""
        import storage
        target = self.articles / 'Existing.md'
        target.write_text('Original')
        with patch.object(Path, 'replace', side_effect=PermissionError('Simulated')):
            with self.assertRaises(PermissionError):
                storage._replace_file(target, b'Changed')
        self.assertEqual(target.read_text(), 'Original')
        self.assertEqual(list(self.articles.glob('.wiki-*')), [])

    def test_companion_metadata_reading(self):
        """Read optional metadata and reject malformed companion JSON."""
        (self.articles / 'Old.md').write_text('# Old')
        result = self.client.get('/article/Old').json()
        self.assertEqual((result['author'], result['tags'], result['category']), ('', [], ''))
        sidecar = self.articles / 'Old.json'
        sidecar.write_text('{"author":"Léa","tags":["Python"]}')
        self.assertEqual(self.client.get('/article/Old').json()['author'], 'Léa')
        sidecar.write_text('{broken')
        self.assertEqual(self.client.get('/article/Old').status_code, 500)

    def test_metadata_creation(self):
        """Store metadata separately and preserve it after reading."""
        result = self.create(author='Léa', tags=['Python'], category='Programming')
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()['author'], 'Léa')
        self.assertEqual(self.client.get('/article/My_article').json(), result.json())
        self.assertEqual((self.articles / 'My_article.md').read_text(), result.json()['source'])
        self.assertEqual(json.loads((self.articles / 'My_article.json').read_text())['tags'], ['Python'])

    def test_body_editing(self):
        """Replace Markdown while preserving the saved metadata."""
        self.create(author='Alex', tags=['Python'])
        result = self.client.post('/article/My_article/edit', json={'content': '# Changed'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['source'], '# Changed')
        self.assertEqual(result.json()['author'], 'Alex')
        self.assertEqual(self.client.get('/article/My_article').json(), result.json())

    def test_partial_metadata_editing(self):
        """Preserve omitted values and clear explicitly empty fields."""
        self.create(author='Alex', tags=['Python'], category='Programming')
        timestamp = (self.articles / 'My_article.md').stat().st_mtime_ns
        result = self.client.post('/article/My_article/edit', json={'author': 'Léa'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['tags'], ['Python'])
        self.assertEqual((self.articles / 'My_article.md').stat().st_mtime_ns, timestamp)
        result = self.client.post('/article/My_article/edit', json={'author': '', 'tags': []})
        self.assertEqual((result.json()['author'], result.json()['tags']), ('', []))
        self.assertEqual(result.json()['category'], 'Programming')

    def test_legacy_header_migration(self):
        """Read inline metadata and migrate it only when editing."""
        path = self.articles / 'Legacy.md'
        path.write_text('{"author":"Alex"}\n# Legacy')
        result = self.client.get('/article/Legacy').json()
        self.assertEqual(result['source'], '# Legacy')
        self.assertEqual(result['author'], 'Alex')
        self.assertFalse(path.with_suffix('.json').exists())
        self.assertEqual(self.client.post('/article/Legacy/edit', json={'tags': ['Old']}).status_code, 200)
        self.assertEqual(path.read_text(), '# Legacy')
        self.assertTrue(path.with_suffix('.json').exists())

    def test_pair_write_rollback(self):
        """Restore the Markdown when the subsequent JSON write fails."""
        import storage
        self.create(author='Original')
        previous = self.client.get('/article/My_article').json()
        replace = storage._replace_file
        failed = False
        def fail_once(path, content):
            nonlocal failed
            if path.suffix == '.json' and not failed:
                failed = True
                raise PermissionError('Simulated')
            replace(path, content)
        with patch.object(storage, '_replace_file', side_effect=fail_once):
            result = self.client.post('/article/My_article/edit', json={'content': '# Changed', 'author': 'New'})
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.client.get('/article/My_article').json(), previous)

    def test_trash_move(self):
        """Remove an article from active storage and preserve its pair."""
        self.create(author='Alex')
        result = self.client.get('/article/My_article/delete')
        self.assertEqual(result.json(), {'deleted': True})
        self.assertEqual(self.client.get('/list').json(), [])
        self.assertTrue((self.root / 'trash/My_article.md').exists())
        self.assertTrue((self.root / 'trash/My_article.json').exists())


if __name__ == '__main__':
    unittest.main()
