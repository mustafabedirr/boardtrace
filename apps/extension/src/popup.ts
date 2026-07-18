const root = document.getElementById('root');
if (root === null) {
  throw new Error('Popup root is unavailable.');
}

const main = document.createElement('main');
const heading = document.createElement('h1');
const selectionInstruction = document.createElement('p');
const fairPlayNotice = document.createElement('p');

heading.textContent = 'BoardTrace';
selectionInstruction.textContent =
  'Select a board from the extension button to begin consented capture.';
fairPlayNotice.textContent =
  'Live games never receive analysis, recommendations, or engine output.';

main.append(heading, selectionInstruction, fairPlayNotice);
root.replaceChildren(main);
