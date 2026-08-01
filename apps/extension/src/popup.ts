const root = document.getElementById('root');
if (root === null) {
  throw new Error('Popup root is unavailable.');
}

const main = document.createElement('main');
const heading = document.createElement('h1');
const selectionInstruction = document.createElement('p');
const fairPlayNotice = document.createElement('p');
const retentionNotice = document.createElement('p');

heading.textContent = 'BoardTrace';
selectionInstruction.textContent =
  'Select a board from the extension button to begin consented capture.';
fairPlayNotice.textContent =
  'Live games never receive analysis, recommendations, or engine output.';
retentionNotice.textContent =
  'Analysis results are session-only. Closing the analysis page loses the result; no analysis history is kept.';

main.append(heading, selectionInstruction, fairPlayNotice, retentionNotice);
root.replaceChildren(main);
