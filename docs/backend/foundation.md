# Backend Foundation

The API uses an application factory, typed settings, versioned routers, request IDs, structured logging, security headers, standard error envelopes, and health/readiness endpoints. PostgreSQL readiness is implemented; workers remain future module boundaries.

## Foundation contract

- Health endpoints report only the application dependency currently present; they do not claim database, cache, worker, or engine readiness.
- Errors use the typed envelope `{ "error": { "code", "message", "request_id" } }` and never expose raw internal failures.
- Logging supports console and JSON formats and allowlists request metadata. Secrets, authorization headers, request bodies, screenshots, and FEN values are excluded.
- The application factory accepts test-only routers per instance. They are absent from the default application and default OpenAPI schema.
- No public endpoint may expose engine output or analysis data until a later phase establishes the server-owned release lock.

Use `uv sync --all-packages` before API validation. Root commands are `pnpm check:api` and `pnpm test:coverage:api`.
