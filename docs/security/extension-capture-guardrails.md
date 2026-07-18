# Extension capture guardrails

## Least privilege

The extension uses Manifest V3 with only `activeTab` and `scripting`. It has no
host permissions, no `chrome.storage` permission, and no background content
scripts. The service worker injects the content script only after the user
clicks the extension action on the active tab.

## Scope and retention

The user explicitly selects one DOM element as the board. The content script
observes only four BoardTrace-prefixed attributes on that element and sends its
bounding rectangle plus raw board/move observations. It does not call
`captureVisibleTab`, `getDisplayMedia`, canvas screenshot APIs, or a full-page
DOM scanner. No image, observation, game context, or move data is persisted in
extension storage. Transport is deliberately deferred until a server capture
contract exists.

## Live-game guardrail

The message protocol is an exact allowlist: unknown message types and extra
fields are rejected. Every accepted runtime message is also recursively checked
for prohibited analysis fields, including `bestMove`, `evaluation`, principal
variation, mate score, candidate moves, alternatives, Stockfish, and engine
hints. Such a message is rejected before it can be handled. The extension has
no engine dependency, worker, analysis endpoint, or report UI.

This guardrail complements, but does not replace, the server-authoritative
`ANALYSIS_AVAILABLE` release lock.

## Dependencies

The package declares only build-time dependencies already approved and used by
the workspace: TypeScript for strict compilation, Vite for the MV3 artifact
build, Vitest for protocol tests, ESLint and Prettier for mandatory quality
gates, and `@types/node` for the Vite configuration. Their pinned compatible
ranges match the root workspace, are open-source tools with no service cost or
runtime extension payload, and avoid an unsafe reliance on hoisted transitive
executables. The small local Chrome API declaration still covers only the APIs
used by this least-privilege foundation. React-based UI, site adapters, image
capture, and backend transport remain deferred until their dedicated scope.
