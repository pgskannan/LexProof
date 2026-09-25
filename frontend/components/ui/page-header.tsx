import type { ReactNode } from 'react'

type PageHeaderProps = {
  /** Small uppercase category label above the title, e.g. "Contracts". */
  eyebrow?: string
  title: string
  /** Short supporting copy under the title -- one line/sentence, not a
   *  paragraph. */
  description?: string
  /** Right-aligned primary/secondary actions (typically Button elements). */
  actions?: ReactNode
  className?: string
}

// New in Phase 2 (2026-09-11) -- the enterprise application-shell pass.
// Implements the redesign brief's page-header pattern (eyebrow / title /
// description, actions right-aligned) as one shared, reusable component so
// every screen that adopts it renders an identical header instead of each
// page hand-rolling its own <h1> block. Title size is intentionally
// Tailwind's own text-3xl (30px) -- within the brief's 30-32px range and
// deliberately smaller than the global h1 default (36px, set in
// globals.css for general prose) so it reads as "strong but compact"
// rather than oversized.
//
// Not yet imported by any existing screen -- adopting it means editing
// each page's own header markup, which is explicitly out of scope for this
// shell-only pass (see the Phase 2 report). It is built and ready for that
// follow-up.
// File-style titles (CONTRACT_03_SaaS_HighRisk.docx) are one unbreakable
// token; offer soft break points after "_" and "." so they wrap at word-ish
// boundaries instead of mid-word.
function withSoftBreaks(title: string): ReactNode {
  const parts = title.split(/(?<=[_.])/)
  if (parts.length === 1) return title
  return parts.map((part, index) => (
    <span key={index}>
      {part}
      {index < parts.length - 1 && <wbr />}
    </span>
  ))
}

export function PageHeader({ eyebrow, title, description, actions, className = '' }: PageHeaderProps) {
  return (
    <div
      className={`flex flex-col gap-4 border-b border-gray-200 pb-6 dark:border-gray-700 sm:flex-row sm:items-end sm:justify-between ${className}`}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {eyebrow}
          </p>
        )}
        <h1 className="text-3xl font-bold leading-tight tracking-tight text-gray-900 [overflow-wrap:anywhere] dark:text-gray-100">{withSoftBreaks(title)}</h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
