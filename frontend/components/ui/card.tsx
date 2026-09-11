import type { HTMLAttributes } from 'react'

// Design tokens (Phase 1 foundation): radius/shadow/motion read from the
// same CSS custom properties Button now uses, so cards and buttons share
// one elevation system. Visual result at default state is unchanged
// (--radius-lg/--shadow-sm below resolve to the same 0.75rem/shadow-sm
// values this component already rendered).
export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white shadow-[var(--shadow-sm)] transition-shadow duration-[var(--duration-base,200ms)] hover:shadow-[var(--shadow-md)] dark:border-gray-700 dark:bg-gray-800 ${className}`} {...props} />
}

export function CardHeader({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`border-b border-gray-200 px-6 py-5 dark:border-gray-700 ${className}`} {...props} />
}

export function CardTitle({ className = '', ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={`text-lg font-semibold text-gray-900 dark:text-gray-100 ${className}`} {...props} />
}

export function CardDescription({ className = '', ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={`text-sm text-gray-500 dark:text-gray-400 ${className}`} {...props} />
}

export function CardContent({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`px-6 py-5 ${className}`} {...props} />
}
