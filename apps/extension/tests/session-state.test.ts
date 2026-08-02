import { describe, expect, it } from 'vitest';

import { createExtensionManifest } from '../build/manifest';
import {
  enterCaptureSession,
  enterLiveSession,
  parseIngestionReceipt,
  parseJobStatus,
  parseQueueActionReceipt,
  parseSessionResult,
  parseStoredSessionResult,
  prepareNextGame,
  type SessionView,
} from '../src/session-state';

describe('extension session safety', () => {
  it('removes every prior result identifier when a live game is observed', () => {
    const prior: SessionView = {
      apiBaseUrl: 'http://127.0.0.1:18080',
      gameId: 'game-id',
      jobId: 'job-id',
      message: 'available',
      paired: true,
      phase: 'AVAILABLE',
      result: {
        black: { accuracy: null, acpl: null, color: 'BLACK' },
        gameId: 'game-id',
        moves: [],
        white: { accuracy: null, acpl: null, color: 'WHITE' },
      },
      sourceGameId: 'lichess-game-id',
    };
    expect(enterLiveSession(prior)).toEqual({
      apiBaseUrl: 'http://127.0.0.1:18080',
      message: 'Live game observed. Analysis is locked until completion.',
      paired: true,
      phase: 'LIVE',
    });
  });

  it('preserves only the same tracked completed game on reconnect', () => {
    const tracked: SessionView = {
      apiBaseUrl: 'http://127.0.0.1:18080',
      gameId: 'game-id',
      jobId: 'job-id',
      message: 'Analysis is queued.',
      paired: true,
      phase: 'QUEUED',
      sourceGameId: 'lichess-id',
    };
    expect(enterCaptureSession(tracked, 'POST_GAME', 'lichess-id')).toBe(tracked);
    expect(enterCaptureSession(tracked, 'POST_GAME', 'different-id')).toEqual({
      apiBaseUrl: tracked.apiBaseUrl,
      message: 'Lichess board connected.',
      paired: true,
      phase: 'READY',
    });
    expect(enterCaptureSession(tracked, 'UNKNOWN', 'lichess-id').phase).toBe('LIVE');
  });

  it('prepares another game without clearing the local pairing', () => {
    const available: SessionView = {
      apiBaseUrl: 'http://127.0.0.1:18080',
      gameId: 'game-id',
      jobId: 'job-id',
      message: 'Post-game analysis is available.',
      paired: true,
      phase: 'AVAILABLE',
      result: {
        black: { accuracy: null, acpl: null, color: 'BLACK' },
        gameId: 'game-id',
        moves: [],
        white: { accuracy: null, acpl: null, color: 'WHITE' },
      },
      sourceGameId: 'lichess-id',
    };

    expect(prepareNextGame(available)).toEqual({
      apiBaseUrl: available.apiBaseUrl,
      message: 'Ready for another Lichess game.',
      paired: true,
      phase: 'READY',
    });
    expect(() => prepareNextGame({ ...available, paired: false })).toThrow(/pair/i);
  });

  it('strictly parses ingestion and queue actions', () => {
    expect(
      parseIngestionReceipt({
        analysis_job_id: 'job-id',
        id: 'game-id',
        queue_deadline_at: 42,
        queue_position: 2,
        queue_state: 'WAITING',
      }),
    ).toMatchObject({ gameId: 'game-id', jobId: 'job-id', queueState: 'WAITING' });
    expect(parseQueueActionReceipt({ queue_state: 'CANCELLED' })).toMatchObject({
      queueState: 'CANCELLED',
    });
    expect(() => parseQueueActionReceipt({ queue_state: 'SUCCEEDED' })).toThrow();
  });

  it('normalizes every backend job lifecycle status for the popup', () => {
    expect(parseJobStatus({ status: 'QUEUED' })).toBe('PENDING');
    expect(parseJobStatus({ status: 'CLAIMED' })).toBe('RUNNING');
    expect(parseJobStatus({ status: 'RETRY_SCHEDULED' })).toBe('PENDING');
    expect(parseJobStatus({ status: 'SUCCEEDED' })).toBe('SUCCEEDED');
    expect(() => parseJobStatus({ status: 'UNKNOWN' })).toThrow(/invalid/i);
  });

  it('accepts only the released, minimized result shape', () => {
    const result = parseSessionResult({
      black: { accuracy: null, acpl: '12.50', color: 'BLACK' },
      game_id: 'game-id',
      moves: [
        {
          alternative_san: 'd4',
          after_position_centipawns: 0,
          centipawn_loss: 4,
          move_san: 'e4',
          move_uci: 'e2e4',
          mover: 'WHITE',
          ply: 1,
          quality: 'GOOD',
        },
      ],
      white: { accuracy: '98.10', acpl: null, color: 'WHITE' },
    });
    expect(result.moves[0]?.afterPositionCentipawns).toBe(0);
    expect(result.moves[0]?.alternativeSan).toBe('d4');
    expect(parseStoredSessionResult(result)).toEqual(result);
    expect(() =>
      parseStoredSessionResult({
        ...result,
        moves: [{ ...result.moves[0], bestMove: 'd4' }],
      }),
    ).toThrow(/unexpected fields/i);
    expect(() => parseSessionResult({ ...result, moves: 'unsafe' })).toThrow();
    expect(() =>
      parseSessionResult({
        black: { accuracy: null, acpl: null, bestMove: 'e5', color: 'BLACK' },
        game_id: 'game-id',
        moves: [],
        white: { accuracy: null, acpl: null, color: 'WHITE' },
      }),
    ).toThrow(/unexpected fields/i);
  });
});

describe('generated manifest', () => {
  it('grants access only to the configured local API origin', () => {
    const manifest = createExtensionManifest('http://127.0.0.1:18080/base');
    expect(manifest.host_permissions).toEqual(['http://127.0.0.1:18080/*']);
    expect(manifest.action.default_popup).toBe('popup.html');
    expect(manifest.permissions).toEqual(['activeTab', 'scripting', 'storage']);
  });
});
