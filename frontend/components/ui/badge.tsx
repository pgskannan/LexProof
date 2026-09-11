import type { HTMLAttributes } from 'react'

type BadgeVariant = 'default' | 'verified' | 'tampered' | 'pending' | 'critical' | 'high' | 'medium' | 'low' | 'secondary'

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant
}

// Design tokens (Phase 1 foundation): every variant now also carries a
// dark: treatment -- previously Badge had none at all, so any badge shown
// while the app's dark mode (§39) was active fell back to raw light-mode
// colors sitting directly on a dark page background. This is purely
// additive (dark: classes only apply when the `dark` class from
// ThemeProvider is present); every variant's light-mode class string,
// and the BadgeVariant keys themselves, are unchanged from before.
const variantStyles: Record<BadgeVariant, string> = {
  default: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100',
  verified: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  tampered: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  pending: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  critical: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  high: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
  medium: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  low: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  secondary: 'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-100',
}

export function Badge({ className = '', variant = 'default', ...props }: BadgeProps) {
  return <span className={`${variantStyles[variant]} ${className}`} {...props} />
}

