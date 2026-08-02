import type { SessionResult, SessionView } from './session-state';

interface UiResponse {
  readonly message?: string;
  readonly ok: boolean;
  readonly session?: SessionView;
}

const root = document.getElementById('root');
if (root === null) throw new Error('Popup root is unavailable.');
const popupRoot = root;

let session: SessionView | undefined;
let busy = false;
let refreshTimer: number | undefined;

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className !== undefined) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function send(message: object): Promise<SessionView> {
  const response = (await chrome.runtime.sendMessage(message)) as UiResponse;
  if (!response.ok || response.session === undefined) {
    throw new Error(response.message ?? 'The extension request failed.');
  }
  return response.session;
}

function formatMetric(value: string | null): string {
  return value === null ? '—' : value;
}

function qualityLabel(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}

function moveLabel(ply: number, san: string): string {
  const moveNumber = Math.ceil(ply / 2);
  return ply % 2 === 1 ? `${moveNumber}. ${san}` : `${moveNumber}… ${san}`;
}

function resultPanel(result: SessionResult): HTMLElement {
  const panel = element('section', 'panel result-panel');
  const title = element('div', 'section-heading');
  title.append(
    element('div', 'section-icon', '↗'),
    element('div', undefined, 'Decision review'),
    element('span', 'section-kicker', `${result.moves.length} half-moves`),
  );
  panel.append(title);
  const metrics = element('div', 'metrics');
  for (const player of [result.white, result.black]) {
    const card = element('div', 'metric-card');
    card.append(
      element('span', 'metric-label', player.color === 'WHITE' ? 'White' : 'Black'),
      element('strong', 'metric-value', formatMetric(player.accuracy)),
      element('span', 'metric-caption', `Accuracy · ACPL ${formatMetric(player.acpl)}`),
    );
    metrics.append(card);
  }
  panel.append(metrics);

  if (result.moves.length === 0) {
    panel.append(element('p', 'empty-state', 'No reviewed moves are available.'));
    return panel;
  }

  let selectedIndex = 0;
  const review = element('div', 'review-card');
  review.setAttribute('aria-live', 'polite');
  const timeline = element('div', 'move-timeline');

  const renderDecision = (): void => {
    const move = result.moves[selectedIndex];
    if (move === undefined) return;
    const top = element('div', 'review-topline');
    top.append(
      element('span', 'review-count', `Decision ${selectedIndex + 1} / ${result.moves.length}`),
      element(
        'span',
        `quality-pill quality-${move.quality.toLowerCase()}`,
        qualityLabel(move.quality),
      ),
    );
    const played = element('div', 'played-move');
    played.append(
      element('span', 'played-label', 'Played'),
      element('strong', undefined, moveLabel(move.ply, move.san)),
    );
    const insight = element(
      'div',
      move.alternativeSan === null ? 'insight insight-match' : 'insight insight-alternative',
    );
    insight.append(
      element('span', 'insight-icon', move.alternativeSan === null ? '✓' : '↗'),
      element(
        'div',
        undefined,
        move.alternativeSan === null ? 'Engine choice matched' : 'Best alternative',
      ),
      element('strong', undefined, move.alternativeSan === null ? move.san : move.alternativeSan),
    );
    const detail = element('div', 'review-detail');
    detail.append(
      element(
        'span',
        undefined,
        move.centipawnLoss === null ? 'CPL —' : `CPL ${move.centipawnLoss}`,
      ),
      element(
        'span',
        undefined,
        move.afterPositionCentipawns === null
          ? 'Evaluation —'
          : `After ${move.afterPositionCentipawns > 0 ? '+' : ''}${(
              move.afterPositionCentipawns / 100
            ).toFixed(2)}`,
      ),
    );
    const controls = element('div', 'review-controls');
    const previous = element('button', 'icon-button', '←');
    previous.type = 'button';
    previous.setAttribute('aria-label', 'Previous decision');
    previous.disabled = selectedIndex === 0;
    previous.addEventListener('click', () => {
      selectedIndex -= 1;
      renderDecision();
    });
    const next = element('button', 'next-button', 'Next decision →');
    next.type = 'button';
    next.disabled = selectedIndex === result.moves.length - 1;
    next.addEventListener('click', () => {
      selectedIndex += 1;
      renderDecision();
    });
    controls.append(previous, next);
    review.replaceChildren(top, played, insight, detail, controls);
    for (const [index, button] of Array.from(timeline.children).entries()) {
      button.classList.toggle('is-selected', index === selectedIndex);
    }
  };

  for (const [index, move] of result.moves.entries()) {
    const button = element('button', `timeline-move quality-dot-${move.quality.toLowerCase()}`);
    button.type = 'button';
    button.textContent = moveLabel(move.ply, move.san);
    button.setAttribute('aria-label', `Review ${moveLabel(move.ply, move.san)}`);
    button.addEventListener('click', () => {
      selectedIndex = index;
      renderDecision();
    });
    timeline.append(button);
  }
  renderDecision();
  panel.append(
    review,
    timeline,
    element(
      'p',
      'fine-print session-note',
      'Session only — closing the browser clears this result.',
    ),
  );
  return panel;
}

function actionButton(label: string, type: string): HTMLButtonElement {
  const button = element('button', 'button secondary', label);
  button.type = 'button';
  button.disabled = busy;
  button.addEventListener('click', () => void run({ type }));
  return button;
}

function pairedView(value: SessionView): HTMLElement {
  const container = element('div');
  const status = element('section', `status status-${value.phase.toLowerCase()}`);
  status.append(
    element('span', 'status-label', value.phase.replaceAll('_', ' ')),
    element('p', undefined, value.message),
  );
  if (value.queuePosition !== undefined) {
    status.append(element('p', 'fine-print', `Queue position ${value.queuePosition}`));
  }
  if (value.queueDeadlineAt !== undefined) {
    const remaining = Math.max(0, value.queueDeadlineAt - Math.floor(Date.now() / 1000));
    status.append(element('p', 'fine-print', `Queue timeout in ${remaining}s`));
  }
  if (
    value.startedAt !== undefined &&
    Date.now() - value.startedAt > 180_000 &&
    ['QUEUED', 'RUNNING'].includes(value.phase)
  ) {
    status.append(element('p', 'warning', 'The local three-minute target has been exceeded.'));
  }
  container.append(status);

  const actions = element('div', 'actions');
  if (value.phase === 'READY')
    actions.append(actionButton('Connect current Lichess game', 'ui/connect-current-tab'));
  if (value.phase === 'CONSENT_REQUIRED')
    actions.append(actionButton('Wait for analysis', 'ui/queue-consent'));
  if (value.phase === 'WAITING') {
    actions.append(
      actionButton('Extend wait', 'ui/queue-extend'),
      actionButton('Cancel queued analysis', 'ui/queue-cancel'),
    );
  }
  if (['QUEUED', 'RUNNING', 'FAILED', 'ERROR'].includes(value.phase)) {
    actions.append(actionButton('Refresh status', 'ui/refresh'));
  }
  if (value.phase === 'AVAILABLE') {
    actions.append(actionButton('Analyze another game', 'ui/analyze-another-game'));
  }
  actions.append(actionButton('Disconnect and clear session', 'ui/disconnect'));
  container.append(actions);
  if (value.phase === 'LIVE') {
    container.append(
      element(
        'p',
        'safety',
        'Safety lock active: no analysis, recommendations, or engine output are requested or displayed during live play.',
      ),
    );
  }
  if (value.phase === 'AVAILABLE' && value.result !== undefined)
    container.append(resultPanel(value.result));
  return container;
}

function pairingView(value: SessionView): HTMLElement {
  const form = element('form', 'panel pairing');
  const email = element('input');
  email.type = 'email';
  email.placeholder = 'Local account email';
  email.autocomplete = 'username';
  email.required = true;
  const password = element('input');
  password.type = 'password';
  password.placeholder = 'Local account password';
  password.autocomplete = 'current-password';
  password.required = true;
  const submit = element('button', 'button', busy ? 'Pairing…' : 'Pair locally');
  submit.type = 'submit';
  submit.disabled = busy;
  form.append(
    element('h2', undefined, 'Local pairing'),
    element(
      'p',
      'fine-print',
      `Connects only to ${value.apiBaseUrl}. Credentials are not stored; tokens remain in session-only extension storage until the browser closes.`,
    ),
    email,
    password,
    submit,
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void run({ email: email.value, password: password.value, type: 'ui/login-and-pair' });
  });
  if (value.phase === 'ERROR') form.append(element('p', 'error', value.message));
  return form;
}

function render(): void {
  if (session === undefined) return;
  const main = element('main');
  const header = element('header', 'app-header');
  header.append(
    element('div', 'mark', 'BT'),
    element('div', undefined, 'BoardTrace'),
    element('span', 'tagline', 'Review every decision.'),
  );
  main.append(header, session.paired ? pairedView(session) : pairingView(session));
  popupRoot.replaceChildren(main);
}

function scheduleRefresh(): void {
  if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
  if (session !== undefined && ['QUEUED', 'RUNNING', 'WAITING'].includes(session.phase)) {
    refreshTimer = window.setTimeout(() => void run({ type: 'ui/refresh' }, true), 3000);
  }
}

async function run(message: object, automatic = false): Promise<void> {
  if (busy) return;
  busy = true;
  if (!automatic) render();
  try {
    session = await send(message);
  } catch (error: unknown) {
    if (session !== undefined) {
      session = {
        ...session,
        message: error instanceof Error ? error.message : 'The extension request failed.',
        phase: 'ERROR',
      };
    }
  } finally {
    busy = false;
    render();
    scheduleRefresh();
  }
}

void run({ type: 'ui/state' });
