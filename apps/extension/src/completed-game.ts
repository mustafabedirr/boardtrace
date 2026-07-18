import type { GameContext } from './protocol';

const MOVE_PATTERN = /^[a-h][1-8][a-h][1-8][qrbn]?$/;
const COMPLETED_AT_ATTRIBUTE = 'data-boardtrace-completed-at';
const MOVES_ATTRIBUTE = 'data-boardtrace-game-moves';
const PLATFORM_ATTRIBUTE = 'data-boardtrace-platform';
const PLAYER_COLOR_ATTRIBUTE = 'data-boardtrace-player-color';
const RESULT_ATTRIBUTE = 'data-boardtrace-game-result';

export interface CompletedGamePayload {
  readonly completed_at: string;
  readonly idempotency_key: string;
  readonly initial_fen: null;
  readonly moves: readonly string[];
  readonly platform: string;
  readonly player_color: 'WHITE' | 'BLACK' | 'UNKNOWN';
  readonly result: 'WHITE_WIN' | 'BLACK_WIN' | 'DRAW' | 'UNKNOWN';
  readonly source_game_id: string;
}

function requiredAttribute(element: Element, name: string): string {
  const value = element.getAttribute(name)?.trim();
  if (!value) throw new Error(`Completed game is missing ${name}.`);
  return value;
}

function enumValue<T extends string>(value: string, allowed: readonly T[]): T {
  if (!allowed.includes(value as T)) throw new Error('Completed game metadata is invalid.');
  return value as T;
}

async function fingerprint(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function normalizeCompletedGame(
  boardElement: Element,
  context: GameContext,
): Promise<CompletedGamePayload> {
  if (context.phase !== 'POST_GAME' || context.gameId === null) {
    throw new Error('Only completed games can be ingested.');
  }
  const parsedMoves: unknown = JSON.parse(requiredAttribute(boardElement, MOVES_ATTRIBUTE));
  if (
    !Array.isArray(parsedMoves) ||
    parsedMoves.length === 0 ||
    !parsedMoves.every((move) => typeof move === 'string')
  ) {
    throw new Error('Completed game moves are invalid.');
  }
  const moves = parsedMoves.map((move) => move.trim().toLowerCase());
  if (!moves.every((move) => MOVE_PATTERN.test(move)))
    throw new Error('Completed game moves must use UCI.');
  const completedAt = requiredAttribute(boardElement, COMPLETED_AT_ATTRIBUTE);
  if (Number.isNaN(Date.parse(completedAt)))
    throw new Error('Completed game timestamp is invalid.');
  const platform = requiredAttribute(boardElement, PLATFORM_ATTRIBUTE);
  const playerColor = enumValue(requiredAttribute(boardElement, PLAYER_COLOR_ATTRIBUTE), [
    'WHITE',
    'BLACK',
    'UNKNOWN',
  ] as const);
  const result = enumValue(requiredAttribute(boardElement, RESULT_ATTRIBUTE), [
    'WHITE_WIN',
    'BLACK_WIN',
    'DRAW',
    'UNKNOWN',
  ] as const);
  return {
    completed_at: new Date(completedAt).toISOString(),
    idempotency_key: await fingerprint(
      JSON.stringify([context.sourceOrigin, context.gameId, completedAt, moves]),
    ),
    initial_fen: null,
    moves,
    platform,
    player_color: playerColor,
    result,
    source_game_id: context.gameId,
  };
}
