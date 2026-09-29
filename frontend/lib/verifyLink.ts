/**
 * Public origin for verification links and QR codes. Set
 * NEXT_PUBLIC_PUBLIC_VERIFY_ORIGIN (e.g. https://lexproof.vercel.app) so QR codes
 * point at the deployed public verifier even when the app itself runs on localhost —
 * otherwise a phone scan would try to open the presenter's own machine.
 */
export const PUBLIC_VERIFY_ORIGIN = (process.env.NEXT_PUBLIC_PUBLIC_VERIFY_ORIGIN || '').replace(/\/$/, '')

export function publicVerifyOrigin(fallback?: string): string {
  return PUBLIC_VERIFY_ORIGIN || (fallback || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '')
}

export function publicVerifyUrl(evidenceId: string, origin?: string): string {
  const base = (origin || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '')
  return `${base}/public-verify?evidence_id=${encodeURIComponent(evidenceId)}`
}
