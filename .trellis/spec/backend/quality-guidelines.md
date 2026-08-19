# Backend Quality Guidelines

Verification is behavior-focused: Django checks, app-scoped tests, cross-app suites, and explicit review of security and data-flow boundaries.

## Change Discipline

- Keep changes inside the owning app and preserve public response/data contracts unless the task explicitly changes them.
- Prefer a small reusable helper over a speculative abstraction. `get_or_create_tags()`, queryset helpers in `notes/views.py`, and typed config factories are current examples.
- Match typing to the local layer. Newer `agent`/`rag` modules use `from __future__ import annotations`, typed dataclasses (often `frozen=True, slots=True`), tuples for immutable results, and explicit protocols/base classes. Do not perform an unrelated typing retrofit in older `accounts`/`notes` code.
- Keep constants for limits/allowed values near the validation that owns them. Do not duplicate upload limits, Agent history limits, index status strings, or provider names across callers.
- Preserve read semantics: GET handlers do not clean trash, rebuild indexes, or mutate state.

## Test Conventions

- Use `SimpleTestCase` for pure logic/configuration that does not touch the database and `TestCase` for ORM/API behavior.
- Use `APIRequestFactory` for isolated view/throttle behavior and `APIClient` when URL routing, authentication, cookies, CSRF, middleware, or final HTTP status is part of the contract. `accounts/tests.py` demonstrates both.
- Use `override_settings()` for configuration branches and clear Django cache/service factories when shared state could leak across tests.
- Mock at external boundaries, not inside the unit under test. Provider tests use `httpx.MockTransport`; API tests patch the Agent entry point; RAG service/worker tests inject fake services/clock functions.
- Assert exact observable contracts: response keys/status, database state, transaction/on-commit effects, error code/retryability, redaction, and call arguments.
- Security tests should prove rejection: XSS removal, upload signature mismatch, anonymous `401`, non-admin `403`, missing CSRF `403`, login throttling `429`, path traversal `404`, and secret-free logs.

## Verification Matrix

From `backend/`:

| Change | Minimum checks |
| --- | --- |
| Settings/auth/cookies | `python manage.py test accounts.tests` |
| Notes, diary, tags, images, versions | `python manage.py test notes.tests` |
| Agent API/LLM/tools/traces | relevant `agent.test_*` and `agent.llm.tests` modules |
| RAG chunking/indexing/jobs/retrieval | relevant `rag.test_*` or subpackage test modules |
| Models/migrations | `python manage.py makemigrations --check --dry-run` plus affected tests |
| Cross-app change | `python manage.py check` and `python manage.py test accounts notes agent rag` |

The repository currently does not configure a Python formatter, linter, or static type-check command. Do not claim those gates ran; rely on Django checks/tests and targeted import/behavior coverage unless tooling is added deliberately.

## Review Checklist

- Does each input cross a serializer/config/domain validation boundary before use?
- Are regular notes, diaries, deleted rows, and per-user Agent records scoped correctly?
- Are query counts/data volume controlled with database filtering, relation loading, aggregation, and pagination?
- Are multi-row changes atomic and derived jobs scheduled only after commit?
- Are source/derived data and MySQL/Qdrant ownership preserved?
- Are errors stable and sanitized, and are logs free of secrets/content?
- Does a rendering/derived-field rule change handle existing data?
- Does every external call have bounded timeout/retry behavior and a typed failure?

## Forbidden Patterns

- Secrets or user content in source, logs, traces, tests, or public error messages.
- Raw `request.data` passed into domain/provider code without validation.
- Python-side full-table filtering/pagination where the ORM can do it.
- External network work in request transactions or signals before commit.
- Broad catches with no explicit fallback, state update, or safe error conversion.
- Product-code refactors bundled into a migration/security/test-only change without a stated need.
