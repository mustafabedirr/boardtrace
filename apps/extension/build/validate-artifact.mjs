import { readFile } from 'node:fs/promises';
import { URL } from 'node:url';

const contentScript = await readFile(new URL('../dist/content-script.js', import.meta.url), 'utf8');

if (/^\s*import\s/mu.test(contentScript) || /\bimport\s*\(/u.test(contentScript)) {
  throw new Error('The content script must be a self-contained classic script.');
}

const manifest = JSON.parse(
  await readFile(new URL('../dist/manifest.json', import.meta.url), 'utf8'),
);

if (!manifest.permissions?.includes('scripting')) {
  throw new Error('The extension manifest must allow programmatic content-script injection.');
}

process.stdout.write('Validated self-contained content-script.js and scripting permission.\n');
