from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from notes.models import DiaryEntry, Note

from .models import SEGMENT_PROJECT, SEGMENT_TODO, Task

BASE_TIME = timezone.now().replace(second=0, microsecond=0)


def build_window(hours):
    return BASE_TIME, BASE_TIME + timedelta(hours=hours)


class TaskSegmentTests(TestCase):
    def _create(self, title, hours):
        start_at, end_at = build_window(hours)
        return Task.objects.create(
            title=title,
            start_at=start_at,
            end_at=end_at,
            urgency=Task.Urgency.MEDIUM,
        )

    def test_short_task_is_todo(self):
        self.assertEqual(self._create('一小时内', 1).segment, SEGMENT_TODO)

    def test_exactly_24_hours_is_todo(self):
        # 边界按「<= 24 小时」处理，恰好 24 小时算待办。
        self.assertEqual(self._create('恰好一天', 24).segment, SEGMENT_TODO)

    def test_over_24_hours_is_project(self):
        self.assertEqual(self._create('跨两天', 25).segment, SEGMENT_PROJECT)

    def test_cross_midnight_but_short_is_todo(self):
        # 21:00 → 次日 01:00 只有 4 小时，只认时长不认自然日。
        start_at = BASE_TIME.replace(hour=21, minute=0)
        task = Task.objects.create(
            title='跨夜四小时',
            start_at=start_at,
            end_at=start_at + timedelta(hours=4),
            urgency=Task.Urgency.HIGH,
        )

        self.assertEqual(task.segment, SEGMENT_TODO)

    def test_missing_time_is_project_and_undated(self):
        task = Task.objects.create(title='没有时间', urgency=Task.Urgency.LOW)

        self.assertEqual(task.segment, SEGMENT_PROJECT)
        self.assertFalse(task.has_time)


class TaskOverdueTests(TestCase):
    def test_unfinished_past_task_is_overdue(self):
        task = Task.objects.create(
            title='已经过期',
            start_at=BASE_TIME - timedelta(hours=3),
            end_at=BASE_TIME - timedelta(hours=1),
            urgency=Task.Urgency.HIGH,
        )

        self.assertTrue(task.is_overdue)

    def test_completed_task_is_never_overdue(self):
        task = Task.objects.create(
            title='已完成',
            start_at=BASE_TIME - timedelta(hours=3),
            end_at=BASE_TIME - timedelta(hours=1),
            urgency=Task.Urgency.HIGH,
            is_completed=True,
            completed_at=timezone.now(),
        )

        self.assertFalse(task.is_overdue)


class TaskApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            username='task-admin',
            password='password',
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(self.admin)

    def _payload(self, title='写报告', hours=1, **overrides):
        start_at, end_at = build_window(hours)
        payload = {
            'title': title,
            'start_at': start_at.isoformat(),
            'end_at': end_at.isoformat(),
            'urgency': Task.Urgency.HIGH,
        }
        payload.update(overrides)
        return payload

    def test_requires_authentication(self):
        response = APIClient().get('/api/tasks/')

        self.assertEqual(response.status_code, 401)

    def test_create_task(self):
        response = self.client.post('/api/tasks/', self._payload(), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['segment'], SEGMENT_TODO)
        self.assertEqual(response.data['urgency_display'], '高')

    def test_create_task_requires_time(self):
        response = self.client.post('/api/tasks/', {'title': '无时间', 'urgency': 2}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('start_at', response.data)

    def test_end_before_start_is_rejected(self):
        start_at, end_at = build_window(2)
        response = self.client.post(
            '/api/tasks/',
            {
                'title': '时间倒置',
                'start_at': end_at.isoformat(),
                'end_at': start_at.isoformat(),
                'urgency': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('end_at', response.data)

    def test_urgency_is_required(self):
        start_at, end_at = build_window(1)
        response = self.client.post(
            '/api/tasks/',
            {'title': '没选紧急度', 'start_at': start_at.isoformat(), 'end_at': end_at.isoformat()},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('urgency', response.data)

    def test_list_splits_by_segment_filter(self):
        Task.objects.create(
            title='待办一条',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=2),
            urgency=Task.Urgency.LOW,
        )
        Task.objects.create(
            title='项目一条',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(days=5),
            urgency=Task.Urgency.LOW,
        )

        todo_response = self.client.get('/api/tasks/', {'segment': 'todo'})
        project_response = self.client.get('/api/tasks/', {'segment': 'project'})

        self.assertEqual([item['title'] for item in todo_response.data['results']], ['待办一条'])
        self.assertEqual([item['title'] for item in project_response.data['results']], ['项目一条'])

    def test_segment_filter_treats_undated_as_project(self):
        Task.objects.create(title='没有时间', urgency=Task.Urgency.LOW)

        project_response = self.client.get('/api/tasks/', {'segment': 'project'})
        todo_response = self.client.get('/api/tasks/', {'segment': 'todo'})

        self.assertEqual(project_response.data['count'], 1)
        self.assertEqual(todo_response.data['count'], 0)

    def test_default_list_hides_completed_tasks(self):
        Task.objects.create(
            title='已完成的',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            is_completed=True,
            completed_at=timezone.now(),
        )
        Task.objects.create(
            title='未完成的',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
        )

        response = self.client.get('/api/tasks/')

        self.assertEqual([item['title'] for item in response.data['results']], ['未完成的'])

    def test_completed_scope_returns_completed_only(self):
        Task.objects.create(
            title='已完成',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            is_completed=True,
            completed_at=timezone.now(),
        )

        response = self.client.get('/api/tasks/', {'scope': 'completed'})

        self.assertEqual([item['title'] for item in response.data['results']], ['已完成'])

    def test_sort_by_due_orders_by_end_at(self):
        Task.objects.create(
            title='晚一点',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=6),
            urgency=Task.Urgency.LOW,
        )
        Task.objects.create(
            title='早一点',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=2),
            urgency=Task.Urgency.LOW,
        )

        response = self.client.get('/api/tasks/', {'sort': 'due'})

        self.assertEqual(
            [item['title'] for item in response.data['results']],
            ['早一点', '晚一点'],
        )

    def test_search_only_matches_title(self):
        Task.objects.create(
            title='买牛奶',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            summary='总结里写了面包',
        )

        title_hit = self.client.get('/api/tasks/', {'search': '牛奶'})
        summary_miss = self.client.get('/api/tasks/', {'search': '面包'})

        self.assertEqual(title_hit.data['count'], 1)
        self.assertEqual(summary_miss.data['count'], 0)

    def test_complete_sets_timestamp_and_summary(self):
        task = Task.objects.create(
            title='待完成',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.MEDIUM,
        )

        response = self.client.post(
            f'/api/tasks/{task.id}/complete/',
            {'summary': '写完了，比预估快'},
            format='json',
        )

        task.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.summary, '写完了，比预估快')

    def test_complete_without_summary_is_allowed(self):
        task = Task.objects.create(
            title='不写总结',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.MEDIUM,
        )

        response = self.client.post(f'/api/tasks/{task.id}/complete/', {}, format='json')

        task.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(task.is_completed)
        self.assertEqual(task.summary, '')

    def test_complete_toggles_back_to_unfinished(self):
        task = Task.objects.create(
            title='反复勾',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.MEDIUM,
            is_completed=True,
            completed_at=timezone.now(),
        )

        response = self.client.post(f'/api/tasks/{task.id}/complete/', {}, format='json')

        task.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(task.is_completed)
        self.assertIsNone(task.completed_at)

    def test_delete_is_hard_delete(self):
        task = Task.objects.create(
            title='删掉',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
        )

        response = self.client.delete(f'/api/tasks/{task.id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Task.objects.filter(pk=task.id).exists())

    def test_link_to_regular_note(self):
        note = Note.objects.create(title='普通笔记', markdown_content='正文', rendered_html='<p>正文</p>')

        response = self.client.post(
            '/api/tasks/',
            self._payload(linked_note_id=note.id),
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['linked_note']['type'], 'note')
        self.assertEqual(response.data['linked_note']['title'], '普通笔记')
        self.assertFalse(response.data['linked_note']['is_deleted'])

    def test_link_to_diary(self):
        note = Note.objects.create(title='某天日记', markdown_content='正文', rendered_html='<p>正文</p>')
        DiaryEntry.objects.create(note=note, diary_date=BASE_TIME.date())

        response = self.client.post('/api/tasks/', self._payload(linked_note_id=note.id), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['linked_note']['type'], 'diary')
        self.assertEqual(
            response.data['linked_note']['diary_date'],
            BASE_TIME.date().isoformat(),
        )

    def test_linked_note_survives_soft_delete_and_is_flagged(self):
        note = Note.objects.create(
            title='会被删的笔记',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        task = Task.objects.create(
            title='关联任务',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            linked_note=note,
        )

        note.is_deleted = True
        note.deleted_at = timezone.now()
        note.save(update_fields=['is_deleted', 'deleted_at'])

        response = self.client.get(f'/api/tasks/{task.id}/')

        self.assertEqual(response.data['linked_note']['id'], note.id)
        self.assertTrue(response.data['linked_note']['is_deleted'])

    def test_linked_note_is_nulled_when_note_row_is_removed(self):
        note = Note.objects.create(
            title='会被彻底删除',
            markdown_content='正文',
            rendered_html='<p>正文</p>',
        )
        task = Task.objects.create(
            title='关联任务',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            linked_note=note,
        )

        note.delete()

        task.refresh_from_db()
        self.assertIsNone(task.linked_note)

    def test_unknown_linked_note_is_rejected(self):
        response = self.client.post('/api/tasks/', self._payload(linked_note_id=999999), format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('linked_note_id', response.data)

    def test_summary_endpoint_only_returns_todo_segment(self):
        Task.objects.create(
            title='待办',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=2),
            urgency=Task.Urgency.LOW,
        )
        Task.objects.create(
            title='项目',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(days=3),
            urgency=Task.Urgency.LOW,
        )
        Task.objects.create(
            title='已完成待办',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=2),
            urgency=Task.Urgency.LOW,
            is_completed=True,
            completed_at=timezone.now(),
        )

        response = self.client.get('/api/tasks/summary/')

        self.assertEqual([item['title'] for item in response.data['todo_tasks']], ['待办'])
        self.assertEqual(response.data['stats']['todo_count'], 1)
        self.assertEqual(response.data['stats']['project_count'], 1)
        self.assertEqual(response.data['stats']['completed_today'], 1)

    def test_partial_update_keeps_range_valid(self):
        start_at, end_at = build_window(2)
        task = Task.objects.create(
            title='改时间',
            start_at=start_at,
            end_at=end_at,
            urgency=Task.Urgency.LOW,
        )

        response = self.client.patch(
            f'/api/tasks/{task.id}/',
            {'end_at': (start_at - timedelta(hours=1)).isoformat()},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('end_at', response.data)


class TaskSearchIntegrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = get_user_model().objects.create_user(
            username='search-admin',
            password='password',
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(self.admin)

    def test_global_search_returns_task_type(self):
        Task.objects.create(
            title='整理季度报告',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.HIGH,
        )

        response = self.client.get('/api/notes/search/', {'search': '季度报告'})

        self.assertEqual(response.status_code, 200)
        types = [item['type'] for item in response.data['results']]
        self.assertIn('task', types)

        task_result = next(item for item in response.data['results'] if item['type'] == 'task')
        self.assertEqual(task_result['title'], '整理季度报告')
        self.assertEqual(task_result['urgency_display'], '高')
        self.assertEqual(task_result['segment'], SEGMENT_TODO)

    def test_task_never_appears_in_note_list(self):
        Task.objects.create(
            title='不该出现在笔记列表',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.HIGH,
        )

        response = self.client.get('/api/notes/', {'search': '不该出现'})

        self.assertEqual(response.data['count'], 0)

    def test_task_summary_never_appears_in_global_search(self):
        Task.objects.create(
            title='买灯泡',
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(hours=1),
            urgency=Task.Urgency.LOW,
            summary='顺路买了螺丝刀',
        )

        response = self.client.get('/api/notes/search/', {'search': '螺丝刀'})

        self.assertEqual(response.data['count'], 0)
