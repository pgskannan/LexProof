'use client'

import { brandCssVars } from '../lib/branding'
import { useOrg } from './OrgProvider'

/**
 * Applies the current org's brand color (Task #109 white-label / custom
 * branding) as CSS custom properties (`--brand-primary` /
 * `--brand-primary-hover`) on the wrapping element, so every descendant --
 * Button's default variant, Navigation's active-nav-item highlight -- picks
 * it up automatically without each needing its own branding lookup. Falls
 * back to LexProof's own blue when the org hasn't customized it (see
 * lib/branding.ts's brandCssVars), so this is purely additive.
 */
export function BrandingRoot({ children }: { children: React.ReactNode }) {
  const { branding } = useOrg()
  return (
    <div className="flex" style={brandCssVars(branding) as React.CSSProperties}>
      {children}
    </div>
  )
}
