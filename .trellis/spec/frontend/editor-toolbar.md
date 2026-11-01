# Editor Toolbar Contract

## 1. Scope / Trigger

Read this contract before changing the editor toolbar, format commands, selection
restoration, callout handling, link/image/table insertion, or sticky editor chrome in
`NoteEditView.vue` and `DiaryEditView.vue`.

MoonBirdNotes deliberately keeps Toast UI's built-in toolbar disabled
(`toolbarItems: []`). There is exactly **one** application-owned toolbar: the sticky
top bar `FixedEditorToolbar.vue`, mounted above the Toast UI body in both editors.

There is no toolbar-mode preference and no selection-anchored floating toolbar. The
former `EDITOR_TOOLBAR_MODES` enum, the `toolbarMode` setting, the
`FloatingFormatToolbar.vue` overlay and the note-side `SideTableToolbar.vue` were all
removed; every insert action lives in the top bar.

## 2. Signatures

`FixedEditorToolbar.vue` accepts:

```js
{
  editorReady: Boolean,
  toolbarState: Object,      // getFixedToolbarSnapshot().state
  selectedText: String,
  headingOptions: Array,
  maxTableRows: Number,
  maxTableColumns: Number,
  activeCallout: String,     // canonical lowercase callout type, '' outside a callout
}
```

It emits only editor-domain data:

```text
command(name, payload?)
apply-heading(level)
insert-link({ linkUrl, linkText })
insert-image
insert-table(rows, columns)
insert-math(displayMode)
insert-callout(kind)
open-code-block-options
apply-code-block-auto-format
remember-selection
```

Buttons that tests address use a stable `data-action` (`callout`, `code-block`,
`code-block-options`, `block-quote`, `bold`, …). The callout button's `aria-label`
switches between `插入提示框` and `修改或取消提示框`, so locating it by accessible name
is fragile.

Parent views map these events to Toast UI 3.2.2 commands: `bold`, `italic`,
`strike`, `code`, `heading`, `blockQuote`, `bulletList`, `orderedList`,
`taskList`, `thematicBreak`, `addLink`, `codeBlock`, and `addTable`. Image
insertion continues through each view's existing authenticated upload path.

`insert-math` and `insert-callout` are **not** Toast UI commands; both are
extension Markdown. Parents write them structurally (see section 8).

## 3. Contracts

- `editorSettings.js` normalizes every read/write and dispatches
  `EDITOR_SETTINGS_CHANGE_EVENT`. A stale `toolbarMode` key from an older build is
  simply ignored (unknown keys are dropped), never resurrected as UI state.
- The toolbar is always mounted, in both editors, with no mode switch in
  `SettingsPanel.vue`.
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
- The toolbar is `position: sticky` with `top: 0`. **No ancestor may compute
  `overflow-y: auto` / `hidden` / `scroll`** — that turns the ancestor into the scroll
  container and the bar scrolls away with the content. `.edit-page` therefore uses
  `overflow-x: clip` (not `hidden`, which forces `overflow-y: auto`).
- The bar has two visual states driven by `IntersectionObserver` on a 1px
  `.fixed-toolbar-sentinel` placed above it (not by a `scroll` listener, which needs
  throttling and breaks inside nested scrollers):
  - at rest: borderless/transparent, flush with the body text;
  - `.is-pinned`: flush against the viewport top, opaque `--overlay-background`,
    hairline bottom border and a soft shadow, so body text slides underneath instead
    of showing through. The background alpha is asserted in
    `e2e/fixed-editor-toolbar.spec.js` — a translucent pinned bar reads as a smudge.
- The single-row track owns `overflow-x: auto` with `scrollbar-width: none`, so the
  page itself never widens and the bar never grows a second row.
- Functional icons must be bundled locally. The fixed toolbar uses the existing
  Element Plus icon package (plus a text glyph for inline code), so controls do
  not become blank when Iconify's remote collection is unavailable.

## 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| editor is not ready | all toolbar controls are disabled; no command emits |
| stale `toolbarMode` key in localStorage | ignore it; the top bar renders as usual |
| link URL empty | keep popover open and show `请输入链接地址` |
| no selected text and link text empty | require link text before insertion |
| explicit link scheme outside http/https/mailto/tel | reject it; relative and anchor URLs remain allowed |
| table exceeds shared row/column constants | parent clamps/rejects through the established table path and shows the existing limit message |
| popover/file chooser moved focus | restore the saved ProseMirror range before mutation |
| callout button clicked while the caret is inside that callout | retype (different kind) or unwrap (same kind); never nest |

## 5. Good / Base / Bad Cases

- Good: select text, open the link popover, enter only the URL, and insert a link
  around the original selection after focus moved into the input.
- Good: place a collapsed caret, toggle italic, type, and receive italic text at
  that caret.
- Base: an older settings object still has `toolbarMode`; the key is dropped and the
  top bar renders as usual.
- Bad: store note content or selection text in localStorage. Toolbar preference
  storage contains settings only.
- Bad: call the notes image API from `FixedEditorToolbar.vue` or duplicate table
  size constants in the component.

## 6. Tests Required

Run `npm run build` and the editor Playwright coverage. Assertions must include:

- the top bar is visible in both note and diary routes, with no
  `.floating-toolbar` / `.editor-side-toolbar` anywhere, and no toolbar-mode switch
  in the settings popover;
- toolbar command results for both editors, an active `aria-pressed` state,
  collapsed-caret formatting, selected-text link insertion, table insertion,
  and the image file-chooser entry;
- sticky positioning, internal horizontal overflow, and no document-level
  horizontal overflow at a narrow viewport;
- the punctuation-selection and empty-note Chinese IME regressions;
- extension authoring: the top bar inserts a real `blockquote` (never literal
  `[!NOTE]` text), the same type toggles it off, a different type retypes it in place
  while keeping a custom title, and the fence options dialog writes `title` / `{1}`
  back into the info-string;
- insertion safety: with a full-document selection every block action wraps the
  selection into that structure, inline actions wrap in place, and an empty selection
  still inserts the placeholder (`e2e/markdown-authoring.spec.js`).

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

## 8. Extension Markdown authoring

Toast UI has no command for callouts, `:::` containers, or fence parameters.
Three rules follow:

1. Never `insertText('> [!NOTE]')`. Toast UI renders `>` as body text and escapes
   the marker, so the note silently stores literal `>[!NOTE]` prose. Build a real
   `blockQuote` node instead (`utils/wysiwygBlocks.js#applyWysiwygCallout`).
2. In-editor preview must be a ProseMirror `Decoration`
   (`utils/editorDecorations.js#createRichBlockPreview`). ProseMirror rebuilds node
   views on every transaction, so hand-appended chips/widgets inside a node view
   are removed — the historical `.inline-code-language-chip` never survived.
3. `Plugin` / `Decoration` must come from the toast-ui plugin `context`
   (`context.pmState`, `context.pmView`). Importing them from the project's own
   prosemirror copy breaks class identity. `eventEmitter` only accepts its built-in
   event types and throws on `listen` for custom names, so widget callbacks are
   passed as closures (`onEditLanguage`, `onEditOptions`), not events.

Fence parameters round-trip through `utils/fenceInfo.js`:

```text
parseFenceInfo(info)  -> { lang, title, showLineNumbers, marks, collapse, … }
buildFenceInfo(state) -> 'js title="a.js" {1} showLineNumbers'
replaceFenceLanguage(info, lang) -> keeps every other token
```

Toast UI stores the **entire** info-string in `codeBlock.attrs.language`, so any
language edit must go through `replaceFenceLanguage`; plain assignment drops
`title`, marks, and collapse ranges.

### One editor only: the rich-text panel

There is **no source/Markdown-textarea mode**. Extension syntax is authored entirely
inside the Toast UI WYSIWYG panel, whose sticky top toolbar carries every insert
action: inline marks, headings, callout picker, block quote, code block, code-block
options, inline/block math, divider, link, image, table.
`NoteEditHeader.vue` therefore exposes only preview/save, no mode switch.

Editing behaviour that the toolbar must honour:

- **Callout toggles.** `utils/wysiwygBlocks.js#applyWysiwygCallout` reads the marker of
  the blockquote under the selection:
  - same type → **unwrap** (delete the marker paragraph, lift the body out);
  - different type → **retype** (replace only the marker text, never wrap again);
  - no blockquote → wrap the selected blocks, or insert a placeholder block.
  The picker marks the active type with a `取消` hint so the same-click-toggles
  behaviour is discoverable.
- **Selection may sit outside the block.** `Ctrl+A` puts `$from` at the document start,
  so `findCalloutAncestor` / `getSelectedCodeBlockInfo` first walk the `$from` ancestor
  chain, then `$to`, then fall back to `doc.nodesBetween(from, to)`. Checking only
  `$from` makes every "select all then click" path silently no-op.
- **Retyping never drops the title.** `retypeCallout` reuses the parsed marker title when
  no new title is passed; otherwise switching 警告 → 提示 silently erases a custom
  heading such as `上线前必看`.
- **The `nodesBetween` fallback takes the first covered block, not `null`.** Returning
  `null` for a document that contains several callouts makes the caller wrap the whole
  selection into a brand-new callout — exactly the nesting this feature removes.
  Touching the first covered callout is bounded and undoable.

### Selected text is wrapped, never replaced

A toolbar button is one click away from `Ctrl+A`. Replacing the selection turns a
harmless click into "the note is gone", and autosave persists it within seconds.
But merely *appending below* the selection is equally wrong: users select a
paragraph because they want **that paragraph** to become the callout/code block.

The rule:

- **Selection + block action** → wrap the selected blocks in the new structure, keeping
  every selected character.
- **Selection + inline action** (`$…$`, `**…**`) → wrap in place.
- **No selection** → insert the placeholder template and select the placeholder
  so the user can type over it.

```js
// wrong: deletes the selection
tr.replaceSelectionWith(quote)
// wrong: silently appends below, so the selection never becomes a callout
tr.insert(selection.to, quote)

// correct: wrap the selected blocks, then insert the marker paragraph
tr.wrap(range, [{ type: blockQuoteType }])
tr.insert(range.start + 1, paragraphType.create(null, schema.text(marker)))
```

Tests: `e2e/markdown-authoring.spec.js` covers wrapping the selection into a callout,
same-type toggle removal, type switching without nesting, the code-block options
dialog, and the fixed toolbar path.

