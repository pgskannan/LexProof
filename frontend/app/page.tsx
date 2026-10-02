import {
  Activity, Anchor, ArrowRight, BarChart3, CheckCircle2, FileSearch, Fingerprint, Lock, MessageSquareQuote,
  ScanText, ShieldCheck, Share2, UserCheck, Users,
} from "lucide-react"
import { SiteFooter } from "../components/marketing/SiteFooter"
import { SiteHeader } from "../components/marketing/SiteHeader"

const GUARANTEES = [
  { icon: Fingerprint, title: "Proof of process", body: "AI findings, the human decision, the published version and its fingerprint are sealed together and timestamped on chain." },
  { icon: ShieldCheck, title: "Verify without trusting us", body: "Anyone's browser recomputes the fingerprint and reads the public chain directly. No login, no LexProof backend." },
  { icon: UserCheck, title: "Enforced, audited approval", body: "Nothing changes until a different person approves, admins included. Overrides need a written reason and are logged." },
  { icon: Lock, title: "Privacy-preserving anchoring", body: "Only 32-byte fingerprints go on chain. Never contract text, never personal data." },
]

const CAPABILITIES = [
  { icon: FileSearch, title: "AI contract review", body: "Risk and compliance scoring, plain-English briefs and clause-level findings with recommended fixes." },
  { icon: Users, title: "Human-approved redlines", body: "AI proposes, people decide. Separation of duties and a full decision history on every change." },
  { icon: Anchor, title: "Legal Passport", body: "One record per contract: risk, findings, decisions, evidence and the on-chain anchor. Exports as an evidence pack; verifies by QR." },
  { icon: Activity, title: "Continuous proof monitoring", body: "A Chainlink CRE workflow re-checks stored evidence against the chain on a schedule and flags any mismatch." },
  { icon: MessageSquareQuote, title: "Ask Lexi", body: "Portfolio questions answered only from verified findings, with a citation for every claim." },
  { icon: Share2, title: "Counterparty portal", body: "Share a review through a secure link. Counterparties read and respond without an account." },
  { icon: BarChart3, title: "Board-ready reporting", body: "Portfolio KPIs, a risk heatmap, top risks and proof coverage, printable in one click." },
  { icon: ScanText, title: "Scanned contracts", body: "OCR for images and scanned PDFs, with personal data flagged on upload." },
]

const STEPS = ["Upload a contract", "AI finds the risks", "A person approves", "Version published", "Fingerprint sealed", "Anchored on chain", "Anyone verifies"]

const AUDIENCES = [
  { title: "Procurement & source-to-pay", body: "Supplier contracts with provable approvals, ready when an audit or a dispute arrives." },
  { title: "Legal operations & GCs", body: "Redlines approved under separation of duties, with a decision trail that holds up." },
  { title: "Audit & compliance", body: "Evidence your auditors can check themselves, with read-only access." },
]

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <SiteHeader />
      <main>
        {/* Hero */}
        <section className="border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white dark:border-slate-800 dark:from-slate-900 dark:to-slate-950">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[1.15fr_1fr] lg:py-24">
            <div>
              <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-300">
                Verifiable legal intelligence
              </p>
              <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
                AI finds the risk.<br /><span className="text-blue-600 dark:text-blue-400">LexProof proves what happened.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600 dark:text-slate-300">
                AI contract review with enforced human approval, sealed into a tamper-evident Legal Passport that auditors, regulators and counterparties can verify for themselves.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <a href="/request-trial" className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-700">
                  Request a trial <ArrowRight className="h-4 w-4" aria-hidden />
                </a>
                <a href="/public-verify/tamper" className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800">
                  Try the live Tamper Test
                </a>
              </div>
              <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">Prefer a guided tour? <a href="/request-demo" className="font-semibold text-blue-600 hover:underline dark:text-blue-400">Book a live demo</a>. No account needed to verify a proof.</p>
            </div>

            {/* Example Legal Passport card */}
            <div aria-label="Example Legal Passport" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Example Legal Passport</p>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> Verified
                </span>
              </div>
              <p className="mt-3 text-lg font-semibold">Supplier NDA · Version 1</p>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Risk score</p>
                  <p className="mt-1 text-2xl font-bold">18<span className="text-sm font-medium text-slate-500"> / 100 · Low</span></p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
                  <p className="text-xs text-slate-500 dark:text-slate-400">Compliance</p>
                  <p className="mt-1 text-2xl font-bold">92<span className="text-sm font-medium text-slate-500"> / 100</span></p>
                </div>
              </div>
              <ol className="mt-5 space-y-2.5 text-sm">
                {["AI analysis", "Findings reviewed by a person", "Version published", "Fingerprint sealed (SHA-256)", "Anchored on Ethereum (Sepolia)"].map((step) => (
                  <li key={step} className="flex items-center gap-2.5">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              <p className="mt-5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">Illustrative example. Load a real anchored passport in the Tamper Test.</p>
            </div>
          </div>
        </section>

        {/* Guarantees */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">Why LexProof</p>
          <h2 className="mt-2 max-w-2xl text-3xl font-bold tracking-tight">Audit logs live inside a vendor&apos;s database. LexProof&apos;s evidence can be checked outside it.</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {GUARANTEES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-2xl border border-slate-200 p-6 dark:border-slate-800">
                <Icon className="h-6 w-6 text-blue-600 dark:text-blue-400" aria-hidden />
                <h3 className="mt-4 text-lg font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Capabilities */}
        <section id="capabilities" className="scroll-mt-20 border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">Capabilities</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight">One evidence system, from first read to board report</h2>
            <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {CAPABILITIES.map(({ icon: Icon, title, body }) => (
                <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-950">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400"><Icon className="h-5 w-5" aria-hidden /></span>
                  <h3 className="mt-4 text-lg font-semibold">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6">
          <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">How it works</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">Every review becomes a record anyone can check</h2>
          <ol className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
            {STEPS.map((step, index) => (
              <li key={step} className={`rounded-xl border p-4 ${index === STEPS.length - 1 ? "border-blue-600 bg-blue-600 text-white" : "border-slate-200 dark:border-slate-800"}`}>
                <span className={`text-xs font-semibold ${index === STEPS.length - 1 ? "text-blue-100" : "text-blue-600 dark:text-blue-400"}`}>Step {index + 1}</span>
                <p className="mt-1 text-sm font-semibold leading-snug">{step}</p>
              </li>
            ))}
          </ol>
          <p className="mt-8 text-lg text-slate-700 dark:text-slate-300">LexProof&apos;s servers produce the record. <strong className="text-slate-900 dark:text-white">They are not needed to check it.</strong></p>
        </section>

        {/* Who */}
        <section id="who" className="scroll-mt-20 border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <p className="text-sm font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">Who it&apos;s for</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight">Built where contracts meet audit</h2>
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {AUDIENCES.map(({ title, body }) => (
                <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-950">
                  <h3 className="text-lg font-semibold">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="bg-slate-900 dark:bg-black">
          <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-4 py-14 sm:px-6 md:flex-row md:items-center">
            <div>
              <h2 className="text-2xl font-bold text-white">Run a pilot on your own supplier contracts</h2>
              <p className="mt-2 text-slate-300">We&apos;re inviting a small number of legal and procurement teams as design partners.</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <a href="/request-trial" className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-400">
                Request a trial <ArrowRight className="h-4 w-4" aria-hidden />
              </a>
              <a href="/request-demo" className="rounded-lg border border-slate-600 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800">Book a demo</a>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  )
}
