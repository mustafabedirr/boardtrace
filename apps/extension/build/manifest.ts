interface ExtensionManifest {
  readonly action: { readonly default_popup: string; readonly default_title: string };
  readonly background: { readonly service_worker: string; readonly type: 'module' };
  readonly content_security_policy: { readonly extension_pages: string };
  readonly description: string;
  readonly host_permissions: readonly string[];
  readonly manifest_version: 3;
  readonly name: string;
  readonly permissions: readonly string[];
  readonly version: string;
}

export function createExtensionManifest(apiBaseUrl: string): ExtensionManifest {
  const endpoint = new URL(apiBaseUrl);
  return {
    action: {
      default_popup: 'popup.html',
      default_title: 'Open BoardTrace',
    },
    background: {
      service_worker: 'service-worker.js',
      type: 'module',
    },
    content_security_policy: {
      extension_pages: "script-src 'self'; object-src 'self'; base-uri 'self'",
    },
    description: 'Local, post-game Lichess capture and session-only analysis review.',
    host_permissions: [`${endpoint.origin}/*`],
    manifest_version: 3,
    name: 'BoardTrace Local',
    permissions: ['activeTab', 'scripting', 'storage'],
    version: '0.2.0',
  };
}
