'use client'

import { useState } from 'react'
import { Check, Clipboard, Copy, KeyRound, Radio, ShieldCheck } from 'lucide-react'
import { auth } from '../lib/auth'
import { Button } from './ui/button'

type IdTokenUser = { getIdToken: (forceRefresh?: boolean) => Promise<string> }
type ClipboardWriter = { writeText: (value: string) => Promise<void> }

export async function copyCurrentFirebaseToken(
  user: IdTokenUser | null,
  clipboard: ClipboardWriter,
): Promise<boolean> {
  if (!user) return false
  const token = await user.getIdToken(true)
  await clipboard.writeText(token)
  return true
}

export function assistantMcpUrl(apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'): string {
  return `${apiUrl.replace(/\/$/, '')}/mcp`
}

const tools = [
  { name: 'list_contracts', detail: 'Browse contracts and passport status' },
  { name: 'ask_contracts', detail: 'Ask grounded questions with cited findings' },
  { name: 'verify_contract_proof', detail: 'Check passport integrity and on-chain roots' },
  { name: 'upcoming_obligations', detail: 'Review due and overdue payments' },
  { name: 'pending_approvals', detail: 'See workflow and payment actions available to you' },
  { name: 'prepare_decision', detail: 'Prepare an approval for explicit confirmation' },
  { name: 'confirm_decision', detail: 'Record a prepared approval after confirmation' },
]

export function ConnectAssistantPanel() {
  const [copied, setCopied] = useState<'token' | 'setup' | null>(null)
  const [error, setError] = useState('')
  const serverUrl = assistantMcpUrl()
  const inspectorSetup = [
    'npx @modelcontextprotocol/inspector',
    'Transport: Streamable HTTP',
    `URL: ${serverUrl}`,
    'Header: Authorization: Bearer <token>',
  ].join('\n')

  async function copyToken() {
    setError('')
    try {
      const copiedToken = await copyCurrentFirebaseToken(auth.currentUser, navigator.clipboard)
      if (!copiedToken) {
        setError('Sign in again to copy an access token.')
        return
      }
      setCopied('token')
    } catch {
      setError('The token could not be copied. Check clipboard permissions and try again.')
    }
  }

  async function copySetup() {
    setError('')
    try {
      await navigator.clipboard.writeText(inspectorSetup)
      setCopied('setup')
    } catch {
      setError('The Inspector setup could not be copied. Check clipboard permissions and try again.')
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 lg:px-10">
      <header className="mb-8 border-b border-gray-200 pb-6 dark:border-gray-700">
        <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-emerald-700 dark:text-emerald-300">
          <Radio className="h-4 w-4" /> Assistant connection
        </p>
        <h1 className="text-2xl font-semibold text-gray-950 dark:text-white">Connect an AI assistant</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600 dark:text-gray-300">
          Connect an MCP-compatible assistant to the contracts and approvals available to your account.
        </p>
      </header>

      <section aria-labelledby="endpoint-heading" className="grid gap-8 border-b border-gray-200 pb-8 dark:border-gray-700 md:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)]">
        <div>
          <h2 id="endpoint-heading" className="text-base font-semibold text-gray-900 dark:text-white">Server endpoint</h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">MCP 2025-11-25 · Streamable HTTP</p>
          <div className="mt-4 flex min-w-0 items-center gap-3 border-l-4 border-emerald-600 bg-white px-4 py-3 dark:bg-gray-800">
            <code className="min-w-0 flex-1 break-all text-sm text-gray-900 dark:text-gray-100">{serverUrl}</code>
            <ShieldCheck aria-hidden="true" className="h-5 w-5 flex-shrink-0 text-emerald-700 dark:text-emerald-300" />
          </div>
        </div>
        <div className="border-l border-gray-200 pl-0 md:pl-6 dark:border-gray-700">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">Access token</h2>
          <p className="mt-1 text-sm leading-6 text-gray-600 dark:text-gray-300">Expires in about 1 hour. Treat it like a password.</p>
          <Button className="mt-4" onClick={() => void copyToken()}>
            {copied === 'token' ? <Check aria-hidden="true" className="h-4 w-4" /> : <KeyRound aria-hidden="true" className="h-4 w-4" />}
            {copied === 'token' ? 'Token copied' : 'Copy access token'}
          </Button>
        </div>
      </section>

      <section aria-labelledby="tools-heading" className="grid gap-8 border-b border-gray-200 py-8 dark:border-gray-700 md:grid-cols-[minmax(0,1fr)_minmax(18rem,0.9fr)]">
        <div>
          <h2 id="tools-heading" className="text-base font-semibold text-gray-900 dark:text-white">Available tools</h2>
          <ul className="mt-4 divide-y divide-gray-200 dark:divide-gray-700">
            {tools.map((tool) => (
              <li key={tool.name} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                <code className="text-sm font-medium text-gray-900 dark:text-gray-100">{tool.name}</code>
                <span className="text-sm text-gray-600 dark:text-gray-300">{tool.detail}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Inspector setup</h2>
            <Button variant="outline" size="sm" onClick={() => void copySetup()}>
              {copied === 'setup' ? <Check aria-hidden="true" className="h-4 w-4" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
              {copied === 'setup' ? 'Copied' : 'Copy setup'}
            </Button>
          </div>
          <pre className="mt-4 overflow-x-auto border border-gray-200 bg-gray-50 p-4 text-xs leading-6 text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100">{inspectorSetup}</pre>
          <p className="mt-3 text-sm leading-6 text-gray-600 dark:text-gray-300">The Inspector setup contains a token placeholder. Copy the current token separately when connecting.</p>
        </div>
      </section>

      {error && <p role="alert" className="mt-5 text-sm text-red-700 dark:text-red-300">{error}</p>}
      {copied && <p role="status" className="mt-5 text-sm text-emerald-700 dark:text-emerald-300">{copied === 'token' ? 'Access token copied to clipboard.' : 'Inspector setup copied to clipboard.'}</p>}
      <div className="flex items-center gap-2 pt-6 text-xs text-gray-500 dark:text-gray-400">
        <Clipboard aria-hidden="true" className="h-4 w-4" /> Tokens are requested only when you copy them and are never saved by this page.
      </div>
    </div>
  )
}