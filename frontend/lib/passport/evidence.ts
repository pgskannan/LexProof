export interface EvidenceLike {
  evidence_type: string
}

/** Actual finding evidence records; excludes score metadata rows. */
export function isLegalEvidenceFinding(item: EvidenceLike): boolean {
  return item.evidence_type !== 'metadata'
}

export function filterLegalEvidenceFindings<T extends EvidenceLike>(items: T[]): T[] {
  return items.filter(isLegalEvidenceFinding)
}

export function countLegalEvidenceFindings(items: EvidenceLike[]): number {
  return filterLegalEvidenceFindings(items).length
}
