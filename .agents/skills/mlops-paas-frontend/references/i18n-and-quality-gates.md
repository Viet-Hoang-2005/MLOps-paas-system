# i18n and quality gates

## Namespaces

`common`, `auth`, `projects`, `deployments`, `training`, `evolution`, `monitoring`, `settings`, `notifications`, `overview`.

- Feature resources live in `features/<domain>/i18n/{en,vi}.ts`; shared copy lives in `shared/i18n/{en,vi}.ts`. Both locales must register every namespace, with non-empty leaves and matching interpolation variables. Vietnamese plurals use the CLDR other category; English uses one/other.
- Header selects language (instead of standalone New model); persist `adaptml.language`, prefer saved choice then browser language then English. Update HTML lang before render/on language change. Never reset routes/forms/polling merely because translation functions change; use Effect Events for translated feedback inside data-loading effects. Use shared locale formatters for visible dates/numbers, never CSV/API/code.
- Use semantic keys, interpolation, and pluralization.
- Translate titles, labels, placeholders, buttons, tables, toasts, dialogs, tooltips, accessibility text, statuses, and frontend validation.
- Do not translate brands, URLs, UUIDs, filenames, API enum values, code samples, runtime logs, or backend error detail.
- Status maps store enum/key values and translate at render time.
- Technical literal exceptions require a narrow `i18n-ignore` explanation.

## Gates

`pnpm lint` runs ESLint, architecture checks, the i18n hard-code checker, and
the color-token checker. `pnpm build` performs TypeScript/Vite production
validation. Keep the eager application chunk under the configured 500 kB
threshold and preserve lazy Monaco/tooling chunks.

`pnpm test:i18n` validates selection/storage and bilingual resources, including negative fixtures. The CI frontend matrix entry runs `check-i18n.mjs` and this test and reports its outcome in the existing quality Summary.
