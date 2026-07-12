# BoardTrace API

FastAPI foundation for BoardTrace post-game analysis. It provides application health endpoints only; PostgreSQL, Redis, workers, Stockfish, authentication, game models, and analysis endpoints are intentionally not present.

## Local run

From the repository root:

```powershell
uv sync --all-packages
uv run --project apps/api uvicorn boardtrace_api.main:app --host 127.0.0.1 --port 8000
```

OpenAPI is at `/openapi.json` and `/docs`. Health routes are `/api/v1/health/live` and `/api/v1/health/ready`.

## Quality checks

```powershell
pnpm check:api
pnpm test:coverage:api
```

The API uses typed settings, an application factory, versioned routing, trusted-host and CORS middleware, request IDs, security headers, structured logging, and a standard error envelope. It must not expose live engine output, evaluations, best moves, principal variations, mate scores, or analysis payloads.
