import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

// The golden-path spec mutates the shared Firestore fixture from DRAFT to
// APPROVED. Re-seed through the existing backend script so a second
// `npx playwright test` still starts at DRAFT. This is the same command a
// human runs after a passing golden-path E2E -- not a product bypass.

function backendPython(backendRoot: string): string {
  if (process.env.E2E_BACKEND_PYTHON) return process.env.E2E_BACKEND_PYTHON
  const win = resolve(backendRoot, '.venv/Scripts/python.exe')
  const unix = resolve(backendRoot, '.venv/bin/python')
  if (existsSync(win)) return win
  if (existsSync(unix)) return unix
  return 'python'
}

export function resetGoldenPathFixture() {
  const backendRoot = resolve(__dirname, '../../../backend')
  const python = backendPython(backendRoot)
  try {
    execFileSync(
      python,
      ['scripts/create_approval_demo_fixture.py', '--fixture', 'golden-path', '--reset'],
      { cwd: backendRoot, stdio: 'inherit' },
    )
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      `Failed to re-seed the golden-path DRAFT fixture. ` +
        `From backend/, run: .venv/Scripts/python.exe scripts/create_approval_demo_fixture.py --fixture golden-path --reset. ` +
        `(${detail})`,
    )
  }
}
