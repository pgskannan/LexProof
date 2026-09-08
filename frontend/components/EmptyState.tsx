import type { ReactNode } from 'react'
import { FileText } from 'lucide-react'
import { Button } from './ui/button'

type EmptyStateProps = {
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
  icon?: ReactNode
  compact?: boolean
}

export function EmptyState({ title, description, actionLabel, onAction, icon, compact = false }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white text-center ${compact ? 'px-4 py-6' : 'px-6 py-12'}`}>
      <div className={`mb-4 flex items-center justify-center rounded-full bg-blue-50 text-blue-600 ${compact ? 'h-9 w-9' : 'h-12 w-12'}`}>
        {icon || <FileText className={compact ? 'h-4 w-4' : 'h-6 w-6'} />}
      </div>
      <h3 className={`font-semibold text-gray-900 ${compact ? 'text-sm' : 'text-lg'}`}>{title}</h3>
      <p className={`mt-2 max-w-md text-gray-600 ${compact ? 'text-xs' : 'text-sm'}`}>{description}</p>
      {actionLabel && onAction && (
        <Button type="button" className="mt-5" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  )
}
