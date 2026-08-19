# Runtime Contracts in JavaScript

Because this frontend is JavaScript-only, reliable boundaries come from runtime props, normalization, API contracts, and observable tests.

## Baseline

The frontend is plain JavaScript (`.js` and `.vue`); `package.json` has no TypeScript compiler or type-check script. Do not write TypeScript syntax, claim compile-time guarantees, or create `.ts` files without an explicit project migration.

Type safety here comes from narrow runtime contracts, normalization, backend validation, and tests.

## Component Contracts

- Use object-form `defineProps()` with `type`, `required`, and `default` for reusable components. Use factory defaults for arrays/objects.
- Declare all emitted event names with `defineEmits()`; use `update:visible` style events for controlled values.
- Normalize optional API values before rendering: `response.data.results || []`, `Boolean(...)`, `Number(value || 0)`, nullish fallback for token counts, and optional chaining are established patterns.
- Do not mutate a server response into several incompatible shapes. Map it once at the boundary, as `KnowledgeChatView.vue` maps persisted turns into display messages.

## API Contracts

- Keep endpoint construction and request payloads in `src/services/` when reused. `knowledgeChat.js` defines the 12-message client history cap and chooses either trusted persisted `conversation_id` or bounded client history.
- Treat DRF response shapes as explicit contracts. Playwright fixtures in `e2e/workspace.spec.js` and `e2e/knowledge-source-navigation.spec.js` are useful examples of required fields for route flows.
- Preserve field meaning across layers: Agent errors use `error.code`; pagination uses `count/next/previous/results`; sources use `type`, `note_id`, and diary sources require `diary_date`.
- When a response can be a Blob or JSON error, branch on runtime type before parsing, as `getNoteExportErrorDetail()` does.

## Validation and Normalization

- Validate persisted browser input on read and write. `editorSettings.js` clamps finite numbers and falls back to defaults; `theme.js` checks membership in `THEMES`.
- Validate user input before sending when it improves feedback, but do not assume frontend validation replaces the backend serializer.
- Use constants for storage keys, event names, bounds, and known values. Import those constants rather than repeating strings.
- Keep pure transformations deterministic and side-effect free (`highlight.js`, table-layout helpers, conversation-history shaping).

## Dynamic DOM and Third-Party Data

- DOM nodes from Toast UI/ProseMirror need explicit null/capability checks before access.
- HTML strings are not ordinary strings: only hand them to `v-html` through the trust/sanitization paths in [API and Security](./api-and-security.md).
- Use `textContent`, not HTML attributes/concatenation, when copying or reading code text (`KnowledgeChatView.vue`).

## Anti-Patterns

- Adding JSDoc/TypeScript-style casts solely to silence uncertainty without runtime validation.
- Assuming optional nested fields always exist or using non-null assertions (not supported in this JavaScript codebase).
- Passing arbitrary objects as component props when a small explicit contract is available.
- Quietly accepting new enum/status/source types without updating rendering, navigation, and Playwright fixtures.
- Duplicating backend validation logic as the sole security boundary.
