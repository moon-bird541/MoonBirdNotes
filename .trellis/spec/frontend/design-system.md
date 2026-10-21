# Frontend Design System

Visible work should extend the existing old-desk writing environment and its global tokens, not introduce a separate dashboard aesthetic.

## Product Character

`FRONTEND_DESIGN_GUIDELINES.md` describes MoonBirdNotes as a quiet, human, old-desk writing tool rather than a generic admin dashboard or marketing page. The current implementation backs that direction in `src/style.css`, `WorkspaceShell.vue`, `HomeView.vue`, and `LoginView.vue`.

For visible changes:

- optimize the real task first: writing quickly, finding old content, understanding failures, and scanning lists;
- preserve clear hierarchy and intentional asymmetry instead of default centered hero/card grids;
- keep copy short, direct, and human; empty/error states should say what happened and what to do next;
- avoid adding a card/background/border to every component or every extracted code boundary.

## Tokens and Color

Use global CSS variables from `src/style.css`:

- ink/paper text and surfaces: `--text-*`, `--paper*`, `--surface*`;
- rust accent: `--accent` and the legacy-named `--brand-blue` (currently rust, not blue);
- moss/gold/danger semantic accents;
- shared borders, shadows, radii, and motion variables.

The palette is old-paper white, ink, warm gray, rust, moss, tea, and muted gold. Do not introduce purple/indigo, blue-purple gradients, Tailwind-default color language, or a flat untextured full-page background. The global body already provides low-contrast gradients/noise and dark-theme equivalents.

Do not opportunistically rename widely used legacy tokens during a feature. New code should prefer the semantic tokens where one exists.

### Dark-theme surface contract

Page and component CSS must consume the shared environment and surface tokens instead of embedding light paper colors. Use `--app-background`/`--sidebar-background` for the frame, `--panel-background*` for content layers, `--overlay-background` for temporary layers, `--control-*` for inputs and interactive states, and the dedicated `--code-*`, `--quote-background`, and `--table-*` tokens for rich content. Both light and dark roots define these tokens, so components must not branch on `data-theme` for ordinary surfaces.

```css
/* Wrong: this remains a white island in dark mode. */
.panel { background: rgba(248, 250, 252, 0.78); }

/* Correct: the same component follows both themes. */
.panel { background: var(--panel-background-soft); }
```

Toast UI Editor/Viewer ships high-specificity heading and code defaults. Override them only inside the owning `.toastui-editor-contents` namespace; headings use `--text-primary`, `pre` uses `--code-background`/`--code-text`, and nested `pre code` must remain transparent with inherited text color. This prevents the editor and reader from reintroducing light code blocks without adding broad global selectors.

For theme-visible work, Playwright must assert immediate switching and stored preference, at least one computed dark surface, a 4.5:1 core text/surface contrast, and no page-level overflow at the 390px viewport. Screenshot representative desktop and mobile routes after their existing entrance transitions settle; animations can otherwise resemble low-contrast theme failures in captures.

## Components and Icons

- Element Plus supplies controls/overlays, but global and scoped overrides give them MoonBird spacing, radii, surfaces, focus, and feedback.
- Iconify is used heavily in the workspace and newer Agent/settings surfaces; established note/editor screens also use Element Plus icons. Match the local surface's icon family and line weight rather than mixing styles within one control group.
- Never use emoji as functional icons. Icon-only controls need a tooltip/title or `aria-label`.
- Images/illustrations must support content and use cases. Brand/desk/landscape assets in `src/assets/` are preferred to arbitrary decorative stock imagery.

## Motion

- Prefer `--motion-snappy` (`cubic-bezier(0.16, 1, 0.3, 1)`) or `--motion-calm` (`cubic-bezier(0.22, 0.61, 0.36, 1)`) with short durations.
- Motion communicates state/navigation; it should not delay work. Global page transitions are subtle opacity changes and `fadeRise` moves only two pixels.
- Preserve the `prefers-reduced-motion` overrides in `src/style.css`. New shared animation needs an equivalent reduced-motion path.

## Responsive and Layout Rules

- Use both `100vh` and `100svh` where full-height mobile browser behavior matters.
- Small screens preserve the primary task rather than squeezing the desktop layout. Existing components use local media queries and the global overflow safety base.
- Long text, media, tables, and third-party overlays must not create page-level horizontal scrolling.
- Buttons should not jump as labels/loading state change, and important text/control labels must remain scannable.

## Review Against Existing UI

Before changing a surface, inspect its nearest reference:

- workspace navigation/frame: `components/WorkspaceShell.vue`;
- global tokens and library overrides: `src/style.css`;
- home information hierarchy: `views/HomeView.vue`;
- login/brand imagery: `views/LoginView.vue`;
- reading content: `views/NoteDetailView.vue` plus `styles/markdown.css`;
- tool-heavy editor UI: `editor/components/` and `views/NoteEditView.vue`.

An engineering extraction should not change the user's familiar visual hierarchy unless the task explicitly asks for redesign.
