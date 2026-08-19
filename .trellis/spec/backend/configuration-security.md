# Configuration and Security

These rules preserve the backend-only secret boundary and the layered protections already exercised by the authentication, upload, media, and provider tests.

## Configuration Source

- `backend/MoonBirdNotes/settings.py` reads `backend/.env` through `python-decouple` (`Config(RepositoryEnv(BASE_DIR / '.env'))`). The committed inventory and safe example values live in `backend/.env.example`.
- Real `.env` files are ignored; only `.env.example` is tracked. Never copy a real secret into source, tests, docs, frontend variables, logs, or API responses.
- Add each backend setting in both `settings.py` and `.env.example`, with an explicit cast and a safe default only when absence is genuinely supported.
- Keep related setting names grouped by subsystem (`RAG_*`, `QDRANT_*`, `AGENT_*`). Provider factories such as `DeepSeekChatConfig.from_django_settings()` and `SiliconFlowEmbeddingConfig.from_django_settings()` centralize reads and validate them before use.
- Validate external base URLs as absolute HTTP(S) URLs and reject embedded credentials, query strings, and fragments, following `agent/llm/deepseek.py`, `rag/embeddings/siliconflow.py`, and `rag/qdrant.py`.
- Process-wide clients/services use `@lru_cache(maxsize=1)` so HTTP connection pools are reused. Tests that override settings must clear the corresponding cached factory.

## Deployment Configuration

- `DEBUG=False` is the default. Production requires explicit hosts/origins, secure cookies, HTTPS proxy signaling, HSTS, SSL redirect, nosniff, and frame denial as configured in `settings.py`.
- Production must provide `CACHE_URL`; `build_cache_config()` refuses to use process-local throttling state when `DEBUG=False`. `LocMemCache` is development-only.
- `compose.yaml` defines MySQL, Redis, Qdrant, Django web/worker, and the Caddy-hosted frontend. Caddy proxies `/api/*`, `/admin/*`, and `/media/*` to Django; do not serve `/media/` directly and bypass `ProtectedMediaView`.
- Qdrant and embedding/LLM model/version settings are coupled contracts. Changing an embedding model, input template, vector size, collection, or dense threshold requires collection compatibility checks, rebuild planning, and RAG evaluation.

## Authentication and Authorization

- Browser JWTs live in `httpOnly`, `SameSite=Lax` cookies set by `accounts/cookies.py`; JavaScript must not store access or refresh tokens. Authorization headers remain supported for non-browser clients.
- Cookie-authenticated unsafe requests require CSRF. `CookieJWTAuthentication` calls `enforce_csrf()` only for the cookie path; the frontend supplies `X-CSRFToken`.
- Default DRF permission is authenticated, but private domain endpoints explicitly use `IsAdminUser`. Preserve `401` versus `403` behavior and its tests.
- Login failures are intentionally generic for nonexistent, wrong-password, non-admin, inactive users. Login is throttled by client IP using the configured shared cache.
- Refresh tokens rotate and old tokens are blacklisted. Logout clears cookies and attempts to blacklist the refresh token even when the access token is no longer valid.
- `ADMIN_PASSWORD` is only for initial default-superuser creation. `accounts/signals.py` never resets an existing password during `migrate`.

## Content and File Security

- All Markdown-to-HTML writes go through `render_markdown_content()` in `notes/serializers.py`: Markdown extensions render first, then Bleach applies tag/attribute/protocol allowlists and adds `noopener noreferrer` to `_blank` links.
- Never expand the allowlists based only on a generic HTML list. Add the smallest required tag/attribute/protocol and regression tests for scripts, event attributes, unsafe URLs, and link behavior.
- A sanitization-rule change affects stored derived HTML. Add a data migration for existing `Note` and `NoteVersion` rows when needed; migrations `0010`, `0017`, and `0018` are precedents.
- Markdown uploads enforce `.md`, 10 MB, and UTF-8. Images enforce an allowlisted extension/MIME pair, 8 MB, and file-signature bytes; do not trust the browser MIME declaration alone.
- `ProtectedMediaView` resolves the requested path, proves it is below `MEDIA_ROOT`, requires admin access, and returns `404` for traversal/missing files.
- AI indexing permission is per note. Saving queues work; the worker must re-check `is_deleted` and `ai_indexing_enabled` before any external embedding/vector operation.

## Security Verification

At minimum, changes in this area should run the focused security suites:

```bash
python manage.py test accounts.tests notes.tests
python manage.py test agent.test_api agent.llm.tests agent.test_tracing
python manage.py test rag.embeddings.tests rag.test_qdrant rag.test_jobs
```

Also verify `git check-ignore -v backend/.env` and confirm `git ls-files '*env*'` contains the example file, not a real secret file.
