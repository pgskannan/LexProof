export function isPublicPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false
  return pathname === '/login' || pathname === '/public-verify' || pathname.startsWith('/counterparty/')
}
