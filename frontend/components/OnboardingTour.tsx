'use client'

import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

type Step = {
  id: string
  title: string
  body: string
  // A `[data-tour="..."]` selector to spotlight, or null for a centered,
  // untargeted card (used for the welcome/finish steps).
  target: string | null
}

const STEPS: Step[] = [
  {
    id: 'welcome',
    title: 'Welcome to LexProof',
    body: "Here's a 60-second tour of where things live. You can skip this any time — you can always restart it later from the account menu.",
    target: null,
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    body: 'Your home base: live activity across contracts, findings, and legal passports for the selected organization. Customizable, too — more on that later.',
    target: '[data-tour="nav-dashboard"]',
  },
  {
    id: 'quick-search',
    title: 'Quick search',
    body: 'Press ⌘K (or Ctrl+K) from anywhere to jump to any page or search contracts, findings, and passports instantly.',
    target: '[data-tour="quick-search"]',
  },
  {
    id: 'contracts',
    title: 'Contracts',
    body: 'Upload contracts here and track their AI analysis, versions, and legal passport status.',
    target: '[data-tour="nav-contracts"]',
  },
  {
    id: 'findings',
    title: 'Findings & Redlines',
    body: 'AI-surfaced risk findings and redline proposals for every contract show up here, ranked by severity.',
    target: '[data-tour="nav-findings"]',
  },
  {
    id: 'ask-lexi',
    title: 'Ask Lexi',
    body: 'Ask natural-language questions about your contracts and get sourced answers back.',
    target: '[data-tour="nav-ask-lexi"]',
  },
  {
    id: 'reviews',
    title: 'Contract Reviews',
    body: 'Approval workflows in progress — see what stage each review is at and act on the ones assigned to you.',
    target: '[data-tour="nav-reviews"]',
  },
  {
    id: 'account-menu',
    title: 'Your account menu',
    body: 'Switch between light, dark, and system theme, manage notification preferences, and sign out — all from here.',
    target: '[data-tour="account-menu"]',
  },
  {
    id: 'finish',
    title: "You're all set",
    body: 'That covers the essentials. Explore the rest of the sidebar whenever you like — and restart this tour any time from the account menu.',
    target: null,
  },
]

const START_EVENT = 'lexproof:start-tour'

type Rect = { top: number; left: number; width: number; height: number }

function measure(selector: string): Rect | null {
  const el = document.querySelector(selector)
  if (!el) return null
  const r = el.getBoundingClientRect()
  if (r.width === 0 && r.height === 0) return null
  return { top: r.top, left: r.left, width: r.width, height: r.height }
}

// Global first-run product tour, mounted once in (authenticated)/layout.tsx.
// Auto-starts for a signed-in user whose persisted `tour_completed` UI
// preference is false (GET/PATCH /api/preferences/ui, same endpoint/pattern
// as theme and dashboard-widget prefs). Can also be replayed any time via
// the `lexproof:start-tour` window event, dispatched by a "Take the tour"
// entry in the account menu -- mirrors the command palette's
// `lexproof:open-command-palette` event pattern.
export function OnboardingTour() {
  const [active, setActive] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)

  // Auto-start check, independent of manual replay below: only ever turns
  // the tour ON (when the persisted preference says it hasn't been seen).
  // Deliberately does *not* gate rendering on "have we heard back yet" --
  // this GET can hang for a long time in this environment (the same
  // Firestore-latency pattern documented elsewhere in the project), and a
  // manual replay via the account menu must keep working even while it's
  // still in flight or never resolves.
  useEffect(() => {
    let cancelled = false
    void apiFetch('/api/preferences/ui')
      .then(async (response) => {
        if (!response.ok || cancelled) return
        const body = await response.json()
        if (body?.tour_completed === false) {
          setActive(true)
          setStepIndex(0)
        }
      })
      .catch(() => {
        // Offline / signed out / server down -- don't force the tour on an
        // uncertain state; it can always be started manually.
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    function onStart() {
      setStepIndex(0)
      setActive(true)
    }
    window.addEventListener(START_EVENT, onStart)
    return () => window.removeEventListener(START_EVENT, onStart)
  }, [])

  const recompute = useCallback(() => {
    const step = STEPS[stepIndex]
    if (!step || !step.target) {
      setRect(null)
      return
    }
    setRect(measure(step.target))
  }, [stepIndex])

  useEffect(() => {
    if (!active) return
    recompute()
    // The sidebar/admin section can change layout (e.g. the admin submenu
    // expanding) after the tour starts, so keep the spotlight in sync.
    const id = window.setInterval(recompute, 200)
    window.addEventListener('resize', recompute)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('resize', recompute)
    }
  }, [active, recompute])

  function persistTourCompleted() {
    void apiFetch('/api/preferences/ui', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tour_completed: true }),
    }).catch(() => {
      // Best-effort; the tour already closed locally either way.
    })
  }

  function end() {
    setActive(false)
    persistTourCompleted()
  }

  function next() {
    if (stepIndex >= STEPS.length - 1) {
      end()
      return
    }
    setStepIndex((i) => i + 1)
  }

  function back() {
    setStepIndex((i) => Math.max(0, i - 1))
  }

  if (!active) return null

  const step = STEPS[stepIndex]
  const isFirst = stepIndex === 0
  const isLast = stepIndex === STEPS.length - 1

  // Position the tooltip card near the spotlighted element, clamped to the
  // viewport; centered when there's no target.
  let cardStyle: React.CSSProperties
  if (rect) {
    const preferBelow = rect.top < window.innerHeight * 0.6
    const top = preferBelow ? rect.top + rect.height + 12 : Math.max(12, rect.top - 12)
    const left = Math.min(Math.max(12, rect.left), window.innerWidth - 336)
    cardStyle = preferBelow
      ? { position: 'fixed', top, left, transform: 'none' }
      : { position: 'fixed', top, left, transform: 'translateY(-100%)' }
  } else {
    cardStyle = { position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
  }

  return (
    <div className="fixed inset-0 z-[100]" role="dialog" aria-modal="true" aria-label="Product tour">
      {/* Spotlight: a single element sized to the target's rect, whose huge
          box-shadow doubles as the dimmed backdrop everywhere else -- this
          avoids needing an SVG mask for the cutout. */}
      {rect ? (
        <div
          className="pointer-events-none fixed rounded-lg transition-all duration-200 ease-out"
          style={{
            top: rect.top - 6,
            left: rect.left - 6,
            width: rect.width + 12,
            height: rect.height + 12,
            boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.6)',
            outline: '2px solid rgb(59, 130, 246)',
          }}
        />
      ) : (
        <div className="fixed inset-0 bg-slate-900/60" />
      )}

      <div
        className="w-80 rounded-lg border border-gray-200 bg-white p-4 shadow-xl dark:border-gray-700 dark:bg-gray-800"
        style={cardStyle}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
          Step {stepIndex + 1} of {STEPS.length}
        </p>
        <h3 className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100">{step.title}</h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{step.body}</p>
        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            onClick={end}
            className="text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {!isFirst && (
              <button
                type="button"
                onClick={back}
                className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
              >
                Back
              </button>
            )}
            <button
              type="button"
              onClick={next}
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              {isLast ? 'Finish' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
