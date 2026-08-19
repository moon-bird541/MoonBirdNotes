# Component Guidelines

Vue components keep page orchestration, reusable UI contracts, third-party DOM work, and visual ownership explicit.

## SFC Shape

Most product components use this order:

1. `<script setup>` with imports, props/emits, local state, computed values, handlers, and lifecycle hooks;
2. `<template>` with semantic elements and explicit events;
3. `<style scoped>` for the component surface.

Reference files: `components/SettingsPanel.vue`, `components/KnowledgeRunTracePanel.vue`, `editor/components/NoteEditorPanel.vue`, and `editor/components/VersionPreviewDialog.vue`.

## Responsibilities

- Route views own fetching, mutation coordination, router navigation, page loading/error state, and feature-level state.
- Reusable components receive data through props and notify parents through emits. Editor controls do not import the notes API; `NoteEditView.vue` binds data/events to components such as `NoteEditHeader.vue` and `VersionHistoryDrawer.vue`.
- `WorkspaceShell.vue` owns the authenticated workspace frame and exposes page content through a default slot.
- A component may own a cohesive browser preference interaction (`SettingsPanel.vue`) or isolated panel fetch/display state, but avoid hidden cross-page state.

## Props and Events

- Declare runtime prop types, required fields, and defaults with object-form `defineProps()`. Array/object defaults must be factory functions; see `VersionHistoryDrawer.vue`.
- Treat props as read-only. Use named events for actions (`save`, `preview`, `open-source`) and `update:<prop>` for two-way visible state (`VersionPreviewDialog.vue`, `SideTableToolbar.vue`).
- Keep event names kebab-case in templates and stable across the parent/child boundary.
- Pass a function prop only when it is genuinely a parent-owned presentation policy, such as `formatDateTime`; otherwise emit data and let the parent coordinate.
- Avoid implicit dependence on a parent's DOM or global variables. When editor overlays must coordinate with third-party DOM, make that contract explicit through props/events/element refs.

## State and Derived Values

- Use `ref()` for scalar/replaceable values, `reactive()` for cohesive mutable records such as forms/positions, and `computed()` for derived labels/availability.
- Keep fast guards at handler boundaries (`if (sending.value) return`) to prevent duplicate mutations.
- Use `nextTick()` when an operation depends on rendered DOM, as chat scrolling and editor overlays do.
- Clean up every timer/listener installed by a component. `GlobalSearchPanel.vue`, `SettingsPanel.vue`, `WorkspaceShell.vue`, and the editor views pair setup with `onBeforeUnmount()`.

## Templates and Accessibility

- Native buttons always use `type="button"` unless they intentionally submit a form.
- Icon-only controls require a useful `aria-label` or tooltip/title. Decorative images/icons use empty `alt` plus `aria-hidden="true"`.
- Use semantic regions and labels (`main`, `aside`, `section`, `role="region"`, `aria-live`) where the current workspace and Agent panels do.
- Associate form controls with labels or an explicit accessible name. Preserve keyboard behavior for list rows/controls and Enter/Escape handling in editor inputs.
- Loading, empty, error, and disabled states are part of the component contract, not optional polish.

## Styling

- Component styles are scoped by default. Use `:deep()` only to style a child library's internal classes within the local surface.
- Put cross-component tokens, base behavior, and global Element Plus overrides in `src/style.css`; do not copy global colors/shadows into every component.
- A small number of unscoped style blocks exist for third-party generated Markdown/editor DOM (`NoteDetailView.vue`, `NoteListView.vue`). Do not add unscoped CSS unless scoped selectors cannot reach generated content and the selector is tightly namespaced.
- Preserve responsive rules near the component they affect and use global motion/tokens where possible.

## Anti-Patterns

- Mutating props, importing a service into a presentational editor control, or emitting raw DOM events when domain data suffices.
- Adding a visual wrapper solely because logic moved into a child component.
- Installing document/window listeners without removal, or timers without clear/replace behavior.
- Icon-only buttons without an accessible name; decorative images with misleading alt text.
- Rendering dynamic HTML in a component without following [API and Security](./api-and-security.md).
