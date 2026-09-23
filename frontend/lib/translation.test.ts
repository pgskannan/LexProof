import { describe, expect, it } from 'vitest';
import { listSupportedLanguagesPath, translateFindingsRequest, translationCacheKey } from './translation';

describe('translation request helpers', () => {
  it('builds the supported-languages path', () => {
    expect(listSupportedLanguagesPath()).toBe('/api/findings/languages');
  });

  it('builds the translate-findings request', () => {
    const request = translateFindingsRequest(['f1', 'f2'], 'es');
    expect(request).toEqual({
      path: '/api/findings/translate',
      method: 'POST',
      body: JSON.stringify({ finding_ids: ['f1', 'f2'], target_language: 'es' }),
    });
  });

  it('builds a stable cache key per (finding, language) pair', () => {
    expect(translationCacheKey('f1', 'es')).toBe('f1::es');
    expect(translationCacheKey('f1', 'fr')).not.toBe(translationCacheKey('f1', 'es'));
  });
});
