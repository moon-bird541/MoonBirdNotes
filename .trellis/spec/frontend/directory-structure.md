# Frontend Directory Structure

Frontend files are organized by routed views, reusable components, editor-only code, HTTP services, focused utilities, and shared presentation layers.

## Layout

```text
frontend/moonsbirdnotrs_vue/
|-- e2e/                       Playwright routed-flow tests with mocked API routes
|-- public/                    copied-as-is browser assets
|-- src/
|   |-- assets/                imported raster/SVG assets
|   |-- components/            reusable workspace/search/settings/Agent panels
|   |-- editor/
|   |   |-- components/        extracted editor controls, overlays, and dialogs
|   |   `-- editorHelpers.js   editor-specific pure helpers
|   |-- router/index.js        lazy routes and session guard
|   |-- services/              Axios client and endpoint-specific wrappers
|   |-- styles/markdown.css    shared rendered-Markdown/editor styles
|   |-- utils/                 focused browser/pure helpers, each with `__tests__/`
|   |-- views/                 route-level pages and feature orchestration
|   |-- App.vue                route transition host
|   |-- main.js                app bootstrap and Element Plus registration
|   `-- style.css              global tokens, base styles, library overrides
|-- playwright.config.js
|-- vitest.config.js           jsdom unit-test runner for src/**/__tests__/
|-- vite.config.js
`-- package.json
```

## Placement Rules

- Route pages live in `src/views/` and are lazy-loaded from `src/router/index.js`. Add route metadata (`requiresAuth` or `guestOnly`) consistently.
- Reusable UI shared across routes lives in `src/components/`. `WorkspaceShell.vue`, `GlobalSearchPanel.vue`, and Agent trace/history panels are reference components.
- Editor-only UI lives under `src/editor/`. Keep Toast UI/ProseMirror DOM coordination in the owning editor view or focused editor helper/component; do not leak it into general utilities.
- HTTP setup belongs in `src/services/api.js`. Add a focused service module when an endpoint family has a real contract, as `services/knowledgeChat.js` does.
- Pure transformations, downloads, local-preference helpers, rendering helpers, and theme helpers live in `src/utils/`. Each module has one clear concern (`highlight.js`, `noteExport.js`, `renderAgentAnswer.js`, `editorSettings.js`, `theme.js`).
- Table behavior is split by concern into four tested modules instead of living in `NoteEditView.vue`: `tableLayout.js` (layout metadata parse/serialize, fit-to-width), `tableResize.js` (drag math for table/row/column), `tableSelection.js` (selection rect and cell lookup), `tableLayoutCss.js` (the per-table `!important` rules). Unit tests live beside them under `src/utils/__tests__/`; `NoteEditView.vue` keeps only DOM orchestration.
- Extension-Markdown helpers are split by concern and must stay in sync with `backend/notes/markdown_extensions.py`: `fenceInfo.js` (info-string parse/build/HTML), `directives.js` (`:::` containers), `richContent.js` (reader callouts/KaTeX), `codeBlockTools.js` (post-sanitize interaction), `editorDecorations.js` (WYSIWYG decoration plugin), `wysiwygBlocks.js` (ProseMirror block insertion + callout toggle), `markdownPreview.js` + `previewSanitizer.js` (editor preview dialog).
- Shared Markdown presentation belongs in `src/styles/markdown.css`; application tokens/global Element Plus overrides belong in `src/style.css`; component-specific CSS stays scoped in its SFC.
- Imported content images belong in `src/assets/`. Use `public/` only when the file must retain a stable public path and is not imported by JavaScript.

## Naming and Imports

- Vue components/views use PascalCase filenames; JavaScript modules/functions/variables use camelCase; constants use uppercase snake case.
- SFC imports use relative paths and group framework/library imports before local components/services/utilities, as shown in `KnowledgeChatView.vue` and `NoteDetailView.vue`.
- Keep one router instance and one primary Axios client. Do not create page-local clients or duplicate route definitions.

## Current Boundaries

- There is no `store/` or `composables/` directory. Do not create one for a single value or one page. Extract only after shared behavior and lifecycle ownership are clear.
- Format is per module: tested pure helper → `src/utils/<concern>.js` + `src/utils/__tests__/<concern>.test.js`; reusable UI → `src/components/`; editor-only UI → `src/editor/components/`. A route view should not own logic that has no DOM dependency.
- Several views are intentionally feature-rich (`NoteEditView.vue`, `DiaryEditView.vue`, `NoteListView.vue`). Extracting a component must preserve the existing DOM/visual hierarchy and behavior; editor components show the established extraction style.
- `HelloWorld.vue` is starter residue and not a reference for new product UI.

## Anti-Patterns

- Do not put API calls or localStorage parsing directly into reusable presentational editor components.
- Do not put reusable domain transformations into a route view when a focused existing utility/service owns the concern.
- Do not add a generic `helpers.js`, page-local Axios instance, or global event name string when an owning module/constant exists.
- Do not wrap every extracted component in a new card/surface. Component boundaries are code boundaries, not automatic visual containers.
