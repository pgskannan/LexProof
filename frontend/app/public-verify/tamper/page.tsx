'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, FileJson, Loader2, RotateCcw, ShieldCheck, Upload, XCircle, Zap } from 'lucide-react'
import {
  PASSPORT_COMPONENTS,
  PASSPORT_REGISTRY_ADDRESS,
  computePassportRoot,
  diffIndexes,
  flipHexDigit,
  parseProofBundle,
  readOnChainPassportRoot,
  type ComponentHashes,
  type OnChainRoot,
  type PassportBundle,
  type PassportComponent,
} from '../../../lib/passportTamper'
import { LegalDisclaimer } from '../../../components/LegalDisclaimer'

const LABELS: Record<PassportComponent, { title: string; what: string; edit: string }> = {
  document_hash: {
    title: 'Contract text',
    what: 'Fingerprint of the contract exactly as it was analysed.',
    edit: 'Someone changes a word in the contract',
  },
  policy_hash: {
    title: 'Review policy',
    what: 'The playbook version the contract was checked against.',
    edit: 'Someone swaps in a softer policy',
  },
  analysis_hash: {
    title: 'AI analysis',
    what: 'The AI findings and risk scores.',
    edit: 'Someone lowers a risk score',
  },
  evidence_hash: {
    title: 'Evidence and redlines',
    what: 'The evidence items behind the review: clauses, findings, redlines.',
    edit: 'Someone edits an approved redline',
  },
}

// Middle of the hash so the changed character is easy to spot on screen.
const TAMPER_INDEX = 31
const DEMO_BUNDLE_URL = '/demo/proof-package.json'

function Hash({ value, changed }: { value: string; changed: number[] }) {
  return (
    <code className="block break-all font-mono text-xs leading-relaxed text-gray-700">
      {value.split('').map((c, i) =>
        changed.includes(i) ? (
          <mark key={i} className="rounded bg-red-600 px-0.5 font-bold text-white">
            {c}
          </mark>
        ) : (
          <span key={i}>{c}</span>
        ),
      )}
    </code>
  )
}

export default function TamperTestPage() {
  const [bundle, setBundle] = useState<PassportBundle | null>(null)
  const [current, setCurrent] = useState<ComponentHashes | null>(null)
  const [originalRoot, setOriginalRoot] = useState<string | null>(null)
  const [currentRoot, setCurrentRoot] = useState<string | null>(null)
  const [chain, setChain] = useState<OnChainRoot | null>(null)
  const [chainLoading, setChainLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async (raw: unknown) => {
    setLoadError(null)
    setCurrentRoot(null)
    try {
      const parsed = parseProofBundle(raw)
      setBundle(parsed)
      setCurrent({ ...parsed.components })
      setOriginalRoot(await computePassportRoot(parsed.components))
      setChain(null)
      setChainLoading(true)
      setChain(await readOnChainPassportRoot(parsed.passportId))
    } catch (err) {
      setBundle(null)
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setChainLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!current) return
    let alive = true
    computePassportRoot(current).then((r) => alive && setCurrentRoot(r))
    return () => {
      alive = false
    }
  }, [current])

  const loadDemo = async () => {
    try {
      const res = await fetch(DEMO_BUNDLE_URL, { cache: 'no-store' })
      if (!res.ok) throw new Error('No demo passport is published on this deployment yet. Upload a proof-package.json instead.')
      await load(await res.json())
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    }
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    try {
      await load(JSON.parse(await file.text()))
    } catch {
      setLoadError('That file is not valid JSON. Load the proof-package.json from a LexProof verification bundle.')
    }
  }

  const tampered = useMemo(
    () => (bundle && current ? PASSPORT_COMPONENTS.filter((k) => current[k] !== bundle.components[k]) : []),
    [bundle, current],
  )

  // What the recomputed root is compared against: the Ethereum anchor when there is one.
  const reference = chain?.status === 'found' ? chain.root : bundle?.statedRoot ?? null
  const referenceLabel = chain?.status === 'found' ? 'Root anchored on Ethereum Sepolia' : 'Root stated in the bundle'
  const verdict: 'match' | 'mismatch' | null = reference && currentRoot ? (reference === currentRoot ? 'match' : 'mismatch') : null
  const bundleInconsistent = !!(bundle?.statedRoot && originalRoot && bundle.statedRoot !== originalRoot)

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 px-4 py-12 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="text-center">
          <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-red-600">
            <Zap className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-4xl font-bold text-gray-900">Tamper Test</h1>
          <p className="mx-auto mt-3 max-w-2xl text-lg text-gray-600">
            Change a single character of a Legal Passport and watch the proof break. Your browser recomputes the
            fingerprint and reads Ethereum Sepolia directly. LexProof&apos;s servers are not involved.
          </p>
        </header>

        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">1 · Load a Legal Passport</h2>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={loadDemo}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700"
            >
              <ShieldCheck className="h-5 w-5" /> Load the demo passport
            </button>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 px-5 py-3 font-semibold text-gray-700 hover:bg-gray-50">
              <Upload className="h-5 w-5" /> Upload proof-package.json
              <input type="file" accept="application/json,.json" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
            </label>
          </div>
          <p className="mt-3 text-sm text-gray-500">
            The proof package is inside the verification bundle you can download from any Legal Passport. This test uses
            only its passport ID and SHA-256 fingerprints, and an uploaded file never leaves your browser.
          </p>
          {loadError && (
            <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {loadError}
            </p>
          )}
        </section>

        {bundle && current && (
          <>
            <section className="rounded-xl border border-gray-200 bg-white p-6 shadow">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">2 · The anchored passport</h2>
                  <p className="mt-2 text-lg font-semibold text-gray-900">
                    {bundle.contractName || 'Legal Passport'}
                    {bundle.contractVersion != null && <span className="ml-2 text-sm font-normal text-gray-500">v{bundle.contractVersion}</span>}
                  </p>
                  <p className="font-mono text-xs text-gray-500">Passport {bundle.passportId}</p>
                </div>
                <a
                  href={`https://sepolia.etherscan.io/address/${PASSPORT_REGISTRY_ADDRESS}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                >
                  Passport registry on Etherscan <ExternalLink className="h-4 w-4" />
                </a>
              </div>
              <div className="mt-4 rounded-lg bg-gray-50 p-4 text-sm">
                {chainLoading && (
                  <span className="inline-flex items-center gap-2 text-gray-600">
                    <Loader2 className="h-4 w-4 animate-spin" /> Reading the LexProofPassportRegistry contract on Ethereum Sepolia…
                  </span>
                )}
                {chain?.status === 'found' && (
                  <p className="text-gray-700">
                    <strong className="text-green-700">Anchor found on Ethereum Sepolia (testnet)</strong>, written{' '}
                    {chain.anchoredAt.toLocaleString()} by <span className="font-mono text-xs">{chain.anchoredBy}</span>.
                  </p>
                )}
                {chain?.status === 'not_anchored' && (
                  <p className="text-amber-700">
                    This passport has not been anchored on Ethereum yet, so the test compares against the root stated in
                    the bundle instead.
                  </p>
                )}
                {chain?.status === 'error' && (
                  <p className="text-amber-700">
                    Could not reach Ethereum Sepolia from your browser ({chain.message}). Comparing against the root stated
                    in the bundle instead.
                  </p>
                )}
                {bundleInconsistent && (
                  <p className="mt-2 text-red-700">
                    Warning: this bundle&apos;s stated root does not match its own component fingerprints.
                  </p>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-gray-200 bg-white p-6 shadow">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">3 · Tamper with it</h2>
                {tampered.length > 0 && (
                  <button
                    onClick={() => setCurrent({ ...bundle.components })}
                    className="inline-flex items-center gap-1 text-sm font-semibold text-blue-600 hover:underline"
                  >
                    <RotateCcw className="h-4 w-4" /> Restore everything
                  </button>
                )}
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {PASSPORT_COMPONENTS.map((key) => {
                  const altered = current[key] !== bundle.components[key]
                  return (
                    <div
                      key={key}
                      data-testid={`component-${key}`}
                      className={`rounded-lg border-2 p-4 ${altered ? 'border-red-400 bg-red-50' : 'border-gray-200'}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="font-semibold text-gray-900">{LABELS[key].title}</h3>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${
                            altered ? 'bg-red-600 text-white' : 'bg-green-100 text-green-800'
                          }`}
                        >
                          {altered ? 'Altered' : 'Original'}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500">{LABELS[key].what}</p>
                      <div className="mt-3">
                        <Hash value={current[key]} changed={diffIndexes(bundle.components[key], current[key])} />
                      </div>
                      <button
                        onClick={() =>
                          setCurrent({
                            ...current,
                            [key]: altered ? bundle.components[key] : flipHexDigit(bundle.components[key], TAMPER_INDEX),
                          })
                        }
                        className={`mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold ${
                          altered ? 'bg-white text-blue-700 ring-1 ring-blue-300 hover:bg-blue-50' : 'bg-red-600 text-white hover:bg-red-700'
                        }`}
                      >
                        {altered ? (
                          <>
                            <RotateCcw className="h-4 w-4" /> Restore original
                          </>
                        ) : (
                          <>
                            <Zap className="h-4 w-4" /> {LABELS[key].edit}
                          </>
                        )}
                      </button>
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 text-xs text-gray-500">
                Any edit to the underlying data produces a completely different SHA-256 fingerprint. To keep it visible,
                this test changes one character of the fingerprint.
              </p>
            </section>

            <section
              data-testid="tamper-verdict"
              className={`rounded-xl border-4 p-8 shadow-lg ${
                verdict === 'match' ? 'border-green-500 bg-green-50' : verdict === 'mismatch' ? 'border-red-500 bg-red-50' : 'border-gray-200 bg-white'
              }`}
            >
              <div className="text-center">
                {verdict === 'match' && (
                  <>
                    <CheckCircle2 className="mx-auto h-16 w-16 text-green-600" />
                    <p className="mt-2 text-4xl font-bold text-green-700">VERIFIED</p>
                    <p className="mt-2 text-gray-700">The recomputed passport root matches. This is the passport that was anchored.</p>
                  </>
                )}
                {verdict === 'mismatch' && (
                  <>
                    <XCircle className="mx-auto h-16 w-16 text-red-600" />
                    <p className="mt-2 text-4xl font-bold text-red-700">ROOT MISMATCH</p>
                    <p className="mt-2 text-gray-700">
                      {tampered.length > 0
                        ? `${tampered.map((k) => LABELS[k].title).join(', ')} changed. This is not the passport that was anchored, and nobody can hide that.`
                        : "Nothing was edited here, but this bundle's fingerprints do not produce the anchored root. This is not the passport that was anchored."}
                    </p>
                  </>
                )}
                {!verdict && (
                  <p className="inline-flex items-center gap-2 text-gray-600">
                    <AlertTriangle className="h-5 w-5" /> Waiting for a reference root…
                  </p>
                )}
              </div>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Recomputed in your browser</p>
                  <div className="mt-1 rounded-lg bg-white p-3">
                    {currentRoot && <Hash value={currentRoot} changed={reference ? diffIndexes(reference, currentRoot) : []} />}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{referenceLabel}</p>
                  <div className="mt-1 rounded-lg bg-white p-3">{reference && <Hash value={reference} changed={[]} />}</div>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-600 shadow">
              <h2 className="mb-2 flex items-center gap-2 font-semibold text-gray-900">
                <FileJson className="h-4 w-4" /> How this works
              </h2>
              <p>
                A Legal Passport root is SHA-256 over four fingerprints: the contract text, the review policy, the AI
                analysis and the evidence. LexProof writes that root to the LexProofPassportRegistry contract on Ethereum
                Sepolia, and the contract never lets it be overwritten. This page recomputes the root in your browser
                and reads the anchored root through a public RPC endpoint, so the result does not depend on trusting
                LexProof.
              </p>
            </section>
          </>
        )}

        {bundle && verdict && (
          // Always-visible result, so the verdict flips on screen the moment a card is tampered with.
          <div
            data-testid="tamper-verdict-bar"
            className={`sticky bottom-4 z-10 mx-auto flex max-w-3xl items-center justify-center gap-3 rounded-full px-6 py-3 text-white shadow-2xl ${
              verdict === 'match' ? 'bg-green-600' : 'bg-red-600'
            }`}
          >
            {verdict === 'match' ? <CheckCircle2 className="h-6 w-6" /> : <XCircle className="h-6 w-6" />}
            <span className="text-lg font-bold">{verdict === 'match' ? 'VERIFIED' : 'ROOT MISMATCH'}</span>
            <span className="hidden text-sm opacity-90 sm:inline">
              {verdict === 'match'
                ? 'matches the root anchored on Ethereum'
                : tampered.length > 0
                  ? `${tampered.map((k) => LABELS[k].title).join(', ')} changed`
                  : 'does not match the anchored root'}
            </span>
          </div>
        )}

        <LegalDisclaimer variant="verifier" className="mx-auto mt-4 max-w-3xl justify-center text-center" />
      </div>
    </div>
  )
}
