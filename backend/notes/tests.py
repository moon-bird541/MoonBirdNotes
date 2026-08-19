import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from MoonBirdNotes.media import ProtectedMediaView
from rag.models import RagIndexDeletionJob

from .models import DiaryEntry, Note, NoteImage, Tag
from .serializers import (
    DiaryEntryCreateSerializer,
    MAX_MARKDOWN_UPLOAD_SIZE,
    NoteUploadSerializer,
    get_or_create_tags,
    render_markdown_content,
)
from .views import (
    GlobalSearchView,
    NoteBatchDeleteView,
    NoteBatchExportView,
    NoteBatchTagsView,
    NoteExportView,
    NoteImageDestroyView,
    NoteImageListCreateView,
    NoteImageOrphanCleanupView,
    NoteImportanceView,
    NoteListView,
    NoteSummaryView,
    NotePinView,
    TagDetailView,
    TagListView,
    TagMergeView,
    TrashNoteBatchDestroyView,
    TrashNoteBatchRestoreView,
)


class MarkdownRenderSecurityTests(SimpleTestCase):
    def test_render_markdown_content_removes_xss_payloads(self):
        html = render_markdown_content(
            """
# 测试 XSS

正常内容和 **加粗** 内容。

<script>alert('xss')</script>
<img src="https://example.com/a.png" onerror="alert('xss')">
<a href="javascript:alert('xss')">危险链接</a>
```python
print("safe")
```
"""
        )

        self.assertIn('<strong>加粗</strong>', html)
        self.assertIn('<img src="https://example.com/a.png">', html)
        self.assertIn('class="language-python"', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('onerror', html)
        self.assertNotIn('javascript:', html)

    def test_render_markdown_content_keeps_heading_ids_for_toc_links(self):
        html = render_markdown_content(
            """
[TOC]

# 目录标题

## 第二节
"""
        )

        self.assertRegex(html, r'<h1 id="[^"]+">目录标题</h1>')
        self.assertRegex(html, r'<h2 id="[^"]+">第二节</h2>')
        self.assertRegex(html, r'<a href="#[^"]+">目录标题</a>')
        self.assertRegex(html, r'<a href="#[^"]+">第二节</a>')

    def test_render_markdown_content_adds_rel_to_blank_target_links(self):
        html = render_markdown_content(
            '<a href="https://example.com" target="_blank">外部链接</a>'
        )

        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_render_markdown_content_preserves_existing_rel_values(self):
        html = render_markdown_content(
            '<a href="https://example.com" target="_blank" rel="nofollow">外部链接</a>'
        )

        self.assertIn('rel="nofollow noopener noreferrer"', html)


class NoteUploadSerializerSecurityTests(SimpleTestCase):
    def _serializer_for_file_size(self, size):
        uploaded_file = SimpleUploadedFile(
            'safe.md',
            b'a' * size,
            content_type='text/markdown',
        )
        return NoteUploadSerializer(data={
            'file': uploaded_file,
            'tag_names': ['安全测试'],
        })

    def test_markdown_file_allows_10_mb_upload(self):
        serializer = self._serializer_for_file_size(MAX_MARKDOWN_UPLOAD_SIZE)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_markdown_file_rejects_upload_over_10_mb(self):
        serializer = self._serializer_for_file_size(MAX_MARKDOWN_UPLOAD_SIZE + 1)

        self.assertFalse(serializer.is_valid())
        self.assertIn('文件大小不能超过 10 MB', str(serializer.errors['file'][0]))


class TagLookupHelperTests(TestCase):
    def test_get_or_create_tags_reuses_existing_and_creates_missing_tags(self):
        existing_tag = Tag.objects.create(name='已有标签')

        tags = get_or_create_tags(['新标签', '已有标签'])

        self.assertEqual([tag.name for tag in tags], ['新标签', '已有标签'])
        self.assertEqual(Tag.objects.count(), 2)
        self.assertEqual(tags[1].pk, existing_tag.pk)


class ProtectedMediaAccessTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.client = APIClient()
        self.factory = APIRequestFactory()
        self.admin_user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.regular_user = get_user_model().objects.create_user(
            username='writer',
            password='password',
        )
        self.media_file = Path(self.media_root) / 'note_images' / 'private.txt'
        self.media_file.parent.mkdir(parents=True, exist_ok=True)
        self.media_file.write_text('private media', encoding='utf-8')

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def test_anonymous_user_cannot_read_media_file(self):
        response = self.client.get('/media/note_images/private.txt')

        self.assertEqual(response.status_code, 401)

    def test_authenticated_non_admin_user_cannot_read_media_file(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get('/media/note_images/private.txt')

        self.assertEqual(response.status_code, 403)

    def test_admin_user_can_read_media_file(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get('/media/note_images/private.txt')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'private media')

    def test_rejects_paths_outside_media_root(self):
        request = self.factory.get('/media/../secret.txt')
        force_authenticate(request, user=self.admin_user)
        response = ProtectedMediaView.as_view()(request, path='../secret.txt')

        self.assertEqual(response.status_code, 404)


class NoteImageApiTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.note = Note.objects.create(
            title='图片笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.diary_note = Note.objects.create(
            title='图片日记',
            markdown_content='日记正文',
            rendered_html='<p>日记正文</p>',
        )
        self.diary_entry = DiaryEntry.objects.create(
            note=self.diary_note,
            diary_date=date(2026, 7, 1),
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def _authenticated_request(self, method, path, data=None, format='json'):
        request = getattr(self.factory, method)(path, data or {}, format=format)
        force_authenticate(request, user=self.user)
        return request

    @staticmethod
    def _png_file(name='image.png'):
        return SimpleUploadedFile(
            name,
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 16,
            content_type='image/png',
        )

    def test_uploads_note_image(self):
        request = self._authenticated_request(
            'post',
            '/api/notes/images/',
            {
                'note_id': self.note.id,
                'image': self._png_file(),
                'alt_text': '截图',
            },
            format='multipart',
        )
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(NoteImage.objects.count(), 1)
        image = NoteImage.objects.get()
        self.assertEqual(image.note, self.note)
        self.assertEqual(image.original_filename, 'image.png')
        self.assertEqual(response.data['note']['title'], '图片笔记')
        self.assertEqual(response.data['note']['type'], 'note')
        self.assertIn('/media/note_images/', response.data['image_url'])

    def test_uploads_diary_image_to_date_directory(self):
        request = self._authenticated_request(
            'post',
            '/api/notes/images/',
            {
                'note_id': self.diary_note.id,
                'image': self._png_file('diary.png'),
                'alt_text': '日记图片',
            },
            format='multipart',
        )
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 201)
        image = NoteImage.objects.get(original_filename='diary.png')
        self.assertEqual(image.note, self.diary_note)
        self.assertIn('/media/diary_images/2026-07-01/', response.data['image_url'])
        self.assertEqual(response.data['note']['type'], 'diary')
        self.assertEqual(response.data['note']['diary_date'], '2026-07-01')

    def test_rejects_non_image_upload(self):
        request = self._authenticated_request(
            'post',
            '/api/notes/images/',
            {
                'note_id': self.note.id,
                'image': SimpleUploadedFile('readme.txt', b'hello', content_type='text/plain'),
            },
            format='multipart',
        )
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('只允许上传 PNG、JPEG、GIF 或 WebP 图片。', str(response.data['image'][0]))

    def test_lists_uploaded_images(self):
        NoteImage.objects.create(
            note=self.note,
            image=self._png_file('listed.png'),
            original_filename='listed.png',
            alt_text='列表图片',
            file_size=24,
            content_type='image/png',
        )
        NoteImage.objects.create(
            note=self.diary_note,
            image=self._png_file('diary-listed.png'),
            original_filename='diary-listed.png',
            alt_text='日记列表图片',
            file_size=24,
            content_type='image/png',
        )
        request = self._authenticated_request('get', '/api/notes/images/')
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['stats']['image_count'], 2)
        self.assertEqual(response.data['stats']['content_count'], 2)
        self.assertEqual(response.data['stats']['total_size'], 48)
        groups_by_key = {group['key']: group for group in response.data['groups']}
        self.assertEqual(groups_by_key[f'content:{self.note.id}']['type'], 'note')
        self.assertEqual(groups_by_key[f'content:{self.note.id}']['image_count'], 1)
        self.assertEqual(groups_by_key[f'content:{self.note.id}']['total_size'], 24)
        self.assertEqual(groups_by_key[f'content:{self.diary_note.id}']['type'], 'diary')
        self.assertEqual(groups_by_key[f'content:{self.diary_note.id}']['diary_date'], '2026-07-01')
        images_by_name = {image['original_filename']: image for image in response.data['results']}
        self.assertEqual(images_by_name['listed.png']['note']['type'], 'note')
        self.assertEqual(images_by_name['diary-listed.png']['note']['type'], 'diary')
        self.assertEqual(images_by_name['diary-listed.png']['note']['diary_date'], '2026-07-01')

    def test_paginates_uploaded_images(self):
        for index in range(13):
            NoteImage.objects.create(
                note=self.note,
                image=self._png_file(f'page-{index}.png'),
                original_filename=f'page-{index}.png',
                alt_text=f'分页图片 {index}',
                file_size=24,
                content_type='image/png',
            )

        request = self._authenticated_request('get', '/api/notes/images/?page=2&page_size=5')
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 13)
        self.assertEqual(len(response.data['results']), 5)
        self.assertEqual(response.data['stats']['image_count'], 13)
        self.assertEqual(response.data['stats']['content_count'], 1)
        self.assertEqual(response.data['stats']['total_size'], 312)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNotNone(response.data['previous'])

    def test_filters_uploaded_images_before_paginating(self):
        NoteImage.objects.create(
            note=self.note,
            image=self._png_file('note-match.png'),
            original_filename='note-match.png',
            alt_text='普通图片',
            file_size=24,
            content_type='image/png',
        )
        NoteImage.objects.create(
            note=self.diary_note,
            image=self._png_file('diary-match.png'),
            original_filename='diary-match.png',
            alt_text='日记图片',
            file_size=24,
            content_type='image/png',
        )

        request = self._authenticated_request(
            'get',
            f'/api/notes/images/?note_id={self.diary_note.id}&search=日记',
        )
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['stats']['image_count'], 1)
        self.assertEqual(response.data['stats']['content_count'], 1)
        self.assertEqual(response.data['stats']['total_size'], 24)
        self.assertEqual(response.data['results'][0]['original_filename'], 'diary-match.png')

    def test_filters_uploaded_images_by_scope(self):
        NoteImage.objects.create(
            note=self.note,
            image=self._png_file('note-scope.png'),
            original_filename='note-scope.png',
            file_size=24,
            content_type='image/png',
        )
        NoteImage.objects.create(
            note=self.diary_note,
            image=self._png_file('diary-scope.png'),
            original_filename='diary-scope.png',
            file_size=32,
            content_type='image/png',
        )

        request = self._authenticated_request('get', '/api/notes/images/?scope=diary')
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['stats']['total_size'], 32)
        self.assertEqual(response.data['results'][0]['original_filename'], 'diary-scope.png')
        self.assertEqual(response.data['groups'][0]['type'], 'diary')

    def test_groups_diary_images_by_diary_date(self):
        second_diary_note = Note.objects.create(
            title='第二篇日记',
            markdown_content='日记正文',
            rendered_html='<p>日记正文</p>',
        )
        DiaryEntry.objects.create(note=second_diary_note, diary_date=date(2026, 7, 2))
        NoteImage.objects.create(
            note=self.diary_note,
            image=self._png_file('diary-date-a.png'),
            original_filename='diary-date-a.png',
            file_size=24,
            content_type='image/png',
        )
        NoteImage.objects.create(
            note=self.diary_note,
            image=self._png_file('diary-date-b.png'),
            original_filename='diary-date-b.png',
            file_size=26,
            content_type='image/png',
        )
        NoteImage.objects.create(
            note=second_diary_note,
            image=self._png_file('diary-date-c.png'),
            original_filename='diary-date-c.png',
            file_size=30,
            content_type='image/png',
        )

        request = self._authenticated_request(
            'get',
            '/api/notes/images/?scope=diary&group_by=diary_date',
        )
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        groups_by_key = {group['key']: group for group in response.data['groups']}
        self.assertEqual(groups_by_key['diary:2026-07-01']['image_count'], 2)
        self.assertEqual(groups_by_key['diary:2026-07-01']['total_size'], 50)
        self.assertEqual(groups_by_key['diary:2026-07-02']['image_count'], 1)
        self.assertEqual(groups_by_key['diary:2026-07-02']['total_size'], 30)

    def test_lists_only_orphan_images(self):
        used_image = NoteImage.objects.create(
            note=self.note,
            image=self._png_file('used.png'),
            original_filename='used.png',
            file_size=24,
            content_type='image/png',
        )
        orphan_image = NoteImage.objects.create(
            note=self.note,
            image=self._png_file('orphan.png'),
            original_filename='orphan.png',
            file_size=30,
            content_type='image/png',
        )
        self.note.markdown_content = f'正文 ![used](http://testserver{used_image.image.url})'
        self.note.save(update_fields=['markdown_content'])

        request = self._authenticated_request('get', '/api/notes/images/?usage=orphan')
        response = NoteImageListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['stats']['image_count'], 1)
        self.assertEqual(response.data['stats']['total_size'], 30)
        self.assertEqual(response.data['results'][0]['id'], orphan_image.id)

    def test_cleans_only_orphan_images(self):
        used_image = NoteImage.objects.create(
            note=self.note,
            image=self._png_file('cleanup-used.png'),
            original_filename='cleanup-used.png',
            file_size=24,
            content_type='image/png',
        )
        orphan_image = NoteImage.objects.create(
            note=self.note,
            image=self._png_file('cleanup-orphan.png'),
            original_filename='cleanup-orphan.png',
            file_size=30,
            content_type='image/png',
        )
        used_path = used_image.image.path
        orphan_path = orphan_image.image.path
        self.note.markdown_content = f'正文 ![used]({used_image.image.url})'
        self.note.save(update_fields=['markdown_content'])

        request = self._authenticated_request('post', '/api/notes/images/orphans/cleanup/')
        response = NoteImageOrphanCleanupView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['cleaned_count'], 1)
        self.assertEqual(response.data['released_size'], 30)
        self.assertTrue(NoteImage.objects.filter(pk=used_image.pk).exists())
        self.assertFalse(NoteImage.objects.filter(pk=orphan_image.pk).exists())
        self.assertTrue(Path(used_path).exists())
        self.assertFalse(Path(orphan_path).exists())

    def test_delete_image_removes_file(self):
        image = NoteImage.objects.create(
            note=self.note,
            image=self._png_file('delete-me.png'),
            original_filename='delete-me.png',
            file_size=24,
            content_type='image/png',
        )
        image_path = image.image.path

        request = self._authenticated_request('delete', f'/api/notes/images/{image.id}/')
        response = NoteImageDestroyView.as_view()(request, pk=image.id)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(NoteImage.objects.filter(pk=image.id).exists())
        self.assertFalse(Path(image_path).exists())


class NoteAuthorizationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.regular_user = get_user_model().objects.create_user(
            username='writer',
            password='password',
        )
        self.note = Note.objects.create(
            title='权限测试笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.deleted_note = Note.objects.create(
            title='回收站权限测试',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        self.diary_note = Note.objects.create(
            title='权限测试日记',
            markdown_content='日记正文',
            rendered_html='<p>日记正文</p>',
        )
        DiaryEntry.objects.create(note=self.diary_note, diary_date=date(2026, 7, 2))

    def _protected_requests(self):
        return [
            ('get', '/api/notes/', None),
            ('get', f'/api/notes/{self.note.id}/', None),
            ('post', '/api/notes/create/', {
                'title': '未授权创建',
                'markdown_content': '正文',
                'tag_names': ['权限'],
            }),
            ('post', '/api/notes/preview/', {
                'markdown_content': '# 预览',
            }),
            ('get', '/api/notes/images/', None),
            ('get', '/api/notes/diaries/', None),
            ('get', '/api/notes/trash/', None),
        ]

    def test_anonymous_requests_are_rejected(self):
        for method, path, payload in self._protected_requests():
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, payload or {}, format='json')

                self.assertEqual(response.status_code, 401)

    def test_authenticated_non_admin_requests_are_rejected(self):
        self.client.force_authenticate(user=self.regular_user)

        for method, path, payload in self._protected_requests():
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, payload or {}, format='json')

                self.assertEqual(response.status_code, 403)


class DiaryEntryCreateSerializerTests(TestCase):
    def test_creates_diary_without_tags(self):
        serializer = DiaryEntryCreateSerializer(data={'diary_date': '2026-07-03'})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        diary_entry = serializer.save()

        self.assertEqual(diary_entry.note.tags.count(), 0)
        self.assertFalse(Tag.objects.filter(name='日记').exists())


class NoteExportViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.tag = Tag.objects.create(name='导出')
        self.note = Note.objects.create(
            title='导出测试/笔记',
            markdown_content='# 导出测试\n\n正文 **加粗**。',
            rendered_html='<h1>导出测试</h1>\n<p>正文 <strong>加粗</strong>。</p>',
        )
        self.note.tags.set([self.tag])

    def _export(self, export_format):
        request = self.factory.get(f'/api/notes/{self.note.id}/export/', {'format': export_format})
        force_authenticate(request, user=self.user)
        return NoteExportView.as_view()(request, pk=self.note.id)

    def test_exports_markdown_file(self):
        response = self._export('markdown')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/markdown; charset=utf-8')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('.md', response['Content-Disposition'])
        self.assertEqual(response.content.decode('utf-8'), self.note.markdown_content)

    def test_exports_html_file(self):
        response = self._export('html')
        content = response.content.decode('utf-8')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertIn('导出测试', content)
        self.assertIn('<strong>加粗</strong>', content)
        self.assertIn('标签：导出', content)

    def test_rejects_unknown_export_format(self):
        response = self._export('pdf')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], '导出格式仅支持 markdown 或 html。')


class NoteBatchDeleteViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.first_note = Note.objects.create(
            title='批量删除 1',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.second_note = Note.objects.create(
            title='批量删除 2',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.deleted_note = Note.objects.create(
            title='已经删除',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )

    def _batch_delete(self, payload):
        request = self.factory.post('/api/notes/batch-delete/', payload, format='json')
        force_authenticate(request, user=self.user)
        return NoteBatchDeleteView.as_view()(request)

    def test_batch_deletes_active_notes(self):
        response = self._batch_delete({
            'note_ids': [self.first_note.id, self.second_note.id, self.deleted_note.id],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted_count'], 2)
        self.first_note.refresh_from_db()
        self.second_note.refresh_from_db()
        self.deleted_note.refresh_from_db()
        self.assertTrue(self.first_note.is_deleted)
        self.assertTrue(self.second_note.is_deleted)
        self.assertTrue(self.deleted_note.is_deleted)
        self.assertIsNotNone(self.first_note.deleted_at)

    def test_rejects_empty_batch_delete(self):
        response = self._batch_delete({'note_ids': []})

        self.assertEqual(response.status_code, 400)
        self.assertIn('请选择要删除的笔记。', response.data['note_ids'])

    def test_rejects_non_integer_note_ids(self):
        response = self._batch_delete({'note_ids': [self.first_note.id, '2']})

        self.assertEqual(response.status_code, 400)
        self.assertIn('笔记 ID 必须是整数。', response.data['note_ids'])


class NoteBatchExportViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.first_note = Note.objects.create(
            title='批量导出',
            markdown_content='# 第一篇',
            rendered_html='<h1>第一篇</h1>',
        )
        self.second_note = Note.objects.create(
            title='批量导出',
            markdown_content='# 第二篇',
            rendered_html='<h1>第二篇</h1>',
        )

    def _batch_export(self, payload):
        request = self.factory.post('/api/notes/batch-export/', payload, format='json')
        force_authenticate(request, user=self.user)
        return NoteBatchExportView.as_view()(request)

    def test_exports_markdown_zip(self):
        response = self._batch_export({
            'note_ids': [self.first_note.id, self.second_note.id],
            'format': 'markdown',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('.zip', response['Content-Disposition'])

        with ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 2)
            self.assertIn('批量导出.md', names)
            self.assertIn('批量导出-2.md', names)
            self.assertEqual(archive.read('批量导出.md').decode('utf-8'), '# 第一篇')

    def test_exports_html_zip(self):
        response = self._batch_export({
            'note_ids': [self.first_note.id],
            'format': 'html',
        })

        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertEqual(names, ['批量导出.html'])
            self.assertIn('<h1>第一篇</h1>', archive.read(names[0]).decode('utf-8'))

    def test_rejects_unknown_batch_export_format(self):
        response = self._batch_export({
            'note_ids': [self.first_note.id],
            'format': 'pdf',
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], '导出格式仅支持 markdown 或 html。')


class NoteBatchTagsViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.python_tag = Tag.objects.create(name='Python')
        self.django_tag = Tag.objects.create(name='Django')
        self.note = Note.objects.create(
            title='批量标签 1',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.note.tags.set([self.python_tag])
        self.second_note = Note.objects.create(
            title='批量标签 2',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.second_note.tags.set([self.python_tag, self.django_tag])

    def _batch_tags(self, payload):
        request = self.factory.post('/api/notes/batch-tags/', payload, format='json')
        force_authenticate(request, user=self.user)
        return NoteBatchTagsView.as_view()(request)

    def test_adds_tags_to_selected_notes(self):
        response = self._batch_tags({
            'note_ids': [self.note.id, self.second_note.id],
            'action': 'add',
            'tag_names': ['项目'],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['updated_count'], 2)
        self.assertTrue(self.note.tags.filter(name='项目').exists())
        self.assertTrue(self.second_note.tags.filter(name='项目').exists())

    def test_removes_tags_from_selected_notes(self):
        response = self._batch_tags({
            'note_ids': [self.second_note.id],
            'action': 'remove',
            'tag_names': ['Python'],
        })

        self.assertEqual(response.status_code, 200)
        self.second_note.refresh_from_db()
        self.assertEqual(list(self.second_note.tags.values_list('name', flat=True)), ['Django'])

    def test_replaces_tags_on_selected_notes(self):
        response = self._batch_tags({
            'note_ids': [self.note.id, self.second_note.id],
            'action': 'replace',
            'tag_names': ['归档', '后端'],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.note.tags.values_list('name', flat=True)), {'归档', '后端'})
        self.assertEqual(set(self.second_note.tags.values_list('name', flat=True)), {'归档', '后端'})

    def test_rejects_update_that_exceeds_tag_limit(self):
        self.note.tags.set([
            self.python_tag,
            self.django_tag,
            Tag.objects.create(name='教程'),
            Tag.objects.create(name='后端'),
        ])

        response = self._batch_tags({
            'note_ids': [self.note.id],
            'action': 'add',
            'tag_names': ['项目'],
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], '《批量标签 1》修改后会超过 4 个标签。')

    def test_rejects_update_that_removes_all_tags(self):
        response = self._batch_tags({
            'note_ids': [self.note.id],
            'action': 'remove',
            'tag_names': ['Python'],
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], '《批量标签 1》至少需要保留一个标签。')


class NotePinViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.note = Note.objects.create(
            title='需要置顶的笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.deleted_note = Note.objects.create(
            title='已删除笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )

    def _pin_note(self, note, payload=None):
        request = self.factory.post(f'/api/notes/{note.id}/pin/', payload or {}, format='json')
        force_authenticate(request, user=self.user)
        return NotePinView.as_view()(request, pk=note.id)

    def test_pins_and_unpins_note(self):
        response = self._pin_note(self.note, {'is_pinned': True})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_pinned'])
        self.assertIsNotNone(response.data['pinned_at'])
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_pinned)
        self.assertIsNotNone(self.note.pinned_at)

        response = self._pin_note(self.note, {'is_pinned': False})

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertFalse(self.note.is_pinned)
        self.assertIsNone(self.note.pinned_at)

    def test_toggles_pin_when_state_is_not_provided(self):
        response = self._pin_note(self.note)

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_pinned)

    def test_rejects_invalid_pin_state(self):
        response = self._pin_note(self.note, {'is_pinned': 'true'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('is_pinned 必须是布尔值。', response.data['is_pinned'])

    def test_deleted_note_cannot_be_pinned(self):
        response = self._pin_note(self.deleted_note, {'is_pinned': True})

        self.assertEqual(response.status_code, 404)


class NoteImportanceViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.note = Note.objects.create(
            title='重要程度笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        self.deleted_note = Note.objects.create(
            title='已删除笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )

    def _set_importance(self, note, payload):
        request = self.factory.post(f'/api/notes/{note.id}/importance/', payload, format='json')
        force_authenticate(request, user=self.user)
        return NoteImportanceView.as_view()(request, pk=note.id)

    def test_updates_note_importance_with_half_star(self):
        response = self._set_importance(self.note, {'importance': 3.5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data['importance']), '3.5')
        self.note.refresh_from_db()
        self.assertEqual(self.note.importance, Decimal('3.5'))

    def test_allows_zero_importance(self):
        self.note.importance = Decimal('4.0')
        self.note.save(update_fields=['importance'])

        response = self._set_importance(self.note, {'importance': 0})

        self.assertEqual(response.status_code, 200)
        self.note.refresh_from_db()
        self.assertEqual(self.note.importance, Decimal('0.0'))

    def test_rejects_importance_out_of_range(self):
        response = self._set_importance(self.note, {'importance': 5.5})

        self.assertEqual(response.status_code, 400)
        self.assertIn('笔记重要程度必须在 0 到 5 星之间。', response.data['importance'])

    def test_rejects_importance_not_half_step(self):
        response = self._set_importance(self.note, {'importance': 4.3})

        self.assertEqual(response.status_code, 400)
        self.assertIn('笔记重要程度只能按 0.5 星调整。', response.data['importance'])

    def test_deleted_note_importance_cannot_be_updated(self):
        response = self._set_importance(self.deleted_note, {'importance': 2})

        self.assertEqual(response.status_code, 404)


class TrashNoteBatchRestoreViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.first_note = Note.objects.create(
            title='待恢复 1',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )
        self.second_note = Note.objects.create(
            title='待恢复 2',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )
        self.active_note = Note.objects.create(
            title='正常笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )

    def _batch_restore(self, payload):
        request = self.factory.post('/api/notes/trash/batch-restore/', payload, format='json')
        force_authenticate(request, user=self.user)
        return TrashNoteBatchRestoreView.as_view()(request)

    def test_batch_restores_deleted_notes(self):
        response = self._batch_restore({
            'note_ids': [self.first_note.id, self.second_note.id, self.active_note.id],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['restored_count'], 2)
        self.first_note.refresh_from_db()
        self.second_note.refresh_from_db()
        self.active_note.refresh_from_db()
        self.assertFalse(self.first_note.is_deleted)
        self.assertFalse(self.second_note.is_deleted)
        self.assertFalse(self.active_note.is_deleted)
        self.assertIsNone(self.first_note.deleted_at)

    def test_rejects_empty_batch_restore(self):
        response = self._batch_restore({'note_ids': []})

        self.assertEqual(response.status_code, 400)
        self.assertIn('请选择要恢复的笔记。', response.data['note_ids'])

    def test_rejects_non_integer_note_ids(self):
        response = self._batch_restore({'note_ids': [self.first_note.id, '2']})

        self.assertEqual(response.status_code, 400)
        self.assertIn('笔记 ID 必须是整数。', response.data['note_ids'])


class TrashNoteBatchDestroyViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.first_note = Note.objects.create(
            title='待彻底删除 1',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )
        self.second_note = Note.objects.create(
            title='待彻底删除 2',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
        )
        self.active_note = Note.objects.create(
            title='正常笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )

    def _batch_destroy(self, payload):
        request = self.factory.post('/api/notes/trash/batch-destroy/', payload, format='json')
        force_authenticate(request, user=self.user)
        return TrashNoteBatchDestroyView.as_view()(request)

    def test_batch_destroys_deleted_notes(self):
        first_note_id = self.first_note.id
        second_note_id = self.second_note.id
        response = self._batch_destroy({
            'note_ids': [self.first_note.id, self.second_note.id, self.active_note.id],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['destroyed_count'], 2)
        self.assertFalse(Note.objects.filter(pk=self.first_note.id).exists())
        self.assertFalse(Note.objects.filter(pk=self.second_note.id).exists())
        self.assertTrue(Note.objects.filter(pk=self.active_note.id).exists())
        self.assertEqual(
            set(RagIndexDeletionJob.objects.values_list('note_id', flat=True)),
            {first_note_id, second_note_id},
        )

    def test_rejects_empty_batch_destroy(self):
        response = self._batch_destroy({'note_ids': []})

        self.assertEqual(response.status_code, 400)
        self.assertIn('请选择要彻底删除的笔记。', response.data['note_ids'])

    def test_rejects_non_integer_note_ids(self):
        response = self._batch_destroy({'note_ids': [self.first_note.id, '2']})

        self.assertEqual(response.status_code, 400)
        self.assertIn('笔记 ID 必须是整数。', response.data['note_ids'])


class TrashPurgeSchedulingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )

    def test_note_list_get_does_not_purge_expired_trash_notes(self):
        expired_note = Note.objects.create(
            title='过期回收站笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
            deleted_at=timezone.now() - timedelta(days=31),
        )
        request = self.factory.get('/api/notes/')
        force_authenticate(request, user=self.user)
        response = NoteListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Note.objects.filter(pk=expired_note.pk).exists())

    def test_purge_trash_command_deletes_only_expired_trash_notes(self):
        expired_note = Note.objects.create(
            title='过期回收站笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
            deleted_at=timezone.now() - timedelta(days=31),
        )
        expired_note_id = expired_note.id
        recent_deleted_note = Note.objects.create(
            title='未过期回收站笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=True,
            deleted_at=timezone.now() - timedelta(days=3),
        )
        active_note = Note.objects.create(
            title='正常笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
            is_deleted=False,
            deleted_at=timezone.now() - timedelta(days=31),
        )
        output = StringIO()

        call_command('purge_trash', stdout=output)

        self.assertIn('Purged 1 expired trash note(s).', output.getvalue())
        self.assertFalse(Note.objects.filter(pk=expired_note.pk).exists())
        self.assertTrue(Note.objects.filter(pk=recent_deleted_note.pk).exists())
        self.assertTrue(Note.objects.filter(pk=active_note.pk).exists())
        self.assertTrue(
            RagIndexDeletionJob.objects.filter(note_id=expired_note_id).exists()
        )


class NoteListFilterTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.python_tag = Tag.objects.create(name='Python')
        self.django_tag = Tag.objects.create(name='Django')

        self.python_note = Note.objects.create(
            title='Python 基础',
            markdown_content='Python 入门内容',
            rendered_html='<p>Python 入门内容</p>',
        )
        self.python_note.tags.set([self.python_tag])

        self.django_note = Note.objects.create(
            title='Django 实战',
            markdown_content='Django 项目内容',
            rendered_html='<p>Django 项目内容</p>',
        )
        self.django_note.tags.set([self.django_tag])

        self.combined_note = Note.objects.create(
            title='Django 与 Python',
            markdown_content='两个标签都有的内容',
            rendered_html='<p>两个标签都有的内容</p>',
        )
        self.combined_note.tags.set([self.python_tag, self.django_tag])

        self.diary_note = Note.objects.create(
            title='Python 日记',
            markdown_content='这是一篇日记，不应出现在普通笔记列表中。',
            rendered_html='<p>这是一篇日记，不应出现在普通笔记列表中。</p>',
        )
        self.diary_note.tags.set([self.python_tag])
        DiaryEntry.objects.create(note=self.diary_note, diary_date=date(2026, 7, 1))

    def _get_note_list(self, params):
        request = self.factory.get('/api/notes/', params)
        force_authenticate(request, user=self.user)
        response = NoteListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response.data['results']

    def _global_search(self, params):
        request = self.factory.get('/api/notes/search/', params)
        force_authenticate(request, user=self.user)
        response = GlobalSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response.data['results']

    def test_filters_notes_by_tag(self):
        results = self._get_note_list({'tag': self.python_tag.id})

        self.assertEqual(
            {note['title'] for note in results},
            {'Python 基础', 'Django 与 Python'},
        )

    def test_combines_tag_filter_with_search(self):
        results = self._get_note_list({
            'tag': self.python_tag.id,
            'search': 'Django',
        })

        self.assertEqual([note['title'] for note in results], ['Django 与 Python'])

    def test_invalid_tag_filter_returns_empty_results(self):
        results = self._get_note_list({'tag': 'invalid'})

        self.assertEqual(results, [])

    def test_note_list_respects_page_size(self):
        request = self.factory.get('/api/notes/', {'page_size': 2})
        force_authenticate(request, user=self.user)
        response = NoteListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])

    def test_excludes_diary_notes_from_note_list_and_search(self):
        results = self._get_note_list({'search': 'Python'})

        self.assertNotIn('Python 日记', {note['title'] for note in results})

    def test_global_search_includes_diary_notes(self):
        results = self._global_search({'search': 'Python', 'page_size': 10})

        results_by_title = {result['title']: result for result in results}
        self.assertIn('Python 基础', results_by_title)
        self.assertIn('Python 日记', results_by_title)
        self.assertEqual(results_by_title['Python 日记']['type'], 'diary')
        self.assertEqual(results_by_title['Python 日记']['diary_date'], '2026-07-01')
        self.assertEqual(results_by_title['Python 日记']['tags'], [])

    def test_global_search_matches_diary_date(self):
        results = self._global_search({'search': '2026-07-01'})

        self.assertEqual([result['title'] for result in results], ['Python 日记'])

    def test_global_search_matches_partial_diary_date(self):
        results = self._global_search({'search': '2026-07'})

        self.assertEqual([result['title'] for result in results], ['Python 日记'])

    def test_pinned_notes_are_listed_first(self):
        request = self.factory.post(
            f'/api/notes/{self.python_note.id}/pin/',
            {'is_pinned': True},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = NotePinView.as_view()(request, pk=self.python_note.id)
        self.assertEqual(response.status_code, 200)

        results = self._get_note_list({})

        self.assertEqual(results[0]['title'], 'Python 基础')
        self.assertTrue(results[0]['is_pinned'])

    def test_summary_excludes_diary_notes(self):
        request = self.factory.get('/api/notes/summary/', {'recent_limit': 10})
        force_authenticate(request, user=self.user)
        response = NoteSummaryView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['stats']['note_count'], 3)
        self.assertNotIn('Python 日记', {note['title'] for note in response.data['recent_notes']})
        self.assertEqual(
            {tag['name']: tag['count'] for tag in response.data['tag_distribution']},
            {'Python': 2, 'Django': 2},
        )

    def test_note_save_updates_word_count(self):
        note = Note.objects.create(
            title='字数测试',
            markdown_content='# 标题\n\n正文 **加粗**',
            rendered_html='<h1>标题</h1><p>正文 <strong>加粗</strong></p>',
        )

        self.assertEqual(note.word_count, 6)

        note.markdown_content = '新的正文'
        note.save(update_fields=['markdown_content'])

        note.refresh_from_db()
        self.assertEqual(note.word_count, 4)

    def test_summary_uses_stored_word_count(self):
        Note.objects.filter(pk=self.python_note.pk).update(word_count=10)
        Note.objects.filter(pk=self.django_note.pk).update(word_count=20)
        Note.objects.filter(pk=self.combined_note.pk).update(word_count=30)

        request = self.factory.get('/api/notes/summary/', {'recent_limit': 10})
        force_authenticate(request, user=self.user)
        response = NoteSummaryView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['stats']['word_count'], 60)

    def test_sorts_notes_by_importance(self):
        self.python_note.importance = Decimal('1.0')
        self.python_note.save(update_fields=['importance'])
        self.django_note.importance = Decimal('4.5')
        self.django_note.save(update_fields=['importance'])
        self.combined_note.importance = Decimal('2.0')
        self.combined_note.save(update_fields=['importance'])

        results = self._get_note_list({'sort': 'importance'})

        self.assertEqual([note['title'] for note in results], ['Django 实战', 'Django 与 Python', 'Python 基础'])

    def test_sorts_notes_by_title(self):
        results = self._get_note_list({'sort': 'title'})

        self.assertEqual([note['title'] for note in results], ['Django 与 Python', 'Django 实战', 'Python 基础'])

    def test_invalid_sort_uses_default_order(self):
        request = self.factory.post(
            f'/api/notes/{self.python_note.id}/pin/',
            {'is_pinned': True},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = NotePinView.as_view()(request, pk=self.python_note.id)
        self.assertEqual(response.status_code, 200)

        results = self._get_note_list({'sort': 'not-supported'})

        self.assertEqual(results[0]['title'], 'Python 基础')
        self.assertTrue(results[0]['is_pinned'])


class TagManagementViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='admin',
            password='password',
        )
        self.python_tag = Tag.objects.create(name='Python')
        self.django_tag = Tag.objects.create(name='Django')
        self.archived_tag = Tag.objects.create(name='Archived')
        self.python_note = Note.objects.create(
            title='Python 基础',
            markdown_content='Python 内容',
            rendered_html='<p>Python 内容</p>',
        )
        self.python_note.tags.set([self.python_tag])
        self.django_note = Note.objects.create(
            title='Django 实战',
            markdown_content='Django 内容',
            rendered_html='<p>Django 内容</p>',
        )
        self.django_note.tags.set([self.django_tag])
        self.deleted_note = Note.objects.create(
            title='已删除笔记',
            markdown_content='归档内容',
            rendered_html='<p>归档内容</p>',
            is_deleted=True,
        )
        self.deleted_note.tags.set([self.archived_tag])
        self.diary_tag = Tag.objects.create(name='日记')
        self.diary_note = Note.objects.create(
            title='日记内容',
            markdown_content='日记正文',
            rendered_html='<p>日记正文</p>',
        )
        self.diary_note.tags.set([self.diary_tag])
        DiaryEntry.objects.create(note=self.diary_note, diary_date=date(2026, 7, 2))

    def _authenticated_request(self, method, path, data=None):
        request = getattr(self.factory, method)(path, data or {}, format='json')
        force_authenticate(request, user=self.user)
        return request

    def test_tag_list_includes_active_note_count(self):
        request = self._authenticated_request('get', '/api/notes/tags/')
        response = TagListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        counts = {tag['name']: tag['note_count'] for tag in response.data}
        self.assertEqual(counts['Python'], 1)
        self.assertEqual(counts['Django'], 1)
        self.assertEqual(counts['Archived'], 0)
        self.assertNotIn('日记', counts)

    def test_renames_tag(self):
        request = self._authenticated_request(
            'patch',
            f'/api/notes/tags/{self.python_tag.id}/',
            {'name': '  Python 进阶  '},
        )
        response = TagDetailView.as_view()(request, pk=self.python_tag.id)

        self.assertEqual(response.status_code, 200)
        self.python_tag.refresh_from_db()
        self.assertEqual(self.python_tag.name, 'Python 进阶')

    def test_rejects_duplicate_tag_name_on_rename(self):
        request = self._authenticated_request(
            'patch',
            f'/api/notes/tags/{self.python_tag.id}/',
            {'name': 'django'},
        )
        response = TagDetailView.as_view()(request, pk=self.python_tag.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('该标签名称已存在。', response.data['name'])

    def test_deletes_tag_without_deleting_notes(self):
        request = self._authenticated_request('delete', f'/api/notes/tags/{self.python_tag.id}/')
        response = TagDetailView.as_view()(request, pk=self.python_tag.id)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Tag.objects.filter(pk=self.python_tag.id).exists())
        self.assertTrue(Note.objects.filter(pk=self.python_note.id).exists())

    def test_merges_source_tag_into_target_tag(self):
        request = self._authenticated_request(
            'post',
            f'/api/notes/tags/{self.python_tag.id}/merge/',
            {'target_tag_id': self.django_tag.id},
        )
        response = TagMergeView.as_view()(request, pk=self.python_tag.id)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tag.objects.filter(pk=self.python_tag.id).exists())
        self.python_note.refresh_from_db()
        self.assertTrue(self.python_note.tags.filter(pk=self.django_tag.id).exists())

    def test_rejects_merging_tag_into_itself(self):
        request = self._authenticated_request(
            'post',
            f'/api/notes/tags/{self.python_tag.id}/merge/',
            {'target_tag_id': self.python_tag.id},
        )
        response = TagMergeView.as_view()(request, pk=self.python_tag.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('不能合并到当前标签。', response.data['target_tag_id'])
