# Project Identity

BoardTrace is a dark-first, post-game chess analysis platform. Tagline: **Review every decision.** Visual direction: Precision Analytics + Modern Chess.

# Product Boundaries

BoardTrace may capture positions for later review but must not provide live chess assistance, coaching, engine output, or move recommendations during an active game.

# Architecture

Use a modular monolith. Keep explicit boundaries for capture, games, analysis, reports, storage, and identity so extraction can happen later only when justified. Do not introduce early microservices.

# Repository Structure

`apps/` is for future applications; `packages/` shared TypeScript code; `workers/` future worker entry points; `ml/` vision assets; `infrastructure/` deployment configuration; `tests/` shared tests; `docs/` project records. Do not scaffold future applications before their dedicated prompt.

# Approved Technology Stack

Web: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand, chess.js, react-chessboard, Recharts. Extension: Chrome Manifest V3, React, TypeScript, Vite, Canvas API, OffscreenCanvas, Web Workers. Backend: Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, python-chess. Vision: PyTorch, OpenCV, Pillow, Albumentations, ONNX, ONNX Runtime. Engine: native Stockfish via python-chess UCI. Infrastructure: PostgreSQL, Redis, Celery, MinIO/S3 storage, Docker Compose. Tests: pytest, Vitest, Playwright. Use pnpm 11.11.0 and plan for uv in Python.

# Security Invariants

1. Engine results must never be sent to a client during a live game.
2. `bestMove`, `evaluation`, `principalVariation`, `mateScore`, and alternative moves must not exist during a live game in any API response, WebSocket message, browser state, local storage, or IndexedDB field.
3. Stockfish must not run in the browser or browser extension.
4. Stockfish runs only in a backend worker process.
5. Analysis endpoints remain locked before `ANALYSIS_AVAILABLE`.
6. The extension processes only the user-selected board region.
7. Full-screen images must not be stored by default.
8. Apply data minimization to user data and images.
9. New dependencies need a documented rationale.
10. A new framework may not invalidate approved technology decisions.
11. TypeScript strict settings may not be weakened.
12. Do not use `any`, `@ts-ignore`, silent exceptions, or temporary security bypasses as default solutions.
13. Preserve Python type hints and validation.
14. Database schema changes require migrations.
15. Do not report placeholder, mock, or TODO code as completed functionality.
16. Do not hide failed tests or skip them without a justified reason.
17. Each prompt implements only its own scope.
18. Do not implement later phases early.
19. Do not alter global Codex or system configuration as part of repository work.
20. Never commit secrets.

# Privacy Rules

Capture only the selected board region and only necessary data. Do not collect credentials, unrelated page content, or full-screen screenshots by default. Document retention and deletion for every new persisted data category.

# Backend Rules

The backend owns game state and release decisions. Validate inputs with Pydantic, preserve Python type hints, use structured audit logs, and do not swallow exceptions.

## FastAPI Foundation Rules

1. Every endpoint must use typed request and response models and live under a versioned router.
2. Preserve the application factory; imports must not start network listeners, workers, or external resources.
3. Read environment configuration only through typed settings.
4. Never log credentials, authorization headers, request bodies, screenshots, FEN values, or secrets.
5. API failures must use the standard error envelope and include a string request ID.
6. Do not use global mutable application state; test-only routes are injected per app instance only.
7. Health endpoints report only real dependencies and must not claim database, worker, or engine readiness before those integrations exist.
8. API changes require API tests and OpenAPI contract validation.
9. No endpoint may expose live analysis, engine output, best moves, evaluations, principal variations, mate scores, or analysis payloads before `ANALYSIS_AVAILABLE`.

# Frontend Rules

Use strict TypeScript. The client is untrusted and may display only server-authorized information.

# Browser Extension Rules

Use Manifest V3 and least privilege. Process only the selected board region; never run Stockfish or persist full-screen captures by default.

# Computer Vision Rules

Keep inputs board-scoped. Version models and preprocessing deliberately; do not commit model binaries except documented, reviewed fixture exceptions.

# Database and Migration Rules

Use Alembic for every schema change. Model state transitions and locks explicitly; never bypass migrations.

# UI and Branding Rules

Use shadcn/ui, Tailwind CSS, and Lucide React. Primary font: IBM Plex Sans; technical font: IBM Plex Mono. Default dark-first colors: primary `#6366F1`, secondary `#06B6D4`, background `#090B10`, surface `#11151E`, border `#2C3547`, light background `#F6F8FC`, light surface `#FFFFFF`, dark text `#F4F7FB`, light text `#101522`. Use controlled 8–12 px radii, thin borders, and limited shadows. No glassmorphism or neon esports aesthetic. Do not use color alone for status; target WCAG 2.2 AA.

# Dependency Policy

Document rationale, maintenance/security fit, cost, and why approved tools are insufficient before adding a dependency.

# Testing Requirements

Add proportionate automated tests, especially for security invariants. Do not hide failures or report mocks, placeholders, or TODOs as complete.

# Tooling Quality Gates

ESLint and Prettier are mandatory for JavaScript and TypeScript. Ruff and Mypy are mandatory for Python. New code is not complete until it has been tested with the relevant language's standard runner. Resolve format and lint errors before committing; agents must not bypass quality-gate commands. Generated files must not be manually edited.

# Documentation Requirements

Update architecture, ADRs, security documentation, environment examples, and setup notes whenever the change affects them.

# Definition of Done

Work is done only when it stays in prompt scope, meets security and privacy rules, is verified proportionately, documented as needed, and accurately reported.

# Forbidden Shortcuts

No weakened TypeScript strictness, default `any`/ignore directives/silent exceptions/security bypasses, migration bypasses, hidden failing tests, premature future work, global configuration changes, or committed secrets.

# Agent Workflow

Read this file and existing files before edits. Check Git status, preserve unrelated work, make small reviewable changes, verify proportionately, and report limitations honestly. Docker inaccessibility inside the Codex sandbox is not a blocker when externally verified.
