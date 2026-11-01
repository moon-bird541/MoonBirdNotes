# Frontend Quality Guidelines

The current frontend gate combines a Vite production build, Vitest unit tests for pure logic, and Playwright coverage for authenticated routed flows and API contracts.

## Required Checks

From `frontend/moonsbirdnotrs_vue/`:

```bash
npm run test:unit
npm run build
npm run test:e2e
```

`npm run test:unit` runs Vitest with the jsdom environment (`vitest.config.js`) over `src/**/__tests__/**/*.test.js`. `npm run build` remains the syntax/import/bundle gate. Neither of them replaces focused manual reasoning in the high-risk areas listed below; there is still no lint or TypeScript-check script.

## Unit Test Conventions

Unit tests cover only what can be asserted without a real browser or backend:

- pure parsing/serialization (`utils/fenceInfo.js`, `utils/tableLayout.js`, `utils/tableResize.js`, `utils/tableSelection.js`);
- HTML generation and its sanitization contract (`utils/tableLayoutCss.js`, `utils/markdownPreview.js`, `utils/previewSanitizer.js`, `utils/renderAgentAnswer.js`);
- small DOM-shaped logic that jsdom reproduces faithfully.

Rules:

- Import from the module under test, not from a copy; never re-implement behavior in the test.
- Prefer asserting observable contracts (returned structure, escaped output, clamped sizes) over internal call order.
- Keep `assert` from `node:assert/strict` plus `describe`/`it` from `vitest`; do not add a second assertion library.
- If a case genuinely needs the toast-ui / ProseMirror editor or a live API, write it in `e2e/` instead of contorting the unit test.
- When extracting logic out of a giant view, move the code into `src/utils/` first and cover it there; the view keeps only DOM orchestration.

Extracted modules so far: `tableResize.js` (drag math), `tableSelection.js` (selection rect and cell lookup), `tableLayoutCss.js` (per-table `!important` rules), all consumed by `NoteEditView.vue`.

## Playwright Conventions

`e2e/workspace.spec.js` and `e2e/knowledge-source-navigation.spec.js` establish the current network, fixture, and navigation patterns:

- mock `**/api/**` at the browser network boundary;
- branch on URL pathname and HTTP method;
- return exact JSON shapes through a small `fulfillJson()` helper;
- fail unexpected requests with a descriptive mocked `404`;
- use semantic locators exposed by roles, labels, and input hints instead of brittle CSS selectors;
- assert URL transitions and visible user outcomes, plus request payloads when contract-sensitive;
- keep tests independent so `fullyParallel: true` remains valid.

`workspace.spec.js` also installs a `pageerror` listener and asserts the collected list is empty after each test. New spec files should install the same guard rather than assuming hooks declared in another spec file apply globally.

Repeated display values need a scoped locator. A metric such as `1,200` can legitimately appear in both a summary and a history row; scope the assertion to the named region/row, or assert the intended count explicitly, so Playwright strict mode does not turn valid duplicate text into an ambiguous match.

Add/update a routed-flow test for authentication, route guards, navigation semantics, cross-page contracts, or a critical API response shape. Pure helpers belong in `src/**/__tests__/` instead; only reach for E2E when the browser or the API is genuinely part of the contract.

## Review Checklist

- Is state owned by the narrowest page/component/service/preference module?
- Are API calls using the shared client, with correct timeout, payload, and 401/CSRF behavior?
- Are loading, empty, disabled, success, and error states understandable?
- Are all `v-html`/dynamic DOM writes backed by the explicit sanitization contract?
- Are props/events declared, defaults safe, and derived values computed rather than duplicated?
- Are document/window listeners, observers, object URLs, editors, intervals, and timeouts cleaned up?
- Can the flow be operated by keyboard and identified by role/label? Are icon-only controls named?
- Does the page preserve the old-desk tokens, visual hierarchy, reduced motion, and mobile overflow behavior?
- If an API enum/shape changed, were all views, services, router behavior, and Playwright fixtures updated?

## High-Risk Areas

- `NoteEditView.vue` and `DiaryEditView.vue`: third-party editor DOM, selection, tables, images, auto-save, and many global listeners.
- `services/api.js`: one mistake affects authentication, CSRF, refresh, and every request.
- HTML render paths: `renderAgentAnswer.js`, `FloatingPreview.vue`, and backend-sanitized `rendered_html` sinks.
- Batch pagination/state transitions in note/trash/image lists.
- Agent source navigation, conversation persistence, trace privacy, and long-request error handling.

Changes in these areas need focused manual reasoning plus the build and relevant E2E/backend tests. When table or selection logic changes, `npm run test:unit` also covers the extracted `table*.js` helpers — run it before touching those files.

## Anti-Patterns

- Silencing a build error by removing behavior, weakening a runtime guard, or swallowing a promise rejection without UI state.
- Tests that assert only a mocked value they set themselves without exercising the user flow.
- Arbitrary sleeps in Playwright; wait on requests, URLs, roles, or visible state.
- Unscoped global CSS for a local component, or visual redesign hidden inside a component extraction.
- Copy-pasted API/auth/storage/sanitization logic instead of the established service/utility.
