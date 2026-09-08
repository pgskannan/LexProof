You are building "Ask Your Contracts" for LexProof — a grounded natural-language Q&A feature over an organization's own contract portfolio (existing FastAPI + Firestore + Next.js + Firebase Auth stack, now with the multi-tenant org/role system from earlier work). Every answer must be traceable: it can only state things backed by retrieved findings/contracts/evidence, and every factual claim in the answer must carry a citation that links to a real finding/evidence/contract ID a user can click through to. If the retrieved context doesn't support an answer, the feature must say so rather than guessing — this is a hard requirement, not a nice-to-have, given LexProof's whole pitch is "don't take AI claims on faith."

Before writing any code, read:
- `backend/app/lexproof/api/findings.py` and whatever service backs it — the shape of a finding record (category, severity, contract_id, evidence references, the actual triggering contract language).
- `backend/app/lexproof/services/organizations.py` and `backend/app/lexproof/services/roles.py` — how org-scoped authorization works now; this new endpoint must be org-scoped like everything else built earlier today (`get_current_org_member`, never trust client-sent org_id).
- Whichever service currently calls Gemini for contract analysis (search for the Vertex AI / `gemini` usage in `backend/app/lexproof/domains` or `services`) — match its existing client setup, model name, and error-handling conventions rather than creating a second, different way of calling the model.
- `frontend/lib/api.ts` and one existing authenticated page (e.g. `dashboard/ai-analysis/findings/page.tsx`) for the frontend's existing API-calling and auth-header conventions.

## What to build

### 1. Backend: `POST /api/orgs/{org_id}/ask`
Request: `{ question: str }`. Auth: `get_current_org_member` (any of the 5 roles can ask; this is read-only).

Retrieval (no vector DB — the corpus is small, keep this simple and structured):
- Parse the question loosely for contract-name mentions and keyword/category mentions (e.g. "governing law", "indemnification", "liability", "termination") using straightforward string matching against known finding categories and contract names/IDs for this org — do not build an embeddings pipeline for this.
- If a specific contract is named, scope retrieval to that contract's current version's findings + evidence. Otherwise, retrieve the top N (e.g. 15–20) findings across the org's contracts ranked by keyword relevance and severity, plus each finding's associated evidence IDs.
- If nothing relevant is retrieved, return a response saying so directly (`grounded: false`, an explanation) rather than calling the model with empty context.

Generation:
- Build a prompt that includes ONLY the retrieved findings (contract name, version, category, severity, the triggering language, and each finding's ID and evidence ID(s)) as context, and instructs the model explicitly: answer only from the provided findings; every factual claim must cite a finding_id/evidence_id from the provided list; if the provided findings don't answer the question, say so instead of speculating.
- Call the model the same way the existing analysis service does (same client, same model, matching temperature/token settings unless there's a good reason to differ).
- Parse the response for the citations it claims (finding_id/evidence_id references) and validate every one actually exists in the retrieved set — drop or flag any citation that doesn't (a hallucinated ID would break the "verifiable" promise; catch it in code, don't just trust the model's output).

Response: `{ answer: str, citations: [{finding_id, evidence_id, contract_id, contract_name}], grounded: bool }`.

### 2. Frontend: a simple chat page
- New route, e.g. `/dashboard/ask`, added to the sidebar nav (a reasonable icon/label near "Findings & Redlines" is fine — check how nav items are registered in the existing layout/sidebar component first).
- A minimal chat UI: message list (user question / AI answer), an input box, send button. Keep this simple — no need for streaming tokens or markdown rendering beyond basic line breaks, unless the rest of this app already has a chat-style pattern to reuse.
- Each citation in an answer renders as a clickable chip/link (e.g. "Broad Data License — CONTRACT_03 v2") that navigates to that finding's Legal Passport / Findings detail view (reuse existing routes — check `dashboard/ai-analysis/findings/page.tsx` for how a single finding is currently linked to/displayed).
- If `grounded: false`, render the "I don't have enough information in your verified findings to answer that" message distinctly from a normal answer (different visual treatment — not an error state, just clearly "no answer" rather than "something broke").

## Constraints

- Org-scoped like every other new endpoint from today's RBAC work — reuse `get_current_org_member`, don't build a parallel auth path.
- No new database/search infrastructure — Firestore queries plus in-process filtering is enough at this data scale (mentioned: 16 contracts, ~95 findings org-wide).
- Every citation must be validated server-side against the actual retrieved set before being returned to the frontend — this is the feature's core integrity guarantee, not optional polish.
- Keep the system prompt and retrieval logic in one clearly-named service file (e.g. `services/ask_contracts.py`) rather than inline in the API route, matching this repo's existing service/route separation.

## Acceptance check

Before calling this done, manually verify: (a) a question naming a specific contract returns an answer scoped to that contract with real, clickable citations; (b) a broad question (no contract named) returns a reasonable cross-portfolio answer with multiple citations; (c) a question with no relevant findings (e.g. asking about something no contract discusses) returns `grounded: false` rather than a fabricated answer; (d) manually inspect one response's citations against the actual finding/evidence records to confirm they're real, not hallucinated.
