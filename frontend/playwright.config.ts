import { defineConfig, devices } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Phase 3J-A: minimal local env loader for E2E credentials/config, with
// NO new dependency (no dotenv package) -- see e2e/README.md. Values already
// present in the environment (e.g. set by CI) always win; this only fills
// gaps from frontend/.env.e2e.local, which is git-ignored and never committed.
function loadLocalEnvFile(path: string) {
  if (!existsSync(path)) return
  for (const rawLine of readFileSync(path, 'utf8').split('\n')) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    const value = line.slice(eq + 1).trim()
    if (key && !(key in process.env)) process.env[key] = value
  }
}
loadLocalEnvFile(resolve(__dirname, '.env.e2e.local'))

// Environment safety (Phase 3I/3J-A context: this repo has no deployed
// production URL and no separate "E2E" Firebase project -- the real
// safety boundary is that E2E must only ever point at a local dev server).
// Default is always localhost; a non-local target requires an explicit,
// deliberate opt-in so a stray/inherited env var can never silently send
// E2E traffic somewhere unintended.
const DEFAULT_BASE_URL = 'http://localhost:3000'
const baseURL = process.env.E2E_BASE_URL || DEFAULT_BASE_URL
const isLocalTarget = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/?$/i.test(baseURL)
if (!isLocalTarget && process.env.E2E_ALLOW_REMOTE !== 'true') {
  throw new Error(
    `Refusing to run E2E tests against a non-local baseURL ("${baseURL}"). ` +
      `LexProof has no dedicated E2E environment/Firebase project, so E2E must target a local dev server. ` +
      `Set E2E_ALLOW_REMOTE=true to override this explicitly if you really mean it.`,
  )
}

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false, // deterministic execution: one real login/session flow at a time
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No webServer entry: LexProof needs both the frontend (next dev) and the
  // real backend (uvicorn) running -- Playwright can only manage one process,
  // so per Step 6/Constraints ("communicate with the real running backend"),
  // both are started by the developer beforehand. See e2e/README.md.
})
