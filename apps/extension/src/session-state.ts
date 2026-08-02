export type SessionPhase =
  | 'UNPAIRED'
  | 'READY'
  | 'LIVE'
  | 'INGESTING'
  | 'CONSENT_REQUIRED'
  | 'WAITING'
  | 'QUEUED'
  | 'RUNNING'
  | 'AVAILABLE'
  | 'FAILED'
  | 'CANCELLED'
  | 'ERROR';

export type MoveQuality =
  'BEST' | 'EXCELLENT' | 'GOOD' | 'INACCURACY' | 'MISTAKE' | 'BLUNDER' | 'UNCLASSIFIED';

export interface ResultMove {
  readonly alternativeSan: string | null;
  readonly afterPositionCentipawns: number | null;
  readonly centipawnLoss: number | null;
  readonly mover: 'WHITE' | 'BLACK';
  readonly ply: number;
  readonly quality: MoveQuality;
  readonly san: string;
}

export interface PlayerResult {
  readonly accuracy: string | null;
  readonly acpl: string | null;
  readonly color: 'WHITE' | 'BLACK';
}

export interface SessionResult {
  readonly black: PlayerResult;
  readonly gameId: string;
  readonly moves: readonly ResultMove[];
  readonly white: PlayerResult;
}

export interface SessionView {
  readonly apiBaseUrl: string;
  readonly gameId?: string | undefined;
  readonly jobId?: string | undefined;
  readonly message: string;
  readonly paired: boolean;
  readonly phase: SessionPhase;
  readonly queueDeadlineAt?: number | undefined;
  readonly queuePosition?: number | undefined;
  readonly result?: SessionResult | undefined;
  readonly sourceGameId?: string | undefined;
  readonly startedAt?: number | undefined;
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('The local API returned an invalid response.');
  }
  return value as Record<string, unknown>;
}

function onlyKeys(value: Record<string, unknown>, keys: readonly string[]): void {
  if (Object.keys(value).some((key) => !keys.includes(key))) {
    throw new Error('The local API returned unexpected fields.');
  }
}

function string(value: unknown): string {
  if (typeof value !== 'string' || value.length === 0) throw new Error('Invalid string field.');
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== 'number' || !Number.isInteger(value))
    throw new Error('Invalid integer field.');
  return value;
}

function nullableInteger(value: unknown): number | null {
  return value === null ? null : integer(value);
}

function nullableDecimal(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !/^-?\d+(?:\.\d+)?$/.test(value)) {
    throw new Error('Invalid decimal field.');
  }
  return value;
}

export interface TokenPair {
  readonly accessToken: string;
  readonly refreshToken: string;
}

export function parseTokenPair(value: unknown): TokenPair {
  const payload = record(value);
  return {
    accessToken: string(payload.access_token),
    refreshToken: string(payload.refresh_token),
  };
}

export function parseExtensionToken(value: unknown): string {
  return string(record(value).access_token);
}

export interface IngestionReceipt {
  readonly gameId: string;
  readonly jobId: string;
  readonly queueDeadlineAt?: number | undefined;
  readonly queuePosition?: number | undefined;
  readonly queueState: 'ACTIVE' | 'WAITING' | 'CONSENT_REQUIRED' | 'TERMINAL';
}

export function parseIngestionReceipt(value: unknown): IngestionReceipt {
  const payload = record(value);
  const queueState = payload.queue_state;
  if (!['ACTIVE', 'WAITING', 'CONSENT_REQUIRED', 'TERMINAL'].includes(String(queueState))) {
    throw new Error('Invalid queue state.');
  }
  return {
    gameId: string(payload.id),
    jobId: string(payload.analysis_job_id),
    queueDeadlineAt:
      payload.queue_deadline_at === null || payload.queue_deadline_at === undefined
        ? undefined
        : integer(payload.queue_deadline_at),
    queuePosition:
      payload.queue_position === null || payload.queue_position === undefined
        ? undefined
        : integer(payload.queue_position),
    queueState: queueState as IngestionReceipt['queueState'],
  };
}

export interface QueueActionReceipt {
  readonly queueDeadlineAt?: number | undefined;
  readonly queuePosition?: number | undefined;
  readonly queueState: 'ACTIVE' | 'WAITING' | 'CANCELLED';
}

export function parseQueueActionReceipt(value: unknown): QueueActionReceipt {
  const payload = record(value);
  if (!['ACTIVE', 'WAITING', 'CANCELLED'].includes(String(payload.queue_state))) {
    throw new Error('Invalid queue action state.');
  }
  return {
    queueDeadlineAt:
      payload.queue_deadline_at === null || payload.queue_deadline_at === undefined
        ? undefined
        : integer(payload.queue_deadline_at),
    queuePosition:
      payload.queue_position === null || payload.queue_position === undefined
        ? undefined
        : integer(payload.queue_position),
    queueState: payload.queue_state as QueueActionReceipt['queueState'],
  };
}

export function parseJobStatus(
  value: unknown,
): 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' {
  const status = record(value).status;
  if (status === 'PENDING' || status === 'QUEUED' || status === 'RETRY_SCHEDULED') return 'PENDING';
  if (status === 'CLAIMED' || status === 'RUNNING') return 'RUNNING';
  if (status === 'SUCCEEDED' || status === 'FAILED' || status === 'CANCELLED') return status;
  throw new Error('Invalid analysis job status.');
}

const QUALITIES: readonly MoveQuality[] = [
  'BEST',
  'EXCELLENT',
  'GOOD',
  'INACCURACY',
  'MISTAKE',
  'BLUNDER',
  'UNCLASSIFIED',
];

function parsePlayer(value: unknown, expected: PlayerResult['color']): PlayerResult {
  const player = record(value);
  onlyKeys(player, [
    'color',
    'total_move_count',
    'cpl_eligible_move_count',
    'excluded_move_count',
    'cpl_coverage',
    'acpl',
    'accuracy',
    'classified_move_count',
    'unclassified_move_count',
    'classification_coverage',
    'quality_counts',
  ]);
  if (player.color !== expected) throw new Error('Invalid result player.');
  return {
    accuracy: nullableDecimal(player.accuracy),
    acpl: nullableDecimal(player.acpl),
    color: expected,
  };
}

export function parseSessionResult(value: unknown): SessionResult {
  const payload = record(value);
  onlyKeys(payload, ['black', 'game_id', 'moves', 'white']);
  if (!Array.isArray(payload.moves)) throw new Error('Invalid result moves.');
  const moves = payload.moves.map((item): ResultMove => {
    const move = record(item);
    onlyKeys(move, [
      'alternative_san',
      'after_position_centipawns',
      'centipawn_loss',
      'move_san',
      'move_uci',
      'mover',
      'ply',
      'quality',
    ]);
    if (
      (move.mover !== 'WHITE' && move.mover !== 'BLACK') ||
      !QUALITIES.includes(move.quality as MoveQuality)
    ) {
      throw new Error('Invalid result move.');
    }
    return {
      alternativeSan: move.alternative_san === null ? null : string(move.alternative_san),
      afterPositionCentipawns: nullableInteger(move.after_position_centipawns),
      centipawnLoss: nullableInteger(move.centipawn_loss),
      mover: move.mover,
      ply: integer(move.ply),
      quality: move.quality as MoveQuality,
      san: string(move.move_san),
    };
  });
  return {
    black: parsePlayer(payload.black, 'BLACK'),
    gameId: string(payload.game_id),
    moves,
    white: parsePlayer(payload.white, 'WHITE'),
  };
}

function parseStoredPlayer(value: unknown, expected: PlayerResult['color']): PlayerResult {
  const player = record(value);
  onlyKeys(player, ['accuracy', 'acpl', 'color']);
  if (player.color !== expected) throw new Error('Invalid stored result player.');
  return {
    accuracy: nullableDecimal(player.accuracy),
    acpl: nullableDecimal(player.acpl),
    color: expected,
  };
}

export function parseStoredSessionResult(value: unknown): SessionResult {
  const payload = record(value);
  onlyKeys(payload, ['black', 'gameId', 'moves', 'white']);
  if (!Array.isArray(payload.moves)) throw new Error('Invalid stored result moves.');
  const moves = payload.moves.map((item): ResultMove => {
    const move = record(item);
    onlyKeys(move, [
      'alternativeSan',
      'afterPositionCentipawns',
      'centipawnLoss',
      'mover',
      'ply',
      'quality',
      'san',
    ]);
    if (
      (move.mover !== 'WHITE' && move.mover !== 'BLACK') ||
      !QUALITIES.includes(move.quality as MoveQuality)
    ) {
      throw new Error('Invalid stored result move.');
    }
    return {
      alternativeSan: move.alternativeSan === null ? null : string(move.alternativeSan),
      afterPositionCentipawns: nullableInteger(move.afterPositionCentipawns),
      centipawnLoss: nullableInteger(move.centipawnLoss),
      mover: move.mover,
      ply: integer(move.ply),
      quality: move.quality as MoveQuality,
      san: string(move.san),
    };
  });
  return {
    black: parseStoredPlayer(payload.black, 'BLACK'),
    gameId: string(payload.gameId),
    moves,
    white: parseStoredPlayer(payload.white, 'WHITE'),
  };
}

export function safeErrorMessage(status: number): string {
  if (status === 401) return 'The local session expired. Pair the extension again.';
  if (status === 404) return 'The requested local analysis was not found.';
  if (status === 429) return 'The local API rate limit was reached. Wait before retrying.';
  if (status === 503) return 'The local analysis service is temporarily unavailable.';
  return 'The local BoardTrace request failed.';
}

export function enterLiveSession(current: SessionView): SessionView {
  return {
    apiBaseUrl: current.apiBaseUrl,
    message: 'Live game observed. Analysis is locked until completion.',
    paired: current.paired,
    phase: 'LIVE',
  };
}

export function enterCaptureSession(
  current: SessionView,
  phase: 'LIVE' | 'POST_GAME' | 'UNKNOWN',
  sourceGameId: string | null,
): SessionView {
  const sameTrackedCompletedGame =
    phase === 'POST_GAME' &&
    sourceGameId === current.sourceGameId &&
    current.gameId !== undefined &&
    current.jobId !== undefined;
  if (sameTrackedCompletedGame) return current;
  if (phase !== 'POST_GAME') return enterLiveSession(current);
  return {
    apiBaseUrl: current.apiBaseUrl,
    message: 'Lichess board connected.',
    paired: current.paired,
    phase: 'READY',
  };
}

export function prepareNextGame(current: SessionView): SessionView {
  if (!current.paired) {
    throw new Error('Pair the extension before starting another game.');
  }
  return {
    apiBaseUrl: current.apiBaseUrl,
    message: 'Ready for another Lichess game.',
    paired: true,
    phase: 'READY',
  };
}
