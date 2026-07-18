import type { BoardObservation, BoardRegion, GameContext, GamePhase } from './protocol';

const BOARD_STATE_ATTRIBUTE = 'data-boardtrace-board-state';
const GAME_ID_ATTRIBUTE = 'data-boardtrace-game-id';
const GAME_PHASE_ATTRIBUTE = 'data-boardtrace-game-phase';
const MOVE_ATTRIBUTE = 'data-boardtrace-move';

function readPhase(value: string | null): GamePhase {
  return value === 'LIVE' || value === 'POST_GAME' ? value : 'UNKNOWN';
}

function selectedRegion(element: Element): BoardRegion {
  const { height, width, x, y } = element.getBoundingClientRect();
  return { height, width, x, y };
}

export function readGameContext(boardElement: Element): GameContext {
  return {
    gameId: boardElement.getAttribute(GAME_ID_ATTRIBUTE),
    phase: readPhase(boardElement.getAttribute(GAME_PHASE_ATTRIBUTE)),
    sourceOrigin: window.location.origin,
  };
}

export function readBoardObservation(boardElement: Element): BoardObservation {
  return {
    boardState: boardElement.getAttribute(BOARD_STATE_ATTRIBUTE),
    moveText: boardElement.getAttribute(MOVE_ATTRIBUTE),
    observedAt: new Date().toISOString(),
    region: selectedRegion(boardElement),
  };
}

export const observationAttributes = [
  BOARD_STATE_ATTRIBUTE,
  GAME_ID_ATTRIBUTE,
  GAME_PHASE_ATTRIBUTE,
  MOVE_ATTRIBUTE,
] as const;
