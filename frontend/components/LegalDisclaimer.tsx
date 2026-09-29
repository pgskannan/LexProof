import { Scale } from "lucide-react"

type Variant = "app" | "verifier" | "counterparty"

const TEXT: Record<Variant, string> = {
  app:
    "LexProof provides AI-assisted contract analysis for information only. It is not legal advice and does not create a lawyer–client relationship. Have a qualified lawyer review important decisions.",
  verifier:
    "Verification confirms that evidence matches the fingerprint anchored on Ethereum Sepolia (testnet). It does not assess the legal merits of any contract and is not legal advice.",
  counterparty:
    "This review was prepared with AI assistance and approved by people at the sending organization. It is not legal advice to you; consult your own lawyer before relying on it.",
}

/** Visible "not legal advice" notice (hackathon review item). Prints with the page. */
export function LegalDisclaimer({ variant = "app", className = "" }: { variant?: Variant; className?: string }) {
  return (
    <p
      role="note"
      data-testid="legal-disclaimer"
      className={`flex items-start gap-2 text-xs leading-relaxed text-gray-500 dark:text-gray-400 ${className}`}
    >
      <Scale aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        <strong className="font-semibold text-gray-600 dark:text-gray-300">Not legal advice.</strong> {TEXT[variant]}
      </span>
    </p>
  )
}
