export type VerificationTone = 'green' | 'red' | 'amber'

export interface VerificationStatusMeta {
  label: string
  tone: VerificationTone
}

const STATUS_LABELS: Record<string, string> = {
  VERIFIED: 'VERIFIED',
  TAMPERED: 'TAMPERED',
  EVIDENCE_NOT_FOUND: 'EVIDENCE NOT FOUND',
  ANCHOR_NOT_FOUND: 'NOT YET ANCHORED',
  NOT_YET_ANCHORED: 'NOT YET ANCHORED',
  NOT_FOUND: 'EVIDENCE NOT FOUND',
}

const STATUS_TONES: Record<string, VerificationTone> = {
  VERIFIED: 'green',
  TAMPERED: 'red',
  EVIDENCE_NOT_FOUND: 'amber',
  ANCHOR_NOT_FOUND: 'amber',
  NOT_YET_ANCHORED: 'amber',
  NOT_FOUND: 'amber',
}

export function normalizeVerificationStatus(value: string | null | undefined): string {
  const raw = value?.trim() ?? ''
  if (!raw) return 'EVIDENCE_NOT_FOUND'
  const upper = raw.toUpperCase().replace(/\s+/g, '_')
  if (upper in STATUS_TONES) return upper
  if (upper === 'VERIFIED') return 'VERIFIED'
  if (upper === 'TAMPERED') return 'TAMPERED'
  if (upper === 'MISSING_ANCHOR' || upper === 'NO_ANCHOR' || upper === 'MISSING_ANCHOR_FOUND') return 'ANCHOR_NOT_FOUND'
  if (upper === 'NOT_FOUND' || upper === 'EVIDENCE_MISSING') return 'EVIDENCE_NOT_FOUND'
  if (upper === 'UNKNOWN') return 'EVIDENCE_NOT_FOUND'
  return raw.toUpperCase().replace(/\s+/g, '_')
}

export function toStatusMeta(value: string | null | undefined): VerificationStatusMeta {
  const normalized = normalizeVerificationStatus(value)
  return {
    label: STATUS_LABELS[normalized] ?? normalized.replace(/_/g, ' '),
    tone: STATUS_TONES[normalized] ?? 'amber',
  }
}

export function formatVerificationStatus(value: string | null | undefined): string {
  return toStatusMeta(value).label
}

export function statusTone(value: string | null | undefined): VerificationTone {
  return toStatusMeta(value).tone
}
