"""Qdrant 连接、Collection 契约与子片段 Point 读写边界。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ApiException


PROVIDER_NAME = 'qdrant'
DocumentType = Literal['note', 'diary']
PointId = int | str | UUID

PAYLOAD_INDEXES = {
    'note_id': models.PayloadSchemaType.INTEGER,
    'parent_id': models.PayloadSchemaType.KEYWORD,
    'type': models.PayloadSchemaType.KEYWORD,
    'tags': models.PayloadSchemaType.KEYWORD,
    'diary_date': models.PayloadSchemaType.DATETIME,
    'source_hash': models.PayloadSchemaType.KEYWORD,
    'index_version': models.PayloadSchemaType.INTEGER,
    'embedding_version': models.PayloadSchemaType.KEYWORD,
}


class QdrantStoreError(RuntimeError):
    """Qdrant 访问层统一、可安全写入日志或任务状态的异常。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.provider = PROVIDER_NAME
        self.status_code = status_code

    def as_dict(self) -> dict[str, str | bool | int | None]:
        return {
            'code': self.code,
            'message': str(self),
            'retryable': self.retryable,
            'provider': self.provider,
            'status_code': self.status_code,
        }


class QdrantConfigurationError(QdrantStoreError):
    """本地连接参数或 Collection 配置不合法。"""


class QdrantCollectionError(QdrantStoreError):
    """现有 Collection 与当前模型版本契约不一致。"""


class QdrantInputError(QdrantStoreError):
    """Point、Payload、Filter 或向量输入不合法。"""


class QdrantOperationError(QdrantStoreError):
    """独立 Qdrant 服务拒绝请求或当前不可用。"""


@dataclass(frozen=True, slots=True)
class QdrantConfig:
    """独立 Qdrant 服务配置；API Key 不进入 repr。"""

    url: str = 'http://127.0.0.1:6333'
    api_key: str = ''
    collection_name: str = 'moonbird_note_chunks_bge_m3_v1'
    vector_name: str = 'dense'
    vector_size: int = 1024
    timeout_seconds: int = 10

    def __repr__(self) -> str:
        return (
            'QdrantConfig('
            f'url={self.url!r}, api_key={"***" if self.api_key else ""!r}, '
            f'collection_name={self.collection_name!r}, vector_name={self.vector_name!r}, '
            f'vector_size={self.vector_size!r}, timeout_seconds={self.timeout_seconds!r})'
        )

    def __post_init__(self):
        parsed_url = urlsplit(self.url)
        if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
            raise _configuration_error('Qdrant URL must be an absolute HTTP(S) URL.')
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise _configuration_error('Qdrant URL cannot contain credentials, query, or fragment.')
        if not self.collection_name or not self.vector_name:
            raise _configuration_error('Qdrant collection and vector names cannot be empty.')
        if self.vector_size < 1 or self.timeout_seconds < 1:
            raise _configuration_error('Qdrant vector size and timeout must be positive.')

    @classmethod
    def from_django_settings(cls) -> QdrantConfig:
        """集中读取环境配置，并阻止 Embedding 与 Collection 维度分叉。"""

        config = cls(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection_name=settings.QDRANT_COLLECTION,
            vector_name=settings.QDRANT_VECTOR_NAME,
            vector_size=settings.QDRANT_VECTOR_SIZE,
            timeout_seconds=settings.QDRANT_TIMEOUT_SECONDS,
        )
        if config.vector_size != settings.RAG_EMBEDDING_DIMENSION:
            raise _configuration_error(
                'Qdrant vector size must match the configured embedding dimension.'
            )
        return config


@dataclass(frozen=True, slots=True)
class QdrantChunkPayload:
    """Qdrant 子片段 Payload；字段均可从 MySQL 和分块规则重建。"""

    note_id: int
    parent_id: str
    document_type: DocumentType
    title: str
    heading_path: tuple[str, ...]
    tags: tuple[str, ...]
    diary_date: date | None
    chunk_index: int
    content: str
    chunk_hash: str
    source_hash: str
    index_version: int
    embedding_version: str

    def __post_init__(self):
        if not isinstance(self.note_id, int) or isinstance(self.note_id, bool) or self.note_id < 1:
            raise _input_error('Qdrant payload note_id must be a positive integer.')
        _validate_uuid(self.parent_id, field_name='parent_id')
        if not isinstance(self.document_type, str) or self.document_type not in {'note', 'diary'}:
            raise _input_error('Qdrant payload type must be note or diary.')
        if not isinstance(self.title, str) or not self.title.strip():
            raise _input_error('Qdrant payload title cannot be empty.')
        if not isinstance(self.heading_path, tuple):
            raise _input_error('Qdrant payload heading_path must be a tuple.')
        if any(not isinstance(item, str) or not item.strip() for item in self.heading_path):
            raise _input_error('Qdrant payload heading_path must contain non-empty strings.')
        if not isinstance(self.tags, tuple):
            raise _input_error('Qdrant payload tags must be a tuple.')
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise _input_error('Qdrant payload tags must contain non-empty strings.')
        if self.diary_date is not None and not isinstance(self.diary_date, date):
            raise _input_error('Qdrant payload diary_date must be a date.')
        if self.document_type == 'note' and self.diary_date is not None:
            raise _input_error('Note payload cannot contain diary_date.')
        if self.document_type == 'diary' and self.diary_date is None:
            raise _input_error('Diary payload requires diary_date.')
        if self.document_type == 'diary' and self.tags:
            raise _input_error('Diary payload cannot contain note tags.')
        if (
            not isinstance(self.chunk_index, int)
            or isinstance(self.chunk_index, bool)
            or self.chunk_index < 0
        ):
            raise _input_error('Qdrant payload chunk_index must be a non-negative integer.')
        if not isinstance(self.content, str) or not self.content.strip():
            raise _input_error('Qdrant payload content cannot be empty.')
        _validate_sha256(self.chunk_hash, field_name='chunk_hash')
        _validate_sha256(self.source_hash, field_name='source_hash')
        if (
            not isinstance(self.index_version, int)
            or isinstance(self.index_version, bool)
            or self.index_version < 1
        ):
            raise _input_error('Qdrant payload index_version must be a positive integer.')
        if not isinstance(self.embedding_version, str) or not self.embedding_version.strip():
            raise _input_error('Qdrant payload embedding_version cannot be empty.')

    def as_dict(self) -> dict[str, object]:
        return {
            'note_id': self.note_id,
            'parent_id': self.parent_id,
            'type': self.document_type,
            'title': self.title,
            'heading_path': list(self.heading_path),
            'tags': list(self.tags),
            'diary_date': self.diary_date.isoformat() if self.diary_date else None,
            'chunk_index': self.chunk_index,
            'content': self.content,
            'chunk_hash': self.chunk_hash,
            'source_hash': self.source_hash,
            'index_version': self.index_version,
            'embedding_version': self.embedding_version,
        }


@dataclass(frozen=True, slots=True)
class QdrantChunkPoint:
    """一次批量写入中的命名 Dense 向量及其可重建 Payload。"""

    point_id: PointId
    vector: tuple[float, ...]
    payload: QdrantChunkPayload

    def __post_init__(self):
        _validate_point_id(self.point_id)


@dataclass(frozen=True, slots=True)
class QdrantPointFilter:
    """只开放已建立 Payload Index 的确定性过滤字段。"""

    note_id: int | None = None
    parent_id: str | None = None
    document_type: DocumentType | None = None
    tags: tuple[str, ...] = ()
    diary_date_from: date | None = None
    diary_date_to: date | None = None
    source_hash: str | None = None
    index_version: int | None = None
    embedding_version: str | None = None

    def __post_init__(self):
        if self.note_id is not None and (
            not isinstance(self.note_id, int)
            or isinstance(self.note_id, bool)
            or self.note_id < 1
        ):
            raise _input_error('Qdrant filter note_id must be a positive integer.')
        if self.parent_id is not None:
            _validate_uuid(self.parent_id, field_name='parent_id')
        if self.document_type is not None and (
            not isinstance(self.document_type, str)
            or self.document_type not in {'note', 'diary'}
        ):
            raise _input_error('Qdrant filter type must be note or diary.')
        if not isinstance(self.tags, tuple):
            raise _input_error('Qdrant filter tags must be a tuple.')
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise _input_error('Qdrant filter tags must contain non-empty strings.')
        if self.diary_date_from is not None and not isinstance(self.diary_date_from, date):
            raise _input_error('Qdrant filter diary_date_from must be a date.')
        if self.diary_date_to is not None and not isinstance(self.diary_date_to, date):
            raise _input_error('Qdrant filter diary_date_to must be a date.')
        if self.diary_date_from and self.diary_date_to and self.diary_date_from > self.diary_date_to:
            raise _input_error('Qdrant filter diary date range is reversed.')
        if self.source_hash is not None:
            _validate_sha256(self.source_hash, field_name='source_hash')
        if self.index_version is not None and (
            not isinstance(self.index_version, int)
            or isinstance(self.index_version, bool)
            or self.index_version < 1
        ):
            raise _input_error('Qdrant filter index_version must be a positive integer.')
        if self.embedding_version is not None and (
            not isinstance(self.embedding_version, str) or not self.embedding_version.strip()
        ):
            raise _input_error('Qdrant filter embedding_version cannot be empty.')

    def to_qdrant_filter(self) -> models.Filter:
        conditions: list[models.FieldCondition] = []
        match_fields = (
            ('note_id', self.note_id),
            ('parent_id', self.parent_id),
            ('type', self.document_type),
            ('source_hash', self.source_hash),
            ('index_version', self.index_version),
            ('embedding_version', self.embedding_version),
        )
        for field_name, value in match_fields:
            if value is not None:
                conditions.append(
                    models.FieldCondition(key=field_name, match=models.MatchValue(value=value))
                )
        # 数组字段使用多个 must 条件，表示结果必须同时包含全部指定标签。
        conditions.extend(
            models.FieldCondition(key='tags', match=models.MatchValue(value=tag))
            for tag in self.tags
        )
        if self.diary_date_from or self.diary_date_to:
            conditions.append(
                models.FieldCondition(
                    key='diary_date',
                    range=models.DatetimeRange(
                        gte=self.diary_date_from,
                        lte=self.diary_date_to,
                    ),
                )
            )
        return models.Filter(must=conditions)


@dataclass(frozen=True, slots=True)
class QdrantStoredPoint:
    """过滤查询返回的 Point，不向业务层泄漏 qdrant-client 模型。"""

    point_id: PointId
    payload: dict[str, object]
    vector: object | None


@dataclass(frozen=True, slots=True)
class QdrantPointPage:
    """有限数量的过滤查询结果及下一页游标。"""

    points: tuple[QdrantStoredPoint, ...]
    next_offset: PointId | None


@dataclass(frozen=True, slots=True)
class QdrantScoredPoint:
    """Dense 查询结果；只保留融合所需分数和 Payload。"""

    point_id: PointId
    score: float
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class QdrantCollectionSummary:
    """健康检查和初始化命令可安全展示的 Collection 摘要。"""

    collection_name: str
    vector_name: str
    vector_size: int
    distance: str
    payload_indexes: tuple[str, ...]


class QdrantVectorStore:
    """封装 Qdrant Collection 生命周期和子片段 Point 基础操作。"""

    def __init__(self, config: QdrantConfig, *, client: QdrantClient | None = None):
        self.config = config
        self._client = client or QdrantClient(
            url=config.url,
            api_key=config.api_key or None,
            timeout=config.timeout_seconds,
        )
        self._owns_client = client is None

    def close(self):
        if self._owns_client:
            self._client.close()

    def health_check(self) -> bool:
        """执行真实服务请求；连接失败时返回结构化可重试异常。"""

        self._call('health check', self._client.get_collections)
        return True

    def ensure_collection(self) -> QdrantCollectionSummary:
        """幂等创建并严格校验命名向量和 Payload Index。"""

        exists = self._call(
            'collection existence check',
            lambda: self._client.collection_exists(self.config.collection_name),
        )
        if not exists:
            created = self._call(
                'collection creation',
                lambda: self._client.create_collection(
                    collection_name=self.config.collection_name,
                    vectors_config={
                        self.config.vector_name: models.VectorParams(
                            size=self.config.vector_size,
                            distance=models.Distance.COSINE,
                        )
                    },
                ),
            )
            if not created:
                raise _operation_error(
                    'qdrant_collection_create_failed',
                    'Qdrant did not confirm collection creation.',
                    retryable=True,
                )

        collection = self._get_collection()
        self._validate_vector_config(collection)
        self._ensure_payload_indexes(collection)
        collection = self._get_collection()
        self._validate_vector_config(collection)
        self._validate_payload_indexes(collection)
        return self._collection_summary(collection)

    def recreate_collection(self) -> QdrantCollectionSummary:
        """显式删除并重建当前配置版本；调用方必须负责恢复全部派生数据。"""

        exists = self._call(
            'collection existence check before recreation',
            lambda: self._client.collection_exists(self.config.collection_name),
        )
        if exists:
            deleted = self._call(
                'collection deletion for recreation',
                lambda: self._client.delete_collection(self.config.collection_name),
            )
            if not deleted:
                raise _operation_error(
                    'qdrant_collection_delete_failed',
                    'Qdrant did not confirm collection deletion.',
                    retryable=True,
                )
        return self.ensure_collection()

    def upsert_points(self, points: list[QdrantChunkPoint]) -> int:
        """在一次等待完成的请求中批量新增或更新子片段 Point。"""

        if not isinstance(points, list):
            raise _input_error('Qdrant points must be provided as a list.')
        if not points:
            return 0

        point_ids = [point.point_id for point in points]
        if len(set(point_ids)) != len(point_ids):
            raise _input_error('Qdrant point batch contains duplicate point IDs.')

        qdrant_points = []
        for point in points:
            vector = self._validate_vector(point.vector)
            qdrant_points.append(
                models.PointStruct(
                    id=point.point_id,
                    vector={self.config.vector_name: vector},
                    payload=point.payload.as_dict(),
                )
            )

        self._call(
            'point upsert',
            lambda: self._client.upsert(
                collection_name=self.config.collection_name,
                points=qdrant_points,
                wait=True,
            ),
        )
        return len(qdrant_points)

    def delete_note_version(self, *, note_id: int, index_version: int):
        """只删除指定笔记和索引版本，避免误删同笔记的当前或其他版本。"""

        point_filter = QdrantPointFilter(note_id=note_id, index_version=index_version)
        self._call(
            'point deletion',
            lambda: self._client.delete(
                collection_name=self.config.collection_name,
                points_selector=models.FilterSelector(
                    filter=point_filter.to_qdrant_filter(),
                ),
                wait=True,
            ),
        )

    def delete_note(self, *, note_id: int):
        """删除一篇 Note 的全部向量版本，供硬删除或显式移除索引使用。"""

        point_filter = QdrantPointFilter(note_id=note_id)
        self._call(
            'note point deletion',
            lambda: self._client.delete(
                collection_name=self.config.collection_name,
                points_selector=models.FilterSelector(
                    filter=point_filter.to_qdrant_filter(),
                ),
                wait=True,
            ),
        )

    def scroll_points(
        self,
        point_filter: QdrantPointFilter,
        *,
        limit: int = 100,
        offset: PointId | None = None,
        with_vectors: bool = False,
    ) -> QdrantPointPage:
        """使用受控 Payload Filter 分页查询，不开放任意 Qdrant 表达式。"""

        if not isinstance(point_filter, QdrantPointFilter):
            raise _input_error('Qdrant scroll requires a QdrantPointFilter.')
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1000:
            raise _input_error('Qdrant scroll limit must be between 1 and 1000.')
        if offset is not None:
            _validate_point_id(offset)

        records, next_offset = self._call(
            'payload filter query',
            lambda: self._client.scroll(
                collection_name=self.config.collection_name,
                scroll_filter=point_filter.to_qdrant_filter(),
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=[self.config.vector_name] if with_vectors else False,
            ),
        )
        return QdrantPointPage(
            points=tuple(
                QdrantStoredPoint(
                    point_id=record.id,
                    payload=dict(record.payload or {}),
                    vector=record.vector,
                )
                for record in records
            ),
            next_offset=next_offset,
        )

    def search_points(
        self,
        query_vector: tuple[float, ...],
        *,
        point_filter: QdrantPointFilter | None = None,
        limit: int = 20,
        score_threshold: float | None = None,
    ) -> tuple[QdrantScoredPoint, ...]:
        """使用配置的命名 Dense 向量检索，并返回受控结构。"""

        vector = self._validate_vector(query_vector)
        if point_filter is not None and not isinstance(point_filter, QdrantPointFilter):
            raise _input_error('Qdrant search requires a QdrantPointFilter.')
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise _input_error('Qdrant search limit must be between 1 and 1000.')
        if score_threshold is not None and (
            not isinstance(score_threshold, (int, float))
            or isinstance(score_threshold, bool)
            or not math.isfinite(score_threshold)
        ):
            raise _input_error('Qdrant search score threshold must be a finite number.')

        response = self._call(
            'dense vector search',
            lambda: self._client.query_points(
                collection_name=self.config.collection_name,
                query=vector,
                using=self.config.vector_name,
                query_filter=(point_filter or QdrantPointFilter()).to_qdrant_filter(),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            ),
        )
        points = []
        for point in response.points:
            score = float(point.score)
            if not math.isfinite(score):
                raise _operation_error(
                    'qdrant_invalid_response',
                    'Qdrant dense vector search returned an invalid score.',
                    retryable=False,
                )
            points.append(
                QdrantScoredPoint(
                    point_id=point.id,
                    score=score,
                    payload=dict(point.payload or {}),
                )
            )
        return tuple(points)

    def _get_collection(self):
        return self._call(
            'collection inspection',
            lambda: self._client.get_collection(self.config.collection_name),
        )

    def _validate_vector_config(self, collection):
        vectors = collection.config.params.vectors
        if not isinstance(vectors, dict) or set(vectors) != {self.config.vector_name}:
            raise _collection_error('Qdrant collection must contain only the configured named vector.')
        vector = vectors[self.config.vector_name]
        if vector.size != self.config.vector_size or vector.distance != models.Distance.COSINE:
            raise _collection_error('Qdrant collection vector size or distance does not match configuration.')

    def _ensure_payload_indexes(self, collection):
        payload_schema = collection.payload_schema or {}
        for field_name, expected_type in PAYLOAD_INDEXES.items():
            current = payload_schema.get(field_name)
            if current is not None and current.data_type != expected_type:
                raise _collection_error(
                    f'Qdrant payload index {field_name} has an incompatible data type.'
                )
            if current is None:
                self._call(
                    f'payload index creation for {field_name}',
                    lambda field_name=field_name, expected_type=expected_type: (
                        self._client.create_payload_index(
                            collection_name=self.config.collection_name,
                            field_name=field_name,
                            field_schema=expected_type,
                            wait=True,
                        )
                    ),
                )

    def _validate_payload_indexes(self, collection):
        payload_schema = collection.payload_schema or {}
        for field_name, expected_type in PAYLOAD_INDEXES.items():
            current = payload_schema.get(field_name)
            if current is None or current.data_type != expected_type:
                raise _collection_error(
                    f'Qdrant payload index {field_name} is missing or incompatible after initialization.'
                )

    def _collection_summary(self, collection) -> QdrantCollectionSummary:
        vector = collection.config.params.vectors[self.config.vector_name]
        return QdrantCollectionSummary(
            collection_name=self.config.collection_name,
            vector_name=self.config.vector_name,
            vector_size=vector.size,
            distance=vector.distance.value,
            payload_indexes=tuple(sorted(PAYLOAD_INDEXES)),
        )

    def _validate_vector(self, value: tuple[float, ...]) -> list[float]:
        if not isinstance(value, tuple) or len(value) != self.config.vector_size:
            raise _input_error('Qdrant point vector has an invalid dimension.')
        vector = []
        for number in value:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise _input_error('Qdrant point vector contains a non-numeric value.')
            converted = float(number)
            if not math.isfinite(converted):
                raise _input_error('Qdrant point vector contains a non-finite value.')
            vector.append(converted)
        return vector

    def _call(self, operation: str, callback):
        try:
            return callback()
        except ApiException as exc:
            status_code = getattr(exc, 'status_code', None)
            retryable = status_code is None or status_code == 429 or status_code >= 500
            raise _operation_error(
                'qdrant_unavailable' if retryable else 'qdrant_request_rejected',
                f'Qdrant {operation} failed.',
                retryable=retryable,
                status_code=status_code,
            ) from None


def _validate_point_id(point_id: PointId):
    if isinstance(point_id, bool):
        raise _input_error('Qdrant point ID must be a non-negative integer or UUID.')
    if isinstance(point_id, int):
        if point_id < 0:
            raise _input_error('Qdrant point ID must be a non-negative integer or UUID.')
        return
    if isinstance(point_id, UUID):
        return
    if isinstance(point_id, str):
        _validate_uuid(point_id, field_name='point_id')
        return
    raise _input_error('Qdrant point ID must be a non-negative integer or UUID.')


def _validate_uuid(value: str, *, field_name: str):
    if not isinstance(value, str):
        raise _input_error(f'Qdrant {field_name} must be a UUID string.')
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise _input_error(f'Qdrant {field_name} must be a UUID string.') from None


def _validate_sha256(value: str, *, field_name: str):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in '0123456789abcdef' for character in value)
    ):
        raise _input_error(f'Qdrant {field_name} must be a lowercase SHA-256 digest.')


def _configuration_error(message: str) -> QdrantConfigurationError:
    return QdrantConfigurationError(
        code='qdrant_configuration_error',
        message=message,
        retryable=False,
    )


def _collection_error(message: str) -> QdrantCollectionError:
    return QdrantCollectionError(
        code='qdrant_collection_mismatch',
        message=message,
        retryable=False,
    )


def _input_error(message: str) -> QdrantInputError:
    return QdrantInputError(
        code='qdrant_input_error',
        message=message,
        retryable=False,
    )


def _operation_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    status_code: int | None = None,
) -> QdrantOperationError:
    return QdrantOperationError(
        code=code,
        message=message,
        retryable=retryable,
        status_code=status_code,
    )


@lru_cache(maxsize=1)
def get_qdrant_store() -> QdrantVectorStore:
    """返回进程级访问层实例，复用 qdrant-client 的 HTTP 连接池。"""

    return QdrantVectorStore(QdrantConfig.from_django_settings())
