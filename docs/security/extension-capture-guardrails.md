# Extension capture guardrails

## Least privilege

The Manifest V3 extension uses `activeTab` and `scripting`. Its generated
manifest grants host access only to the explicitly configured BoardTrace API
origin. It has no persistent content script, screenshot permission, or browser
history permission. The `storage` permission is used only for
`chrome.storage.session`; no data is written to persistent extension storage.
Pressing **Connect current Lichess game** explicitly injects the board adapter
into the active tab.

## Lichess scope and retention

The adapter runs only on exact `https://lichess.org` game URLs and locates the
page's `cg-board`. It records the board rectangle but does not capture pixels,
screenshots, credentials, chat, unrelated page content, or full-page DOM data.
During a live game it sends only game identity, origin, phase, and board
rectangle. It does not send or retain the move list while a clock is active.

After a terminal result is present and no clock is active, the adapter reads
main-line SAN move elements, excludes variation and engine containers, and uses
`chess.js` to validate and convert the completed line to UCI. Invalid,
unsupported, or ambiguous move lists fail closed and are not ingested.

Tokens, queue state, the current Lichess source-game identifier, and a released
result exist only in service-worker memory and `chrome.storage.session`. The
stored result is validated against an exact minimized schema before restoration.
Nothing is written to `chrome.storage.local`, local storage, or IndexedDB.
Browser closure ends the local session. Starting a live game clears earlier
results and identifiers immediately.

## Live-game guardrail

The capture protocol is an exact allowlist. Unknown messages and extra fields
are rejected, and accepted messages are recursively checked for prohibited
analysis fields including `bestMove`, `evaluation`, principal variation, mate
score, alternatives, Stockfish, engine hints, and recommendations.

The service worker never polls a job or result in `LIVE`. Safe job status is
read with the extension token only after completed-game ingestion. Released
analysis is fetched with the paired user's regular token only after the job is
`SUCCEEDED`; the backend remains authoritative for `ANALYSIS_AVAILABLE`.

## Pairing and result delivery

For local development, the popup accepts credentials for an existing local
BoardTrace account. The password is sent directly to the configured local API
and is never retained. The worker creates a one-time pairing for its own
extension ID, exchanges it for `games:ingest` and `games:read-status` scopes,
and immediately revokes the unused refresh token. Only the short-lived user
access token and extension token remain in memory.

The extension token cannot read results or perform user-authorized queue
actions. Queue consent, extension, cancellation, and released-result reads use
the paired user's ordinary access token. The result panel exposes only the
minimized public post-game DTO and is session-only. The DTO may include a SAN
best alternative only after the backend has verified completion and released
`ANALYSIS_AVAILABLE`. The extension does not receive a principal variation or
browser-side engine capability and renders no analysis on the Lichess page.

## Dependency rationale

`chess.js` is an approved workspace technology used only for legal post-game
SAN parsing and UCI conversion. It is maintained, open-source, has no service
cost, and replaces error-prone handwritten notation logic. It is not an engine
and performs no evaluation, search, recommendation, or network operation.
Browser APIs do not provide SAN-to-UCI conversion.
