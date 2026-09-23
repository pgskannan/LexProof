import React from 'react';

/**
 * Reviewer-facing feedback for the benchmark review save workflow.
 *
 * The save path used to end silently: a successful PATCH produced no visible
 * message at all, so "Save Draft" and "Save & Next" looked like they did
 * nothing even though the write succeeded. Success and failure now render
 * through this single component, at the point of action.
 */
export function ReviewFeedback({ success, error }: { success?: string; error?: string }) {
  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {error}
      </div>
    )
  }
  if (success) {
    return (
      <div role="status" aria-live="polite" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        {success}
      </div>
    )
  }
  return null
}
