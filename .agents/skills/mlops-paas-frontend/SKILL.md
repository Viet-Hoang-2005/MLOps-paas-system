---
name: mlops-paas-frontend
description: Implement or review the React/Vite frontend, including feature-first boundaries, route coordinators, React Query, API clients, design tokens, responsive UI, accessibility, i18n, and runtime logs. Use for any change under web/ or any browser-facing workflow.
---

# MLOps PaaS Frontend

Use this skill to implement, modify, review, or troubleshoot the React 18 / TypeScript / Vite frontend application (`web/`).

Never embed passwords, tokens, private keys, or credentials in source code, mock fixtures, or translations.

## Workflow

1. Inspect the relevant route, page coordinator, feature API client, React Query hook, shared component, and translation files (`web/src/locales/`).
2. Read the relevant references: [code-architecture.md](references/code-architecture.md), [routing-and-state.md](references/routing-and-state.md), [api-and-server-state.md](references/api-and-server-state.md), [design-system.md](references/design-system.md), and [i18n-and-quality-gates.md](references/i18n-and-quality-gates.md).
3. Preserve the strict dependency direction: `app` $\rightarrow$ `features` $\rightarrow$ `shared`. Components in `shared/` must never import from `features/`.
4. Keep page components as coordinators and compositional shells (`Outlet`); delegate network calls to domain API clients and server state to `@tanstack/react-query` hooks.
5. Maintain route conventions, payload typing, error handling, dark/light theme tokens, ARIA accessibility, and responsive layouts.
6. Verify live backend endpoints and serializers (`services/control-plane/src/apps/`) when an API contract is uncertain.
7. Support real-time task log streaming via cursor-based HTTP polling hooks (`useRuntimeLogs`).
8. Ensure all user-facing strings are localized in both English (`en.json`) and Vietnamese (`vi.json`).

## Required Validation

Execute from the `web/` directory:
```bash
pnpm lint
pnpm build
```

Manually smoke-test:
- Affected routes and query parameter preservation.
- Light and dark theme transitions.
- Form validation, dirty form exit confirmation, and error recovery states.
- Responsive breakpoints (mobile, tablet, desktop).
