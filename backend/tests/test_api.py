"""Verify the frontend contract using temporary storage only."""

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

import article
import comments
import main
import storage
from config import StoragePaths
from models import NewComment


class WikiApiTests(unittest.TestCase):
    """Exercise articles, comments and filesystem failure handling."""

    def setUp(self):
        """Build isolated storage and a client for each test."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = StoragePaths(Path(self.directory.name))
        self.paths.articles.mkdir()
        for module in (article, comments):
            replacement = patch.object(module, 'paths', self.paths)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def create(self, **changes):
        """Submit an article with defaults overridden by the test."""
        payload = {'name': 'My article', 'content': '# Title\n\nBody\n'}
        payload.update(changes)
        return self.client.post('/create', json=payload)

    def test_article_round_trip_uses_companion_json(self):
        """Persist Unicode metadata separately and preserve Markdown."""
        created = self.create(author='Léa', tags=['été', 'Python'], category='Programming')
        self.assertEqual(created.status_code, 201, created.text)
        expected = created.json()
        self.assertEqual(expected['articleUrl'], 'My_article')
        self.assertEqual(expected['author'], 'Léa')
        self.assertEqual(expected['tags'], ['été', 'Python'])
        self.assertEqual((self.paths.articles / 'My_article.md').read_text(), expected['source'])
        self.assertEqual(json.loads((self.paths.articles / 'My_article.json').read_text())['author'], 'Léa')
        self.assertEqual(self.client.get('/article/My_article').json(), expected)
        self.assertIn('<h1>Title</h1>', expected['content'])
        self.assertEqual(self.client.get('/list').json(), [{'name': 'My article', 'articleUrl': 'My_article'}])

    def test_omitted_metadata_and_legacy_files(self):
        """Read old files and partial companion metadata with defaults."""
        (self.paths.articles / 'Old.md').write_text('# Old')
        (self.paths.articles / 'Old.json').write_text('{"author":"Alex"}')
        result = self.client.get('/article/Old').json()
        self.assertEqual((result['author'], result['tags'], result['category']), ('Alex', [], ''))
        created = self.create()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['tags'], [])

    def test_empty_existing_article(self):
        """Treat an existing empty file as a valid article."""
        (self.paths.articles / 'Empty.md').write_text('')
        result = self.client.get('/article/Empty')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['source'], '')

    def test_inline_header_migrates_only_when_editing(self):
        """Read the older README format and migrate on an update."""
        path = self.paths.articles / 'Old.md'
        path.write_text('{"author":"Alex","tags":["old"]}\n# Old')
        read = self.client.get('/article/Old')
        self.assertEqual(read.json()['source'], '# Old')
        self.assertFalse(path.with_suffix('.json').exists())
        edited = self.client.post('/article/Old/edit', json={'category': 'History'})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(path.read_text(), '# Old')
        self.assertEqual(edited.json()['author'], 'Alex')
        self.assertTrue(path.with_suffix('.json').exists())

    def test_update_preserves_omitted_fields_and_clears_empty_fields(self):
        """Distinguish absent metadata from explicitly empty values."""
        self.create(author='Alex', tags=['Python'], category='Programming')
        path = self.paths.articles / 'My_article.md'
        timestamp = path.stat().st_mtime_ns
        result = self.client.post('/article/My_article/edit', json={'author': 'Léa'})
        self.assertEqual(result.json()['tags'], ['Python'])
        self.assertEqual(path.stat().st_mtime_ns, timestamp)
        cleared = self.client.post('/article/My_article/edit', json={'author': '', 'tags': [], 'category': ''})
        self.assertEqual((cleared.json()['author'], cleared.json()['tags']), ('', []))
        edited = self.client.post('/article/My_article/edit', json={'content': '# Changed'})
        self.assertEqual(edited.json()['source'], '# Changed')
        self.assertEqual(self.client.get('/article/My_article').json(), edited.json())

    def test_invalid_create_and_edit(self):
        """Reject blank content, wrong types and invalid identifiers."""
        for payload in ({'name': ''}, {'content': '  '}, {'name': '../outside'}, {'name': '/tmp/outside'}, {'content': 'x' * 100001}):
            self.assertEqual(self.create(**payload).status_code, 400)
        self.assertEqual(self.create(tags='Python').status_code, 422)
        self.assertEqual(self.client.post('/create', json={'name': 'Missing'}).status_code, 422)
        self.create()
        for body in ({'content': None}, {'content': '  '}):
            self.assertEqual(self.client.post('/article/My_article/edit', json=body).status_code, 400)
        self.assertEqual(self.client.get('/article/a%00b').status_code, 400)
        self.assertEqual(self.client.get('/article/').status_code, 400)

    def test_duplicate_does_not_overwrite(self):
        """Return conflict and preserve both existing files."""
        self.create(author='Original')
        self.assertEqual(self.create(author='Replacement').status_code, 409)
        self.assertEqual(self.client.get('/article/My_article').json()['author'], 'Original')

    def test_missing_article_and_missing_storage_are_distinct(self):
        """Return 404 for a missing article and 500 for missing storage."""
        self.assertEqual(self.client.get('/article/Missing').status_code, 404)
        self.assertEqual(self.client.post('/article/Missing/edit', json={}).status_code, 404)
        self.assertEqual(self.client.get('/article/Missing/delete').status_code, 404)
        self.paths.articles.rmdir()
        self.assertEqual(self.client.get('/article/Missing').status_code, 500)
        self.assertEqual(self.client.get('/list').status_code, 500)

    def test_delete_moves_both_files_and_replaces_trash(self):
        """Move the pair into trash and replace a previous deleted copy."""
        self.create(author='Alex')
        self.paths.trash.mkdir()
        (self.paths.trash / 'My_article.md').write_text('Previous')
        (self.paths.trash / 'My_article.json').write_text('{}')
        result = self.client.get('/article/My_article/delete')
        self.assertEqual(result.json(), {'deleted': True})
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/list').json(), [])
        self.assertFalse((self.paths.articles / 'My_article.json').exists())
        self.assertIn('# Title', (self.paths.trash / 'My_article.md').read_text())
        self.assertEqual(json.loads((self.paths.trash / 'My_article.json').read_text())['author'], 'Alex')

    def test_delete_without_metadata_removes_stale_trash_metadata(self):
        """Avoid associating old metadata with a newly trashed article."""
        (self.paths.articles / 'Old.md').write_text('# Old')
        self.paths.trash.mkdir()
        (self.paths.trash / 'Old.json').write_text('{"author":"Unrelated"}')
        self.assertEqual(self.client.get('/article/Old/delete').status_code, 200)
        self.assertFalse((self.paths.trash / 'Old.json').exists())

    def test_malformed_metadata_is_not_overwritten(self):
        """Reject corrupt JSON and valid JSON with invalid field types."""
        self.create()
        metadata_path = self.paths.articles / 'My_article.json'
        for source in ('{broken', '[]', '{"tags":42}', '{"author":null}'):
            metadata_path.write_text(source)
            self.assertEqual(self.client.get('/article/My_article').status_code, 500)
            self.assertEqual(self.client.post('/article/My_article/edit', json={'author': 'New'}).status_code, 500)
            self.assertEqual(metadata_path.read_text(), source)

    def test_symlinks_are_not_followed(self):
        """Reject linked article and metadata files."""
        outside = self.paths.root / 'outside.md'
        outside.write_text('Private')
        (self.paths.articles / 'Linked.md').symlink_to(outside)
        self.assertEqual(self.client.get('/article/Linked').status_code, 400)
        self.assertEqual(self.client.get('/list').json(), [])
        self.create()
        metadata = self.paths.articles / 'My_article.json'
        metadata.unlink()
        metadata.symlink_to(outside)
        self.assertEqual(self.client.get('/article/My_article').status_code, 500)
        self.assertEqual(outside.read_text(), 'Private')

    def test_list_excludes_non_articles(self):
        """Exclude JSON, images, directories, unsafe names and links."""
        (self.paths.articles / 'b.md').write_text('# B')
        (self.paths.articles / 'A.md').write_text('# A')
        (self.paths.articles / 'Photo.jpg').write_bytes(b'')
        (self.paths.articles / 'folder.md').mkdir()
        (self.paths.articles / 'bad..name.md').write_text('Bad')
        self.assertEqual([entry['articleUrl'] for entry in self.client.get('/list').json()], ['A', 'b'])

    def test_comment_persistence_order_and_anonymous_author(self):
        """Persist comments and read them from a fresh Python process."""
        self.assertEqual(self.client.get('/comments').json(), [])
        first = self.client.post('/comments', json={'content': 'Hello', 'author': None})
        second = self.client.post('/comments', json={'content': '<b>Plain text</b>', 'author': 'Léa'})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()['author'], '')
        self.assertNotEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.client.get('/comments').json(), [first.json(), second.json()])
        environment = dict(os.environ, WIKI_CONTENT_DIR=str(self.paths.root))
        result = subprocess.run(
            [sys.executable, '-B', '-c', 'import comments; print(len(comments.list_comments()))'],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), '2')

    def test_comment_validation_and_corruption(self):
        """Reject blank comments and never replace corrupt storage."""
        self.assertEqual(self.client.post('/comments', json={'content': '  '}).status_code, 400)
        self.assertEqual(self.client.post('/comments', json={}).status_code, 422)
        self.paths.comments.write_text('{broken')
        self.assertEqual(self.client.get('/comments').status_code, 500)
        self.assertEqual(self.client.post('/comments', json={'content': 'Hi'}).status_code, 500)
        self.assertEqual(self.paths.comments.read_text(), '{broken')

    def test_concurrent_comments_are_not_lost(self):
        """Keep every concurrent comment and generate distinct IDs."""
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda index: comments.create_comment(NewComment(content=str(index))), range(20)))
        self.assertEqual(len(comments.list_comments()), 20)
        self.assertEqual(len({entry.id for entry in results}), 20)

    def test_concurrent_article_creation_has_one_winner(self):
        """Prevent concurrent creates from overwriting the same article."""
        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(lambda _: self.create().status_code, range(4)))
        self.assertEqual(sorted(statuses), [201, 409, 409, 409])

    def test_failed_pair_write_rolls_back(self):
        """Restore the original Markdown if metadata replacement fails."""
        self.create(author='Original')
        original = self.client.get('/article/My_article').json()
        replace = storage._replace_file
        failed = False
        def fail_metadata_once(path, content):
            nonlocal failed
            if path.suffix == '.json' and not failed:
                failed = True
                raise PermissionError('Simulated failure')
            replace(path, content)
        with patch.object(storage, '_replace_file', side_effect=fail_metadata_once):
            response = self.client.post('/article/My_article/edit', json={'content': '# Replaced', 'author': 'New'})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get('/article/My_article').json(), original)

    def test_raw_html_and_dangerous_links(self):
        """Escape raw HTML and reject executable Markdown link targets."""
        result = self.create(content='<script>alert(1)</script>\n\n[link](javascript:alert(1))').json()
        self.assertNotIn('<script>', result['content'])
        self.assertNotIn('href="javascript:', result['content'])
        self.assertIn('<script>', result['source'])

    def test_cors_and_openapi(self):
        """Expose frontend routes and support local-file browser origins."""
        response = self.client.options('/create', headers={
            'Origin': 'null', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['access-control-allow-origin'], '*')
        schema = self.client.get('/openapi.json').json()
        for route in ('/list', '/create', '/comments', '/article/{article_identifier}/edit', '/article/{article_identifier}/delete'):
            self.assertIn(route, schema['paths'])
        self.assertEqual(set(schema['components']['schemas']['NewArticle']['required']), {'name', 'content'})


if __name__ == '__main__':
    unittest.main()
