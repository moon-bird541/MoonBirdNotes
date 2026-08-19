# State Management

State stays near its consumer and is shared only through the server, router, or the established normalized preference-event modules.

## Current Model

The frontend has no Pinia/Vuex/React Query equivalent. State is deliberately kept near its consumer:

| State kind | Project pattern | Examples |
| --- | --- | --- |
| Component/page UI state | `ref()` / `reactive()` | dialogs, loading flags, forms, editor selections |
| Derived state | `computed()` | `canSend`, pagination, selected counts, theme labels |
| Server state | fetch in route view through `services/` | notes, conversations, token usage, images |
| URL state | Vue Router params/query | note ID, diary date, RAG run ID |
| Persistent preferences | normalized localStorage helper + event | `editorSettings.js`, `theme.js` |
| Authentication UX cache | localStorage user summary + server session check | `services/api.js`, router guard |

## Server State

- Route views own loading/error/data refs and call the shared Axios client or a focused endpoint service.
- Refetch or update local collections after successful mutations. Conversation create/delete reloads the list; note/image/list views recalculate the next valid page after batch changes.
- Do not introduce an implicit global cache. The API remains authoritative; current-user localStorage is only a UI cache and `ensureSession()` verifies the cookie-backed server session.
- Deduplicate only requests with a demonstrated concurrency problem. `api.js` shares one in-flight refresh request and one in-flight session request to prevent refresh storms.
- Keep long-request exceptions explicit. Standard API timeout is 10 seconds; Knowledge Agent chat deliberately opts into 95 seconds in `knowledgeChat.js`.

## Persistent Preferences

`src/utils/editorSettings.js` is the reference pattern:

1. define one storage key, defaults, and bounds;
2. parse defensively and return defaults for malformed storage;
3. normalize all writes;
4. emit a named `CustomEvent` carrying the normalized value;
5. listeners import the event constant and unregister on unmount.

Theme state follows the same shape in `src/utils/theme.js`: validated values, resolved effective theme, one DOM application function, one event contract.

Do not create page-specific localStorage keys for settings already owned by these modules. Never put JWT access/refresh tokens or private note content in localStorage.

## URL and Navigation State

- Use named routes with typed-by-convention params objects, as `openSource()` in `KnowledgeChatView.vue` does for diary dates versus note IDs.
- Shareable/navigation-defining state belongs in the route (`/diary/:date`, `/notes/:id`, `?run=...`), not an invisible global variable.
- Router guards call `ensureSession()` and redirect based on `requiresAuth`/`guestOnly`; views should not duplicate the global guard.

## Timers, Watchers, and DOM State

- Debounced searches clear the prior timer before scheduling a new request and clear it at unmount (`GlobalSearchPanel.vue`, `ImageManagementView.vue`, `NoteListView.vue`).
- Auto-save interval ownership stays in the editor view and is rebuilt when normalized editor settings change.
- A watcher should synchronize a clear boundary (prop-to-local form, filters-to-fetch, route-to-view). Avoid watchers for values that are directly computable.
- Third-party editor selections, overlay positions, and drag state are ephemeral DOM state. Keep them in the owning editor view/component and tear down global listeners.

### Third-party editor selection synchronization

Toast UI/ProseMirror has two observable selection states: the browser's native
`Selection` and ProseMirror's `EditorState.selection`. During an IME commit they
can briefly disagree. Dispatching a `TextSelection` that is already equal to the
ProseMirror state does not necessarily repaint a stale native DOM selection.

When normalizing a confirmed input defect, synchronize both states and keep the
guard at the exact editor boundary:

```js
if (event.target !== view.dom || !singlePunctuationPattern.test(event.data || '')) return

requestAnimationFrame(() => {
  // Re-read and verify that the DOM selection still covers exactly the newly
  // inserted punctuation and that the document contains the same text.
  window.getSelection()?.collapseToEnd()
  view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, expectedTo)))
})
```

- Listen only on `input`/`compositionend`; never collapse from generic
  `selectionchange`, mouse, touch, or keyboard-selection events.
- Require `event.target === view.dom`, not `view.dom.contains(event.target)`, so
  punctuation typed into an embedded native input cannot alter the document
  selection.
- Snapshot the expected range, then revalidate range, selected text, and editor
  instance in the animation frame before mutating either state.
- Cancel a superseded/pending animation frame when rebinding or unmounting.
- Browser coverage must include forward and reverse ranges, Chinese and ASCII
  punctuation, UTF-16 text such as emoji, the following character, deliberate
  selections, embedded inputs, and the empty-note IME composition path.

## When to Extract State

Extract to a utility/service only when multiple consumers need the same contract or the code needs independent testing. Add a new store/composable layer only if several routes require shared live state that cannot be represented by server state, URL state, or the established preference-event pattern.

## Anti-Patterns

- A global store for one dialog, one page's filters, or one API response.
- Treating localStorage as the authentication authority or a place for tokens/content.
- Duplicating derived values in mutable refs instead of using `computed()`.
- Unbounded history arrays, repeated refresh requests, or stale timers/listeners after navigation.
- Passing a whole page state object through many components when narrow props/events describe the contract.
