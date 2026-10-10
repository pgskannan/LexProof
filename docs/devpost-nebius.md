# Devpost draft: LexProof × Nebius × NVIDIA

Submit by **Tue 28 Oct 2026**. The hard deadline is Fri 30 Oct, 10:00 AM PT. Track: **Best Apps and Agents**. Judging runs 1–15 Dec, so keep the preview and `lexproof-api-nebius` healthy until then.

Never put the judge password in this file or the repo. It goes only in Devpost's private "testing instructions" field.

---

## Project name
LexProof: verifiable contract AI on open models

## Tagline (one line)
NVIDIA Nemotron reviews the contract; LexProof seals which model said what, who approved it, and proves it on Ethereum.

## Track
Best Apps and Agents

## Links
- Live demo (judge URL): https://lexproof-git-feat-nebius-nemotron-pgskannans-projects.vercel.app
- Public proof, no login: https://lexproof-git-feat-nebius-nemotron-pgskannans-projects.vercel.app/public-verify?evidence_id=0a439fb1-5063-4284-a3d7-ac54c5ddfe00
- Video: https://youtu.be/4ztjcuZxPCA
- Code: https://github.com/pgskannan/LexProof (branch `feat/nebius-nemotron`, Apache-2.0)
- API health (shows the active model): https://lexproof-api-nebius-icsvy7jira-uc.a.run.app/health

---

## Inspiration
AI contract review is fast, but it leaves no proof. Months later, an auditor or a counterparty asks which model flagged this clause, whether a person signed off, and whether the record changed since. With a closed, hosted model there's no good answer: the model behind the API changes silently, and the audit log lives inside the vendor's own database. We wanted contract AI whose output can be checked by someone who doesn't trust us, and that needs an open model whose exact identity can be sealed into the record.

## What it does
- Upload a contract. **NVIDIA Nemotron 3 Ultra**, served by **Nebius Token Factory**, returns risk and compliance scores and findings as strict, schema-validated JSON. Each finding includes the exact clause quote, the reasoning, a severity and any regulatory citations.
- A person reviews it. Nothing changes in a contract until a *different* person approves the redline (separation of duties).
- LexProof seals a **Legal Passport**: SHA-256 fingerprints of the document, the review policy, the AI analysis and the evidence. The **exact open-weight model ID** is part of the analysis hash.
- Fingerprints are anchored on **Ethereum Sepolia**. Only 32-byte hashes go on chain, never contract text.
- **Anyone can verify, without a login:** the public verifier recomputes the hash in the browser and reads the anchor directly from the chain. It shows "Analyzed by NVIDIA Nemotron 3 Ultra · Nebius Token Factory" with the model ID. The **Tamper Test** shows that changing a single character breaks the proof.
- **Ask Lexi** answers portfolio questions on **Nemotron 3 Super**, citing evidence for every claim. Findings translation also runs on Super.

## How we built it
- **Nemotron on Token Factory.** An OpenAI-compatible endpoint behind one provider class written in plain `httpx`. There are two tiers:
  - **Analysis:** `nvidia/Nemotron-3-Ultra-550b-a55b`, used for analysis, redlines, payment-obligation extraction and the executive summary.
  - **Fast:** `nvidia/nemotron-3-super-120b-a12b`, used for Q&A and translation.
- **Strict structured output.** `response_format: json_schema` with `strict: true`, plus `jsonschema` validation on our side. If validation fails, we retry once with the validator error, and only then fall back to `json_object`.
- **Reasoning off** (`chat_template_kwargs.enable_thinking=false` and `/no_think`). This cut output tokens 2–7× and removed truncation.
- **Truncation handling.** `finish_reason=length` triggers one retry with double the budget. `reasoning_content` is never parsed as the answer.
- **Provenance.** The model that actually answered goes into the passport hash. An optional Gemini fallback is labelled as such, so the record never claims Nemotron when Gemini answered.
- **Stack:**
  - Next.js on Vercel
  - FastAPI on Google Cloud Run (a separate `lexproof-api-nebius` service)
  - Firestore and Cloud Storage
  - Solidity registries on Ethereum Sepolia
  - a Chainlink CRE workflow that re-checks anchors
- **Testing:** 1,206 backend and 248 frontend tests. The Token Factory client is tested against a mocked transport for schema success, the reasoning-off flags, truncation, repair, 429 retries and key redaction.
- **Before writing app code,** a spike script ran our production prompt through all four Nemotron models on Token Factory and validated every reply against the production schema (`ForNebius/nebius_spike.py`).

## Challenges we ran into
- **Reasoning ate the output budget.** With reasoning on and an 8k token limit, Super and Lightning spent most tokens thinking, and the JSON was cut off mid-string (`finish_reason: length`). One model wrote its "thinking process" into the content field. Turning reasoning off fixed it and made Ultra both faster and better calibrated: it rated a clean NDA LOW instead of MEDIUM.
- **Making provenance honest.** Adding the model ID to the hash had to leave every passport already anchored on Sepolia verifiable. Legacy records hash with an empty model value, exactly as before, and new records hash with the real Nemotron ID.
- **Judges need to see Nemotron live without being able to spend our gas or edit others' data.** We added a judge mode, scoped to the Nebius service only. A judge can upload, analyze, ask and translate on their own contracts (10 analyses per day), and every other write stays blocked.
- **Google sign-in redirects break on preview domains** in Chrome, because of third-party storage partitioning. The judge path uses email login.

## Accomplishments that we're proud of
- On the same high-risk contract, Nemotron 3 Ultra found **12–13 issues where our previous Gemini Flash-Lite setup found 4**, with the same CRITICAL call, in about 16–18 s.
- **Open-model provenance on chain:** a public verifier anyone can open shows which open-weight model produced an analysis, and that claim is covered by the Ethereum anchor.
- We swapped the AI provider across six features with one provider class, kept the full test suite green, and changed nothing on the verification side.

## What we learned
- For evidence-grade output, strict JSON schema plus local validation matters more than raw model size, and open models on Token Factory handle it well.
- Reasoning models need an explicit choice. For extraction against a schema, reasoning off was both faster and more accurate for us.
- A model ID in a hash is only useful if it's the model that actually answered. That's why fallback provenance is recorded per call.

## What's next for LexProof
- Run the benchmark runner against reviewed ground truth across the full sample portfolio, Nemotron vs. the previous provider, and publish the numbers.
- Citation check: verify each regulatory citation against live sources and hash the source snapshot into the evidence.
- Nebius Serverless Endpoints for a dedicated Nemotron deployment, for customers who want a pinned model version.
- Passkey-signed approvals; mainnet or an L2 with a gas-sponsoring relayer.

## Built with
nvidia-nemotron, nebius-token-factory, python, fastapi, httpx, jsonschema, next.js, typescript, google-cloud-run, firestore, vercel, solidity, ethereum-sepolia, chainlink-cre, firebase-auth

---

## Significant updates during the submission period (required field)
LexProof was started on 27 August 2026, after the submission period opened on 26 August. For this hackathon specifically, on branch `feat/nebius-nemotron`:
1. `384df79`: a Nemotron provider on Nebius Token Factory (Ultra for analysis, Super for Q&A and translation). It brings strict JSON schema, reasoning off, truncation and repair retries, the model ID in the passport hash, and provider badges in the app and on the public verifier.
2. `87bab6c`: tests for the provider and for provenance.
3. `b643f81`: a separate Cloud Run service `lexproof-api-nebius`, `/health` reporting the active model, and judge analyze access with daily limits.

## Feedback on Nebius Token Factory and NVIDIA models (required field)

**What worked well**
- The OpenAI-compatible API made Token Factory a drop-in provider: one `httpx` class, with no SDK and no rewrite.
- `GET /v1/models` made it easy to discover which Nemotron models our key could use and to benchmark all four in one script.
- Strict `json_schema` worked reliably on Nemotron 3 Ultra and Super once reasoning was off, which is the key feature for our use case.
- Nemotron 3 Ultra's findings were more thorough than our previous provider's on the same contract, at a cost low enough for a free judge demo.

**What could be better**
- **Reasoning tokens and `max_tokens`.** With reasoning on, the reasoning counted against `max_tokens` and the JSON answer was cut off. A note in the structured-output docs, or a separate reasoning budget, would save others the debugging.
- **Turning reasoning off.** We found the `chat_template_kwargs.enable_thinking=false` / `/no_think` pair by trial. A per-model table of supported reasoning controls would help.
- **Reasoning leaking into content.** One model (`Nemotron-3_5-Lightning`) wrote its reasoning into `content` under `json_object` mode. Always separating it into `reasoning_content` would make parsing safer.
- **Credits.** The promo code arrives by email after a form, and the Builder Program credit after approval. Showing the expected arrival time on the form would reduce guesswork.

---

## Private testing instructions (paste into Devpost's private field; fill in the password)
```
Judge URL: https://lexproof-git-feat-nebius-nemotron-pgskannans-projects.vercel.app
Sign in with EMAIL + PASSWORD (not Google):
  Email:    judge@lexproof.demo
  Password: <JUDGE PASSWORD>
1. Contracts > "Analyze a contract": upload any DOCX/PDF/TXT (2 MB max) or a sample from
   github.com/pgskannan/LexProof/tree/feat/nebius-nemotron/sampleContracts, click Upload and analyze (~15-20 s).
2. Open the Legal Passport: badge "Analyzed by NVIDIA Nemotron 3 Ultra · Nebius Token Factory" + model ID.
3. Ask Lexi a question about your contract (runs on Nemotron 3 Super).
4. Public proof, no login: /public-verify?evidence_id=0a439fb1-5063-4284-a3d7-ac54c5ddfe00
   -> VERIFIED, Nemotron provenance, View Ethereum Proof (Sepolia).
5. Tamper Test: /public-verify/tamper
Limits: 10 analyses/day, 30 Q&A or translations/hour for the judge account. Anchoring is owner-only (spends gas).
If the upload card is missing, wait for "LexProof Demo" to load in the organization picker, or refresh.
API health: https://lexproof-api-nebius-icsvy7jira-uc.a.run.app/health
```

## Gallery images
- `docs/images/nebius-workflow.png`
- `docs/images/nebius-architecture.png`
- Screenshots: the passport with the Nemotron badge, and the public verifier (VERIFIED + Nemotron badge).
