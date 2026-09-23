export function shouldAbortPreviousRequest(
  previousRequestId: number,
  latestRequestId: number,
  previousContextKey?: string,
  latestContextKey?: string,
): boolean {
  if (previousRequestId <= 0) return false
  if (latestRequestId === previousRequestId) return false

  if (previousContextKey === undefined || latestContextKey === undefined) {
    return false
  }

  return previousContextKey !== latestContextKey
}
