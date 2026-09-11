import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  size?: 'sm' | 'default' | 'lg'
  variant?: 'default' | 'outline' | 'secondary' | 'destructive'
}

export function Button({
  className = '',
  size = 'default',
  variant = 'default',
  ...props
}: ButtonProps) {
  // Design tokens (Phase 1 foundation): radius/shadow/motion read from the
  // CSS custom properties defined in app/globals.css rather than a fixed
  // Tailwind utility, so every button in the app shares one elevation and
  // easing system. Prop API (size/variant keys) is unchanged from before
  // this pass -- only the underlying class strings were refined.
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all ease-[var(--ease-standard,ease)] duration-[var(--duration-base,200ms)] rounded-[var(--radius-md,0.5rem)] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed disabled:active:scale-100'

  const sizeStyles = {
    sm: 'px-3 py-1.5 text-xs gap-1',
    default: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2',
  }

  // "default" reads its color from the --brand-primary CSS custom property
  // (see lib/branding.ts + components/BrandingRoot.tsx) rather than a fixed
  // Tailwind blue, so white-labeled orgs (Task #109) automatically get
  // their own brand color on every primary button. The literal fallback in
  // each var() is LexProof's own default blue-600/700/500, so this is
  // pixel-identical to before for any org that hasn't customized a color.
  const variantStyles = {
    default:
      'bg-[var(--brand-primary,#2563eb)] text-white shadow-[var(--shadow-xs)] hover:bg-[var(--brand-primary-hover,#1d4ed8)] hover:shadow-[var(--shadow-sm)] focus:ring-[var(--brand-primary,#3b82f6)]',
    outline: 'border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:text-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700',
    secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200 focus:ring-gray-500 dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600',
    destructive: 'bg-red-600 text-white shadow-[var(--shadow-xs)] hover:bg-red-700 hover:shadow-[var(--shadow-sm)] focus:ring-red-500',
  }

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      {...props}
    />
  )
}
