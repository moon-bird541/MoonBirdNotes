# Frontend Quality Guidelines

The current frontend gate combines a Vite production build with Playwright coverage for authenticated routed flows and API contracts.

## Required Checks

From `frontend/moonsbirdnotrs_vue/`:

```bash
npm run build
npm run test:e2e
```

The production build is the current syntax/import/bundle gate. The repository does not define lint, unit-test, or TypeScript-check scripts; do not report those as passing unless tooling is deliberately added.

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

Add/update a routed-flow test for authentication, route guards, navigation semantics, cross-page contracts, or a critical API response shape. Unit-level pure helpers currently have no configured runner; keep them small and exercise their important output through build/E2E or add test tooling only as a scoped task.

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

Changes in these areas need focused manual reasoning plus the build and relevant E2E/backend tests.

## Anti-Patterns

- Silencing a build error by removing behavior, weakening a runtime guard, or swallowing a promise rejection without UI state.
- Tests that assert only a mocked value they set themselves without exercising the user flow.
- Arbitrary sleeps in Playwright; wait on requests, URLs, roles, or visible state.
- Unscoped global CSS for a local component, or visual redesign hidden inside a component extraction.
- Copy-pasted API/auth/storage/sanitization logic instead of the established service/utility.
