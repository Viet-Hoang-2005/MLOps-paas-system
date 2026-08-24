---
name: mlops-paas-frontend
description: Implement or review the React/Vite frontend, including feature-first boundaries, route coordinators, React Query, API clients, design tokens, responsive UI, accessibility, i18n, and runtime logs. Use for any change under web/ or any browser-facing workflow.
---

# MLOps PaaS frontend

## Workflow

1. Inspect the current route, page, feature API, query hook, shared component, and translations before editing.
2. Read the relevant references: [code-architecture.md](references/code-architecture.md), [routing-and-state.md](references/routing-and-state.md), [api-and-server-state.md](references/api-and-server-state.md), [design-system.md](references/design-system.md), and [i18n-and-quality-gates.md](references/i18n-and-quality-gates.md).
3. Preserve `app → features → shared`; shared must not import a feature.
4. Keep pages as coordinators/composition. Put HTTP in domain clients and server state in query hooks.
5. Preserve routes, payloads, status semantics, dark mode, accessibility, and responsive behavior unless the request changes them.
6. Inspect live backend serializers/endpoints when a frontend contract is uncertain.
7. Preserve user changes and avoid unrelated visual refactors.
8. If the change intentionally alters a frontend contract, update this skill.

Load `$mlops-paas-overview` for cross-service workflows and `$mlops-paas-security` for auth, tenancy, credentials, uploads, or public endpoints.

Treat code, tests, build configuration, and the live backend contract as more authoritative than README or architecture prose; reconcile conflicts explicitly. Never embed passwords, tokens, private keys, real environment values, or SSH credentials.

## Required validation

From `web/`, run:

```bash
pnpm lint
pnpm build
```

Manually smoke-test the affected route, theme modes, keyboard focus, loading/empty/error states, and API recovery path.
