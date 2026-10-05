# AdaptML frontend

The AdaptML frontend is a React 19, TypeScript, Vite, and Tailwind CSS v4 application for the MLOps PaaS control plane. It follows a feature-oriented architecture and keeps backend lifecycle state in React Query.

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
pnpm test:i18n
```

`pnpm lint` runs both ESLint boundary rules and the architecture check for allowed source roots, parent-relative imports, legacy imports, and circular dependencies.

`pnpm test:workflow` checks Header navigation across main/detail/create/account routes without a browser. It does not replace manual UI or Docker/S3 end-to-end acceptance. See the [local workflow runbook](../docs/dev/web-workflow-local.md).

Deployment history provides Re-build and Delete actions. Re-build creates a new
attempt from the current Preview or original training output; Delete asynchronously
cleans unregistered builds and their images, never Evolution versions. Run
`pnpm test:build-actions` for button eligibility tests. See the
[build history actions contract](../docs/dev/build-history-actions.md).

Deployment has two pages: `/dashboard/deployment/build/new?projectId=<uuid>`
selects Preview/Training, builds, and explicitly registers the immutable snapshot.
The Build URL also keeps `source/jobId` or `buildId` to restore selection/logs.
Registration polling continues until the API confirms `registered` and `version_id`,
then opens `/dashboard/deployment/run/<projectId>/<buildId>` without deploying.
Run's Terminal Deploy button creates the deployment; `?deploymentId=<uuid>` restores
its status/logs on reload. Version selection changes the Build in the route.
Evolution and registered history actions only open Run, never start a deployment.
Run refuses unregistered/deleting builds and mismatched project/version/attempt IDs.
`pnpm test:deployment-flow` covers navigation, eligibility and action boundaries.

Local Overview metrics use Docker SDK CPU/RAM snapshots and a short-lived shared gateway counter for RPS. Polling runs every 5 seconds while foregrounded; at most 60 samples/5 minutes are held in page memory, not localStorage or a history database. Leaving, refreshing or changing the Running deployment resets the window. `pnpm test:metrics` covers buffering, counter resets and gaps. Production retains Prometheus history mode.

## Source architecture

```text
src/
  main.tsx   application entry point
  app/       router, providers, layouts, theme, i18n, and global styles
  assets/    static brand and product assets
  features/  domain APIs, pages, components, hooks, types, and query keys
  shared/    HTTP/error foundation, shared types, utilities, and UI primitives
```

The active domains are `auth`, `projects`, `deployments`, `training`, `evolution`, `monitoring`, `api-tokens`, `settings`, and `notifications`.

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
- Routes are lazy-loaded under `/dashboard/projects/:projectId/{overview,deployment,monitoring,training,evolution}`. New forms use independent selectors; old upload/management/registry routes are removed. Monaco and ZIP tooling stay outside the eager application bundle.

See [Frontend architecture](docs/frontend-architecture.md) and [Design system](docs/design-system.md) before adding a new domain or primitive.

## UI conventions

- Use shared primitives before creating page-local buttons, dialogs, cards, tables, badges, loading states, or error states.
- Use semantic tokens instead of color literals in new code.
- Status must include text or an icon; color alone is not sufficient.
- Every interactive control needs a visible `focus-visible` state and a meaningful accessible name.
- Support `light`, `dark`, and `system` themes. Theme preference is persisted locally.
- Copy belongs to its feature i18n namespace. All ten namespaces have English and Vietnamese resources. The Header language dropdown replaces the standalone New model button; project creation remains in Model Project and the model-selector menu.
- Language selection uses `adaptml.language` in localStorage, then the first supported browser language, then English. Switching updates UI and HTML `lang` without navigation, reload or clearing forms. Dates/numbers use `vi-VN`/`en-US`; browser timezone stays unchanged. Backend messages, logs, code, CSV, names and UUIDs are not translated.
- `pnpm test:i18n` tests language selection/storage, registration, resource parity/interpolation/plurals and negative fixtures. `pnpm lint` checks both locale resources and hardcoded UI; the CI frontend entry runs these i18n checks alongside build/ESLint.

## Manual verification checklist

- Login, signup, OAuth, password recovery, and session refresh
- Header preserves a main section, but choosing a project from detail/create/account pages goes to its Overview; dirty forms confirm exit
- New/Edit Preview, immutable source/reference snapshots, explicit Build → Register → Deploy, prediction and runtime logs
- Training create, list, detail polling, cancel, retry, register, artifacts, and deployment
- Evolution snapshot comparison/lineage, Running badge and confirmed deploy; deployment failure keeps the old Running version
- Drift configure, run, runtime logs, report, and delete
- Profile, avatar, password, and the separate API Token feature
- English/Vietnamese on every page, including loading/error/empty states, tables, status badges and confirmation dialogs
- Change language with a dirty form, open modal or polling job; preserve input, route, selected project and progress. Refresh and logout must preserve the preference; blocked storage must not break switching.
- Header language menu on mobile (320 px and up), checked selection, keyboard access, tooltip and HTML `lang`; user content and technical logs remain unchanged
- Light/dark/system at 768 px, 1024 px, and 1440 px
- Keyboard navigation, visible focus, 200% zoom, WCAG AA contrast, and reduced motion

## Environment variables

Use `.env.example` as the source for supported local configuration. Never commit credentials or provider secrets into the frontend; browser-delivered values are public by definition.
