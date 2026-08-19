"""Knowledge Agent 使用的当前笔记、父片段、日记和标签只读服务。"""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import UUID

from django.conf import settings
from django.db.models import Count, F, Q

from notes.models import DiaryEntry, Note, Tag

from .chunking import parse_markdown
from .chunking.parent import extract_heading_title
from .models import RagParentChunk


class KnowledgeReadError(RuntimeError):
    """当前知识来源不存在、过期或类型不符合工具契约。"""

    def __init__(
        self,
        *,
        code: str,
        category: str,
        message: str,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable


def read_current_parent_chunks(parent_ids: tuple[str, ...]) -> dict[str, object]:
    """按调用方顺序读取当前父片段，旧版本和未授权来源不会返回。"""

    canonical_ids = tuple(str(UUID(value)) for value in parent_ids)
    queryset = (
        RagParentChunk.objects.select_related('note', 'note__diary_entry')
        .prefetch_related('note__tags')
        .filter(
            pk__in=canonical_ids,
            note__is_deleted=False,
            note__ai_indexing_enabled=True,
            note__rag_index_state__embedding_version=settings.RAG_EMBEDDING_VERSION,
            # Keep serving the last activated version while a newer attempt is
            # indexing or failed. Empty source_hash means no active version exists.
            note__rag_index_state__source_hash__gt='',
            index_version=F('note__rag_index_state__index_version'),
            source_hash=F('note__rag_index_state__source_hash'),
        )
    )
    current = {
        str(parent.pk): parent
        for parent in queryset
        if parent.source_hash == _source_hash(parent.note.markdown_content)
    }
    if not current:
        raise _not_found('parent_chunks_not_found', 'No current parent chunks were found.')

    chunks = [_parent_payload(current[parent_id]) for parent_id in canonical_ids if parent_id in current]
    return {
        'chunks': chunks,
        'missing_parent_ids': [parent_id for parent_id in canonical_ids if parent_id not in current],
    }


def read_note(note_id: int, *, expected_source_hash: str | None = None) -> dict[str, object]:
    note = _get_current_note(note_id, document_type='note')
    source_hash = _source_hash(note.markdown_content)
    _check_expected_hash(source_hash, expected_source_hash)
    return {
        'type': 'note',
        'note_id': note.pk,
        'title': note.title,
        'source_filename': note.source_filename,
        'tags': sorted(tag.name for tag in note.tags.all()),
        'markdown_content': note.markdown_content,
        'source_hash': source_hash,
        'updated_at': note.updated_at.isoformat(),
    }


def read_note_section(
    note_id: int,
    heading_path: tuple[str, ...],
    *,
    expected_source_hash: str | None = None,
) -> dict[str, object]:
    note = _get_current_note(note_id, document_type='note')
    source_hash = _source_hash(note.markdown_content)
    _check_expected_hash(source_hash, expected_source_hash)
    sections = _find_sections(note.markdown_content, heading_path)
    if not sections:
        raise _not_found('note_section_not_found', 'The requested note section was not found.')
    if len(sections) > 1:
        raise KnowledgeReadError(
            code='note_section_ambiguous',
            category='conflict',
            message='The requested heading path matches multiple current sections.',
        )
    content, start_line, end_line = sections[0]
    return {
        'type': 'note',
        'note_id': note.pk,
        'title': note.title,
        'heading_path': list(heading_path),
        'content': content,
        'start_line': start_line,
        'end_line': end_line,
        'source_hash': source_hash,
    }


def read_diary_by_date(diary_date: date) -> dict[str, object]:
    try:
        diary = (
            DiaryEntry.objects.select_related('note')
            .get(
                diary_date=diary_date,
                note__is_deleted=False,
                note__ai_indexing_enabled=True,
            )
        )
    except DiaryEntry.DoesNotExist:
        raise _not_found('diary_not_found', 'No current diary exists for this date.') from None
    fields = {
        'summary': diary.summary,
        'mood': diary.mood,
        'weather': diary.weather,
        'markdown_content': diary.note.markdown_content,
    }
    return {
        'type': 'diary',
        'note_id': diary.note_id,
        'diary_date': diary.diary_date.isoformat(),
        'title': diary.note.title,
        # 与日记索引根片段保持一致，使 Agent 引用可以精确匹配标题路径。
        'heading_path': [diary.note.title],
        **fields,
        # 空元数据必须显式标记，避免模型把“字段存在但为空”误当成可推断事实。
        'available_fields': [name for name, value in fields.items() if value.strip()],
        'missing_fields': [name for name, value in fields.items() if not value.strip()],
        'source_hash': _source_hash(diary.note.markdown_content),
        'updated_at': diary.note.updated_at.isoformat(),
    }


def list_knowledge_tags(*, query: str = '', limit: int = 50) -> dict[str, object]:
    note_filter = Q(
        notes__is_deleted=False,
        notes__ai_indexing_enabled=True,
        notes__diary_entry__isnull=True,
    )
    queryset = Tag.objects.annotate(
        note_count=Count('notes', filter=note_filter, distinct=True)
    ).filter(note_count__gt=0)
    if query:
        queryset = queryset.filter(name__icontains=query)
    tags = queryset.order_by('name', 'id')[:limit]
    return {
        'tags': [
            {'id': tag.pk, 'name': tag.name, 'note_count': tag.note_count}
            for tag in tags
        ]
    }


def _get_current_note(note_id: int, *, document_type: str) -> Note:
    queryset = Note.objects.filter(
        pk=note_id,
        is_deleted=False,
        ai_indexing_enabled=True,
    ).prefetch_related('tags')
    if document_type == 'note':
        queryset = queryset.filter(diary_entry__isnull=True)
    try:
        return queryset.get()
    except Note.DoesNotExist:
        raise _not_found('note_not_found', 'The requested current note was not found.') from None


def _parent_payload(parent: RagParentChunk) -> dict[str, object]:
    diary = getattr(parent.note, 'diary_entry', None)
    return {
        'note_id': parent.note_id,
        'parent_id': str(parent.pk),
        'type': 'diary' if diary else 'note',
        'title': parent.note.title,
        'heading_path': list(parent.heading_path),
        'content': parent.content,
        'start_line': parent.start_line,
        'end_line': parent.end_line,
        'source_hash': parent.source_hash,
        'diary_date': diary.diary_date.isoformat() if diary else None,
    }


def _find_sections(
    markdown: str,
    target_path: tuple[str, ...],
) -> list[tuple[str, int, int]]:
    blocks = parse_markdown(markdown)
    source_lines = markdown.splitlines()
    heading_stack: list[tuple[int, str]] = []
    matches: list[tuple[str, int, int]] = []

    for index, block in enumerate(blocks):
        if block.block_type != 'heading':
            continue
        level = block.heading_level
        assert level is not None
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, extract_heading_title(block)))
        if tuple(title for _, title in heading_stack) != target_path:
            continue

        end_line = len(source_lines)
        for following in blocks[index + 1 :]:
            if (
                following.block_type == 'heading'
                and following.heading_level is not None
                and following.heading_level <= level
            ):
                end_line = following.start_line - 1
                break
        content = '\n'.join(source_lines[block.start_line - 1 : end_line])
        matches.append((content, block.start_line, end_line))
    return matches


def _check_expected_hash(current_hash: str, expected_hash: str | None):
    if expected_hash is not None and expected_hash != current_hash:
        raise KnowledgeReadError(
            code='source_hash_mismatch',
            category='stale_source',
            message='The requested source hash is no longer current.',
        )


def _source_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _not_found(code: str, message: str) -> KnowledgeReadError:
    return KnowledgeReadError(code=code, category='not_found', message=message)
