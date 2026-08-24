# i18n and quality gates

## Namespaces

`common`, `auth`, `catalog`, `deploy`, `training`, `registry`, `drift`, `settings`, `notifications`.

- Feature resources live in `features/<domain>/i18n/en.ts`; shared copy lives in `shared/i18n/en.ts`.
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
