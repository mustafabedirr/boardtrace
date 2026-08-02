import { normalizeCompletedLichessGame } from './completed-game';
import {
  extractCompletedLichessGame,
  fetchCompletedLichessGame,
  findLichessBoard,
  inspectLichessAdapter,
  isLichessPage,
  readLichessGamePhase,
} from './lichess-adapter';
import { assertFairPlayMessage, type ExtensionMessage } from './protocol';

let observer: MutationObserver | undefined;
let submittedGameId: string | undefined;
let submissionInFlight = false;

async function send(message: ExtensionMessage): Promise<void> {
  await chrome.runtime.sendMessage(assertFairPlayMessage(message));
}

function regionFor(board: Element) {
  const { height, width, x, y } = board.getBoundingClientRect();
  return { height, width, x, y };
}

async function submitIfCompleted(): Promise<void> {
  if (submissionInFlight) return;
  submissionInFlight = true;
  let completed = extractCompletedLichessGame(document, window.location);
  const diagnostics = inspectLichessAdapter(document, window.location);
  if (
    completed === null &&
    diagnostics.resultDetected &&
    !diagnostics.hasActiveClock &&
    diagnostics.canonicalGameUrl
  ) {
    try {
      completed = await fetchCompletedLichessGame(window.location);
    } catch (error: unknown) {
      console.warn('BoardTrace could not read the completed public Lichess game export.', error);
    }
  }
  if (completed === null) {
    await send({
      ...diagnostics,
      status: 'MAINLINE_CONVERSION_FAILED',
      type: 'capture/adapter-status',
    });
    submissionInFlight = false;
    return;
  }
  if (completed.sourceGameId === submittedGameId) {
    submissionInFlight = false;
    return;
  }
  submittedGameId = completed.sourceGameId;
  try {
    const payload = await normalizeCompletedLichessGame(completed);
    await send({ payload, type: 'capture/completed-game' });
  } catch (error: unknown) {
    submittedGameId = undefined;
    console.warn('BoardTrace completed-game normalization failed.', error);
  } finally {
    submissionInFlight = false;
  }
}

async function connectToLichess(): Promise<void> {
  if (!isLichessPage(window.location))
    throw new Error('BoardTrace supports lichess.org game pages.');
  const board = findLichessBoard(document);
  if (board === null) throw new Error('A Lichess chessboard is not available on this page.');

  observer?.disconnect();
  const phase = readLichessGamePhase(document);
  const gameId = window.location.pathname.split('/').filter(Boolean)[0] ?? null;
  await send({
    context: { gameId, phase, sourceOrigin: window.location.origin },
    region: regionFor(board),
    type: 'capture/started',
  });
  if (phase === 'POST_GAME') {
    await submitIfCompleted();
  } else if (phase === 'UNKNOWN') {
    await send({
      ...inspectLichessAdapter(document, window.location),
      status: 'TERMINAL_SCORE_NOT_FOUND',
      type: 'capture/adapter-status',
    });
  }

  observer = new MutationObserver(() => {
    if (readLichessGamePhase(document) === 'POST_GAME') void submitIfCompleted();
  });
  observer.observe(document.body, {
    attributeFilter: ['class', 'data-clock-running', 'data-result'],
    attributes: true,
    childList: true,
    subtree: true,
  });
}

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (
    typeof message === 'object' &&
    message !== null &&
    'type' in message &&
    message.type === 'capture/connect-lichess'
  ) {
    void connectToLichess()
      .then(() => sendResponse({ ok: true }))
      .catch((error: unknown) =>
        sendResponse({
          message: error instanceof Error ? error.message : 'Lichess connection failed.',
          ok: false,
        }),
      );
    return true;
  }
  return false;
});
