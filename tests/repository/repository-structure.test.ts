import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '../..');

function readRepositoryFile(relativePath: string): string {
  return readFileSync(resolve(root, relativePath), 'utf8');
}

describe('repository contract', () => {
  it('keeps required repository and security documents', () => {
    for (const relativePath of [
      'AGENTS.md',
      'README.md',
      '.env.example',
      'docs/security/live-analysis-lock.md',
    ]) {
      expect(existsSync(resolve(root, relativePath))).toBe(true);
    }
  });

  it('uses the approved pnpm package manager metadata', () => {
    const packageMetadata: unknown = JSON.parse(readRepositoryFile('package.json'));

    expect(packageMetadata).toMatchObject({
      name: 'boardtrace',
      packageManager: 'pnpm@11.11.0',
      private: true,
    });
  });

  it('documents every live-analysis lifecycle state', () => {
    const securityDocument = readRepositoryFile('docs/security/live-analysis-lock.md');

    for (const state of [
      'CREATED',
      'CAPTURING',
      'FINISH_PENDING',
      'FINISHED',
      'DEEP_ANALYSIS_RUNNING',
      'ANALYSIS_AVAILABLE',
      'FAILED',
    ]) {
      expect(securityDocument).toContain(state);
    }
  });
});
