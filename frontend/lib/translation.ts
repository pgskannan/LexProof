export type SupportedLanguages = Record<string, string>

export type FindingTranslation = {
  title?: string | null
  description?: string | null
  recommendation?: string | null
  playbook_notes?: string | null
  target_language: string
}

export type FindingTranslations = Record<string, FindingTranslation>

export function listSupportedLanguagesPath(): string {
  return '/api/findings/languages'
}

export function translateFindingsRequest(findingIds: string[], targetLanguage: string) {
  return {
    path: '/api/findings/translate',
    method: 'POST' as const,
    body: JSON.stringify({ finding_ids: findingIds, target_language: targetLanguage }),
  }
}

/** Cache key for one (finding, language) pair -- mirrors the backend's own
 * `finding_translations` cache document id, so the two stay easy to reason
 * about together even though this key never leaves the browser. */
export function translationCacheKey(findingId: string, targetLanguage: string): string {
  return `${findingId}::${targetLanguage}`
}
