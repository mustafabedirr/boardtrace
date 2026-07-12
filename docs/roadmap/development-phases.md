# Development Phases

This roadmap defines delivery order. A phase may start only after its stated prerequisites and completion criteria are met. Documenting a phase does not authorize implementing it early.

## 1. Environment validation

- **Goal:** Confirm the local development environment and repository access are suitable for planned work.
- **Key output:** Recorded tool, version, access, and constraint checks.
- **Prerequisites:** Repository is available locally.
- **Completion criteria:** Required checks are documented; sandbox limitations are distinguished from project blockers.

## 2. Repository initialization

- **Goal:** Establish the repository foundation and monorepo layout.
- **Key output:** Root metadata, documentation, agent rules, ignore files, environment template, and tracked empty top-level directories.
- **Prerequisites:** Environment validation is complete.
- **Completion criteria:** Repository structure and baseline documentation exist without application scaffolding or dependencies.

## 3. Project standards and tooling

- **Goal:** Define code-quality, formatting, linting, type-checking, and test conventions.
- **Key output:** Scoped tool configurations and documented contributor workflows.
- **Prerequisites:** Repository initialization is complete.
- **Completion criteria:** Standards can be run consistently in their applicable projects without weakening security or type rules.

## 4. Design system foundation

- **Goal:** Establish reusable BoardTrace visual foundations for the dark-first product.
- **Key output:** Tokens, typography, color, accessibility, and component conventions.
- **Prerequisites:** Project standards and tooling are complete.
- **Completion criteria:** Design rules reflect the approved branding, avoid glassmorphism and neon esports styling, and target WCAG 2.2 AA.

## 5. FastAPI backend foundation

- **Goal:** Create the modular-monolith backend boundary and base application conventions.
- **Key output:** FastAPI project structure, configuration, validation, error handling, and health-oriented foundations.
- **Prerequisites:** Project standards and tooling are complete.
- **Completion criteria:** Backend modules have explicit boundaries and preserve Python typing and Pydantic validation.

## 6. PostgreSQL data model

- **Goal:** Model durable game, capture, analysis, report, and audit state.
- **Key output:** SQLAlchemy models and Alembic migrations.
- **Prerequisites:** FastAPI backend foundation is complete.
- **Completion criteria:** Schema changes are migration-backed; lifecycle and locked analysis data are explicitly represented.

## 7. Stockfish analysis core

- **Goal:** Build backend-only engine analysis capabilities.
- **Key output:** Native Stockfish integration through python-chess UCI with persisted, locked results.
- **Prerequisites:** FastAPI backend foundation and PostgreSQL data model are complete.
- **Completion criteria:** Stockfish executes only in a backend worker context and no engine result is client-accessible during a live game.

## 8. Game state and analysis lock

- **Goal:** Enforce server-authoritative game lifecycle and report release controls.
- **Key output:** State machine, lock checks, audit logging, and state-aware serializers.
- **Prerequisites:** PostgreSQL data model and Stockfish analysis core are complete.
- **Completion criteria:** Reports remain locked until `ANALYSIS_AVAILABLE`; pre-release payloads contain no engine-derived fields.

## 9. Browser capture prototype

- **Goal:** Prove safe, user-selected chessboard capture.
- **Key output:** A scoped capture flow for the selected board region.
- **Prerequisites:** Project standards and tooling are complete.
- **Completion criteria:** The prototype processes only the selected board region and does not store full-screen images by default.

## 10. Board change detection

- **Goal:** Detect meaningful changes between captured board states.
- **Key output:** Reliable board-change signals and capture deduplication behavior.
- **Prerequisites:** Browser capture prototype is complete.
- **Completion criteria:** Repeated unchanged captures are filtered and changes are observable without collecting unrelated page content.

## 11. Vision inference contract

- **Goal:** Define the boundary between board images and validated position outputs.
- **Key output:** Versioned inference inputs, outputs, confidence handling, and error contract.
- **Prerequisites:** Board change detection and PostgreSQL data model are complete.
- **Completion criteria:** Vision consumers can validate FEN candidates, confidence, provenance, and failures through a stable contract.

## 12. Synthetic dataset and model training

- **Goal:** Produce reproducible training data and a board-recognition model pipeline.
- **Key output:** Dataset specification, training workflow, evaluation metrics, and model-version records.
- **Prerequisites:** Vision inference contract is complete.
- **Completion criteria:** Training and evaluation are reproducible; generated models remain outside source control unless a reviewed fixture exception exists.

## 13. Legal move inference

- **Goal:** Infer legal position transitions from recognized board states.
- **Key output:** Chess-rule validation and ambiguity-resolution logic using python-chess.
- **Prerequisites:** Vision inference contract and synthetic-model evaluation are complete.
- **Completion criteria:** Inferred moves are legal or explicitly marked unresolved; invalid transitions cannot silently enter analysis.

## 14. Chrome extension

- **Goal:** Deliver the Manifest V3 capture client with consented board selection.
- **Key output:** Chrome extension UI, capture controls, scoped transport, and safe local state.
- **Prerequisites:** Browser capture prototype, board change detection, and legal move inference are complete.
- **Completion criteria:** Least-privilege capture works end-to-end without client-side Stockfish or stored live-analysis data.

## 15. Celery and Redis workers

- **Goal:** Run vision, engine, and report jobs reliably in the backend.
- **Key output:** Celery queues, Redis coordination, retry policy, job lifecycle records, and worker boundaries.
- **Prerequisites:** FastAPI backend foundation, PostgreSQL data model, Stockfish analysis core, and vision inference contract are complete.
- **Completion criteria:** Jobs are observable, idempotency and failures are handled deliberately, and workers preserve the analysis lock.

## 16. Game history interface

- **Goal:** Let users find completed games and their release state.
- **Key output:** Secure game-history views and non-sensitive lifecycle indicators.
- **Prerequisites:** Chrome extension, game state and analysis lock, and backend APIs are complete.
- **Completion criteria:** Active games reveal no analysis data; completed and available reports are clearly distinguishable.

## 17. Post-game analysis dashboard

- **Goal:** Present released analysis clearly after verified game completion.
- **Key output:** Evaluation graph, critical moves, classifications, comparisons, variations, and summary UI.
- **Prerequisites:** Game history interface, Celery and Redis workers, and analysis lock are complete.
- **Completion criteria:** The dashboard reads only released reports and meets established visual and accessibility standards.

## 18. End-to-end and security tests

- **Goal:** Verify critical user paths and the fair-play boundary.
- **Key output:** End-to-end, integration, and security-invariant test coverage.
- **Prerequisites:** Chrome extension, workers, locking, and post-game dashboard are complete.
- **Completion criteria:** Tests demonstrate that engine fields cannot reach the client before release and key completion flows pass.

## 19. Docker Compose environment

- **Goal:** Provide a repeatable local multi-service environment.
- **Key output:** Documented Compose configuration for approved infrastructure and services.
- **Prerequisites:** Backend, workers, data stores, and their configuration contracts are complete.
- **Completion criteria:** A documented local environment can run supported services with safe example configuration.

## 20. CI/CD

- **Goal:** Automate quality gates and controlled delivery.
- **Key output:** Continuous integration checks and deployment pipeline documentation/configuration.
- **Prerequisites:** End-to-end tests and Docker Compose environment are complete.
- **Completion criteria:** Required validation gates run automatically and deployment does not bypass security or migration controls.

## 21. MVP audit

- **Goal:** Assess MVP readiness across product, security, privacy, quality, and operations.
- **Key output:** Auditable launch checklist, risk register, and deferred-work record.
- **Prerequisites:** CI/CD and all MVP capabilities are complete.
- **Completion criteria:** Open risks have owners and decisions; no known live-analysis-lock violation remains; launch scope is explicitly approved.
