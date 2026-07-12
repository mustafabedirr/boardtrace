import { spawnSync } from 'node:child_process';

const pnpmEntrypoint = process.env.npm_execpath;
const checks = ['format:check', 'lint', 'typecheck', 'test'];

if (!pnpmEntrypoint) {
  throw new Error('Run this quality gate through pnpm.');
}

for (const check of checks) {
  const result = spawnSync(process.execPath, [pnpmEntrypoint, 'run', check], {
    stdio: 'inherit',
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
