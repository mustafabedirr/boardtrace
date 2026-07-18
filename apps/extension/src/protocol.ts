export const FORBIDDEN_ANALYSIS_FIELD_NAMES = new Set([
  'bestmove',
  'evaluation',
  'principalvariation',
  'pv',
  'matescore',
  'candidatemoves',
  'alternatives',
  'stockfish',
  'engineanalysis',
  'enginehint',
  'moverecommendation',
]);

export type GamePhase = 'UNKNOWN' | 'LIVE' | 'POST_GAME';

export interface BoardRegion {
  readonly height: number;
  readonly width: number;
  readonly x: number;
  readonly y: number;
}

export interface GameContext {
  readonly gameId: string | null;
  readonly phase: GamePhase;
  readonly sourceOrigin: string;
}

export interface BoardObservation {
  readonly boardState: string | null;
  readonly moveText: string | null;
  readonly observedAt: string;
  readonly region: BoardRegion;
}

export interface CaptureStartedMessage {
  readonly context: GameContext;
  readonly region: BoardRegion;
  readonly type: 'capture/started';
}

export interface BoardObservedMessage {
  readonly context: GameContext;
  readonly observation: BoardObservation;
  readonly type: 'capture/board-observed';
}

export interface SelectBoardMessage {
  readonly type: 'capture/select-board';
}

export interface CompletedGameMessage {
  readonly payload: {
    readonly completed_at: string;
    readonly idempotency_key: string;
    readonly initial_fen: null;
    readonly moves: readonly string[];
    readonly platform: string;
    readonly player_color: 'WHITE' | 'BLACK' | 'UNKNOWN';
    readonly result: 'WHITE_WIN' | 'BLACK_WIN' | 'DRAW' | 'UNKNOWN';
    readonly source_game_id: string;
  };
  readonly type: 'capture/completed-game';
}

export type ExtensionMessage =
  BoardObservedMessage | CaptureStartedMessage | CompletedGameMessage | SelectBoardMessage;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key));
}

function isBoardRegion(value: unknown): value is BoardRegion {
  if (!isRecord(value) || !hasOnlyKeys(value, ['height', 'width', 'x', 'y'])) {
    return false;
  }

  return ['height', 'width', 'x', 'y'].every(
    (key) => typeof value[key] === 'number' && Number.isFinite(value[key]),
  );
}

function isGameContext(value: unknown): value is GameContext {
  if (!isRecord(value) || !hasOnlyKeys(value, ['gameId', 'phase', 'sourceOrigin'])) {
    return false;
  }

  return (
    (typeof value.gameId === 'string' || value.gameId === null) &&
    (value.phase === 'UNKNOWN' || value.phase === 'LIVE' || value.phase === 'POST_GAME') &&
    typeof value.sourceOrigin === 'string'
  );
}

function isBoardObservation(value: unknown): value is BoardObservation {
  if (!isRecord(value) || !hasOnlyKeys(value, ['boardState', 'moveText', 'observedAt', 'region'])) {
    return false;
  }

  return (
    (typeof value.boardState === 'string' || value.boardState === null) &&
    (typeof value.moveText === 'string' || value.moveText === null) &&
    typeof value.observedAt === 'string' &&
    isBoardRegion(value.region)
  );
}

function isCompletedGamePayload(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, [
      'completed_at',
      'idempotency_key',
      'initial_fen',
      'moves',
      'platform',
      'player_color',
      'result',
      'source_game_id',
    ])
  ) {
    return false;
  }
  return (
    typeof value.completed_at === 'string' &&
    typeof value.idempotency_key === 'string' &&
    value.initial_fen === null &&
    Array.isArray(value.moves) &&
    value.moves.every((move) => typeof move === 'string') &&
    typeof value.platform === 'string' &&
    (value.player_color === 'WHITE' ||
      value.player_color === 'BLACK' ||
      value.player_color === 'UNKNOWN') &&
    (value.result === 'WHITE_WIN' ||
      value.result === 'BLACK_WIN' ||
      value.result === 'DRAW' ||
      value.result === 'UNKNOWN') &&
    typeof value.source_game_id === 'string'
  );
}

function isAllowedCaptureMessage(value: unknown): value is ExtensionMessage {
  if (!isRecord(value) || typeof value.type !== 'string') {
    return false;
  }

  switch (value.type) {
    case 'capture/select-board':
      return hasOnlyKeys(value, ['type']);
    case 'capture/started':
      return (
        hasOnlyKeys(value, ['context', 'region', 'type']) &&
        isGameContext(value.context) &&
        isBoardRegion(value.region)
      );
    case 'capture/board-observed':
      return (
        hasOnlyKeys(value, ['context', 'observation', 'type']) &&
        isGameContext(value.context) &&
        isBoardObservation(value.observation)
      );
    case 'capture/completed-game':
      return hasOnlyKeys(value, ['payload', 'type']) && isCompletedGamePayload(value.payload);
    default:
      return false;
  }
}

function hasForbiddenAnalysisField(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasForbiddenAnalysisField);
  }

  if (!isRecord(value)) {
    return false;
  }

  return Object.entries(value).some(
    ([key, nestedValue]) =>
      FORBIDDEN_ANALYSIS_FIELD_NAMES.has(key.toLowerCase()) ||
      hasForbiddenAnalysisField(nestedValue),
  );
}

export function assertFairPlayMessage(message: unknown): ExtensionMessage {
  if (!isAllowedCaptureMessage(message)) {
    throw new Error('Extension messages must match the board-capture allowlist.');
  }

  if (hasForbiddenAnalysisField(message)) {
    throw new Error('Engine-derived analysis fields are forbidden in extension messages.');
  }

  return message;
}
