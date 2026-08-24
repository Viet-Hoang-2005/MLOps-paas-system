# Frontend code architecture

## Dependency direction

```text
main.tsx → app → features → shared
                 app → shared
```

- `app/`: router, providers, layouts, theme, i18n registration, global styles.
- `features/<domain>/`: pages, components, hooks, API, query keys, types, i18n, domain helpers.
- `shared/`: domain-agnostic UI, HTTP foundation, hooks, utilities, and shared contracts.
- Use `@/` across directories and `./` within one directory.
- Do not recreate legacy root `components`, `hooks`, `lib`, `pages`, or `types`.
- Avoid feature barrel files and hidden dependency cycles.

## Responsibilities

- Page: reads route state and composes feature sections.
- Hook: owns queries, mutations, polling, and derived server state.
- API module: maps typed HTTP request/response contracts.
- Component: renders UI and emits user intent.
- Shared primitive: knows no business domain.

Architecture checks live in `web/scripts/check-architecture.mjs`; inspect it before changing import boundaries.
