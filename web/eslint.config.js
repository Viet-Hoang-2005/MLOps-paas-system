import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import boundaries from 'eslint-plugin-boundaries'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

const architectureImportRestrictions = [
  {
    group: ['@/components/**', '@/hooks/**', '@/lib/**', '@/pages/**', '@/types/**'],
    message: 'Import from app, features, or shared; legacy source roots are not allowed.',
  },
  {
    group: ['antd', 'antd/**', '@ant-design/**'],
    message: 'Ant Design is not part of the frontend design system; use shared Tailwind/Radix primitives.',
  },
  {
    group: ['../*', '../../*', '../../../*', '../../../../*', '../../../../../*'],
    message: 'Use the @/ alias for imports that cross a directory boundary.',
  },
]

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    plugins: { boundaries },
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    settings: {
      'boundaries/elements': [
        { type: 'app', pattern: 'src/app/**' },
        { type: 'feature', pattern: 'src/features/**' },
        { type: 'shared', pattern: 'src/shared/**' },
        { type: 'asset', pattern: 'src/assets/**' },
      ],
    },
    rules: {
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/no-base-to-string': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
      '@typescript-eslint/no-misused-promises': 'off',
      '@typescript-eslint/no-redundant-type-constituents': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/prefer-promise-reject-errors': 'off',
      '@typescript-eslint/require-await': 'off',
      'no-restricted-imports': ['error', { patterns: architectureImportRestrictions }],
      'boundaries/dependencies': ['error', {
        default: 'disallow',
        policies: [
          {
            from: { element: { types: 'app' } },
            allow: { to: { element: { types: { anyOf: ['app', 'feature', 'shared', 'asset'] } } } },
          },
          {
            from: { element: { types: 'feature' } },
            allow: { to: { element: { types: { anyOf: ['feature', 'shared', 'asset'] } } } },
          },
          {
            from: { element: { types: 'shared' } },
            allow: { to: { element: { types: { anyOf: ['shared', 'asset'] } } } },
          },
        ],
      }],
    },
  },
  {
    files: ['src/features/*/pages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': ['error', {
        paths: [{ name: 'axios', message: 'Pages must call a feature API or hook instead of Axios directly.' }],
        patterns: [
          ...architectureImportRestrictions,
          { group: ['**/shared/api/client', '**/lib/api'], message: 'Pages must call a feature API or hook.' },
        ],
      }],
    },
  },
])
