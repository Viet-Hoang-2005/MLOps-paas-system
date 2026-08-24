# Design system

- `web/src/app/styles/tokens.css` is the only frontend color source and follows
  `primitive palette → semantic token → component token`.
- Tailwind CSS v4 exposes those values as semantic utilities.
- Light mode follows the monochrome legacy design; dark mode uses slate surfaces and blue primary actions.
- Light and dark values are authored independently. Do not use `dark:` color
  utilities to invert component colors.
- Use semantic tokens instead of hard-coded palettes, hexadecimal values, or
  functional colors.
- Shared primitives use Radix for accessible behavior and CVA for variants.
- Use TanStack Table through the shared DataTable for structured lists.

## UI rules

- Preserve visible focus, keyboard navigation, labels, and meaningful `aria-*`.
- Status must include text/icon, never color alone.
- Map API statuses to the shared `SemanticTone` values: `neutral`, `info`,
  `success`, `warning`, and `danger`.
- Provide loading, disabled, error, empty, hover, and focus-visible states.
- Form controls keep their surface color and use the dedicated blue
  `input-hover` border. Keep hover visually distinct from the stronger focus
  `ring`, including in dark mode.
- Respect `prefers-reduced-motion`.
- Test light, dark, and system themes.
- Desktop uses the full sidebar, tablet an icon rail, and mobile a drawer.
- Keep technical consoles and syntax palettes intentionally dark and readable.
- Keep chart series ordered through `chart-1` to `chart-6`; use
  `terminal-*`/`syntax-*` component tokens for technical output.
- Use the shared semantic radius roles: `compact` (4 px) for menu/tree items,
  `surface` (8 px) for cards, tables, terminals, dropzones, dropdown shells and
  icon buttons, `control` (12 px) for form controls and buttons, `overlay`
  (16 px) for dialogs/drawers/Auth cards, and `full` for pills and circles.
  Do not use Tailwind size-based or arbitrary radius utilities.
- `pnpm lint` runs `scripts/check-colors.mjs`. A genuine technical exception
  needs a narrow `color-ignore: reason` comment.
- `pnpm lint` also runs `scripts/check-radii.mjs`. A genuine graphical
  exception needs a narrow `radius-ignore: reason` comment.
- Use the semantic typography roles exported from `tokens.css` with the
  `text-style-*` prefix: `display`, `page-title`, `section-title`, `heading`,
  `metric`, `body-lg`, `body`, `body-strong`, `control`, `caption`,
  `caption-strong`, `overline`, `code-sm`, `code-sm-strong`, and `terminal`.
  Each role owns size, line height, weight, and tracking.
- Foreground colors use the separate `text-color-*` prefix, such as
  `text-color-foreground`, `text-color-danger`, and
  `text-color-terminal-muted`. Never use the legacy unprefixed semantic
  `text-*` forms. `cn()` configures Tailwind Merge to keep one typography role
  and one foreground color at the same time.
- Inter is the UI font at weights 400–700. Use system monospace only for
  terminal output, code, UUIDs, URIs, paths, commands, and technical IDs.
  User-readable text must be at least 12 px.
- Do not use Tailwind's raw text-size, line-height, or tracking scale, arbitrary
  typography values, or weights 800/900. `pnpm lint` runs
  `scripts/check-typography.mjs`; third-party numeric APIs require a narrow
  `typography-ignore: reason` comment.

Before introducing a new primitive, inspect `shared/components` and extend the
existing API where appropriate. When adding a color, define its primitive and
both theme semantics before consuming it.
