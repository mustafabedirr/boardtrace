import { resolve } from 'node:path';
import { defineConfig, loadEnv } from 'vite';

import { resolveExtensionApiBaseUrl } from './build/production-config';
import { createExtensionManifest } from './build/manifest';

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, import.meta.dirname, '');
  const apiBaseUrl = resolveExtensionApiBaseUrl(
    mode,
    process.env.BOARDTRACE_EXTENSION_API_BASE_URL ?? environment.BOARDTRACE_EXTENSION_API_BASE_URL,
  );
  return {
    define: {
      __BOARDTRACE_EXTENSION_API_BASE_URL__: JSON.stringify(apiBaseUrl),
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      sourcemap: false,
      rollupOptions: {
        input: {
          popup: resolve(import.meta.dirname, 'popup.html'),
          'service-worker': resolve(import.meta.dirname, 'src/service-worker.ts'),
        },
        output: {
          entryFileNames: '[name].js',
          chunkFileNames: 'chunks/[name]-[hash].js',
          assetFileNames: 'assets/[name]-[hash][extname]',
        },
      },
    },
    plugins: [
      {
        name: 'boardtrace-extension-manifest',
        generateBundle() {
          this.emitFile({
            fileName: 'manifest.json',
            source: `${JSON.stringify(createExtensionManifest(apiBaseUrl), null, 2)}\n`,
            type: 'asset',
          });
        },
      },
    ],
    publicDir: false,
  };
});
