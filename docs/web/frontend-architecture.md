# Frontend architecture

## Dependency direction

The application is organized so that route code remains thin and domain behavior can evolve without creating another global API or type module.

```text
main -> app -> features -> shared
       app -----------> shared
       shared -> external libraries only
```

`shared` cannot depend on a feature. A feature may use shared HTTP, error, type, utility, and UI modules. Feature pages coordinate route parameters and assemble their own domain components; they do not implement transport or parsing rules. Application layouts and route composition live exclusively under `app`.

## Domain slice

A complete feature slice normally contains:

```text
features/<domain>/
  api/          typed request functions
  components/   domain-specific UI sections
  hooks/        queries, mutations, polling, and orchestration
  lib/          domain-only parsing or packaging utilities, when needed
  pages/        lazy-loaded route coordinators
  queryKeys.ts  one query-key factory
  types.ts      DTO and domain types
```

Not every slice needs every folder. Do not create barrel modules that hide circular dependencies or reintroduce a global API surface.

Cross-directory imports use `@/`; `./` is reserved for files in the same directory. ESLint boundaries enforce `app -> features -> shared` and reject the removed roots `components`, `hooks`, `lib`, `pages`, and `types`.
The `pnpm lint` command also runs `scripts/check-architecture.mjs` to verify the root shape and detect circular TypeScript dependencies.

## Server state

React Query owns server state. A query key must come from its domain factory, for example:

```ts
useQuery({
  queryKey: trainingQueryKeys.job(jobId),
  queryFn: () => getTrainingJob(jobId),
})
```

Mutations invalidate or update keys from the same factory. Local React state is reserved for interaction state such as open dialogs, selected tabs, unsaved editor content, or temporary form values.

The model ID in the current route has priority over local storage. Local storage is only a fallback. When a model-scoped page receives an invalid ID, model selection resolves to the first accessible model without changing backend contracts.

## HTTP and errors

`src/shared/api/client.ts` owns authentication, token refresh, and Axios interceptors. Feature API modules are the only application code that should call that client.

All UI error messages pass through `getApiErrorMessage`. The normalizer handles strings, validation arrays, nested `detail`, and `{ code, detail }` responses so a response object is never rendered as a React child.

## Runtime logs

`src/shared/api/runtimeLogs.ts` normalizes log batches from build, deployment, training, and drift endpoints into `RuntimeLogBatch`. `TerminalViewer` consumes this adapter and accepts callbacks for feature-specific result lookup, keeping shared UI independent from domain APIs.

Runtime output and lifecycle state have different authority:

- Redis-backed logs provide incremental console output.
- The Control Plane database is authoritative for pending/running/completed/failed state.

## Manual upload lifecycle

Manual model upload is coordinated by `UploadModelPage`, which owns the in-memory files, navigation guards, validation, and typed Outlet context for three nested routes:

- `/dashboard/management/model/upload/metadata` persists latest-only project metadata and optional source/reference attachments when Continue is selected.
- `/dashboard/management/model/upload/build?modelId=<uuid>` submits immutable flavor, artifact, attachment, and requirements inputs for one Build UUID.
- `/dashboard/management/model/upload/deploy?modelId=<uuid>&buildId=<uuid>` deploys exactly the ready Build identified by the URL.

`LineSteps` uses the same transitions as Back/Continue, so a future step cannot bypass validation. Files remain available while navigating inside the upload layout, but refresh or browser close clears files that have not been submitted; `beforeunload`, `useBlocker`, and the shared confirm dialog communicate that boundary.

Project metadata is latest-only and never creates a registry version. Every successful manual Build creates exactly one immutable registry version and stores its image automatically. Failed or cancelled Builds keep audit metadata while their binary input and partial image are cleaned up. Deployment accepts only a tenant-owned ready Build with a registered version.

## Training lifecycle

`CreateTrainingJobPage` coordinates three nested, model-selection-independent routes:

- `/dashboard/model-training/create/metadata` creates a project or selects and updates an existing one.
- `/dashboard/model-training/create/source?modelId=<uuid>` saves source, reference data, flavor, entry point, and optional requirements.
- `/dashboard/model-training/create/execution?modelId=<uuid>&jobId=<uuid>` selects server-advertised CPU/GPU capabilities and creates a new immutable TrainingJob for every run.

Back/LineSteps preserve unsaved editor state inside the coordinator. Direct URLs rehydrate project/job server state, while browser refresh cannot preserve unsent files. Training completion stores a TrainingOutput only. `TrainingJobDetailPage` then exposes Build & Register, retry, output deletion, build logs, and Open in Registry. A successful Build creates the next model version; Training never deploys a worker directly.

## Routing and bundles

All route pages use `React.lazy`. The global error boundary prevents a render error from blanking the entire application. Loading fallbacks use shared skeleton/state components.

Monaco is loaded through `LazyCodeEditor`; feature code must not import `@monaco-editor/react` directly. ZIP operations use `fflate`. Keep large editor and packaging code out of the eager application entry chunk.

## Adding a feature

1. Define the domain DTOs and resource IDs.
2. Add feature API functions and query keys.
3. Put orchestration in a feature hook when a page would otherwise contain polling, parsing, or mutation coordination.
4. Build the feature section from shared primitives.
5. Keep the page limited to route input and composition.
6. Add English copy to the domain i18n namespace.
7. Run `pnpm lint` and `pnpm build`, then execute the relevant manual journey.

## Internationalization

All user-facing copy is served through `react-i18next`. English is currently the
only resource language, but feature resources must remain ready for additional
languages.

- Put reusable actions, status labels, accessibility copy, and shared component
  text in `src/shared/i18n/en.ts` under the `common` namespace.
- Put domain copy in `src/features/<feature>/i18n/en.ts` and use semantic keys
  such as `detail.metadata.internalJobId` or `messages.deleteFailed`. Do not use
  an English sentence as its own key.
- Use interpolation and pluralization for runtime values instead of assembling
  translated sentences in JSX: `t("testing.rowsProcessed", { count })`.
- Translate status enums at render time. Keep API wire values, routes, UUIDs,
  filenames, package names, source snippets, runtime logs, and brand names
  unchanged.
- Pass frontend fallback errors through `getApiErrorMessage`. A detailed backend
  message remains authoritative and must not be replaced or translated.
- To add a language, mirror every namespace resource, register it in
  `src/app/i18n.ts`, and keep English as `fallbackLng`.

`pnpm lint` runs `scripts/check-i18n.mjs` after ESLint and the architecture
check. The checker rejects visible JSX literals, display props, toast literals,
and UI configuration labels. A technical literal that cannot be inferred by the
checker may be exempted only with a nearby `i18n-ignore: <reason>` comment.
Feature-wide or file-wide exemptions are not allowed.

## Color tokens

`src/app/styles/tokens.css` is the only source of frontend color values. It
defines primitive colors, independent light/dark semantic tokens, and
component palettes for charts, terminals, syntax highlighting, and auth
decoration. Application code consumes semantic Tailwind utilities and maps
domain statuses to `SemanticTone`; it does not use Tailwind palette utilities
or `dark:` color overrides.

`pnpm lint` also runs `scripts/check-colors.mjs`. The checker rejects direct
palette utilities, raw hexadecimal/functional colors outside the token file,
and `dark:` color utilities. A genuinely fixed technical exception requires a
nearby `color-ignore: <reason>` comment.
