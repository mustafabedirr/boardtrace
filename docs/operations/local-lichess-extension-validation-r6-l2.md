# Local Lichess extension validation — R6-L2

This checklist is local-development evidence only. It authorizes no deployment,
pilot, browser-store submission, or technical go/no-go decision.

## Automated evidence captured 2026-08-03

| Check                                       | Result                                                    |
| ------------------------------------------- | --------------------------------------------------------- |
| Extension Vitest                            | 25 passed                                                 |
| Strict TypeScript                           | Passed                                                    |
| ESLint                                      | Passed                                                    |
| Development build                           | Passed; generated manifest targets only `127.0.0.1:18080` |
| Synthetic DOM attribute scan                | No source matches                                         |
| Focused backend live/ineligible safety      | 42 passed                                                 |
| Local login, pairing creation, and exchange | Passed; token output suppressed                           |
| Local API, PostgreSQL, Redis, worker, Caddy | Healthy                                                   |
| Real browser live-game safety smoke         | Passed in user-assisted Edge run                          |
| Completed-game ingestion and worker smoke   | Passed in user-assisted Edge run                          |

The local stack remains running only for final result-panel validation. It must
be stopped after that test, without volume deletion.

## Build and load

1. Verify `http://127.0.0.1:18080/health` returns `{"status":"ok"}`.
2. Build from the repository root:

   ```powershell
   $env:BOARDTRACE_EXTENSION_API_BASE_URL='http://127.0.0.1:18080'
   pnpm --filter @boardtrace/extension build:local
   ```

3. Open `chrome://extensions` or `edge://extensions`, enable developer mode,
   choose **Load unpacked**, and select `C:\boardtrace\apps\extension\dist`.
4. Confirm only `activeTab`, `scripting`, `storage`, and
   `http://127.0.0.1:18080/*` API host access are requested.

## Pairing

Use an existing disposable local account. Open the popup, enter that account's
email and password, and press **Pair locally**. Expected state: `READY`. Never
use production or personal credentials.

Credentials are never stored. Access tokens and minimized UI state use
`chrome.storage.session`, which survives Manifest V3 service-worker suspension
but is cleared when the browser session ends.

## Live-game safety smoke test

This requires user-controlled normal Lichess activity. Do not automate
matchmaking, moves, clocks, or gameplay.

1. Open a real active Lichess game already being played or observed normally.
2. Press **Connect current Lichess game**.
3. Confirm `LIVE` and the safety-lock notice.
4. Confirm there is no ingestion, job, outbox event, Stockfish invocation,
   analysis request, result DTO, centipawn value, recommendation, or prior
   result retained in extension state.
5. Any such output is an immediate blocker.

## Completed-game smoke test

1. Wait for an exact terminal result and inactive clocks, or open an already
   completed standard-chess Lichess game and connect.
2. Confirm `INGESTING`, then `QUEUED` or a server-authorized queue state.
3. If busy, verify `CONSENT_REQUIRED`, `WAITING`, position, countdown,
   **Extend wait**, and **Cancel queued analysis**.
4. Confirm `RUNNING` appears only after the safe job endpoint reports it.
5. Confirm the result appears only after worker success and server release.
   Compare game ID, move count, SAN, quality, CPL, accuracy, ACPL, and the
   server-authorized best alternative with the public API response. A best
   alternative is displayed only when it differs from the played move.
6. Clear the session and confirm the result disappears. Starting another live
   game must also clear it immediately.

After reviewing a released result, **Analyze another game** clears only the
previous game, job, source identifier, and result while preserving local
pairing. **Disconnect and clear session** is the explicit full sign-out action
and requires pairing again.

The decision-review panel is intentionally interactive only after release. It
shows played SAN, quality, CPL, after-position evaluation, and the released
alternative SAN. It never overlays the Lichess page and never creates a live
toast, alert, recommendation, or next-move prompt.

If a completed Lichess view does not expose main-line move nodes, the content
script makes one credential-free, read-only request to Lichess's public
single-game export endpoint. The fallback runs only after a terminal score is
present in the page; it explicitly excludes clocks, evaluations, openings, and
computer annotations, and retains the response only long enough to normalize
the completed game for the local API.

## Automated evidence

```powershell
pnpm --filter @boardtrace/extension test
pnpm --filter @boardtrace/extension typecheck
pnpm --filter @boardtrace/extension lint
pnpm exec prettier --check apps/extension
rg "data-boardtrace|capture/board-observed" apps/extension/src
```

The source scan must return no matches. `dist` is a local unpacked artifact and
is not committed by this stage.

## Cleanup

Clear the popup session, remove the unpacked extension if no longer needed, and
stop the local stack without deleting volumes:

```powershell
docker compose -f infrastructure/production-like/compose.yaml down
```
