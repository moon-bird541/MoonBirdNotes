# Editor Toolbar Contract

## 1. Scope / Trigger

Read this contract before changing toolbar modes, editor format commands, selection
restoration, link/image/table insertion, or sticky editor chrome in
`NoteEditView.vue` and `DiaryEditView.vue`.

MoonBirdNotes deliberately keeps Toast UI's built-in toolbar disabled
(`toolbarItems: []`). The current selection toolbar and the shared fixed toolbar
are application-owned UI over the same Toast UI/ProseMirror document.

## 2. Signatures

The persisted preference is a closed enum:

```js
EDITOR_TOOLBAR_MODES = {
  CURRENT: 'current',
  FIXED: 'fixed',
}

DEFAULT_EDITOR_SETTINGS.toolbarMode = EDITOR_TOOLBAR_MODES.CURRENT
```

`FixedEditorToolbar.vue` accepts:

```js
{
  editorReady: Boolean,
  toolbarState: Object,
  selectedText: String,
  headingOptions: Array,
  maxTableRows: Number,
  maxTableColumns: Number,
}
```

It emits only editor-domain data:

```text
command(name, payload?)
apply-heading(level)
insert-link({ linkUrl, linkText })
insert-image
insert-table(rows, columns)
remember-selection
```

Parent views map these events to Toast UI 3.2.2 commands: `bold`, `italic`,
`strike`, `code`, `heading`, `blockQuote`, `bulletList`, `orderedList`,
`taskList`, `thematicBreak`, `addLink`, `codeBlock`, and `addTable`. Image
insertion continues through each view's existing authenticated upload path.

## 3. Contracts

- `editorSettings.js` normalizes every read/write. Missing or unknown
  `toolbarMode` values become `current`; writes preserve and normalize the other
  editor settings before dispatching `EDITOR_SETTINGS_CHANGE_EVENT`.
- `current` keeps the existing selection-based toolbar and independent image /
  table controls. `fixed` hides those controls and mounts one
  `FixedEditorToolbar` immediately above the Toast UI body.
- The shared toolbar owns presentation, popovers, field validation, and table
  size selection only. It must not import the notes API, read localStorage, or
  hold a Toast UI instance. `NoteEditView` and `DiaryEditView` own editor/API/
  Markdown side effects.
- `getFixedToolbarSnapshot(view)` returns `{ range, selectedText, state }` for
  both a non-empty selection and a collapsed caret. At a caret it reads stored
  marks / `$from.marks()` plus ancestor blocks; across selected text it exposes
  partial (`active`) and complete (`full`) state.
- Every toolbar button emits `remember-selection` on `mousedown.prevent`.
  Parents save the ProseMirror `[from, to]`, including `from === to`, and restore
  it before commands whose popover or file chooser moved browser focus.
- The fixed toolbar is `position: sticky`. Its outer surface must not be placed
  under an overflow-clipping ancestor; clip the editor body in a separate inner
  wrapper. The single-row track owns `overflow-x: auto` so the page itself never
  widens.
- Functional icons must be bundled locally. The fixed toolbar uses the existing
  Element Plus icon package (plus a text glyph for inline code), so controls do
  not become blank when Iconify's remote collection is unavailable.

## 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| editor is not ready | all toolbar controls are disabled; no command emits |
| stored mode missing/invalid/malformed | render `current`; do not throw |
| link URL empty | keep popover open and show `请输入链接地址` |
| no selected text and link text empty | require link text before insertion |
| explicit link scheme outside http/https/mailto/tel | reject it; relative and anchor URLs remain allowed |
| table exceeds shared row/column constants | parent clamps/rejects through the established table path and shows the existing limit message |
| popover/file chooser moved focus | restore the saved ProseMirror range before mutation |
| mode changes while floating controls are open | close/hide controls from the previous mode immediately |

## 5. Good / Base / Bad Cases

- Good: select text, open the link popover, enter only the URL, and insert a link
  around the original selection after focus moved into the input.
- Good: place a collapsed caret, toggle italic, type, and receive italic text at
  that caret.
- Base: an older settings object has no `toolbarMode`; both editors retain the
  familiar current toolbar.
- Bad: store note content or selection text in localStorage. Toolbar preference
  storage contains settings only.
- Bad: call the notes image API from `FixedEditorToolbar.vue` or duplicate table
  size constants in the component.

## 6. Tests Required

Run `npm run build` and the editor Playwright coverage. Assertions must include:

- setting `current -> fixed -> current`, normalized persistence, and live change
  in both note and diary routes;
- current mode's selection toolbar and note-side insertion controls remain
  available;
- fixed mode command results for both editors, an active `aria-pressed` state,
  collapsed-caret formatting, selected-text link insertion, table insertion,
  and the image file-chooser entry;
- sticky positioning, internal horizontal overflow, and no document-level
  horizontal overflow at a narrow viewport;
- the punctuation-selection and empty-note Chinese IME regressions.

All new E2E specs must keep the project `pageerror` guard and fail unexpected
mocked API requests descriptively.

## 7. Wrong vs Correct

Wrong: let a popover erase the editor selection, then execute against the new
browser focus.

```js
const insertLink = (payload) => editor.exec('addLink', payload)
```

Correct: remember the editor range on pointer-down, restore the bounded range,
then execute and refresh Markdown/toolbar state in the owning view.

```js
const insertLink = (payload) => {
  restoreFixedToolbarSelection()
  editorInstance.exec('addLink', payload)
  syncAfterFixedToolbarCommand()
}
```

