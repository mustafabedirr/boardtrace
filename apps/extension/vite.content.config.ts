import { resolve } from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  publicDir: false,
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    sourcemap: false,
    lib: {
      entry: resolve(import.meta.dirname, 'src/content-script.ts'),
      formats: ['iife'],
      name: 'BoardTraceLichessContentScript',
      fileName: () => 'content-script.js',
    },
  },
});
