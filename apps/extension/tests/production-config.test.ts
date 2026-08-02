import { describe, expect, it } from 'vitest';

import { resolveExtensionApiBaseUrl } from '../build/production-config';

describe('production extension endpoint configuration', () => {
  it('uses the local Caddy endpoint for development builds', () => {
    expect(resolveExtensionApiBaseUrl('development', undefined)).toBe('http://127.0.0.1:18080');
  });

  it('requires an explicit endpoint in production', () => {
    expect(() => resolveExtensionApiBaseUrl('production', undefined)).toThrowError(
      /required for production/i,
    );
  });

  it('accepts and normalizes an explicit non-local HTTPS endpoint', () => {
    expect(resolveExtensionApiBaseUrl('production', 'https://api.example.test/base/')).toBe(
      'https://api.example.test/base',
    );
  });

  it.each([
    'http://api.example.test',
    'https://localhost:8000',
    'https://127.0.0.1:8000',
    'https://user:password@api.example.test',
    'https://api.example.test?target=test',
  ])('rejects unsafe production endpoint %s', (value) => {
    expect(() => resolveExtensionApiBaseUrl('production', value)).toThrowError();
  });
});
