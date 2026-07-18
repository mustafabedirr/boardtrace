import { observationAttributes, readBoardObservation, readGameContext } from './board-observer';
import { normalizeCompletedGame } from './completed-game';
import { isCompletedLichessGame, isLichessPage, lichessPayloadFromBoard } from './lichess-adapter';
import { assertFairPlayMessage, type ExtensionMessage } from './protocol';

let observer: MutationObserver | undefined;

function send(message: ExtensionMessage): void {
  chrome.runtime.sendMessage(assertFairPlayMessage(message)).catch((error: unknown) => {
    console.warn('BoardTrace capture message was not delivered.', error);
  });
}

function observeBoard(board: Element): void {
  observer?.disconnect();
  const context = readGameContext(board);

  send({
    context,
    region: readBoardObservation(board).region,
    type: 'capture/started',
  });
  if (
    context.phase === 'POST_GAME' &&
    isLichessPage(window.location) &&
    isCompletedLichessGame(document)
  ) {
    void normalizeCompletedGame(board, context)
      .then((payload) => lichessPayloadFromBoard(payload, board))
      .then((payload) => {
        if (payload !== null) send({ payload, type: 'capture/completed-game' });
      })
      .catch((error: unknown) =>
        console.warn('BoardTrace completed-game normalization failed.', error),
      );
  }

  observer = new MutationObserver((records) => {
    if (
      !records.some(
        (record) =>
          record.type === 'attributes' &&
          record.attributeName !== null &&
          observationAttributes.includes(
            record.attributeName as (typeof observationAttributes)[number],
          ),
      )
    ) {
      return;
    }

    send({
      context: readGameContext(board),
      observation: readBoardObservation(board),
      type: 'capture/board-observed',
    });
  });

  observer.observe(board, { attributes: true, attributeFilter: [...observationAttributes] });
}

function selectBoardFromClick(event: MouseEvent): void {
  const candidate = event.target;
  if (!(candidate instanceof Element)) {
    return;
  }

  event.preventDefault();
  event.stopPropagation();
  document.removeEventListener('click', selectBoardFromClick, true);
  observeBoard(candidate);
}

chrome.runtime.onMessage.addListener((message: unknown) => {
  if (
    typeof message === 'object' &&
    message !== null &&
    'type' in message &&
    message.type === 'capture/select-board'
  ) {
    document.addEventListener('click', selectBoardFromClick, true);
  }
});
