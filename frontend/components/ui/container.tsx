import type { HTMLAttributes } from 'react'

// New in Phase 2 (2026-09-11) -- the enterprise application-shell pass.
// A consistent content-area wrapper: horizontal padding, a sane max-width
// so lines of text/tables don't stretch edge-to-edge on wide monitors, and
// a standard vertical rhythm -- the "CONTENT AREA" conventions from the
// redesign brief, as one reusable primitive.
//
// Phase 4 (2026-09-11, gold-standard visual consistency pass): widened from
// max-w-7xl (1280px) to the brief's explicit ~1440px target and normalized
// horizontal padding to the requested 24-32px range (was px-4/24px on
// mobile already; sm/lg breakpoints now land on 24px/32px exactly instead
// of Tailwind's default 24px/32px-via-lg:px-8, which happened to already
// match -- so this is a max-width change plus an explicit, documented
// value rather than a visual regression). This phase also completes the
// screen-by-screen adoption Phase 2 deliberately deferred: every
// authenticated screen now imports PageContainer/PageHeader (see the
// Phase 4 screen inventory in the project for the per-screen list).
export function PageContainer({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`mx-auto w-full max-w-[1440px] px-6 py-6 sm:px-8 ${className}`} {...props} />
}
