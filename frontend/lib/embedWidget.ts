/**
 * Helpers for the "Copy embed code" action on the public-verification
 * widget (Task #108) -- builds the two-tag HTML snippet a user pastes onto
 * a THIRD PARTY website (e.g. a counterparty's own site) to show a live
 * "Verified by LexProof" badge for one piece of anchored evidence. The
 * widget script itself lives at frontend/public/lexproof-verify-widget.js.
 */

export function widgetScriptUrl(origin: string): string {
  return `${origin.replace(/\/$/, '')}/lexproof-verify-widget.js`
}

/**
 * The widget script needs an absolute API origin to call from a foreign
 * domain -- a relative path only resolves against the embedding site's own
 * origin, not LexProof's. Prefer an explicitly configured API base
 * (NEXT_PUBLIC_API_URL, passed in by the caller so this stays pure and
 * testable); fall back to the frontend's own origin, which is correct
 * whenever the API is reverse-proxied onto the same domain as the app.
 */
export function defaultApiBase(origin: string, configuredApiBase?: string | null): string {
  const trimmed = (configuredApiBase ?? '').trim()
  return (trimmed || origin).replace(/\/$/, '')
}

export type EmbedSnippetParams = {
  evidenceId: string
  scriptOrigin: string
  apiBase: string
  verifyPageOrigin?: string
}

export function embedSnippet({ evidenceId, scriptOrigin, apiBase, verifyPageOrigin }: EmbedSnippetParams): string {
  const script = widgetScriptUrl(scriptOrigin)
  const api = apiBase.replace(/\/$/, '')
  const verifyPageAttr = verifyPageOrigin
    ? ` data-lexproof-verify-page="${verifyPageOrigin.replace(/\/$/, '')}/public-verify"`
    : ''
  return [
    `<script src="${script}" data-api-base="${api}" async></script>`,
    `<div class="lexproof-verify" data-lexproof-evidence-id="${evidenceId}"${verifyPageAttr}></div>`,
  ].join('\n')
}
