export const EVIDENCE_HASH_FIELDS = [
  'evidence_id',
  'passport_id',
  'evidence_type',
  'title',
  'description',
  'content',
  'content_type',
  'risk_impact',
  'compliance_impact',
  'evidence_status',
  'contract_reference',
  'policy_reference',
  'analysis_reference',
  'source',
  'source_id',
  'metadata',
] as const

export type EvidenceHashField = (typeof EVIDENCE_HASH_FIELDS)[number]

export function normalizeEvidenceValue(value: unknown): unknown {
  if (value === undefined) return null
  if (value === null) return null
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new TypeError('Unsupported numeric value: NaN/Infinity is not allowed')
    }
    return value
  }
  if (typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'bigint') {
    throw new TypeError('Unsupported numeric value: bigint is not allowed')
  }
  if (Array.isArray(value)) return value.map(item => normalizeEvidenceValue(item))
  if (typeof value === 'object') {
    const sorted: Record<string, unknown> = {}
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[key] = normalizeEvidenceValue((value as Record<string, unknown>)[key])
    }
    return sorted
  }
  return String(value)
}

export function canonicalizeEvidenceItem(
  evidence: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const source = evidence && typeof evidence === 'object' ? evidence : {}
  const canonical: Record<string, unknown> = {}

  for (const field of EVIDENCE_HASH_FIELDS) {
    const hasKey = Object.prototype.hasOwnProperty.call(source, field)
    const value = hasKey ? (source as Record<string, unknown>)[field] : undefined
    canonical[field] = value === undefined ? null : normalizeEvidenceValue(value)
  }

  return canonical
}

export function serializeCanonicalValue(value: unknown): string {
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new TypeError('Unsupported numeric value: NaN/Infinity is not allowed')
    }
    return String(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map(item => serializeCanonicalValue(item)).join(', ')}]`
  }
  if (typeof value === 'object') {
    const entries = Object.keys(value as Record<string, unknown>)
      .sort()
      .map(key => `${JSON.stringify(key)}: ${serializeCanonicalValue((value as Record<string, unknown>)[key])}`)
    return `{${entries.join(', ')}}`
  }
  throw new TypeError(`Unsupported value for canonical serialization: ${String(value)}`)
}

export function serializeCanonicalEvidence(evidence: Record<string, unknown> | null | undefined): string {
  const canonical = canonicalizeEvidenceItem(evidence)
  const entries = Object.keys(canonical)
    .sort()
    .map(key => `${JSON.stringify(key)}: ${serializeCanonicalValue(canonical[key])}`)
  return `{${entries.join(', ')}}`
}

export async function hashEvidenceItem(
  evidence: Record<string, unknown> | null | undefined,
): Promise<string> {
  const serialized = serializeCanonicalEvidence(evidence)
  const bytes = new TextEncoder().encode(serialized)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('')
}

export function normalizeHexHash(hash: string | null | undefined): string {
  if (!hash) return ''
  const trimmed = hash.trim().replace(/^0x/i, '')
  return trimmed.toLowerCase()
}

export async function compareEvidenceHash(
  evidence: Record<string, unknown> | null | undefined,
  onChainHash: string | null | undefined,
): Promise<boolean> {
  const localHash = await hashEvidenceItem(evidence)
  const normalizedOnChainHash = normalizeHexHash(onChainHash)
  if (!normalizedOnChainHash) return false
  return localHash.toLowerCase() === normalizedOnChainHash.toLowerCase()
}
