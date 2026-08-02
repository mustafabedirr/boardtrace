export function resolveExtensionApiBaseUrl(mode: string, configured: string | undefined): string {
  if (configured === undefined || configured.length === 0) {
    if (mode === 'production') {
      throw new Error('BOARDTRACE_EXTENSION_API_BASE_URL is required for production builds.');
    }
    return 'http://127.0.0.1:18080';
  }
  const parsed = new URL(configured);
  if (
    !['http:', 'https:'].includes(parsed.protocol) ||
    parsed.username.length > 0 ||
    parsed.password.length > 0 ||
    parsed.search.length > 0 ||
    parsed.hash.length > 0
  ) {
    throw new Error('BOARDTRACE_EXTENSION_API_BASE_URL must be a credential-free HTTP(S) URL.');
  }
  if (
    mode === 'production' &&
    (parsed.protocol !== 'https:' || ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname))
  ) {
    throw new Error('Production extension API endpoint must use non-local HTTPS.');
  }
  return configured.replace(/\/+$/, '');
}
