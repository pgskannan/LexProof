export function publicVerifyUrl(evidenceId: string, origin?: string): string {
  const base = (origin || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '')
  return `${base}/public-verify?evidence_id=${encodeURIComponent(evidenceId)}`
}
