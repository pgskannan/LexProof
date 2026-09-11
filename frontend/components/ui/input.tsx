import { forwardRef, useId } from 'react'
import type { InputHTMLAttributes } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  /** Marks the field invalid and (if a string) renders it as an inline
   *  error message below the input, associated via aria-describedby. */
  error?: boolean | string
}

// New in Phase 1 (2026-09-11) -- the design-system foundation pass added
// design tokens plus a refresh of the existing Button/Badge/Card/Skeleton
// primitives; Input itself did not exist yet (every screen that needed a
// text field styled a bare <input> by hand, so appearance drifted between
// pages). This component is purely additive: it is not yet imported by any
// existing screen, so shipping it carries zero risk of changing current
// behavior. Adopting it on actual pages is Phase 2+ work.
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className = '', error, id, 'aria-describedby': ariaDescribedBy, ...props },
  ref,
) {
  const generatedId = useId()
  const errorId = error ? `${id ?? generatedId}-error` : undefined
  const describedBy = [ariaDescribedBy, errorId].filter(Boolean).join(' ') || undefined

  const baseStyles =
    'block w-full rounded-[var(--radius-md,0.5rem)] border bg-white px-3 py-2 text-sm text-gray-900 transition-colors duration-[var(--duration-fast,120ms)] placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-500 dark:disabled:bg-gray-900'

  // Valid state reads its focus ring from --brand-primary, same mechanism
  // as Button's default variant, so a white-labeled org's color shows up
  // consistently across every interactive primitive, not just buttons.
  const stateStyles = error
    ? 'border-red-300 focus:border-red-500 focus:ring-red-500 dark:border-red-700'
    : 'border-gray-300 focus:border-[var(--brand-primary,#2563eb)] focus:ring-[var(--brand-primary,#3b82f6)] dark:border-gray-600'

  return (
    <>
      <input
        ref={ref}
        id={id}
        className={`${baseStyles} ${stateStyles} ${className}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...props}
      />
      {typeof error === 'string' && error.length > 0 && (
        <p id={errorId} className="mt-1.5 text-xs text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
    </>
  )
})
