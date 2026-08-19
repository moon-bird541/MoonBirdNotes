# Database Guidelines

Use these rules for canonical note data, derived RAG data, ORM query shape, concurrency, and historical migrations.

## Storage Roles

- Django ORM with MySQL is the source-of-truth persistence layer. `MoonBirdNotes/settings.py` configures `utf8mb4`; do not bypass the ORM with ad hoc SQL for application features.
- `Note.markdown_content` and note/diary metadata are canonical. `rendered_html`, `word_count`, `RagParentChunk`, Qdrant points, and embedding caches are derived and must remain rebuildable.
- Qdrant access is isolated behind `rag/qdrant.py`. Collection name, named vector, dimension, and version are configuration contracts, not values to duplicate in callers.

## Model Patterns

- Keep relationship names explicit (`related_name='versions'`, `related_name='images'`, `related_name='rag_index_jobs'`) as in `notes/models.py` and `rag/models.py`.
- Put stable ordering, uniqueness, checks, and high-value indexes in model `Meta`. `RagParentChunk` combines a unique constraint, line/version checks, and lookup indexes; job models index their claim paths.
- Use `TextChoices` for persisted state machines. RAG state/job models share `pending`, `indexing`, `completed`, and `failed` values and also enforce valid values at the database layer.
- When overriding `save()`, honor `update_fields`. `Note.save()` refreshes `word_count` only when Markdown can have changed and adds the derived field to `update_fields`.
- File fields represent material resources. Permanent deletion must remove stored files through `notes/services/trash.py` before deleting database rows.

## Query Patterns

- Filter product scope in the database. `notes/views.py` centralizes active/deleted regular-note and active-diary querysets; reuse these helpers rather than filtering after serialization.
- Use `select_related()` for single-valued relationships and `prefetch_related()` for collections. Examples include diary queries loading `note` and `note__tags`, and image queries loading `note__diary_entry`.
- Paginate list endpoints before returning large collections. `NoteListPagination` and `NoteImagePagination` define client-controlled but capped `page_size` values.
- Use database aggregation and annotations for counts/sums. Tag counts and note summaries in `notes/views.py` are the reference; do not restore Python full-table scans.
- Batch lookups and creation. `get_or_create_tags()` queries existing tags once, bulk-creates missing names with `ignore_conflicts=True`, then reloads them in requested order.
- If `QuerySet.update()` bypasses signals, explicitly preserve downstream behavior. Batch delete/restore views call `enqueue_note_ids_on_commit()` because `save` signals do not run.

## Transactions and Background Work

- Wrap multi-row invariants in `transaction.atomic()`: diary plus underlying note creation, tag merges/batch changes, version restores, conversation turn persistence, and RAG job claims all follow this pattern.
- Lock rows with `select_for_update()` when concurrent writers could create duplicate work or activate stale state. `rag/jobs.py` and version restore in `notes/views.py` are reference flows.
- Queue derived work only after successful commit. Use `enqueue_note_index_on_commit()`/`transaction.on_commit()` so a rolled-back note change cannot leave a ghost job.
- Never sleep in an HTTP request to debounce work. `RagIndexJob.available_at` carries debounce/retry scheduling, while a management-command worker processes due jobs.
- Treat source hashes and monotonic index versions as concurrency contracts. Workers stop stale jobs rather than publishing vectors for old content.

## Migrations

1. Change the model, generate a Django migration, and inspect it.
2. Use a separate `RunPython` operation when existing rows need derived-data repair. Historical models must come from the migration `apps` registry.
3. Make reverse behavior explicit. `notes/migrations/0020_enable_ai_indexing_by_default.py` uses a no-op reverse to avoid overwriting later user choices.
4. A rendering, sanitization, word-count, or index-version rule change requires an explicit decision about existing data; changing only the write path produces mixed behavior.

Verification:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test notes rag
```

## Anti-Patterns

- Do not make Qdrant the authority for note content or authorization.
- Do not rely on model `choices` alone for critical persisted state; match the existing database constraints.
- Do not call external embedding/vector services inside a database transaction or user save request.
- Do not import current application models inside historical data migrations.
- Do not hard-delete a note row before preserving the outbox information needed to remove its Qdrant points; `RagIndexDeletionJob` intentionally stores `note_id` without a foreign key.
