/**
 * Browser-side Legal Passport root recomputation for the public Tamper Test.
 *
 * Mirrors backend `compute_passport_hash` (domains/passport/utils/hashing.py):
 *   root = SHA-256( json.dumps({document_hash, policy_hash, analysis_hash,
 *                               evidence_hash, passport_hash_algorithm: "sha256"},
 *                              sort_keys=True) )
 * Python's default json.dumps separators are ", " and ": ", reproduced here
 * byte-for-byte so a root computed in the browser equals the one LexProof
 * anchored on the LexProofPassportRegistry contract.
 *
 * On-chain lookup key mirrors `compute_passport_key`: keccak256(UTF-8(passport_id)).
 */

export const PASSPORT_COMPONENTS = ['document_hash', 'policy_hash', 'analysis_hash', 'evidence_hash'] as const
export type PassportComponent = (typeof PASSPORT_COMPONENTS)[number]
export type ComponentHashes = Record<PassportComponent, string>

export const PASSPORT_REGISTRY_ADDRESS =
  process.env.NEXT_PUBLIC_LEXPROOF_PASSPORT_REGISTRY_ADDRESS || '0x21Ddd03549c2d4fb75336b616f18c34D4a9BFDE6'

export const SEPOLIA_CHAIN_ID = 11155111

export const PASSPORT_REGISTRY_ABI = [
  'function getPassportRoot(bytes32 passportKey) view returns (bytes32 passportRoot, uint256 timestamp, address anchoredBy)',
]

const HEX64 = /^[0-9a-f]{64}$/

export function normalizeHash(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const v = value.trim().toLowerCase().replace(/^0x/, '')
  return HEX64.test(v) ? v : null
}

/** Byte-identical to Python json.dumps(data, sort_keys=True) for this flat string dict. */
export function canonicalPassportJson(components: ComponentHashes): string {
  const data: Record<string, string> = { ...components, passport_hash_algorithm: 'sha256' }
  return '{' + Object.keys(data).sort().map((k) => `${JSON.stringify(k)}: ${JSON.stringify(data[k])}`).join(', ') + '}'
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

export async function computePassportRoot(components: ComponentHashes): Promise<string> {
  return sha256Hex(canonicalPassportJson(components))
}

/** Change exactly one hex digit (default: the last one) — the smallest possible edit. */
export function flipHexDigit(hash: string, index = hash.length - 1): string {
  const i = Math.max(0, Math.min(index, hash.length - 1))
  const c = hash[i]
  const next = c === 'f' ? '0' : (parseInt(c, 16) + 1).toString(16)
  return hash.slice(0, i) + next + hash.slice(i + 1)
}

/** Indexes where two equal-length hashes differ (used to highlight the edit). */
export function diffIndexes(a: string, b: string): number[] {
  const out: number[] = []
  for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) out.push(i)
  return out
}

export interface PassportBundle {
  passportId: string
  contractName: string | null
  contractVersion: string | number | null
  statedRoot: string | null
  components: ComponentHashes
}

/** Parse a LexProof proof-package.json (bundle_version 1) into what the Tamper Test needs. */
export function parseProofBundle(raw: unknown): PassportBundle {
  const obj = (raw ?? {}) as Record<string, any>
  const hashes = (obj.hashes ?? {}) as Record<string, unknown>
  const contract = (obj.contract ?? {}) as Record<string, unknown>
  const passportId = typeof contract.passport_id === 'string' ? contract.passport_id.trim() : ''
  if (!passportId) throw new Error('This file has no passport ID. Load the proof-package.json from a LexProof verification bundle.')
  const components = {} as ComponentHashes
  for (const key of PASSPORT_COMPONENTS) {
    const h = normalizeHash(hashes[key])
    if (!h) throw new Error(`This bundle is missing a valid ${key.replace('_', ' ')}.`)
    components[key] = h
  }
  return {
    passportId,
    contractName: typeof contract.name === 'string' ? contract.name : null,
    contractVersion: (contract.contract_version as string | number | undefined) ?? null,
    statedRoot: normalizeHash(hashes.passport_hash),
    components,
  }
}

export type OnChainRoot =
  | { status: 'found'; root: string; anchoredAt: Date; anchoredBy: string }
  | { status: 'not_anchored' }
  | { status: 'error'; message: string }

export async function passportKeyFor(passportId: string): Promise<string> {
  const { ethers } = await import('ethers')
  return ethers.id(passportId)
}

/** Read the anchored root straight from Ethereum Sepolia via a public RPC — never through LexProof. */
export async function readOnChainPassportRoot(
  passportId: string,
  options?: { rpcUrl?: string; contractAddress?: string },
): Promise<OnChainRoot> {
  try {
    const { ethers } = await import('ethers')
    const { SEPOLIA_RPC_URL } = await import('./independentChainVerify')
    // staticNetwork: fail fast instead of retrying network detection forever if the RPC is unreachable.
    const provider = new ethers.JsonRpcProvider(options?.rpcUrl || SEPOLIA_RPC_URL, SEPOLIA_CHAIN_ID, { staticNetwork: true })
    const registry = new ethers.Contract(options?.contractAddress || PASSPORT_REGISTRY_ADDRESS, PASSPORT_REGISTRY_ABI, provider)
    const [root, timestamp, anchoredBy] = await registry.getPassportRoot(ethers.id(passportId))
    return {
      status: 'found',
      root: String(root).toLowerCase().replace(/^0x/, ''),
      anchoredAt: new Date(Number(timestamp) * 1000),
      anchoredBy: String(anchoredBy),
    }
  } catch (err) {
    const reason =
      (err as { shortMessage?: string })?.shortMessage ||
      (err as { reason?: string })?.reason ||
      (err instanceof Error ? err.message : String(err))
    if (String(reason).toLowerCase().includes('does not exist')) return { status: 'not_anchored' }
    return { status: 'error', message: String(reason) }
  }
}
