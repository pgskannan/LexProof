import { defineConfig } from 'vitest/config'

export default defineConfig({
  // tsconfig sets `"jsx": "preserve"` for Next.js, which Vite/esbuild downgrades
  // to the classic runtime. Tests render real app components (Card, Button, ...)
  // that rely on the automatic runtime Next.js itself uses, so pin it here
  // instead of forcing a vestigial `import React` into every component.
  esbuild: { jsx: 'automatic' },
  test: {
    include: ['**/*.{test,spec}.{ts,tsx}'],
    // Phase 3J-A: e2e/ holds Playwright specs (auth.smoke.spec.ts), not
    // Vitest tests -- they import '@playwright/test', not 'vitest', and are
    // run separately via `npm run test:e2e`. Exclude the whole directory so
    // this unit/component suite never tries to collect them.
    exclude: ['**/node_modules/**', 'e2e/**'],
  },
})