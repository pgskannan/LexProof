'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'

export type Theme = 'light' | 'dark' | 'system'
type ResolvedTheme = 'light' | 'dark'

type ThemeContextValue = {
  theme: Theme
  resolvedTheme: ResolvedTheme
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)
const STORAGE_KEY = 'lexproof-theme'

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolve(theme: Theme): ResolvedTheme {
  if (theme === 'system') return systemPrefersDark() ? 'dark' : 'light'
  return theme
}

function readStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
}

// Persisted per-user via GET/PATCH /api/preferences/ui (falls back to, and
// stays synced with, localStorage so the toggle is instant and still works
// signed out or offline). The root layout's inline script applies the
// localStorage value to <html> before hydration to avoid a flash of the
// wrong theme; this provider then reconciles with the server's copy once
// auth is ready.
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme())

  useEffect(() => {
    let cancelled = false
    void apiFetch('/api/preferences/ui')
      .then(async (response) => {
        if (!response.ok || cancelled) return
        const body = await response.json()
        if (body?.theme && body.theme !== readStoredTheme()) {
          window.localStorage.setItem(STORAGE_KEY, body.theme)
          setThemeState(body.theme)
        }
      })
      .catch(() => {
        // Offline / signed out / server down -- localStorage's value (already
        // applied) stands, and the toggle keeps working locally either way.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const resolvedTheme = useMemo(() => resolve(theme), [theme])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  useEffect(() => {
    if (theme !== 'system') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => document.documentElement.classList.toggle('dark', media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    window.localStorage.setItem(STORAGE_KEY, next)
    void apiFetch('/api/preferences/ui', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: next }),
    }).catch(() => {
      // Best-effort sync; the local toggle already applied regardless.
    })
  }, [])

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within ThemeProvider')
  return context
}
