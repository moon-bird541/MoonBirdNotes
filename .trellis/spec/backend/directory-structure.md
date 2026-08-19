# Backend Directory Structure

The backend is divided by runtime ownership: Django project configuration, accounts, canonical note data, derived retrieval, and Agent orchestration.

## Runtime Boundaries

```text
backend/
|-- MoonBirdNotes/       Django settings, root URLs, ASGI/WSGI, protected media
|-- accounts/            admin login, JWT cookies, CSRF authentication, throttling
|-- notes/               source note/diary/tag/image/version data and HTTP APIs
|   |-- services/        reusable note-domain workflows such as trash cleanup
|   `-- management/      scheduled/operational commands
|-- rag/                 chunking, embeddings, Qdrant, retrieval, jobs, evaluation
|   |-- chunking/        Markdown parsing and parent/child chunk contracts
|   |-- embeddings/      provider-neutral interface plus SiliconFlow adapter
|   |-- retrieval/       keyword and hybrid retrieval
|   `-- management/      initialize, rebuild, process, status, and evaluation commands
`-- agent/               conversation, LLM orchestration, tools, tracing, Agent APIs
    |-- agents/          Knowledge Agent loop and result contracts
    |-- llm/             provider-neutral chat types plus DeepSeek adapter
    |-- tools/           strict tool schemas and RAG-backed tool adapter
    `-- management/      conversation-retention command
```

`backend/MoonBirdNotes/urls.py` owns only top-level routing. App URL patterns remain in `accounts/urls.py`, `notes/urls.py`, and `agent/urls.py`.

## Ownership Rules

- `notes` owns canonical user content. `Note.markdown_content` is the source for rendered HTML, word counts, and RAG indexing. `DiaryEntry` reuses a `Note` row but remains a distinct product concept; regular-note querysets explicitly use `diary_entry__isnull=True` in `notes/views.py`.
- `rag` owns all derived retrieval data and external vector-store interaction. `rag/models.py` states that parent chunks, index states, and jobs are rebuildable from notes. Keep Qdrant calls out of `notes` request handlers.
- `agent` owns conversations, model calls, tool orchestration, stable Agent API errors, and redacted run traces. It may consume RAG read/retrieval APIs, but it must not absorb indexing lifecycle code.
- `accounts` owns browser authentication. Cookie creation/clearing belongs in `accounts/cookies.py`; token validation and cookie-specific CSRF enforcement belong in `accounts/authentication.py`.
- Shared workflows earn a focused service module only when reused or operationally independent. `notes/services/trash.py` and `rag/services/__init__.py` are examples. Small domain helpers stay near their callers, as `get_or_create_tags()` and `render_markdown_content()` do in `notes/serializers.py`.
- Scheduled work belongs in a management command, not a GET request. `notes/management/commands/purge_trash.py` and `agent/management/commands/cleanup_agent_conversations.py` are reference examples.

## Tests and Migrations

- Tests are colocated with their Django app. Small apps use `tests.py`; larger areas use focused `test_*.py` modules such as `agent/test_api.py`, `rag/test_jobs.py`, and `rag/retrieval/test_hybrid.py`.
- Django migrations stay under each app's `migrations/` directory and remain sequential. Data migrations such as `notes/migrations/0010_resanitize_rendered_html.py` use `apps.get_model()` rather than importing live models.

## Naming and File Placement

- Use snake_case for Python modules/functions and PascalCase for classes.
- Place DRF request/response contracts in `serializers.py`, HTTP coordination in `views.py`, persistence in `models.py`, and routes in `urls.py`.
- Put provider-neutral interfaces in `base.py` and concrete adapters in provider-named modules. See `agent/llm/base.py` plus `agent/llm/deepseek.py`, and `rag/embeddings/base.py` plus `rag/embeddings/siliconflow.py`.
- Do not put new backend code in the repository root, in `MoonBirdNotes/settings.py`, or in a generic `utils.py` when an owning app/module exists.

## Anti-Patterns

- Do not merge `agent` and `rag`: conversation reasoning and index maintenance have different failure and data-lifecycle boundaries.
- Do not treat diary-backed `Note` rows as regular notes. Preserve the explicit filters used by `get_regular_note_queryset()` and `get_active_diary_entries()`.
- Do not make read endpoints run cleanup, indexing, or other writes. Use transactions, `transaction.on_commit()`, jobs, or management commands.
- Do not introduce a broad service/repository abstraction for one local helper; the existing code favors surgical helpers with clear reuse.
