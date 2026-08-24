# API and server state

- Axios configuration and error normalization are shared infrastructure.
- Each domain owns its API modules and DTOs.
- React Query hooks own fetching, mutations, invalidation, polling, and retries.
- Each domain provides query-key factories; do not write inline query-key arrays in pages.
- Pages must not call Axios or the shared HTTP client directly.
- Prefer PostgreSQL-backed API lifecycle status over Redis log completion guesses.

## Errors

- Normalize nested API error objects before rendering.
- Prefer backend `detail` when present; translate only the frontend fallback.
- Handle validation dictionaries and `non_field_errors` without rendering objects as React children.
- Distinguish transport/network errors, authorization, conflict, and server failure.

## Runtime logs

`TerminalViewer` is presentation-only: title, copy action, optional header actions, placeholder, and supplied log content. Pages/hooks own polling, stream cursors, Run/Stop/Retry behavior, and lifecycle callbacks.
