# Logging Guidelines

Backend logs and run traces carry operational metadata only; private note/conversation content and credentials remain outside both channels.

## Current Pattern

Application modules use the standard library logger scoped to the module:

```python
logger = logging.getLogger(__name__)
logger.info('Knowledge Agent API request completed.', extra={...})
```

There is no project-specific `LOGGING` dictionary in `MoonBirdNotes/settings.py`; deployment controls handlers/formatting. Code should emit stable messages plus structured `extra` fields rather than format large payloads into strings.

Reference implementations:

- `agent/views.py`: one completion log per Agent HTTP request;
- `agent/llm/deepseek.py`: provider request metadata without prompt/key content;
- `agent/tools/knowledge.py`: tool name, outcome, counts, and duration;
- `agent/tracing.py`: redacted diagnostic trace persistence;
- `rag/embeddings/siliconflow.py`: request completion/retry/failure fields;
- `rag/indexing.py` and `rag/retrieval/hybrid.py`: indexing/retrieval outcomes.

## Levels

- `info`: completed request/stage and normal operational metrics such as duration, counts, status, model/version, or run ID.
- `warning`: retry/degraded best-effort behavior where the user operation can continue, such as memory compression or trace persistence failure.
- `error`: terminal operational failure or a 5xx Agent response. Log safe classification fields, not `exc` text that may contain provider material.
- `debug` is not an established project convention; do not depend on it for required diagnostics.

## Allowed Fields

Prefer identifiers and bounded metadata:

- `run_id`, `conversation_id`, `user_id`, `note_id`, job ID;
- HTTP status, stable error code, retryable flag, attempt count;
- duration, tool/source/candidate counts, token counts and usage status;
- provider/model/version names when they are not secret;
- booleans describing availability or completion.

The Agent completion log in `agent/views.py` is the canonical shape: stable message plus `run_id`, status, duration, tool/source counts, error code, and aggregate token usage.

## Never Log

- API keys, JWTs, cookies, CSRF tokens, passwords, or full configuration representations;
- user questions, note/diary Markdown, rendered HTML, answers, conversation history, tool result bodies, or provider raw responses;
- Authorization headers or URLs containing credentials/query secrets;
- raw exception text at an untrusted provider/API boundary.

Provider config `__repr__` methods intentionally render `api_key='***'`; retain and test that behavior (`agent/llm/tests.py`, `rag/embeddings/tests.py`). Token logging uses counts only, as implemented by `AgentTokenUsage` and Agent completion logs.

## Run Traces Are Not Raw Logs

`agent/tracing.py` stores a bounded, user-scoped diagnostic trace with stage names and sanitized metadata. Trace APIs filter by the current user and do not expose prompt/answer/note bodies. When adding trace metadata:

1. pass IDs, counts, timing, hashes, status, and bounded source descriptors only;
2. keep persistence best-effort so cache/database failure cannot fail the answer;
3. update trace redaction/contract tests in `agent/test_tracing.py`.

## Anti-Patterns

- Do not use `print()` for application diagnostics or add per-item logs inside large loops.
- Do not log success at warning/error just to make it visible.
- Do not use `logger.exception()` at provider boundaries unless the full traceback has been proven free of secrets and user content; current sensitive boundaries deliberately avoid it.
- Do not invent a second trace format in a view; use `trace_event()` and the existing completion log.
