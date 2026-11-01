# API and Security

The browser uses a single cookie-aware Axios boundary and explicit sanitization rules for every dynamic HTML path.

## Shared HTTP Client

`src/services/api.js` is the only general Axios setup:

- `baseURL: '/api'` assumes same-origin deployment or Vite/Caddy proxying;
- `withCredentials: true` sends httpOnly auth cookies;
- the normal timeout is 10 seconds;
- unsafe methods attach the `csrftoken` cookie as `X-CSRFToken`;
- one shared refresh promise prevents concurrent `401` responses from starting a refresh storm;
- a request retries only once (`_retry`) and never refreshes login/logout/refresh calls;
- terminal `401` clears cached user state and redirects to `/login`.

Do not create a page-local Axios client, store JWTs, add bearer headers from localStorage, or bypass the interceptors. `refreshClient` exists only to avoid recursively refreshing its own request.

## Session Model

- JWT access/refresh values are httpOnly cookies and are intentionally unavailable to JavaScript.
- `current_user` localStorage contains only the display/user summary. It is not proof of authentication.
- `ensureSession()` checks `/api/session/`, deduplicates concurrent checks, and is called by the router guard.
- Login stores the returned user summary; logout calls the backend first, then always clears local state and navigates away.

## Service Modules and Errors

- Add thin endpoint wrappers in `src/services/` when several views/actions share a contract. Keep UI messages and router navigation in the view.
- Read DRF field/detail errors only when the screen can present them meaningfully. Otherwise map stable backend codes to calm user-facing text, as `KnowledgeChatView.vue` does for throttling/timeouts.
- Do not display raw `error.message`, provider response text, stack traces, or backend configuration details.
- Blob downloads must parse an error body defensively and always revoke object URLs (`utils/noteExport.js`).

## Safe HTML

There are three established trust paths:

1. Note/version/upload `rendered_html` is generated and Bleach-sanitized by the backend before storage/response. Existing `v-html` uses in `NoteUploadView.vue` and `VersionPreviewDialog.vue` rely on that backend contract.
2. Client-generated or Agent Markdown is untrusted and must be sanitized in the owning helper/component. `renderAgentAnswer.js` runs `marked` then DOMPurify; `FloatingPreview.vue` sanitizes `bodyHtml` before `v-html`.
3. The editor body/source preview (`markdownPreview.js` → `previewSanitizer.js`) renders unsanitized Markdown to HTML; callers must sanitize before `v-html`. `NoteEditView.vue` and `MarkdownSourceEditor.vue` both go through `sanitizePreviewHtml`.

Rules:

- Never bind raw note Markdown, Agent text, user input, or editor HTML directly to `v-html`/`innerHTML`.
- Keep sanitization immediately adjacent to the dangerous sink or in its dedicated renderer; do not rely only on a distant caller.
- Do not weaken DOMPurify forbidden tags/attributes or post-process sanitized HTML with unsanitized user data.
- The code-block toolbar in `renderAgentAnswer.js` is added only after sanitization and copies from `code.textContent`.
- If backend `rendered_html` provenance changes, add frontend sanitization rather than assuming the old contract.
- Extension Markdown helpers (`fenceInfo.js#escapeHtml`, callout labels, code-group labels, fence `title`) always escape interpolated text. Never interpolate raw user text into a generated code block/callout string.
- The reader-side `customHTMLRenderer` output is re-sanitized by the Viewer's own DOMPurify; do not assume generated attributes survive, and do not add `data-*` attributes there. Interactive controls belong in `codeBlockTools.js`, which runs after sanitization.

## Navigation and Private Data

- Navigate Agent sources by declared `type`: diary sources use `diary_date`, notes use `note_id`. Do not infer type from title/content.
- Media URLs remain behind authenticated `/media/` proxying. Do not rewrite them to a public static origin.
- Conversation and trace screens must not add prompts, answers, note bodies, keys, or provider payloads to URLs, localStorage, console logs, or analytics.

## Security Verification

- Run `npm run build` for every change in services/rendering.
- Run `npm run test:e2e` for auth redirects/login/logout and source-navigation contracts.
- Backend security remains part of the same flow: cookie/CSRF and sanitized HTML changes also require the relevant Django tests.
