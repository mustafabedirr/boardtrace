import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/.git/**',
      '**/.next/**',
      '**/.venv/**',
      '**/.vite/**',
      '**/coverage/**',
      '**/dist/**',
      '**/node_modules/**',
      '**/test-results/**',
      '**/ml/checkpoints/**',
      '**/ml/outputs/**',
      '**/ml/runs/**',
    ],
  },
  js.configs.recommended,
  {
    files: ['**/*.mjs'],
    languageOptions: {
      globals: {
        process: 'readonly',
      },
    },
  },
  ...tseslint.configs.recommendedTypeChecked.map((config) => ({
    ...config,
    files: ['**/*.ts', '**/*.mts', '**/*.cts'],
  })),
  {
    files: ['**/*.ts', '**/*.mts', '**/*.cts'],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
    },
  },
  prettier,
);
