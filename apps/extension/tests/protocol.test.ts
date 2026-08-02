import { describe, expect, it } from 'vitest';

import { assertFairPlayMessage } from '../src/protocol';
import {
  canonicalLichessGameUrl,
  classifyLichessPhase,
  fetchCompletedLichessGame,
  lichessSansToUci,
  parseLichessResult,
  readLichessGamePhase,
} from '../src/lichess-adapter';

const captureMessage = {
  context: {
    gameId: 'game-42',
    phase: 'LIVE' as const,
    sourceOrigin: 'https://example.test',
  },
  region: { height: 640, width: 640, x: 20, y: 40 },
  type: 'capture/started' as const,
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
        queue_consent: false,
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
    const unsafeMessage = { ...captureMessage, engineHint: 'e4' };

    expect(() => assertFairPlayMessage(unsafeMessage)).toThrow(/allowlist|forbidden/i);
  });

  it('allows only minimized adapter diagnostics', () => {
    expect(
      assertFairPlayMessage({
        canonicalGameUrl: true,
        hasActiveClock: false,
        moveNodeCount: 99,
        resultDetected: true,
        status: 'MAINLINE_CONVERSION_FAILED',
        type: 'capture/adapter-status',
      }),
    ).toMatchObject({ moveNodeCount: 99, resultDetected: true });
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
    expect(canonicalLichessGameUrl(new URL('https://lichess.org/AbCd1234EfGh'))).toBe(
      'https://lichess.org/AbCd1234',
    );
    expect(canonicalLichessGameUrl(new URL('https://lichess.org/AbCd1234/extra/path'))).toBeNull();
  });

  it('converts only a legal post-game SAN main line to UCI', () => {
    expect(lichessSansToUci(['1. e4', 'e5', '2. Nf3', 'Nc6'])).toEqual([
      'e2e4',
      'e7e5',
      'g1f3',
      'b8c6',
    ]);
    expect(lichessSansToUci(['e4', 'not-a-move'])).toBeNull();
  });

  it('uses a terminal public game export as a minimized post-game fallback', async () => {
    const completed = await fetchCompletedLichessGame(
      new URL('https://lichess.org/AbCd1234/white'),
      () =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'AbCd1234',
              lastMoveAt: Date.parse('2026-08-02T22:00:00Z'),
              moves: 'e4 e5 Nf3 Nc6',
              status: 'resign',
              winner: 'white',
            }),
            { headers: { 'Content-Type': 'application/json' }, status: 200 },
          ),
        ),
    );
    expect(completed).toMatchObject({
      moves: ['e2e4', 'e7e5', 'g1f3', 'b8c6'],
      playerColor: 'WHITE',
      result: 'WHITE_WIN',
      sourceGameId: 'AbCd1234',
    });
  });

  it('rejects a live public game export', async () => {
    const completed = await fetchCompletedLichessGame(new URL('https://lichess.org/AbCd1234'), () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            id: 'AbCd1234',
            lastMoveAt: Date.now(),
            moves: 'e4 e5',
            status: 'started',
          }),
          { headers: { 'Content-Type': 'application/json' }, status: 200 },
        ),
      ),
    );
    expect(completed).toBeNull();
  });

  it('keeps the game live whenever a clock remains active', () => {
    expect(parseLichessResult(['½-½'])).toBe('DRAW');
    expect(classifyLichessPhase('WHITE_WIN', true)).toBe('LIVE');
    expect(classifyLichessPhase(null, false)).toBe('UNKNOWN');
    expect(classifyLichessPhase('BLACK_WIN', false)).toBe('POST_GAME');
  });

  it('recognizes a valid score from Lichess result nodes without relying on page layout', () => {
    const resultElement = {
      dataset: {},
      textContent: '1-0',
    } as HTMLElement;
    const resultDocument = {
      querySelector: () => null,
      querySelectorAll: (selectors: string) => {
        expect(selectors).toContain('.analyse__moves .result');
        expect(selectors.split(',')).toContain('.result');
        return [resultElement];
      },
    } as unknown as Document;

    expect(readLichessGamePhase(resultDocument)).toBe('POST_GAME');
  });
});
