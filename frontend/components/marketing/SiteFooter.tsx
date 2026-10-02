import { LegalDisclaimer } from "../LegalDisclaimer"

export function SiteFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-10 sm:px-6">
        <div className="flex flex-col justify-between gap-4 text-sm text-slate-600 sm:flex-row dark:text-slate-400">
          <p>© 2026 NexaEdge LLC · LexProof</p>
          <div className="flex flex-wrap gap-5">
            <a href="/public-verify/tamper" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">Tamper Test</a>
            <a href="/public-verify" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">Verify evidence</a>
            <a href="https://github.com/pgskannan/LexProof" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">Source code</a>
            <a href="/request-trial" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">Request a trial</a>
            <a href="/login" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">Sign in</a>
          </div>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-500">Anchors are currently written to the Ethereum Sepolia test network. Only 32-byte fingerprints go on chain, never contract text or personal data.</p>
        <LegalDisclaimer variant="app" />
      </div>
    </footer>
  )
}
