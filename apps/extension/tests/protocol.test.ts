import { describe, expect, it } from 'vitest';

import { assertFairPlayMessage } from '../src/protocol';
import { canonicalLichessGameUrl } from '../src/lichess-adapter';

const captureMessage = {
  context: {
    gameId: 'game-42',
    phase: 'LIVE' as const,
    sourceOrigin: 'https://example.test',
  },
  observation: {
    boardState: 'raw-board-observation',
    moveText: 'e2-e4',
    observedAt: '2026-07-13T10:00:00.000Z',
    region: { height: 640, width: 640, x: 20, y: 40 },
  },
  type: 'capture/board-observed' as const,
};

describe('extension fair-play protocol', () => {
  it('allows board-scoped capture observations during live play', () => {
    expect(assertFairPlayMessage(captureMessage)).toEqual(captureMessage);
  });

  it('accepts only browser-extension provenance fields for completed games', () => {
    const completed = {
      payload: {
        acquisition_method: 'browser_extension',
        completed_at: '2026-07-31T10:00:00.000Z',
        idempotency_key: 'a'.repeat(64),
        initial_fen: null,
        manual_retry: false,
        moves: ['e2e4'],
        platform: 'lichess',
        player_color: 'WHITE',
        result: 'WHITE_WIN',
        source_checksum: 'b'.repeat(64),
        source_game_id: 'AbCd1234',
      },
      type: 'capture/completed-game',
    } as const;
    expect(assertFairPlayMessage(completed)).toEqual(completed);
    expect(() =>
      assertFairPlayMessage({
        ...completed,
        payload: { ...completed.payload, acquisition_method: 'manual_pgn' },
      }),
    ).toThrow(/allowlist/i);
  });

  it('rejects engine fields at every nested runtime-message level', () => {
    const unsafeMessage = {
      ...captureMessage,
      observation: { ...captureMessage.observation, engineHint: 'e4' },
    };

    expect(() => assertFairPlayMessage(unsafeMessage)).toThrow(/allowlist|forbidden/i);
  });
});

describe('Lichess completed-game identity', () => {
  it('normalizes a game URL without accepting lookalike origins', () => {
    expect(canonicalLichessGameUrl(new URL('https://lichess.org/AbCd1234/black?x=1#moves'))).toBe(
      'https://lichess.org/AbCd1234',
    );
    expect(canonicalLichessGameUrl(new URL('https://lichess.org.evil.test/AbCd1234'))).toBeNull();
    expect(canonicalLichessGameUrl(new URL('http://lichess.org/AbCd1234'))).toBeNull();
    expect(canonicalLichessGameUrl(new URL('https://lichess.org/AbCd1234/white'))).toBe(
      'https://lichess.org/AbCd1234',
    );
    expect(canonicalLichessGameUrl(new URL('https://lichess.org/AbCd1234/extra/path'))).toBeNull();
  });
});
