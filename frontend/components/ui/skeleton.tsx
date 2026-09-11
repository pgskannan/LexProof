import type { HTMLAttributes } from 'react'

// Design tokens (Phase 1 foundation): radius aligned to the shared scale
// (--radius-lg resolves to the same 0.75rem this component already used).
export function Skeleton({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`animate-pulse rounded-[var(--radius-lg,0.75rem)] bg-gray-200 dark:bg-gray-700 ${className}`} {...props} />
}
