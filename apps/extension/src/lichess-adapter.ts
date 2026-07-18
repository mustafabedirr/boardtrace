import type { CompletedGamePayload } from './completed-game';

type LichessLocation = Pick<Location, 'protocol' | 'hostname' | 'pathname'> & {
  readonly username?: string;
  readonly password?: string;
};

export function isLichessPage(location: LichessLocation): boolean {
  return location.protocol === 'https:' && location.hostname === 'lichess.org';
}

export function canonicalLichessGameUrl(location: LichessLocation): string | null {
  if (!isLichessPage(location) || location.username || location.password) return null;
  const segments = location.pathname.split('/').filter(Boolean);
  if (segments.length > 2) return null;
  const [gameId, suffix] = segments;
  if (suffix !== undefined && suffix !== 'white' && suffix !== 'black') return null;
  if (gameId === undefined || !/^[a-zA-Z0-9]{8}$/.test(gameId)) return null;
  return `https://lichess.org/${gameId}`;
}

export function isCompletedLichessGame(document: Document): boolean {
  const result = document.querySelector('.game__meta .result, .status.result');
  const postGameControls = document.querySelector(
    '.game__actions, .game__meta .result, [data-icon="flag"]',
  );
  const activeClock = document.querySelector(
    '.clock.running, .clock.active, [data-clock-running="true"]',
  );
  return result !== null && postGameControls !== null && activeClock === null;
}

export function readLichessUciMoves(board: Element): readonly string[] | null {
  const moves = Array.from(board.querySelectorAll<HTMLElement>('[data-uci]'))
    .filter(
      (element) =>
        element.closest(
          '[data-variation], [data-engine], .variation, .pv, .engine, .suggested-move, .opening-explorer',
        ) === null,
    )
    .map((element) => element.dataset.uci?.trim().toLowerCase())
    .filter((move): move is string => move !== undefined);
  return moves.length > 0 ? moves : null;
}

export function lichessPayloadFromBoard(
  payload: CompletedGamePayload,
  board: Element,
): CompletedGamePayload | null {
  const moves = readLichessUciMoves(board);
  if (moves === null) return null;
  return { ...payload, moves, platform: 'lichess' };
}
