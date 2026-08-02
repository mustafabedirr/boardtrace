import { Chess } from 'chess.js';

import type { CompletedLichessGame } from './completed-game';
import type { GamePhase } from './protocol';

type LichessLocation = Pick<Location, 'protocol' | 'hostname' | 'pathname'> & {
  readonly password?: string;
  readonly username?: string;
};

const MOVE_SELECTORS = [
  '.analyse__moves move',
  '.round__app move',
  'l4x move',
  'kwdb move',
  'rm6 move',
  '.moves move',
  '[data-ply][data-san]',
].join(',');

const RESULT_SELECTORS = [
  '.analyse__moves .result',
  '.round__app .result',
  '.result-wrap .result',
  '.game__meta .result',
  '.status.result',
  '[data-result]',
  '.result',
  '.round__app rm6',
  '.round__app kwdb',
  '.round__app l4x',
].join(',');

const ACTIVE_CLOCK_SELECTORS = [
  '.clock.running',
  '.clock.active',
  '.rclock.running',
  '.rclock.active',
  '[data-clock-running="true"]',
].join(',');

export function isLichessPage(location: LichessLocation): boolean {
  return location.protocol === 'https:' && location.hostname === 'lichess.org';
}

export function canonicalLichessGameUrl(location: LichessLocation): string | null {
  if (!isLichessPage(location) || location.username || location.password) return null;
  const segments = location.pathname.split('/').filter(Boolean);
  if (segments.length > 2) return null;
  const [gameIdWithPlayerToken, suffix] = segments;
  if (suffix !== undefined && suffix !== 'white' && suffix !== 'black') return null;
  if (
    gameIdWithPlayerToken === undefined ||
    !/^(?:[a-zA-Z0-9]{8}|[a-zA-Z0-9]{12})$/.test(gameIdWithPlayerToken)
  ) {
    return null;
  }
  const gameId = gameIdWithPlayerToken.slice(0, 8);
  return `https://lichess.org/${gameId}`;
}

export function parseLichessResult(
  values: readonly string[],
): CompletedLichessGame['result'] | null {
  for (const value of values) {
    const normalized = value.replaceAll('\u00bd', '1/2').replaceAll(' ', '');
    if (normalized.includes('1-0')) return 'WHITE_WIN';
    if (normalized.includes('0-1')) return 'BLACK_WIN';
    if (normalized.includes('1/2-1/2')) return 'DRAW';
  }
  return null;
}

function cleanSan(value: string): string {
  return value
    .replaceAll('\u00a0', ' ')
    .replace(/^\s*\d+\.(?:\.\.)?\s*/, '')
    .replace(/[?!]+$/u, '')
    .trim();
}

export function lichessSansToUci(values: readonly string[]): readonly string[] | null {
  const chess = new Chess();
  const moves: string[] = [];
  try {
    for (const value of values) {
      const san = cleanSan(value);
      if (san.length === 0) continue;
      const move = chess.move(san, { strict: false });
      moves.push(`${move.from}${move.to}${move.promotion ?? ''}`);
    }
  } catch {
    return null;
  }
  return moves.length > 0 ? moves : null;
}

export function classifyLichessPhase(
  result: CompletedLichessGame['result'] | null,
  hasActiveClock: boolean,
): GamePhase {
  if (hasActiveClock) return 'LIVE';
  return result === null ? 'UNKNOWN' : 'POST_GAME';
}

function resultTexts(document: Document): readonly string[] {
  return Array.from(document.querySelectorAll<HTMLElement>(RESULT_SELECTORS)).map(
    (element) => element.dataset.result ?? element.textContent ?? '',
  );
}

function sanTexts(document: Document): readonly string[] {
  return Array.from(document.querySelectorAll<HTMLElement>(MOVE_SELECTORS))
    .filter(
      (element) =>
        element.closest('[data-variation], .variation, .pv, .engine, .opening-explorer') === null,
    )
    .map(
      (element) =>
        element.dataset.san ??
        element.querySelector('san')?.textContent ??
        element.textContent ??
        '',
    );
}

export interface LichessAdapterDiagnostics {
  readonly canonicalGameUrl: boolean;
  readonly hasActiveClock: boolean;
  readonly moveNodeCount: number;
  readonly resultDetected: boolean;
}

export function inspectLichessAdapter(
  document: Document,
  location: LichessLocation,
): LichessAdapterDiagnostics {
  return {
    canonicalGameUrl: canonicalLichessGameUrl(location) !== null,
    hasActiveClock: document.querySelector(ACTIVE_CLOCK_SELECTORS) !== null,
    moveNodeCount: sanTexts(document).length,
    resultDetected: parseLichessResult(resultTexts(document)) !== null,
  };
}

function playerColor(location: LichessLocation): CompletedLichessGame['playerColor'] {
  const suffix = location.pathname.split('/').filter(Boolean)[1];
  if (suffix === 'white') return 'WHITE';
  if (suffix === 'black') return 'BLACK';
  return 'UNKNOWN';
}

export function readLichessGamePhase(document: Document): GamePhase {
  return classifyLichessPhase(
    parseLichessResult(resultTexts(document)),
    document.querySelector(ACTIVE_CLOCK_SELECTORS) !== null,
  );
}

export function extractCompletedLichessGame(
  document: Document,
  location: LichessLocation,
  now = new Date(),
): CompletedLichessGame | null {
  const canonicalUrl = canonicalLichessGameUrl(location);
  const result = parseLichessResult(resultTexts(document));
  if (
    canonicalUrl === null ||
    result === null ||
    document.querySelector(ACTIVE_CLOCK_SELECTORS) !== null
  ) {
    return null;
  }
  const sanMoves = sanTexts(document);
  const moves = lichessSansToUci(sanMoves);
  if (moves === null) return null;
  return {
    completedAt: now.toISOString(),
    moves,
    playerColor: playerColor(location),
    result,
    sourceGameId: canonicalUrl.slice(-8),
  };
}

interface LichessExport {
  readonly id: string;
  readonly lastMoveAt: number;
  readonly moves: string;
  readonly status: string;
  readonly winner?: 'black' | 'white';
}

function parseLichessExport(value: unknown, expectedGameId: string): LichessExport | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const payload = value as Record<string, unknown>;
  if (
    payload.id !== expectedGameId ||
    typeof payload.lastMoveAt !== 'number' ||
    !Number.isFinite(payload.lastMoveAt) ||
    typeof payload.moves !== 'string' ||
    typeof payload.status !== 'string' ||
    (payload.winner !== undefined && payload.winner !== 'white' && payload.winner !== 'black')
  ) {
    return null;
  }
  return {
    id: payload.id,
    lastMoveAt: payload.lastMoveAt,
    moves: payload.moves,
    status: payload.status,
    ...(payload.winner === undefined ? {} : { winner: payload.winner }),
  };
}

export async function fetchCompletedLichessGame(
  location: LichessLocation,
  fetcher: typeof fetch = fetch,
): Promise<CompletedLichessGame | null> {
  const canonicalUrl = canonicalLichessGameUrl(location);
  if (canonicalUrl === null) return null;
  const gameId = canonicalUrl.slice(-8);
  const response = await fetcher(
    `https://lichess.org/game/export/${gameId}?evals=false&clocks=false&opening=false&literate=false`,
    {
      cache: 'no-store',
      credentials: 'omit',
      headers: { Accept: 'application/json' },
      method: 'GET',
    },
  );
  if (!response.ok) return null;
  const exported = parseLichessExport(await response.json(), gameId);
  if (exported === null || ['created', 'started'].includes(exported.status)) return null;
  const result: CompletedLichessGame['result'] | null =
    exported.winner === 'white'
      ? 'WHITE_WIN'
      : exported.winner === 'black'
        ? 'BLACK_WIN'
        : ['draw', 'stalemate'].includes(exported.status)
          ? 'DRAW'
          : null;
  if (result === null) return null;
  const moves = lichessSansToUci(exported.moves.split(/\s+/u));
  if (moves === null) return null;
  return {
    completedAt: new Date(exported.lastMoveAt).toISOString(),
    moves,
    playerColor: playerColor(location),
    result,
    sourceGameId: gameId,
  };
}

export function findLichessBoard(document: Document): Element | null {
  return document.querySelector('cg-board');
}
