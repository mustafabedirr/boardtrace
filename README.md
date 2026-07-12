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

| Area | Technologies |
| --- | --- |
| Web | Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand, chess.js, react-chessboard, Recharts |
| Extension | Chrome Manifest V3, React, TypeScript, Vite, Canvas API, OffscreenCanvas, Web Workers |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, python-chess |
| Vision | PyTorch, OpenCV, Pillow, Albumentations, ONNX, ONNX Runtime |
| Engine | Native Stockfish via python-chess UCI |
| Infrastructure | PostgreSQL, Redis, Celery, MinIO/S3-compatible storage, Docker Compose |
| Testing | pytest, Vitest, Playwright |
| Packages | pnpm 11.11.0; Python is planned to use uv |

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

## Current status

Repository initialization only. No application framework, database, container service, worker, or product feature has been scaffolded.

## Local setup

Local setup will be introduced in later prompts.

## Security and fair play

The live-analysis lock is a product invariant, not a UI preference. See [the security policy](docs/security/live-analysis-lock.md).

## License

The license has not yet been determined.
