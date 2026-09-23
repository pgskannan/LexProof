/**
 * Helpers for white-label / custom branding (Task #109) -- an org Admin can
 * set a logo URL and a primary brand color (Administration > Settings),
 * which the app applies via CSS custom properties instead of touching every
 * hardcoded Tailwind color class individually. An org that hasn't
 * customized branding (the default) falls back to LexProof's own blue --
 * this is purely additive, never a regression to the existing look.
 */

export type OrgBranding = {
  logo_url?: string | null
  primary_color?: string | null
}

const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/

export function isValidHexColor(value: string): boolean {
  return HEX_COLOR_RE.test(value.trim())
}

/** LexProof's own default brand color (Tailwind blue-600) -- used whenever an org hasn't set one. */
export const DEFAULT_PRIMARY_COLOR = '#2563eb'

/**
 * Darkens a #rrggbb hex color by `amount` (0-1), for a hover/active shade.
 * Returns the input unchanged if it isn't a valid hex color.
 */
export function darkenHex(hex: string, amount = 0.15): string {
  const trimmed = hex.trim()
  if (!isValidHexColor(trimmed)) return trimmed
  const num = parseInt(trimmed.slice(1), 16)
  const channel = (shift: number) => Math.max(0, Math.min(255, Math.round(((num >> shift) & 0xff) * (1 - amount))))
  const [r, g, b] = [channel(16), channel(8), channel(0)]
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, '0')).join('')}`
}

/**
 * CSS custom properties for the app's brand accent, derived from an org's
 * branding settings. Always returns a complete, valid pair -- an unset or
 * invalid primary_color falls back to LexProof's default rather than
 * producing an empty or invalid CSS value. Spread the result into a React
 * `style` prop on a wrapping element; descendants (Button's default
 * variant, Navigation's active-item highlight) read `var(--brand-primary, ...)`
 * with the same default baked in, so this is safe to apply even when
 * `branding` is null.
 */
export function brandCssVars(branding: OrgBranding | null | undefined): Record<string, string> {
  const raw = (branding?.primary_color || '').trim()
  const primary = isValidHexColor(raw) ? raw : DEFAULT_PRIMARY_COLOR
  return {
    '--brand-primary': primary,
    '--brand-primary-hover': darkenHex(primary, 0.15),
  }
}

/** True when an org has customized at least one branding field. */
export function hasCustomBranding(branding: OrgBranding | null | undefined): boolean {
  return Boolean(branding?.logo_url || branding?.primary_color)
}
