const PUBLIC_EXACT = new Set(['/', '/login', '/request-trial', '/public-verify'])

export function isPublicPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  return PUBLIC_EXACT.has(pathname) || pathname.startsWith('/public-verify/') || pathname.startsWith('/counterparty/')
}
