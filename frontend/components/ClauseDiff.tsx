import type { HTMLAttributes } from 'react'

type ClauseDiffProps = HTMLAttributes<HTMLDivElement> & {
  originalText?: string | null
  proposedText?: string | null
}

export function ClauseDiff({ originalText, proposedText, className = '', ...props }: ClauseDiffProps) {
  return (
    <div className={`grid gap-4 sm:grid-cols-2 ${className}`} {...props}>
      <div>
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Original clause</p>
        <p className="mt-2 whitespace-pre-wrap rounded border border-red-200 bg-red-50 p-3 text-sm text-gray-800">
          {originalText || 'Not available'}
        </p>
      </div>
      <div>
        <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Proposed redline</p>
        <p className="mt-2 whitespace-pre-wrap rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-gray-800">
          {proposedText || 'Not proposed yet'}
        </p>
      </div>
    </div>
  )
}
