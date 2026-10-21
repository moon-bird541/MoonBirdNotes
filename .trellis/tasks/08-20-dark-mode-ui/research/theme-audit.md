# Dark Theme Audit

## Existing mechanism

- `frontend/moonsbirdnotrs_vue/src/utils/theme.js` owns the persisted `system` / `light` / `dark` preference and applies the effective value through `document.documentElement.dataset.theme`.
- `frontend/moonsbirdnotrs_vue/src/style.css` already exposes the core paper, text, accent, border, and shadow variables for both effective themes.
- Theme behavior is therefore not the defect; incomplete visual token coverage and later hard-coded component styles are the defect.

## Static style findings

A repository scan of Vue and CSS files found 103 fixed light-background declarations across 26 files. The highest concentrations are:

| File | Fixed light surfaces |
| --- | ---: |
| `views/DiaryView.vue` | 23 |
| `views/NoteListView.vue` | 14 |
| `views/NoteDetailView.vue` | 8 |
| `views/KnowledgeChatView.vue` | 6 |
| `views/HomeView.vue` | 6 |
| `editor/components/EditorTableOverlays.vue` | 5 |
| `views/NoteEditView.vue` | 5 |

Only `DiaryView.vue` and the global stylesheet contain meaningful dedicated dark-theme selectors. Several other components start with semantic variables but later visual-tuning blocks replace them with fixed light gradients and text colors.

## Root causes

1. The global `body` background is a fixed light gradient, so the dark root background never becomes the visible page environment.
2. Common concepts such as sidebar, panel, raised panel, control, selected row, editor canvas, code block, and inset highlight have no shared token contract.
3. Screenshot-matched or late-file CSS blocks override earlier token-based declarations in the cascade.
4. Element Plus and Toast UI render internal DOM that needs explicit, namespaced theme mappings.
5. Earlier dark-mode work repaired reader content, code blocks, tables, and dividers one symptom at a time; session `019f110a-fbd6-7ad3-b297-63a484d8bcca` records repeated misses.

## Recommended implementation

Keep `theme.js` unchanged. Expand the semantic variables in `style.css`, migrate component-owned fixed colors to those variables, and use narrow third-party overrides only where variable consumption is impossible. Validate representative pages at desktop and mobile sizes in both light and dark themes.
