"""把会影响 RAG 的 Note、标签和日记变化在事务提交后加入队列。"""

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from notes.models import DiaryEntry, Note, Tag

from .jobs import (
    enqueue_note_deletion,
    enqueue_note_ids_on_commit,
    enqueue_note_index_on_commit,
)


NOTE_INDEX_FIELDS = ('title', 'markdown_content', 'is_deleted', 'ai_indexing_enabled')
DIARY_INDEX_FIELDS = ('diary_date', 'mood', 'weather', 'summary')


@receiver(pre_delete, sender=Note)
def enqueue_permanent_note_index_deletion(sender, instance, **kwargs):
    """在 Note 级联删除 RAG 外键前写入独立 Qdrant 清理任务。"""

    if instance.pk is not None:
        enqueue_note_deletion(instance.pk)


@receiver(pre_save, sender=Note)
def detect_note_index_change(sender, instance, raw=False, **kwargs):
    """保存前比较会影响索引的字段，避免置顶或星级变化触发云端请求。"""

    if raw:
        instance._rag_should_enqueue = False
        return
    if instance._state.adding:
        instance._rag_should_enqueue = bool(instance.ai_indexing_enabled)
        instance._rag_enqueue_reason = 'note_created'
        return

    old = Note.objects.filter(pk=instance.pk).values(*NOTE_INDEX_FIELDS).first()
    if old is None:
        instance._rag_should_enqueue = False
        return
    changed = any(old[field] != getattr(instance, field) for field in NOTE_INDEX_FIELDS)
    instance._rag_should_enqueue = changed and (
        old['ai_indexing_enabled'] or instance.ai_indexing_enabled
    )
    if old['ai_indexing_enabled'] != instance.ai_indexing_enabled:
        instance._rag_enqueue_reason = 'ai_indexing_changed'
    elif old['is_deleted'] != instance.is_deleted:
        instance._rag_enqueue_reason = 'note_deleted' if instance.is_deleted else 'note_restored'
    else:
        instance._rag_enqueue_reason = 'note_saved'


@receiver(post_save, sender=Note)
def enqueue_changed_note(sender, instance, raw=False, **kwargs):
    if raw or not getattr(instance, '_rag_should_enqueue', False):
        return
    enqueue_note_index_on_commit(
        instance.pk,
        reason=getattr(instance, '_rag_enqueue_reason', 'note_saved'),
    )


@receiver(m2m_changed, sender=Note.tags.through)
def enqueue_changed_note_tags(sender, instance, action, reverse, pk_set, **kwargs):
    """标签集合会进入普通笔记向量文本，变化后必须重新索引。"""

    if action == 'pre_clear':
        if reverse:
            instance._rag_note_ids_before_clear = tuple(
                instance.notes.filter(ai_indexing_enabled=True, is_deleted=False).values_list(
                    'id', flat=True
                )
            )
        else:
            instance._rag_note_ids_before_clear = (instance.pk,)
        return
    if action not in {'post_add', 'post_remove', 'post_clear'}:
        return

    if action == 'post_clear':
        note_ids = getattr(instance, '_rag_note_ids_before_clear', ())
    elif reverse:
        note_ids = tuple(pk_set or ())
    else:
        note_ids = (instance.pk,)
    eligible_ids = Note.objects.filter(
        pk__in=note_ids,
        ai_indexing_enabled=True,
        is_deleted=False,
    ).values_list('id', flat=True)
    enqueue_note_ids_on_commit(eligible_ids, reason='note_tags_changed')


@receiver(pre_save, sender=DiaryEntry)
def detect_diary_index_change(sender, instance, raw=False, **kwargs):
    if raw:
        instance._rag_should_enqueue = False
        return
    if instance._state.adding:
        instance._rag_should_enqueue = True
        return
    old = DiaryEntry.objects.filter(pk=instance.pk).values(*DIARY_INDEX_FIELDS).first()
    instance._rag_should_enqueue = old is not None and any(
        old[field] != getattr(instance, field) for field in DIARY_INDEX_FIELDS
    )


@receiver(post_save, sender=DiaryEntry)
def enqueue_changed_diary(sender, instance, raw=False, **kwargs):
    if raw or not getattr(instance, '_rag_should_enqueue', False):
        return
    note = Note.objects.filter(pk=instance.note_id).only(
        'ai_indexing_enabled', 'is_deleted'
    ).first()
    if note and note.ai_indexing_enabled and not note.is_deleted:
        enqueue_note_index_on_commit(instance.note_id, reason='diary_metadata_changed')


@receiver(pre_save, sender=Tag)
def detect_tag_name_change(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding:
        instance._rag_name_changed = False
        return
    old_name = Tag.objects.filter(pk=instance.pk).values_list('name', flat=True).first()
    instance._rag_name_changed = old_name is not None and old_name != instance.name


@receiver(post_save, sender=Tag)
def enqueue_renamed_tag_notes(sender, instance, raw=False, **kwargs):
    if raw or not getattr(instance, '_rag_name_changed', False):
        return
    note_ids = instance.notes.filter(
        ai_indexing_enabled=True,
        is_deleted=False,
    ).values_list('id', flat=True)
    enqueue_note_ids_on_commit(note_ids, reason='tag_renamed')


@receiver(pre_delete, sender=Tag)
def remember_deleted_tag_notes(sender, instance, **kwargs):
    instance._rag_note_ids_before_delete = tuple(
        instance.notes.filter(ai_indexing_enabled=True, is_deleted=False).values_list(
            'id', flat=True
        )
    )


@receiver(post_delete, sender=Tag)
def enqueue_deleted_tag_notes(sender, instance, **kwargs):
    enqueue_note_ids_on_commit(
        getattr(instance, '_rag_note_ids_before_delete', ()),
        reason='tag_deleted',
    )
