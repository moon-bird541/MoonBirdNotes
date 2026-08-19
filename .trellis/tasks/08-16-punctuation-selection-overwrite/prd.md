# Fix punctuation selection overwrite

## Goal

Fix the note WYSIWYG editor so punctuation input leaves the caret collapsed after
the inserted punctuation. The next character must append normally instead of
replacing the punctuation.

## Background and confirmed facts

- The user observes that entering punctuation automatically selects that
  punctuation; the next typed character overwrites it.
- Cross-session history `019fd783-c762-7901-a28d-1783b8602826` shows this was the
  second editor bug reported after the empty-note Chinese IME bug.
- The first bug was fixed in
  `frontend/moonsbirdnotrs_vue/src/views/NoteEditView.vue` by replacing Toast UI's
  editable placeholder widget with a CSS placeholder. That existing uncommitted
  change must be preserved.
- The note editor listens to Toast UI `caretChange`, document `selectionchange`,
  and editor `keyup`/mouse/touch events to remember selections and synchronize
  the floating toolbar. The bug must be fixed without collapsing deliberate user
  selections.
- `DiaryEditView.vue` has a similar editor but was not part of the original bug
  report. It is comparison evidence, not an automatic change target.

## Requirements

1. After Chinese or ASCII punctuation is inserted into ordinary note text, the
   ProseMirror selection is collapsed immediately after the new punctuation.
2. Typing the next letter or Chinese character appends after the punctuation and
   does not replace it.
3. Any normalization must be limited to a real text-input/composition path. It
   must not collapse a selection created deliberately with mouse, touch, or
   keyboard selection commands.
4. Preserve the existing empty-note IME placeholder fix: entering the first
   Chinese character must not restore the stray Latin composition prefix.
5. Preserve selection-based formatting, the floating toolbar, table/image
   controls, and saved Markdown behavior.
6. Keep the change local to the smallest editor boundary that reproduces the
   defect. Do not refactor the editor or alter backend contracts.

## Technical notes

- Primary file: `frontend/moonsbirdnotrs_vue/src/views/NoteEditView.vue`.
- Relevant current paths include `handleSelectionCommit`, the Toast UI
  `caretChange` handler, `handleDocumentSelection`, and the ProseMirror WYSIWYG
  view available as `editorInstance.wwEditor.view`.
- Reproduce and validate in a real browser. A build-only check cannot prove the
  caret/selection behavior.
- Add a focused Playwright regression when the behavior can be represented with
  browser text insertion and selection inspection; avoid a test that only mocks
  the selection state it asserts.

## Out of scope

- General editor refactoring or extraction.
- Changes to backend note APIs, persistence, autosave, tables, images, or format
  commands.
- Diary editor changes unless reproduction demonstrates the same root cause and
  the same minimal fix is required there.
- Fixing unrelated existing Playwright or Element Plus warnings.

## Acceptance criteria

- [x] In a normal note paragraph, entering `，。！？；：` or `,.!?;:` does not
  leave the inserted punctuation selected.
- [x] After entering `你好，`, typing `世界` yields `你好，世界`; the comma is
  retained.
- [x] The editor selection reports `from === to` after punctuation input.
- [x] Deliberately selecting existing text still produces a non-empty selection
  and keeps the floating formatting toolbar usable.
- [x] Empty-note Chinese IME input still avoids the stray Latin prefix fixed in
  the earlier session.
- [x] A focused browser regression passes, or the task records why the platform
  cannot synthesize the relevant IME path and provides an equivalent verified
  browser reproduction.
- [x] `npm run build` passes.

## Bug retrospective

### 1. Root cause category

- **Category E — Implicit assumption**: browser DOM selection and ProseMirror
  state selection were assumed to update atomically after an IME punctuation
  commit. On Windows they can diverge, leaving the inserted punctuation selected
  in the DOM while ProseMirror already reports a collapsed caret.

### 2. Why the first fix was incomplete

1. The initial guarded `TextSelection` dispatch addressed the visible symptom
   when ProseMirror had observed the DOM range.
2. Cold-start repeated regression exposed the missing case: dispatching a
   selection equal to ProseMirror's current selection may not repaint the stale
   browser selection.
3. The final fix collapses the validated DOM range and synchronizes the
   ProseMirror transaction, covering either observation order.

### 3. Prevention mechanisms

| Priority | Mechanism | Specific action | Status |
| --- | --- | --- | --- |
| P0 | Runtime guard | Revalidate event target, range, document text, and editor instance before collapsing both selection states | Done |
| P0 | Browser test | Exercise all supported punctuation, following text, reverse ranges, emoji, deliberate selections, embedded inputs, and empty-note IME | Done |
| P1 | Specification | Record the dual-selection synchronization contract in frontend state management guidance | Done |

### 4. Systematic expansion

- `DiaryEditView.vue` also embeds Toast UI, but it was not changed because the
  reported defect and verified reproduction are note-editor-specific.
- Future third-party-editor fixes must distinguish native DOM state from library
  state and test the full event/paint boundary rather than only the library API.

## Verification

- 2026-08-16: focused anomalous-selection case repeated 5 times in system Edge,
  all passed.
- 2026-08-16: `note-punctuation-selection.spec.js` passed 4/4 in system Edge
  with one worker.
- 2026-08-16: `npm run build` passed (1,749 modules transformed).
- Playwright cannot open the Windows system IME candidate window. The suite uses
  real DOM `input`/`compositionend` events plus CDP composition for the closest
  reproducible browser boundary; one manual Windows IME smoke test remains
  recommended after checkout.

## Artifact status

- Lightweight bug task: PRD-only planning is sufficient.
- No unresolved product or scope decisions remain.
