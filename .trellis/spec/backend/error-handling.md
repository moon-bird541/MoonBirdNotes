# Error Handling

MoonBirdNotes validates inputs at DRF/domain boundaries and exposes stable, sanitized failures rather than provider or infrastructure details.

## Validate at the Boundary

- Use DRF serializers for request shape, field limits, and normalization. `agent/serializers.py` rejects unknown fields and implicit number-to-string conversion; `notes/serializers.py` validates titles, tag counts, file sizes, MIME/extension pairs, and image magic bytes.
- Use `serializer.is_valid(raise_exception=True)` when the standard DRF field-error response is the contract.
- For small view-only parameters, return field-keyed errors such as `{'note_ids': ['...']}` with an explicit 4xx status. Date helpers in `notes/views.py` raise `DRFValidationError` with field names.
- Fetch objects from a queryset that already encodes allowed state. Version restore, trash, and note detail endpoints use active/deleted and diary/regular filters with `get_object_or_404()`.

## Error Contracts

The notes/accounts APIs mostly use DRF conventions:

- Field validation: `{ "field": ["message"] }`
- General failure or operation result: `{ "detail": "message" }`
- Status codes are explicit (`400`, `401`, `403`, `404`, `429`, and operation-specific success codes).

The Knowledge Agent API has a stricter public envelope in `agent/views.py`:

```json
{
  "error": {
    "code": "llm_transport_error",
    "message": "The language model is temporarily unavailable.",
    "retryable": true
  },
  "run_id": "..."
}
```

Keep `AGENT_ERROR_RESPONSES`/`HTTP_ERROR_RESPONSES` as the mapping from internal codes to safe HTTP status/message values. Provider response text, keys, URLs with credentials, and local paths must never enter the response.

## Domain and Integration Exceptions

- Integration layers use typed exceptions carrying a stable `code` and `retryable` flag: `ChatModelError`, `EmbeddingServiceError`, `QdrantStoreError`, `NoteIndexingError`, and `KnowledgeAgentError`.
- Validate configuration and inputs before network calls. Provider adapters distinguish configuration/input failures from transport/provider/response failures.
- Normalize lower-level failures at the owning boundary. `_normalize_indexing_error()` in `rag/indexing.py` preserves known codes and converts unknown exceptions to a generic non-sensitive error.
- Use `raise ... from None` when a parse/validation exception would otherwise leak noisy provider internals to the caller.
- Management commands catch domain exceptions and raise `CommandError` with the safe code/message; see `initialize_qdrant.py` and `rebuild_rag_index.py`.

## Broad Exception Handling

A broad `except Exception` is allowed only at an operational boundary where it has a documented fallback:

- `KnowledgeChatView` records a failed turn and returns `internal_error` without logging the raw exception.
- Conversation-memory compression logs a redacted warning but does not fail an already completed answer.
- Index cleanup can mark `cleanup_pending` after the new version is active.
- Trace persistence is best-effort and must not break the user request.

Do not silently swallow exceptions in core validation or transformation code. Convert them to the local typed error or let tests expose the bug.

## Retry Rules

- Retry only failures marked retryable and bound attempts/backoff by configuration. DeepSeek, SiliconFlow, and the RAG job worker are reference implementations.
- Do not retry invalid input, malformed provider responses, collection-schema mismatches, or authorization failures.
- Record stable error codes in state/job/conversation records; do not persist raw secret-bearing exception strings.

## Tests

Test the contract, not merely that an exception occurred:

- exact status and field/envelope shape;
- `retryable` mapping and stable error code;
- no provider input or API key in logs/responses;
- transaction rollback or failed-turn/job state;
- authorization returns `401` for anonymous and `403` for authenticated non-admin users.

Reference tests: `accounts/tests.py`, `notes/tests.py`, `agent/test_api.py`, `agent/llm/tests.py`, `rag/embeddings/tests.py`, and `rag/test_jobs.py`.
