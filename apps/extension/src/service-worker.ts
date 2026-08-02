import { assertFairPlayMessage } from './protocol';
import {
  enterCaptureSession,
  parseExtensionToken,
  parseIngestionReceipt,
  parseJobStatus,
  prepareNextGame,
  parseQueueActionReceipt,
  parseSessionResult,
  parseStoredSessionResult,
  parseTokenPair,
  safeErrorMessage,
  type SessionView,
} from './session-state';

interface UiMessage {
  readonly email?: string;
  readonly password?: string;
  readonly type: string;
}

const apiBaseUrl = __BOARDTRACE_EXTENSION_API_BASE_URL__;
const storedSessionKey = 'boardtrace-session-v1';
let userAccessToken: string | undefined;
let extensionAccessToken: string | undefined;
let state: SessionView = {
  apiBaseUrl,
  message: 'Pair with the local BoardTrace API to begin.',
  paired: false,
  phase: 'UNPAIRED',
};

interface StoredSession {
  readonly extensionAccessToken: string;
  readonly state: SessionView;
  readonly userAccessToken: string;
}

const phases: readonly SessionView['phase'][] = [
  'UNPAIRED',
  'READY',
  'LIVE',
  'INGESTING',
  'CONSENT_REQUIRED',
  'WAITING',
  'QUEUED',
  'RUNNING',
  'AVAILABLE',
  'FAILED',
  'CANCELLED',
  'ERROR',
];

function restoreStoredSession(value: unknown): StoredSession | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const stored = value as Record<string, unknown>;
  const storedState = stored.state;
  if (
    typeof stored.extensionAccessToken !== 'string' ||
    typeof stored.userAccessToken !== 'string' ||
    typeof storedState !== 'object' ||
    storedState === null ||
    Array.isArray(storedState)
  ) {
    return null;
  }
  const view = storedState as Record<string, unknown>;
  if (
    view.apiBaseUrl !== apiBaseUrl ||
    typeof view.message !== 'string' ||
    view.paired !== true ||
    !phases.includes(view.phase as SessionView['phase']) ||
    (view.gameId !== undefined && typeof view.gameId !== 'string') ||
    (view.jobId !== undefined && typeof view.jobId !== 'string') ||
    (view.queueDeadlineAt !== undefined && typeof view.queueDeadlineAt !== 'number') ||
    (view.queuePosition !== undefined && typeof view.queuePosition !== 'number') ||
    (view.sourceGameId !== undefined && typeof view.sourceGameId !== 'string') ||
    (view.startedAt !== undefined && typeof view.startedAt !== 'number')
  ) {
    return null;
  }
  let result: SessionView['result'];
  try {
    result = view.result === undefined ? undefined : parseStoredSessionResult(view.result);
  } catch {
    return null;
  }
  if ((view.phase === 'AVAILABLE') !== (result !== undefined)) return null;
  const restoredState = { ...view, result } as unknown as SessionView;
  return {
    extensionAccessToken: stored.extensionAccessToken,
    state: restoredState,
    userAccessToken: stored.userAccessToken,
  };
}

function storedState(): SessionView {
  return state;
}

async function persist(): Promise<void> {
  if (userAccessToken === undefined || extensionAccessToken === undefined || !state.paired) {
    await chrome.storage.session.remove(storedSessionKey);
    return;
  }
  await chrome.storage.session.set({
    [storedSessionKey]: {
      extensionAccessToken,
      state: storedState(),
      userAccessToken,
    } satisfies StoredSession,
  });
}

async function restore(): Promise<void> {
  const values = await chrome.storage.session.get(storedSessionKey);
  const stored = restoreStoredSession(values[storedSessionKey]);
  if (stored === null) {
    await chrome.storage.session.remove(storedSessionKey);
    return;
  }
  extensionAccessToken = stored.extensionAccessToken;
  userAccessToken = stored.userAccessToken;
  state = stored.state;
}

const initialization = restore();

function update(patch: Partial<SessionView>): SessionView {
  state = { ...state, ...patch };
  return state;
}

async function commit(patch: Partial<SessionView>): Promise<SessionView> {
  update(patch);
  await persist();
  return state;
}

async function request(path: string, init: RequestInit, token?: string): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (token !== undefined) headers.set('Authorization', `Bearer ${token}`);
  return fetch(`${apiBaseUrl}${path}`, { ...init, cache: 'no-store', headers });
}

async function json(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(safeErrorMessage(response.status));
  return response.json() as Promise<unknown>;
}

async function loginAndPair(email: string, password: string): Promise<SessionView> {
  await disconnect(false);
  try {
    const login = await request('/api/v1/auth/login', {
      body: JSON.stringify({ email, password }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    const userTokens = parseTokenPair(await json(login));
    const pairing = await request(
      '/api/v1/extension-pairings',
      {
        body: JSON.stringify({
          extension_id: chrome.runtime.id,
          scopes: ['games:ingest', 'games:read-status'],
        }),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      },
      userTokens.accessToken,
    );
    const pairingPayload = (await json(pairing)) as { readonly code?: unknown };
    if (typeof pairingPayload.code !== 'string')
      throw new Error('Pairing returned an invalid code.');
    const exchange = await request('/api/v1/extension-pairings/exchange', {
      body: JSON.stringify({ code: pairingPayload.code, extension_id: chrome.runtime.id }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    extensionAccessToken = parseExtensionToken(await json(exchange));
    const logout = await request(
      '/api/v1/auth/logout',
      {
        body: JSON.stringify({ refresh_token: userTokens.refreshToken }),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      },
      userTokens.accessToken,
    );
    await json(logout);
    userAccessToken = userTokens.accessToken;
    return commit({
      message: 'Paired locally. Open a Lichess game and connect BoardTrace.',
      paired: true,
      phase: 'READY',
    });
  } catch (error: unknown) {
    await disconnect(false);
    throw error;
  }
}

async function disconnect(clearMessage = true): Promise<SessionView> {
  userAccessToken = undefined;
  extensionAccessToken = undefined;
  state = {
    apiBaseUrl,
    message: clearMessage ? 'Local session cleared.' : 'Pairing in progress.',
    paired: false,
    phase: 'UNPAIRED',
  };
  await persist();
  return state;
}

async function analyzeAnotherGame(): Promise<SessionView> {
  state = prepareNextGame(state);
  await persist();
  return state;
}

async function connectCurrentTab(): Promise<SessionView> {
  if (extensionAccessToken === undefined) throw new Error('Pair the extension first.');
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) throw new Error('An active browser tab is required.');
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'capture/connect-lichess' });
  } catch {
    await chrome.scripting.executeScript({
      files: ['content-script.js'],
      target: { tabId: tab.id },
    });
    await chrome.tabs.sendMessage(tab.id, { type: 'capture/connect-lichess' });
  }
  return state;
}

async function refresh(): Promise<SessionView> {
  if (
    state.jobId === undefined ||
    state.gameId === undefined ||
    extensionAccessToken === undefined
  ) {
    return state;
  }
  if (state.phase === 'WAITING' || state.phase === 'CONSENT_REQUIRED') {
    const queueResponse = await request(
      `/api/v1/games/${encodeURIComponent(state.gameId)}/ingestion-status`,
      { method: 'GET' },
      extensionAccessToken,
    );
    const queue = parseIngestionReceipt(await json(queueResponse));
    if (queue.queueState !== 'ACTIVE' && queue.queueState !== 'TERMINAL') {
      return commit({
        queueDeadlineAt: queue.queueDeadlineAt,
        queuePosition: queue.queuePosition,
      });
    }
  }
  const response = await request(
    `/api/v1/analysis/jobs/${encodeURIComponent(state.jobId)}`,
    { method: 'GET' },
    extensionAccessToken,
  );
  const status = parseJobStatus(await json(response));
  if (status === 'PENDING') return commit({ message: 'Analysis is queued.', phase: 'QUEUED' });
  if (status === 'RUNNING')
    return commit({ message: 'Post-game analysis is running.', phase: 'RUNNING' });
  if (status === 'FAILED')
    return commit({ message: 'Post-game analysis failed.', phase: 'FAILED' });
  if (status === 'CANCELLED')
    return commit({ message: 'Queued analysis was cancelled.', phase: 'CANCELLED' });
  if (userAccessToken === undefined) throw new Error('Pair again to read the released result.');
  const resultResponse = await request(
    `/api/v1/analysis/games/${encodeURIComponent(state.gameId)}`,
    { method: 'GET' },
    userAccessToken,
  );
  const result = parseSessionResult(await json(resultResponse));
  return commit({ message: 'Post-game analysis is available.', phase: 'AVAILABLE', result });
}

async function queueAction(action: 'queue-consent' | 'queue-cancel' | 'queue-extend') {
  if (state.jobId === undefined || userAccessToken === undefined)
    throw new Error('Pairing is required.');
  const response = await request(
    `/api/v1/games/analysis-jobs/${encodeURIComponent(state.jobId)}/${action}`,
    { headers: { 'Content-Type': 'application/json' }, method: 'POST', body: '{}' },
    userAccessToken,
  );
  const receipt = parseQueueActionReceipt(await json(response));
  return commit({
    message:
      action === 'queue-cancel'
        ? 'Queued analysis was cancelled.'
        : action === 'queue-extend'
          ? 'Queue wait was extended.'
          : 'Queue consent recorded.',
    phase:
      action === 'queue-cancel'
        ? 'CANCELLED'
        : receipt.queueState === 'WAITING'
          ? 'WAITING'
          : 'QUEUED',
    queueDeadlineAt: receipt.queueDeadlineAt,
    queuePosition: receipt.queuePosition,
  });
}

async function handleUi(message: UiMessage): Promise<SessionView> {
  await initialization;
  switch (message.type) {
    case 'ui/state':
      return state;
    case 'ui/login-and-pair':
      if (typeof message.email !== 'string' || typeof message.password !== 'string') {
        throw new Error('Email and password are required.');
      }
      return loginAndPair(message.email, message.password);
    case 'ui/disconnect':
      return disconnect();
    case 'ui/analyze-another-game':
      return analyzeAnotherGame();
    case 'ui/connect-current-tab':
      return connectCurrentTab();
    case 'ui/refresh':
      return refresh();
    case 'ui/queue-consent':
      return queueAction('queue-consent');
    case 'ui/queue-cancel':
      return queueAction('queue-cancel');
    case 'ui/queue-extend':
      return queueAction('queue-extend');
    default:
      throw new Error('Unsupported extension action.');
  }
}

async function ingestCompletedGame(message: unknown): Promise<void> {
  await initialization;
  const safeMessage = assertFairPlayMessage(message);
  if (safeMessage.type !== 'capture/completed-game') return;
  if (extensionAccessToken === undefined) {
    await commit({
      message: 'The game finished, but local pairing expired.',
      paired: false,
      phase: 'ERROR',
    });
    return;
  }
  if (
    state.sourceGameId === safeMessage.payload.source_game_id &&
    state.gameId !== undefined &&
    state.jobId !== undefined
  ) {
    return;
  }
  await commit({
    message: 'Submitting the completed game.',
    phase: 'INGESTING',
    startedAt: Date.now(),
  });
  try {
    const response = await request(
      '/api/v1/games/ingestions',
      {
        body: JSON.stringify(safeMessage.payload),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      },
      extensionAccessToken,
    );
    const receipt = parseIngestionReceipt(await json(response));
    await commit({
      gameId: receipt.gameId,
      jobId: receipt.jobId,
      sourceGameId: safeMessage.payload.source_game_id,
      message:
        receipt.queueState === 'CONSENT_REQUIRED'
          ? 'Analysis capacity is busy. Consent is required to wait.'
          : receipt.queueState === 'WAITING'
            ? 'Waiting for local analysis capacity.'
            : 'Completed game accepted for post-game analysis.',
      phase:
        receipt.queueState === 'CONSENT_REQUIRED'
          ? 'CONSENT_REQUIRED'
          : receipt.queueState === 'WAITING'
            ? 'WAITING'
            : 'QUEUED',
      queueDeadlineAt: receipt.queueDeadlineAt,
      queuePosition: receipt.queuePosition,
    });
  } catch (error: unknown) {
    await commit({
      message: error instanceof Error ? error.message : 'Completed-game ingestion failed.',
      phase: 'ERROR',
    });
  }
}

chrome.runtime.onMessage.addListener((message: unknown, _sender, sendResponse) => {
  if (typeof message === 'object' && message !== null && 'type' in message) {
    if (typeof message.type === 'string' && message.type.startsWith('ui/')) {
      void handleUi(message as UiMessage)
        .then((session) => sendResponse({ ok: true, session }))
        .catch((error: unknown) =>
          sendResponse({
            ok: false,
            message: error instanceof Error ? error.message : 'Request failed.',
          }),
        );
      return true;
    }
    if (message.type === 'capture/started') {
      const safe = assertFairPlayMessage(message);
      if (safe.type === 'capture/started') {
        void initialization
          .then(async () => {
            state = enterCaptureSession(state, safe.context.phase, safe.context.gameId);
            await persist();
            sendResponse({ ok: true });
          })
          .catch((error: unknown) => {
            console.error('BoardTrace session persistence failed.', error);
            sendResponse({
              message: 'BoardTrace could not enter a safe capture state.',
              ok: false,
            });
          });
      }
      return true;
    }
    if (message.type === 'capture/adapter-status') {
      const safe = assertFairPlayMessage(message);
      if (safe.type === 'capture/adapter-status') {
        const detail = `result=${safe.resultDetected ? 'yes' : 'no'}, moves=${safe.moveNodeCount}, active-clock=${safe.hasActiveClock ? 'yes' : 'no'}, canonical-url=${safe.canonicalGameUrl ? 'yes' : 'no'}`;
        void initialization
          .then(() =>
            commit({
              message:
                safe.status === 'TERMINAL_SCORE_NOT_FOUND'
                  ? `Terminal score was not detected (${detail}).`
                  : `The terminal score was detected, but the main line could not be converted (${detail}).`,
              phase: 'READY',
            }),
          )
          .catch((error: unknown) => console.error('BoardTrace adapter status failed.', error));
      }
      return false;
    }
    if (message.type === 'capture/completed-game') {
      void ingestCompletedGame(message)
        .then(() => sendResponse({ ok: true }))
        .catch((error: unknown) =>
          sendResponse({
            message: error instanceof Error ? error.message : 'Completed-game ingestion failed.',
            ok: false,
          }),
        );
      return true;
    }
  }
  return false;
});
