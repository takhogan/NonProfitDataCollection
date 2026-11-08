import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'playwright-report', 'test-results'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // WEB-060: no persistent browser storage for anything; use in-memory state.
      'no-restricted-globals': [
        'error',
        { name: 'localStorage', message: 'WEB-060: no persistent browser storage.' },
        { name: 'sessionStorage', message: 'WEB-060: no persistent browser storage.' },
        { name: 'indexedDB', message: 'WEB-060: no persistent browser storage.' },
      ],
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'localStorage', message: 'WEB-060' },
        { object: 'window', property: 'sessionStorage', message: 'WEB-060' },
        { object: 'window', property: 'indexedDB', message: 'WEB-060' },
      ],
    },
  },
  {
    // Tests assert that storage stays empty, so they may read it.
    files: ['**/*.test.{ts,tsx}', 'e2e/**'],
    rules: { 'no-restricted-globals': 'off', 'no-restricted-properties': 'off' },
  },
);
