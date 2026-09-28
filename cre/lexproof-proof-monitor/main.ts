/**
 * LexProof Proof Monitor: a Chainlink CRE workflow.
 *
 * LexProof turns AI contract findings into evidence records whose SHA-256
 * fingerprints are anchored on Ethereum Sepolia. This workflow is an
 * independent, decentralized auditor of that claim. On a schedule it:
 *
 *   1. asks LexProof's PUBLIC verification API (no login) for each monitored
 *      evidence item's hash, recomputed from LexProof's current stored record.
 *      Every node fetches it and the DON must agree (identical consensus);
 *   2. reads the anchored hash for that item straight from the
 *      LexProofRegistry contract on Sepolia (CRE EVM client, finalized block),
 *      not from LexProof's own chain read;
 *   3. reads each monitored Legal Passport's root from LexProofPassportRegistry
 *      and compares it with the root published in that passport's proof
 *      package;
 *   4. returns a verdict per item: VERIFIED, TAMPERED (record changed after
 *      anchoring), NOT_ANCHORED, EVIDENCE_NOT_FOUND, ROOT_VERIFIED,
 *      ROOT_MISMATCH or ROOT_NOT_ANCHORED, plus an overall `alert` flag.
 *
 * Nothing here writes to chain or needs a secret: it composes one external
 * API with two smart contracts, which is the CRE orchestration pattern the
 * "automated risk monitoring" use case describes.
 */
import {
  CronCapability,
  EVMClient,
  HTTPClient,
  LAST_FINALIZED_BLOCK_NUMBER,
  Runner,
  bytesToHex,
  consensusIdenticalAggregation,
  encodeCallMsg,
  getNetwork,
  handler,
  type NodeRuntime,
  type Runtime,
} from '@chainlink/cre-sdk'
import { decodeFunctionResult, encodeFunctionData, keccak256, toBytes, zeroAddress, type Hex } from 'viem'
import { LexProofPassportRegistry, LexProofRegistry } from '../contracts/abi'

type MonitoredPassport = {
  label: string
  passportId: string
  /** metadata.passport_hash as published in the passport's proof package. */
  expectedRoot: string
}

type Config = {
  schedule: string
  lexproofApiUrl: string
  chainName: string
  evidenceRegistry: string
  passportRegistry: string
  evidenceIds: string[]
  passports: MonitoredPassport[]
}

type OffchainEvidence = {
  evidenceId: string
  apiStatus: string
  computedHash: string
}

type ItemVerdict = {
  kind: 'evidence' | 'passport-root'
  id: string
  label: string
  verdict: string
  offchainHash: string
  onchainHash: string
  anchoredAt: number
}

type MonitorReport = {
  network: string
  checked: number
  verified: number
  problems: number
  alert: boolean
  items: ItemVerdict[]
}

const ZERO_HASH = '0'.repeat(64)

const normalizeHash = (value: string | null | undefined): string =>
  (value ?? '').toLowerCase().replace(/^0x/, '')

// ---------------------------------------------------------------------------
// Off-chain: LexProof public verification API, fetched by every node.
// ---------------------------------------------------------------------------

const fetchOffchainEvidence = (nodeRuntime: NodeRuntime<Config>): OffchainEvidence[] => {
  const http = new HTTPClient()
  const base = nodeRuntime.config.lexproofApiUrl.replace(/\/$/, '')
  return nodeRuntime.config.evidenceIds.map((evidenceId) => {
    const response = http
      .sendRequest(nodeRuntime, {
        url: `${base}/api/verify/${encodeURIComponent(evidenceId)}`,
        method: 'GET' as const,
      })
      .result()
    if (response.statusCode !== 200) {
      return { evidenceId, apiStatus: `HTTP_${response.statusCode}`, computedHash: '' }
    }
    const body = JSON.parse(new TextDecoder().decode(response.body)) as {
      status?: string
      computed_hash?: string | null
    }
    return {
      evidenceId,
      apiStatus: body.status ?? 'UNKNOWN',
      computedHash: normalizeHash(body.computed_hash),
    }
  })
}

// ---------------------------------------------------------------------------
// On-chain: direct Sepolia reads through the CRE EVM capability.
// ---------------------------------------------------------------------------

const readAnchor = (
  runtime: Runtime<Config>,
  evm: EVMClient,
  registry: string,
  abi: typeof LexProofRegistry | typeof LexProofPassportRegistry,
  functionName: 'evidenceAnchors' | 'passportRoots',
  key: Hex,
): { hash: string; timestamp: number } => {
  const data = encodeFunctionData({ abi, functionName, args: [key] } as never)
  const reply = evm
    .callContract(runtime, {
      call: encodeCallMsg({ from: zeroAddress, to: registry as Hex, data }),
      blockNumber: LAST_FINALIZED_BLOCK_NUMBER,
    })
    .result()
  const [hash, timestamp] = decodeFunctionResult({
    abi,
    functionName,
    data: bytesToHex(reply.data),
  } as never) as readonly [Hex, bigint, Hex]
  return { hash: normalizeHash(hash), timestamp: Number(timestamp) }
}

const evidenceVerdict = (offchain: OffchainEvidence, onchainHash: string): string => {
  if (onchainHash === ZERO_HASH) return 'NOT_ANCHORED'
  if (!offchain.computedHash) return 'EVIDENCE_NOT_FOUND'
  return offchain.computedHash === onchainHash ? 'VERIFIED' : 'TAMPERED'
}

const rootVerdict = (expectedRoot: string, onchainRoot: string): string => {
  if (onchainRoot === ZERO_HASH) return 'ROOT_NOT_ANCHORED'
  return normalizeHash(expectedRoot) === onchainRoot ? 'ROOT_VERIFIED' : 'ROOT_MISMATCH'
}

const HEALTHY = new Set(['VERIFIED', 'ROOT_VERIFIED'])

// ---------------------------------------------------------------------------
// Workflow
// ---------------------------------------------------------------------------

const onCronTrigger = (runtime: Runtime<Config>): MonitorReport => {
  const config = runtime.config
  const network = getNetwork({ chainFamily: 'evm', chainSelectorName: config.chainName })
  if (!network) throw new Error(`Unknown chain name: ${config.chainName}`)
  const evm = new EVMClient(network.chainSelector.selector)

  const offchain = runtime
    .runInNodeMode(fetchOffchainEvidence, consensusIdenticalAggregation<OffchainEvidence[]>())()
    .result()
  runtime.log(`Fetched ${offchain.length} evidence fingerprint(s) from LexProof with DON consensus`)

  const items: ItemVerdict[] = []

  for (const item of offchain) {
    const anchor = readAnchor(
      runtime,
      evm,
      config.evidenceRegistry,
      LexProofRegistry,
      'evidenceAnchors',
      keccak256(toBytes(item.evidenceId)),
    )
    const verdict = evidenceVerdict(item, anchor.hash)
    items.push({
      kind: 'evidence',
      id: item.evidenceId,
      label: `evidence (LexProof API: ${item.apiStatus})`,
      verdict,
      offchainHash: item.computedHash,
      onchainHash: anchor.hash === ZERO_HASH ? '' : anchor.hash,
      anchoredAt: anchor.timestamp,
    })
    runtime.log(`[${verdict}] evidence ${item.evidenceId}`)
  }

  for (const passport of config.passports) {
    const anchor = readAnchor(
      runtime,
      evm,
      config.passportRegistry,
      LexProofPassportRegistry,
      'passportRoots',
      keccak256(toBytes(passport.passportId)),
    )
    const verdict = rootVerdict(passport.expectedRoot, anchor.hash)
    items.push({
      kind: 'passport-root',
      id: passport.passportId,
      label: passport.label,
      verdict,
      offchainHash: normalizeHash(passport.expectedRoot),
      onchainHash: anchor.hash === ZERO_HASH ? '' : anchor.hash,
      anchoredAt: anchor.timestamp,
    })
    runtime.log(`[${verdict}] passport root ${passport.passportId} (${passport.label})`)
  }

  const verified = items.filter((item) => HEALTHY.has(item.verdict)).length
  const problems = items.filter((item) => item.verdict === 'TAMPERED' || item.verdict === 'ROOT_MISMATCH').length
  const report: MonitorReport = {
    network: config.chainName,
    checked: items.length,
    verified,
    problems,
    alert: problems > 0,
    items,
  }
  runtime.log(
    report.alert
      ? `ALERT: ${problems} item(s) no longer match their on-chain anchor`
      : `All ${verified} anchored item(s) match Sepolia; ${items.length - verified} not anchored/not found`,
  )
  return report
}

const initWorkflow = (config: Config) => {
  const cron = new CronCapability()
  return [handler(cron.trigger({ schedule: config.schedule }), onCronTrigger)]
}

export async function main() {
  const runner = await Runner.newRunner<Config>()
  await runner.run(initWorkflow)
}
