# BoardTrace

> Review every decision.

BoardTrace is a post-game chess analysis platform. It captures positions from a user-selected online chessboard region, analyzes them on the backend, and releases the review only after the game is finished.

## Scope and fair play

BoardTrace provides no live assistance. During an active game, no engine evaluation, best move, principal variation, mate score, or alternative move reaches the client. Results remain locked server-side until game completion is verified.

## Core data flow

1. The capture client processes only the board region selected by the user.
2. Changed positions become FEN candidates and are sent to the FastAPI backend.
3. Vision, engine, and report workers perform server-side processing.
4. PostgreSQL stores state and locked results; Redis coordinates work; object storage retains approved capture artifacts.
5. After verified completion, the Next.js analysis application displays the report.

## Approved technology stack

| Area           | Technologies                                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------------------------------ |
| Web            | Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand, chess.js, react-chessboard, Recharts |
| Extension      | Chrome Manifest V3, React, TypeScript, Vite, Canvas API, OffscreenCanvas, Web Workers                              |
| Backend        | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, python-chess                                                     |
| Vision         | PyTorch, OpenCV, Pillow, Albumentations, ONNX, ONNX Runtime                                                        |
| Engine         | Native Stockfish via python-chess UCI                                                                              |
| Infrastructure | PostgreSQL, Redis, Celery, MinIO/S3-compatible storage, Docker Compose                                             |
| Testing        | pytest, Vitest, Playwright                                                                                         |
| Packages       | pnpm 11.11.0; Python is planned to use uv                                                                          |

## Planned repository structure

```text
apps/           # Future applications
packages/       # Shared TypeScript packages
workers/        # Future worker entry points
ml/             # Computer-vision assets
infrastructure/ # Deployment and local infrastructure
tests/          # Cross-application tests
docs/           # Architecture, decisions, security, roadmap
```

## Development phases

Repository foundation, application scaffolding, capture and ingestion, secure analysis pipeline, post-game reporting, then hardening. See [the roadmap](docs/roadmap/development-phases.md).

## Backend Development

The FastAPI foundation is in `apps/api`. It includes typed settings, an application factory, versioned health endpoints, CORS and trusted-host protection, request IDs, security headers, structured logging, and standard errors.

It intentionally does **not** include PostgreSQL, Redis, workers, Stockfish, authentication, game models, or analysis endpoints. Engine output remains unavailable to every client-facing API surface during live play.

Prepare all workspace packages, then run API checks:

```powershell
uv sync --all-packages
pnpm check:api
pnpm test:coverage:api
```

For local development only, start the API with:

```powershell
uv run --project apps/api uvicorn boardtrace_api.main:app --host 127.0.0.1 --port 8000
```

Available foundation endpoints are `/api/v1/health/live`, `/api/v1/health/ready`, `/openapi.json`, and `/docs`.

## Development tooling

BoardTrace uses pnpm 11.11.0 for JavaScript and TypeScript tooling and uv for Python tooling. Install [pnpm](https://pnpm.io/installation) and [uv](https://docs.astral.sh/uv/getting-started/installation/) before running local quality checks.

```powershell
pnpm install
uv sync
```

Use these JavaScript and TypeScript commands:

```powershell
pnpm format
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm test:coverage
pnpm check
pnpm lint:api
pnpm format:api
pnpm format:check:api
pnpm typecheck:api
pnpm test:api
pnpm test:coverage:api
pnpm check:api
```

Use these Python commands:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest
uv run pytest --cov
```

`pnpm check` runs the JavaScript and TypeScript format check, lint, type check, and test steps in sequence. Run both command groups before submitting work that touches both ecosystems.

## Chrome extension foundation

`apps/extension` contains the Manifest V3 capture foundation. Build it with
`pnpm --filter @boardtrace/extension build`, then load its `dist` directory as
an unpacked extension in Chrome. The action injects capture code only for the
active tab after a user click; it has no host permissions or persistent local
capture storage. Its current observer supports BoardTrace-prefixed raw board
attributes only—site adapters, image capture, move inference, and transport
are intentionally outside this phase. See
[extension capture guardrails](docs/security/extension-capture-guardrails.md).

## Security and fair play

The live-analysis lock is a product invariant, not a UI preference. See [the security policy](docs/security/live-analysis-lock.md).

## License

This project is available under the [MIT License](LICENSE).
