"""基于 MySQL 当前 Note 数据的确定性关键词检索。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal

from django.db.models import CharField, F, Q
from django.db.models.functions import Cast

from notes.models import Note
from rag.chunking import parse_markdown
from rag.chunking.parent import extract_heading_title
from rag.models import RagParentChunk


DocumentType = Literal['note', 'diary']
ALLOWED_DOCUMENT_TYPES = frozenset({'note', 'diary'})
MAX_KEYWORD_QUERY_LENGTH = 500
MAX_KEYWORD_RESULTS = 100
EXCERPT_LENGTH = 240
MAX_SEARCH_TERMS = 8
SEARCH_TOKEN_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]*|[\u4e00-\u9fff]+')
QUERY_FILLER_PHRASES = (
    '有多少个',
    '有哪几个',
    '有哪些',
    '有几个',
    '是多少',
    '是什么',
    '请问',
    '麻烦',
    '告诉我',
    '帮我',
    '这个',
    '那个',
    '这些',
    '那些',
    '怎么',
    '如何',
    '能否',
    '是否',
    '一下',
    '多少',
    '哪些',
    '几个',
    '数量',
    '个数',
    '的',
)


class KeywordSearchError(ValueError):
    """关键词检索参数错误；code 供后续工具层转换为结构化响应。"""

    def __init__(self, *, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {'code': self.code, 'message': str(self)}


@dataclass(frozen=True, slots=True)
class KeywordCandidate:
    """可直接交给后续混合检索层的单篇 Note 关键词候选。"""

    note_id: int
    parent_id: str | None
    document_type: DocumentType
    title: str
    heading_path: tuple[str, ...]
    source_hash: str
    score: float
    matched_excerpt: str
    matched_fields: tuple[str, ...]
    diary_date: date | None = None
    content: str = ''
    start_line: int = 1
    end_line: int = 1

    def as_dict(self) -> dict[str, object]:
        """使用规范中的字段名输出 JSON 友好结构。"""

        return {
            'note_id': self.note_id,
            'parent_id': self.parent_id,
            'type': self.document_type,
            'title': self.title,
            'heading_path': list(self.heading_path),
            'source_hash': self.source_hash,
            'score': self.score,
            'matched_excerpt': self.matched_excerpt,
            'matched_fields': list(self.matched_fields),
            'diary_date': self.diary_date.isoformat() if self.diary_date else None,
        }


@dataclass(frozen=True, slots=True)
class _RankedNote:
    note: Note
    document_type: DocumentType
    score: float
    matched_excerpt: str
    matched_fields: tuple[str, ...]
    diary_date: date | None


@dataclass(frozen=True, slots=True)
class _CandidateSection:
    parent_id: str | None
    chunk_index: int
    heading_path: tuple[str, ...]
    content: str
    start_line: int
    end_line: int


def search_keywords(
    query: str,
    *,
    types: Iterable[DocumentType] | None = None,
    tags: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
) -> tuple[KeywordCandidate, ...]:
    """检索当前有效 Note；types 为空时同时检索普通笔记和日记。"""

    normalized_query = _validate_query(query)
    search_terms = _search_terms(normalized_query)
    selected_types = _validate_types(types)
    normalized_tags = _validate_tags(tags)
    _validate_date_range(date_from, date_to)
    _validate_limit(limit)

    ranked_notes: list[_RankedNote] = []
    # 标签与日期均为 AND 过滤；Note 没有日记日期，Diary 也不消费 Note 标签。
    if 'note' in selected_types and date_from is None and date_to is None:
        ranked_notes.extend(
            _search_regular_notes(normalized_query, search_terms, normalized_tags)
        )
    if 'diary' in selected_types and not normalized_tags:
        ranked_notes.extend(
            _search_diaries(normalized_query, search_terms, date_from, date_to)
        )

    # 同分时优先返回最近更新内容，再用主键保证重复查询顺序稳定。
    ranked_notes.sort(
        key=lambda item: (item.score, item.note.updated_at, item.note.pk),
        reverse=True,
    )
    selected = ranked_notes[:limit]
    parents_by_note = _load_current_parents(selected)
    return tuple(
        _build_candidate(
            item,
            normalized_query,
            search_terms,
            parents_by_note.get(item.note.pk, ()),
        )
        for item in selected
    )


def _search_regular_notes(
    query: str,
    search_terms: tuple[str, ...],
    tags: tuple[str, ...],
) -> list[_RankedNote]:
    queryset = (
        Note.objects.filter(is_deleted=False, diary_entry__isnull=True)
        .filter(_term_filter(search_terms, ('title', 'markdown_content', 'source_filename', 'tags__name')))
        .prefetch_related('tags')
        .distinct()
    )
    for tag in tags:
        queryset = queryset.filter(tags__name=tag)
    ranked = [_rank_regular_note(note, query, search_terms) for note in queryset]
    return [item for item in ranked if item.score > 0]


def _search_diaries(
    query: str,
    search_terms: tuple[str, ...],
    date_from: date | None,
    date_to: date | None,
) -> list[_RankedNote]:
    queryset = (
        Note.objects.filter(is_deleted=False, diary_entry__isnull=False)
        .select_related('diary_entry')
        .annotate(
            # Cast 允许 `2026-07` 这类部分日期继续由 MySQL 精确匹配。
            diary_date_text=Cast('diary_entry__diary_date', output_field=CharField())
        )
        .filter(
            _term_filter(
                search_terms,
                (
                    'title',
                    'markdown_content',
                    'diary_entry__summary',
                    'diary_entry__mood',
                    'diary_entry__weather',
                    'diary_date_text',
                ),
            )
        )
        .distinct()
    )
    if date_from:
        queryset = queryset.filter(diary_entry__diary_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(diary_entry__diary_date__lte=date_to)
    ranked = [_rank_diary(note, query, search_terms) for note in queryset]
    return [item for item in ranked if item.score > 0]


def _rank_regular_note(
    note: Note,
    query: str,
    search_terms: tuple[str, ...],
) -> _RankedNote:
    fields = [
        ('title', note.title, 1.0, 0.90),
        ('source_filename', note.source_filename, 0.98, 0.88),
        ('tags', _matching_tag(note, query), 0.95, 0.85),
        ('markdown_content', note.markdown_content, 0.70, 0.70),
    ]
    score, excerpt, matched_fields = _score_fields(fields, query, search_terms)
    return _RankedNote(
        note=note,
        document_type='note',
        score=score,
        matched_excerpt=excerpt,
        matched_fields=matched_fields,
        diary_date=None,
    )


def _rank_diary(
    note: Note,
    query: str,
    search_terms: tuple[str, ...],
) -> _RankedNote:
    diary = note.diary_entry
    fields = [
        ('title', note.title, 1.0, 0.90),
        ('diary_date', diary.diary_date.isoformat(), 0.98, 0.88),
        ('summary', diary.summary, 0.85, 0.80),
        ('mood', diary.mood, 0.85, 0.80),
        ('weather', diary.weather, 0.85, 0.80),
        ('markdown_content', note.markdown_content, 0.70, 0.70),
    ]
    score, excerpt, matched_fields = _score_fields(fields, query, search_terms)
    return _RankedNote(
        note=note,
        document_type='diary',
        score=score,
        matched_excerpt=excerpt,
        matched_fields=matched_fields,
        diary_date=diary.diary_date,
    )


def _score_fields(
    fields: list[tuple[str, str, float, float]],
    query: str,
    search_terms: tuple[str, ...],
    *,
    minimum_fallback_terms: int = 2,
) -> tuple[float, str, tuple[str, ...]]:
    matches: list[tuple[float, str, str, str]] = []
    query_folded = query.casefold()
    fallback_terms = tuple(
        term for term in search_terms if term.casefold() != query_folded
    )
    searchable_text = '\n'.join(value.casefold() for _, value, _, _ in fields if value)
    if query_folded not in searchable_text:
        matched_term_count = sum(
            1 for term in fallback_terms if term.casefold() in searchable_text
        )
        required_term_count = min(minimum_fallback_terms, len(fallback_terms))
        if matched_term_count < required_term_count:
            return 0.0, '', ()

    for field_name, value, exact_score, contains_score in fields:
        if not value:
            continue
        value_folded = value.casefold()
        if query_folded in value_folded:
            score = exact_score if query_folded == value_folded else contains_score
            matches.append((score, field_name, value, query))
            continue

        matched_terms = tuple(
            term for term in fallback_terms if term.casefold() in value_folded
        )
        if not matched_terms:
            continue
        coverage = len(matched_terms) / max(1, len(fallback_terms))
        score = contains_score * (0.5 + 0.5 * coverage)
        matches.append((score, field_name, value, max(matched_terms, key=len)))

    if not matches:
        return 0.0, '', ()
    # QuerySet 已保证至少一个字段命中；排序后首项同时决定主分数与摘要来源。
    matches.sort(key=lambda item: item[0], reverse=True)
    best_score, _, best_value, best_term = matches[0]
    return (
        best_score,
        _build_excerpt(best_value, best_term),
        tuple(field_name for _, field_name, _, _ in matches),
    )


def _term_filter(search_terms: tuple[str, ...], field_names: tuple[str, ...]) -> Q:
    condition = Q()
    for term in search_terms:
        for field_name in field_names:
            condition |= Q(**{f'{field_name}__icontains': term})
    return condition


def _search_terms(query: str) -> tuple[str, ...]:
    candidates = [query]
    for token in SEARCH_TOKEN_PATTERN.findall(query):
        if token.isascii():
            candidates.append(token)
            continue
        pieces = [token]
        for phrase in QUERY_FILLER_PHRASES:
            pieces = [part for piece in pieces for part in piece.split(phrase)]
        candidates.extend(piece for piece in pieces if len(piece) >= 2)

    terms = []
    seen = set()
    for candidate in candidates:
        normalized = candidate.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        terms.append(normalized)
        if len(terms) >= MAX_SEARCH_TERMS:
            break
    return tuple(terms)


def _matching_tag(note: Note, query: str) -> str:
    query_folded = query.casefold()
    return next(
        (tag.name for tag in note.tags.all() if query_folded in tag.name.casefold()),
        '',
    )


def _load_current_parents(
    ranked_notes: list[_RankedNote],
) -> dict[int, tuple[RagParentChunk, ...]]:
    if not ranked_notes:
        return {}
    note_ids = [item.note.pk for item in ranked_notes]
    chunks = (
        RagParentChunk.objects.filter(
            note_id__in=note_ids,
            # An older active version remains readable while a newer attempt is
            # indexing or failed; an empty source_hash means no active version exists.
            note__rag_index_state__source_hash__gt='',
            index_version=F('note__rag_index_state__index_version'),
            source_hash=F('note__rag_index_state__source_hash'),
        )
        .order_by('note_id', 'chunk_index')
    )
    grouped: dict[int, list[RagParentChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.note_id, []).append(chunk)
    return {note_id: tuple(items) for note_id, items in grouped.items()}


def _build_candidate(
    ranked: _RankedNote,
    query: str,
    search_terms: tuple[str, ...],
    parents: tuple[RagParentChunk, ...],
) -> KeywordCandidate:
    source_hash = _source_hash(ranked.note.markdown_content)
    # 旧索引父片段不能作为当前来源；没有当前父片段时解析当前 Markdown 临时章节。
    current_parents = tuple(parent for parent in parents if parent.source_hash == source_hash)
    sections = (
        tuple(_section_from_parent(parent) for parent in current_parents)
        if current_parents
        else _temporary_sections(ranked.note.markdown_content)
    )
    section_matches = []
    for section in sections:
        score, excerpt, matched_fields = _score_fields(
            [
                (
                    'heading_path',
                    section.heading_path[-1] if section.heading_path else '',
                    0.85,
                    0.80,
                ),
                ('markdown_content', section.content, 0.70, 0.70),
            ],
            query,
            search_terms,
            minimum_fallback_terms=1,
        )
        if score > 0:
            exact_term_count, bigram_count = _section_specificity(
                section.content,
                search_terms,
            )
            section_matches.append(
                (
                    score,
                    exact_term_count,
                    bigram_count,
                    -section.chunk_index,
                    section,
                    excerpt,
                    matched_fields,
                )
            )

    if section_matches:
        (
            section_score,
            _,
            _,
            _,
            section,
            excerpt,
            matched_fields,
        ) = max(section_matches)
        score = max(ranked.score, section_score)
    else:
        # 标题、标签、文件名或日记元数据命中时使用 Note 级当前快照，不能误绑第一章节。
        section = _whole_note_section(ranked.note.markdown_content)
        score = ranked.score
        excerpt = ranked.matched_excerpt
        matched_fields = ranked.matched_fields

    return KeywordCandidate(
        note_id=ranked.note.pk,
        parent_id=section.parent_id,
        document_type=ranked.document_type,
        title=ranked.note.title,
        heading_path=section.heading_path,
        source_hash=source_hash,
        score=score,
        matched_excerpt=excerpt,
        matched_fields=matched_fields,
        diary_date=ranked.diary_date,
        content=section.content,
        start_line=section.start_line,
        end_line=section.end_line,
    )


def _section_from_parent(parent: RagParentChunk) -> _CandidateSection:
    return _CandidateSection(
        parent_id=str(parent.pk),
        chunk_index=parent.chunk_index,
        heading_path=tuple(parent.heading_path),
        content=parent.content,
        start_line=parent.start_line,
        end_line=parent.end_line,
    )


def _section_specificity(
    content: str,
    search_terms: tuple[str, ...],
) -> tuple[int, int]:
    """Break ties toward sections containing more exact query wording."""

    folded = content.casefold()
    exact_count = sum(
        term.casefold() in folded
        for term in search_terms[1:]
    )
    chinese_bigram_count = sum(
        sum(
            folded.find(term[index:index + 2].casefold()) >= 0
            for index in range(len(term) - 1)
        )
        for term in search_terms[1:]
        if len(term) >= 4 and any(not character.isascii() for character in term)
    )
    return exact_count, chinese_bigram_count


def _temporary_sections(markdown_content: str) -> tuple[_CandidateSection, ...]:
    """按 Markdown 标题构建无需 tokenizer 或持久化索引的临时章节。"""

    blocks = parse_markdown(markdown_content)
    if not blocks:
        return (_whole_note_section(markdown_content),)

    sections = []
    heading_stack: list[tuple[int, str]] = []
    current_blocks = []
    current_path: tuple[str, ...] = ()

    def flush():
        if not current_blocks:
            return
        sections.append(
            _CandidateSection(
                parent_id=None,
                chunk_index=len(sections),
                heading_path=current_path,
                content='\n\n'.join(block.content for block in current_blocks),
                start_line=current_blocks[0].start_line,
                end_line=current_blocks[-1].end_line,
            )
        )
        current_blocks.clear()

    for block in blocks:
        if block.block_type == 'heading':
            flush()
            level = block.heading_level
            assert level is not None
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, extract_heading_title(block)))
            current_path = tuple(title for _, title in heading_stack)
        current_blocks.append(block)
    flush()
    return tuple(sections)


def _whole_note_section(markdown_content: str) -> _CandidateSection:
    return _CandidateSection(
        parent_id=None,
        chunk_index=0,
        heading_path=(),
        content=markdown_content,
        start_line=1,
        end_line=max(1, len(markdown_content.splitlines())),
    )


def _source_hash(markdown_content: str) -> str:
    # 与索引层约定一致，source_hash 只标识完整 Markdown 原文。
    return hashlib.sha256(markdown_content.encode('utf-8')).hexdigest()


def _build_excerpt(value: str, query: str) -> str:
    flattened = ' '.join(value.split())
    position = flattened.casefold().find(query.casefold())
    if position < 0 or len(flattened) <= EXCERPT_LENGTH:
        return flattened[:EXCERPT_LENGTH]

    half = EXCERPT_LENGTH // 2
    start = max(0, position - half)
    end = min(len(flattened), start + EXCERPT_LENGTH)
    if end - start < EXCERPT_LENGTH:
        start = max(0, end - EXCERPT_LENGTH)
    excerpt = flattened[start:end]
    return f"{'…' if start else ''}{excerpt}{'…' if end < len(flattened) else ''}"


def _validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise KeywordSearchError(
            code='keyword_query_empty',
            message='Keyword query must not be empty.',
        )
    normalized = query.strip()
    if len(normalized) > MAX_KEYWORD_QUERY_LENGTH:
        raise KeywordSearchError(
            code='keyword_query_too_long',
            message=f'Keyword query must not exceed {MAX_KEYWORD_QUERY_LENGTH} characters.',
        )
    return normalized


def _validate_types(types: Iterable[DocumentType] | None) -> frozenset[str]:
    if types is None:
        return ALLOWED_DOCUMENT_TYPES
    if isinstance(types, str):
        selected = {types}
    else:
        try:
            selected = set(types)
        except TypeError:
            selected = set()
    if not selected or not selected.issubset(ALLOWED_DOCUMENT_TYPES):
        raise KeywordSearchError(
            code='keyword_types_invalid',
            message='Keyword types must contain note, diary, or both.',
        )
    return frozenset(selected)


def _validate_limit(limit: int):
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_KEYWORD_RESULTS
    ):
        raise KeywordSearchError(
            code='keyword_limit_invalid',
            message=f'Keyword limit must be between 1 and {MAX_KEYWORD_RESULTS}.',
        )


def _validate_tags(tags: Iterable[str] | None) -> tuple[str, ...]:
    if tags is None:
        return ()
    try:
        values = (tags,) if isinstance(tags, str) else tuple(tags)
    except TypeError:
        values = None
    if values is None:
        raise KeywordSearchError(
            code='keyword_tags_invalid',
            message='Keyword tags must contain between 1 and 20 non-empty names.',
        )
    if not values:
        return ()
    try:
        normalized = tuple(dict.fromkeys(tag.strip() for tag in values))
    except AttributeError:
        normalized = ()
    if not normalized or any(not tag for tag in normalized) or len(normalized) > 20:
        raise KeywordSearchError(
            code='keyword_tags_invalid',
            message='Keyword tags must contain between 1 and 20 non-empty names.',
        )
    return normalized


def _validate_date_range(date_from: date | None, date_to: date | None):
    if date_from is not None and not isinstance(date_from, date):
        raise KeywordSearchError(
            code='keyword_date_invalid',
            message='Keyword date_from must be a date.',
        )
    if date_to is not None and not isinstance(date_to, date):
        raise KeywordSearchError(
            code='keyword_date_invalid',
            message='Keyword date_to must be a date.',
        )
    if date_from and date_to and date_from > date_to:
        raise KeywordSearchError(
            code='keyword_date_range_reversed',
            message='Keyword date range must not be reversed.',
        )
