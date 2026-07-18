import { assertFairPlayMessage } from './protocol';

interface PairingExchangeMessage {
  readonly apiBaseUrl: string;
  readonly code: string;
  readonly extensionId: string;
  readonly type: 'pairing/exchange';
}

let extensionAccessToken: string | undefined;
let apiBaseUrl: string | undefined;

function isPairingExchange(value: unknown): value is PairingExchangeMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    Object.keys(value).every((key) =>
      ['type', 'apiBaseUrl', 'code', 'extensionId'].includes(key),
    ) &&
    'type' in value &&
    value.type === 'pairing/exchange' &&
    'apiBaseUrl' in value &&
    typeof value.apiBaseUrl === 'string' &&
    'code' in value &&
    typeof value.code === 'string' &&
    'extensionId' in value &&
    typeof value.extensionId === 'string'
  );
}

async function exchangePairing(message: PairingExchangeMessage): Promise<void> {
  extensionAccessToken = undefined;
  apiBaseUrl = undefined;
  const response = await fetch(`${message.apiBaseUrl}/api/v1/extension-pairings/exchange`, {
    body: JSON.stringify({ code: message.code, extension_id: message.extensionId }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
  if (!response.ok) throw new Error('Pairing exchange failed.');
  const payload: unknown = await response.json();
  if (
    typeof payload !== 'object' ||
    payload === null ||
    !('access_token' in payload) ||
    typeof payload.access_token !== 'string'
  ) {
    throw new Error('Pairing exchange returned an invalid token response.');
  }
  apiBaseUrl = message.apiBaseUrl;
  extensionAccessToken = payload.access_token;
}

async function injectCaptureScript(tabId: number): Promise<void> {
  try {
    await chrome.tabs.sendMessage(tabId, { type: 'capture/select-board' });
    return;
  } catch {
    // The content script is not present on this document yet.
  }

  await chrome.scripting.executeScript({
    files: ['content-script.js'],
    target: { tabId },
  });
  await chrome.tabs.sendMessage(tabId, { type: 'capture/select-board' });
}

chrome.action.onClicked.addListener((tab) => {
  if (tab.id === undefined) {
    return;
  }

  void injectCaptureScript(tab.id).catch((error: unknown) => {
    console.warn('BoardTrace could not start board selection.', error);
  });
});

chrome.runtime.onMessage.addListener((message: unknown) => {
  if (isPairingExchange(message)) {
    void exchangePairing(message).catch(() => undefined);
    return;
  }
  const safeMessage = assertFairPlayMessage(message);
  if (
    safeMessage.type !== 'capture/completed-game' ||
    extensionAccessToken === undefined ||
    apiBaseUrl === undefined
  )
    return;
  void fetch(`${apiBaseUrl}/api/v1/games/ingestions`, {
    body: JSON.stringify(safeMessage.payload),
    headers: {
      Authorization: `Bearer ${extensionAccessToken}`,
      'Content-Type': 'application/json',
    },
    method: 'POST',
  })
    .then((response) => {
      if (response.status === 401) extensionAccessToken = undefined;
    })
    .catch(() => undefined);
});
