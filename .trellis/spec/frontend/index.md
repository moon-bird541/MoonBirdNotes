# Frontend Development Guidelines

MoonBirdNotes is a Vue 3 single-page application built with Vite. It uses JavaScript, `<script setup>`, Vue Router, Axios, Element Plus, Iconify, Toast UI Editor, and scoped component CSS. There is no TypeScript or global state-store package.

## Guides

| Guide | Scope |
| --- | --- |
| [Directory Structure](./directory-structure.md) | Views, components, editor, services, utilities, and styles |
| [Component Guidelines](./component-guidelines.md) | SFC structure, props/events, composition, lifecycle, accessibility |
| [State Management](./state-management.md) | Local/server/URL/persistent state without a store library |
| [Runtime Contracts](./type-safety.md) | JavaScript runtime validation and API-shape discipline |
| [API and Security](./api-and-security.md) | Axios session handling, CSRF, error mapping, safe HTML |
| [Design System](./design-system.md) | MoonBird visual language, tokens, motion, responsive behavior |
| [Editor Toolbar](./editor-toolbar.md) | Toolbar modes, command/event contracts, selection restoration, and sticky layout |
| [Quality Guidelines](./quality-guidelines.md) | Build, Playwright, review, and verification expectations |

The original hook template was removed because this is Vue, not React, and the repository currently has no composables layer. Shared stateful behavior is documented in State Management and Component Guidelines.

## Pre-Development Checklist

1. Read [Directory Structure](./directory-structure.md) and [Component Guidelines](./component-guidelines.md) for any Vue change.
2. Read [API and Security](./api-and-security.md) before changing authentication, service calls, errors, uploads, Markdown, or any `v-html` path.
3. Read [State Management](./state-management.md) before adding persistent settings, cross-view coordination, route state, timers, or event listeners.
4. Read [Design System](./design-system.md) for visible UI work, then inspect the nearest existing view/component rather than introducing a new visual vocabulary.
5. Read [Editor Toolbar](./editor-toolbar.md) before changing editor commands, toolbar modes, or selection restoration.
6. Run the production build. Add/run Playwright coverage when changing a routed user flow or API contract.

## Project Commands

From `frontend/moonsbirdnotrs_vue/`:

```bash
npm run build
npm run test:e2e
```

`PLAYWRIGHT_BASE_URL` can point the suite at an already running site. Without it, Playwright starts Vite on `127.0.0.1:4173`.
