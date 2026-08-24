# MLdrift frontend

The MLdrift frontend is a React 19, TypeScript, Vite, and Tailwind CSS v4 application for the MLOps PaaS control plane. It follows a feature-oriented architecture and keeps backend lifecycle state in React Query.

## Local development

Requirements:

- Node.js compatible with the version used by CI
- pnpm
- A running Control Plane API (the default local URL is configured through Vite environment variables)

```bash
pnpm install
pnpm dev
```

Quality gates used by CI:

```bash
pnpm lint
pnpm build
```

`pnpm lint` runs both ESLint boundary rules and the architecture check for allowed source roots, parent-relative imports, legacy imports, and circular dependencies.

The current migration intentionally does not add a frontend unit-test or browser-test gate. Use the manual verification checklist below before merging changes that affect a user journey.

## Source architecture

```text
src/
  main.tsx   application entry point
  app/       router, providers, layouts, theme, i18n, and global styles
  assets/    static brand and product assets
  features/  domain APIs, pages, components, hooks, types, and query keys
  shared/    HTTP/error foundation, shared types, utilities, and UI primitives
```

The active domains are `auth`, `catalog`, `build-deploy`, `training`, `registry`, `drift`, `settings`, and `notifications`.

Architecture rules:

- Pages do not import Axios or the shared HTTP client directly.
- Every domain owns its API functions, DTO/domain types, and query-key factory.
- Pages never write inline React Query key arrays.
- `ResourceId` is a string and shared response shapes live in `src/shared/types`.
- Runtime logs for build, deployment, training, and drift use the shared runtime-log adapter.
- PostgreSQL/Control Plane responses remain the lifecycle source of truth; Redis logs are runtime output only.
- Shared modules must not import features. ESLint enforces the most important import boundaries.
- Cross-directory imports use the `@/` alias; parent-relative imports are rejected by ESLint.
- The legacy roots `components`, `hooks`, `lib`, `pages`, and `types` are not allowed under `src`.
- Routes keep their existing public URLs and are lazy-loaded. Monaco and ZIP tooling stay outside the eager application bundle.

See [Frontend architecture](docs/frontend-architecture.md) and [Design system](docs/design-system.md) before adding a new domain or primitive.

## UI conventions

- Use shared primitives before creating page-local buttons, dialogs, cards, tables, badges, loading states, or error states.
- Use semantic tokens instead of color literals in new code.
- Status must include text or an icon; color alone is not sufficient.
- Every interactive control needs a visible `focus-visible` state and a meaningful accessible name.
- Support `light`, `dark`, and `system` themes. Theme preference is persisted locally.
- User-facing copy is English and belongs to the relevant i18n namespace even though no language selector is currently shown.

## Manual verification checklist

- Login, signup, OAuth, password recovery, and session refresh
- Model selection and lifecycle navigation across Overview, Build & Deploy, Training, Registry, and Monitoring
- Upload, source/reference editing, build, deployment, health, prediction, stop, and runtime logs
- Training create, list, detail polling, cancel, retry, register, artifacts, and deployment
- Registry compare, promote, rollback, build, deploy, health, and history
- Drift configure, run, runtime logs, report, and delete
- Profile, avatar, password, and API keys
- Light/dark/system at 768 px, 1024 px, and 1440 px
- Keyboard navigation, visible focus, 200% zoom, WCAG AA contrast, and reduced motion

## Environment variables

Use `.env.example` as the source for supported local configuration. Never commit credentials or provider secrets into the frontend; browser-delivered values are public by definition.
