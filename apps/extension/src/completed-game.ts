export interface CompletedGamePayload {
  readonly acquisition_method: 'browser_extension';
  readonly completed_at: string;
  readonly idempotency_key: string;
  readonly initial_fen: null;
  readonly moves: readonly string[];
  readonly manual_retry: false;
  readonly platform: 'lichess';
  readonly player_color: 'WHITE' | 'BLACK' | 'UNKNOWN';
  readonly queue_consent: false;
  readonly result: 'WHITE_WIN' | 'BLACK_WIN' | 'DRAW';
  readonly source_game_id: string;
  readonly source_checksum: string;
}

export interface CompletedLichessGame {
  readonly completedAt: string;
  readonly moves: readonly string[];
  readonly playerColor: CompletedGamePayload['player_color'];
  readonly result: CompletedGamePayload['result'];
  readonly sourceGameId: string;
}

async function fingerprint(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function normalizeCompletedLichessGame(
  game: CompletedLichessGame,
): Promise<CompletedGamePayload> {
  const moves = game.moves.map((move) => move.trim().toLowerCase());
  const completedAt = new Date(game.completedAt).toISOString();
  return {
    acquisition_method: 'browser_extension',
    completed_at: completedAt,
    idempotency_key: await fingerprint(
      JSON.stringify(['https://lichess.org', game.sourceGameId, completedAt, moves]),
    ),
    initial_fen: null,
    manual_retry: false,
    moves,
    platform: 'lichess',
    player_color: game.playerColor,
    queue_consent: false,
    result: game.result,
    source_checksum: await fingerprint(JSON.stringify(['lichess', game.sourceGameId, moves])),
    source_game_id: game.sourceGameId,
  };
}
