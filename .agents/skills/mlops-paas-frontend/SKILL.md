---
name: mlops-paas-frontend
description: Implement or diagnose React/Vite routes, feature state, API integration, shared UI, accessibility, or i18n under web/.
---

# MLOps PaaS Frontend

Find the route in [AppRouter](../../../web/src/app/router/AppRouter.tsx). Follow the page into its feature components, query keys and API client. Keep page coordination in the feature and use shared components for interaction patterns already provided by the design system.

- [Code architecture](references/code-architecture.md) explains feature and shared-module ownership.
- [Routing and state](references/routing-and-state.md) covers navigation, Model Project context and the Training workspace/job routes.
- [API and server state](references/api-and-server-state.md) covers caching, invalidation, errors and log queries.
- [Design system](references/design-system.md) locates the shared components and styling conventions. [i18n and quality gates](references/i18n-and-quality-gates.md) covers both locales and the matching tests.

Run the focused tests from `web/` using `pnpm exec vitest run <test-path>`. Use the lint, quality and build scripts in [package.json](../../../web/package.json) when the affected behavior warrants them. Verify user-visible route or state changes in the relevant loading, error and success states.
