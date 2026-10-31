import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    settings: { react: { version: 'detect' } },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,

      // Without these two, `no-unused-vars` cannot see that a binding is used
      // inside JSX, and every component and icon prop reads as unused.
      'react/jsx-uses-vars': 'error',
      'react/jsx-uses-react': 'error',

      // The point of linting here is to catch identifiers used but never
      // imported, and imports that are never used - mistakes a Vite build does
      // not surface because it only resolves module-level bindings.
      'no-undef': 'error',
      'no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', ignoreRestSiblings: true },
      ],

      // react-hooks v7 treats any setState inside an effect as an error. Most
      // of ours are the ordinary "fetched data has arrived, put it in state"
      // and "restore the session on mount" patterns, which is what effects are
      // for. Kept as a warning so a genuinely cascading render still shows up
      // without 10 false alarms burying it.
      'react-hooks/set-state-in-effect': 'warn',

      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Build configs run in Node, not the browser.
    files: ['vite.config.js', 'vitest.config.js', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },
  {
    // The smoke suite runs in jsdom but also reads Node's process.env.
    files: ['src/**/*.test.{js,jsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
]
