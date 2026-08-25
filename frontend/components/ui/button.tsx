import type { ButtonHTMLAttributes } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  size?: 'sm' | 'default' | 'lg'
  variant?: 'default' | 'outline'
}

export function Button({ className = '', size = 'default', variant = 'default', ...props }: ButtonProps) {
  return <button className={`inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition ${className}`} {...props} />
}
