# LexProof Workflow E2E Findings

## Result

The real browser workflow remains blocked before the first workflow transition. No code, seed data, workflow logic, authentication, or authorization behavior was modified during this retry.

The second attempt used the tenant-aligned fixture in `lexproof-demo` and the requested authenticated browser session. It still rendered `Contract not found` and returned `403 Forbidden` for the seeded contract's findings and proposal requests.

The latest retry did not reach a contract GET response. After reloading the authenticated page, the browser remained on an empty/loading contract shell with no organization selector or contract content. A direct local request to `http://127.0.0.1:8000/health` timed out, so the backend was unavailable for this attempt. No workflow action was attempted.

## Backend Recovery and Latest Browser Check

The wedged Uvicorn `--reload` process was stopped and restarted with the existing non-reload command:

```powershell
Set-Location 'c:\Projects\LexProof\backend'
& '.\.venv\Scripts\python.exe' -m uvicorn app.lexproof.main:app --host 127.0.0.1 --port 8000
```

The recovered backend returned:

```text
GET /health -> 200 {"status":"ok","service":"lexproof"}
```

The existing authenticated browser tab was reloaded against the verified fixture identifier `demo-lexproof-pending-master-services-agreement`. Backend logs show:

- `GET /api/contracts/demo-lexproof-pending-master-services-agreement` -> `200 OK`
- `GET /api/findings?contract_id=demo-lexproof-pending-master-services-agreement` -> `200 OK`
- `GET /api/contracts/demo-lexproof-pending-master-services-agreement/redline-proposals` -> `200 OK`
- `GET /api/passports?contract_id=demo-lexproof-pending-master-services-agreement&limit=100` -> `200 OK`
- `GET /api/contracts/demo-lexproof-pending-master-services-agreement/versions` -> `404 Not Found`
- `GET /api/contracts/demo-lexproof-pending-master-services-agreement/executive-summary` -> `403 Forbidden`

Despite the successful contract/findings/proposals responses, the browser UI rendered `Contract not found` rather than the contract content. The `/versions` 404 and executive-summary 403 are ancillary failures observed during page loading; no workflow action was attempted.

The persisted initial state remained unchanged:

- Proposal `5c27085f-464a-408f-bea2-86f6a7a6e3be`: `PROPOSED`
- Workflow `7f64f88a-beac-4f24-ab23-67ab61cdecfe`: `in_review`, `in_progress`
- Review decision: none
- Published version: `None`
- Workflow audit events: none

## First Failure

**FIRST BROKEN TRANSITION:** Open the seeded demo contract

**EXPECTED:** The authenticated browser session should open contract `demo-lexproof-pending-master-services-agreement` in organization `lexproof-demo`, then expose its Findings / Human Review area and proposal.

**ACTUAL:** The browser session was scoped to `LexProof Demo` (`lexproof-demo`). Direct navigation to `/dashboard/contracts/demo-lexproof-pending-master-services-agreement` rendered `Contract not found`. The browser recorded `403 Forbidden` responses for the contract-related API requests:

- `/api/findings?contract_id=demo-lexproof-pending-master-services-agreement`
- `/api/contracts/demo-lexproof-pending-master-services-agreement/redline-proposals`

**UI:** Organization selector showed only `LexProof Demo`; the contract page showed `Contract not found`. No Findings / Human Review content was available.

**BACKEND:** Direct Firestore repository verification confirmed that the tenant-aligned seeded records exist and remain in the required pre-approval state:

- Contract exists in `lexproof-demo`.
- Version `demo-lexproof-pending-master-services-agreement-v1` has `analysis_status: complete`.
- Finding `demo-lexproof-pending-liability-cap-finding` is linked to the contract/version.
- Proposal `5c27085f-464a-408f-bea2-86f6a7a6e3be` has status `PROPOSED`.
- Workflow `7f64f88a-beac-4f24-ab23-67ab61cdecfe` has state `in_review` and available roles `reviewer`, `admin`.
- No redline review decision exists.
- Published version is `None`.

The authenticated account `pgskannan@gmail.com` is an active `admin` and `contract_owner` member of `lexproof-demo`, and the seed's service-path access check succeeds for this user. The browser session nevertheless receives `403` for the seeded contract.

**AUDIT:** No audit event was recorded. This is expected because no workflow transition was attempted.

**LIKELY ROOT CAUSE:** The authenticated browser user is not a member of the seeded organization, and the browser session has no organization switch to `demo-pending-approval-workflow`. This is an environment/session access precondition, not a demonstrated workflow-engine failure.

For the tenant-aligned second attempt, the remaining supported conclusion is narrower: the browser's authenticated authorization context does not reflect the Firestore membership change, or the running backend process is using stale authorization/session state. No code or data repair was attempted.

**FILES INVOLVED:**

- `frontend/app/(authenticated)/dashboard/contracts/[contractId]/page.tsx`
- `backend/app/lexproof/api/contracts.py`
- `backend/app/lexproof/api/findings.py`
- `backend/app/lexproof/api/redline_proposals.py`
- `backend/app/lexproof/services/organizations.py`

## Transition Table

| # | Transition | Actor/Role | UI | Backend | Audit | Result |
|---|---|---|---|---|---|---|
| 1 | Open seeded demo contract | Authenticated browser user `pgskannan@gmail.com` / `VJEexqdPVwYJ73D6vShQ75DSGdZ2` | `Contract not found`; organization is `LexProof Demo`; contract APIs return `403` | Tenant-aligned records exist in `lexproof-demo`; service-path access succeeds for the user; browser request remains forbidden | No event; no transition attempted | BLOCKED |
| 2 | Open Findings / Human Review | Not reached | Not reached | Not reached | Not reached | NOT REACHED |
| 3 | Execute Human Review action | Not reached | Not reached | Not reached | Not reached | NOT REACHED |
| 4 | Redline Approval | Not reached | Not reached | Not reached | Not reached | NOT REACHED |
| 5 | Publish | Not reached | Not reached | Not reached | Not reached | NOT REACHED |
| 6 | Post-publish analysis | Not reached | Not reached | Not reached | Not reached | NOT REACHED |
| 7 | Blockchain anchor | Not reached | Not reached | Not reached | Not reached | NOT REACHED |

## Latest Retry

| # | Transition | Actor | UI | Backend | Audit | Result |
|---|---|---|---|---|---|---|
| 1 | Open seeded demo contract | `pgskannan@gmail.com` | Authenticated shell remained blank/loading; no contract content rendered | `http://127.0.0.1:8000/health` timed out; contract GET could not complete | No event; no transition attempted | BLOCKED |
| 2 | Render seeded contract after backend recovery | `pgskannan@gmail.com` / existing authenticated session | `Contract not found`, despite contract page load; no Findings/Human Review action available | Contract GET 200; findings GET 200; proposal list GET 200; versions GET 404; executive summary GET 403 | No event; no transition attempted | BLOCKED |

## E2E Claim

E2E success is **not claimed**. The browser workflow did not reach the first legitimate transition because the authenticated session could not access the seeded organization.

## Read-Only Authentication/Tenant Trace

This trace was performed after workflow testing was stopped. No application or seed changes were made, and no Firebase token value was printed.

### Request path

1. `frontend/lib/api.ts` resolves `auth.currentUser`, waits for `onAuthStateChanged` if necessary, calls `user.getIdToken()`, and sets `Authorization: Bearer <redacted-token>` when a Firebase user exists. It also may set `X-Org-Id` from `frontend/lib/orgStore.ts`.
2. `backend/app/lexproof/services/auth.py:get_current_user` receives the bearer credential through FastAPI `HTTPBearer`, calls `verify_firebase_token`, and returns the decoded claims including `uid`.
3. `backend/app/lexproof/services/firebase_auth.py:verify_firebase_token` calls Firebase Admin `auth.verify_id_token` against the backend's configured Firebase project.
4. The contract GET route in `backend/app/lexproof/api/contracts.py` depends on `get_current_user`, but does not resolve organization membership. It checks `_is_visible_to_user(contract, uid)`, which is `not owner_id or owner_id == uid`.
5. The findings route applies the same owner check in `backend/app/lexproof/api/findings.py`.
6. The redline-proposal list route depends on `get_current_user`, then `ProposalService.list()` calls `_require_contract_member()`, which resolves the contract organization and checks `OrganizationService.get_active_member(org_id, uid)`.

### Evidence answers

1. **Authorization header:** The frontend implementation constructs and sends a bearer header whenever Firebase `auth.currentUser` exists. The browser request reached authorization decisions rather than a missing-token `401`, so the observed request was not rejected by the missing/invalid-bearer branch. The actual header value was not captured or printed.
2. **Firebase user ID derived by backend:** Not directly observable from the redacted browser evidence. The successful service-level comparison used `VJEexqdPVwYJ73D6vShQ75DSGdZ2`; the browser UI identifies the account as `pgskannan@gmail.com`, but an email display is not proof of the decoded Firebase UID. A backend log containing only a redacted UID prefix or a diagnostic response would be required to prove the runtime claim without exposing a token.
3. **Organization derived by backend:** For these GET routes, no organization is derived from the bearer token. `get_current_user` returns token claims only. `X-Org-Id` is not used by `GET /api/contracts/{contract_id}`, `GET /api/findings`, or `GET /api/contracts/{contract_id}/redline-proposals`; the redline service derives organization from the contract document.
4. **Roles derived by backend:** The contract and findings GET routes do not resolve roles. The redline service resolves roles only after identifying the contract organization and active membership. The service-level path saw `admin`, `contract_owner` for `VJEexqdPVwYJ73D6vShQ75DSGdZ2`; the browser runtime role set is not directly observable from the redacted request.
5. **Contract organization checked:** The persisted contract and proposal both contain `org_id: lexproof-demo`.
6. **403/denial condition:** The contract GET and findings visibility checks compare the token-derived UID to the contract/finding `owner_id`. The seeded records use `owner_id: demo-owner-1`, so the authenticated browser UID cannot pass those owner checks. The redline list path checks active membership for `lexproof-demo`; it returns forbidden when the token-derived UID is not found as an active member in that runtime lookup. `ProposalService.get()` succeeds only because the test supplied the known Firestore user ID directly.
7. **Stale backend configuration/state:** Not proven. The persisted Firestore membership and service-level access are current. A stale backend process, different Firebase project credentials, or stale token verification could explain a mismatch, but no runtime claim/config dump was performed.
8. **Stale browser Firebase session/token:** Not proven. The UI shows `pgskannan@gmail.com`, and the client requests a fresh token through `getIdToken()`. The decoded UID and token project were intentionally not exposed.
9. **Service override mismatch:** Yes, the service-level check is not equivalent to a real HTTP request. It calls `ProposalService.get(proposal_id, known_uid)` directly, bypassing FastAPI `get_current_user` and therefore bypassing Firebase token decoding. It still uses the real Firestore organization membership lookup. The browser path must first derive the UID from the Firebase token, then apply route-specific owner or membership checks.

### Trace conclusion

**FIRST DIVERGENCE:** The first unverified boundary is Firebase token claims at `get_current_user`: the service path supplies `VJEexqdPVwYJ73D6vShQ75DSGdZ2` directly, while the browser path derives `uid` from the live Firebase ID token. After that boundary, the route-specific authorization behavior diverges from the service path: contract/findings use owner equality, while `ProposalService.get()` uses active organization membership.

**EXPECTED CONTEXT:** Firebase token UID `VJEexqdPVwYJ73D6vShQ75DSGdZ2`; active membership in `lexproof-demo`; roles `admin`, `contract_owner`; contract organization `lexproof-demo`; contract access granted.

**ACTUAL CONTEXT:** Browser UI identifies `pgskannan@gmail.com`; bearer-auth request reaches a non-401 authorization path; decoded UID/roles were not exposed by the available redacted browser evidence; contract access was denied/not visible.

**403 CONDITION:** Runtime token-derived identity fails the applicable route authorization: owner equality for contract/findings, or active membership lookup for redline proposals. The exact failing comparison cannot be distinguished further without a redacted runtime UID/membership log.

**ROOT CAUSE:** A mismatch exists between the direct service invocation's explicitly supplied UID and the browser request's Firebase-derived authorization context and/or route-specific owner authorization. The evidence does not support claiming stale configuration or stale browser token as fact.

**FILES INVOLVED:**

- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/lib/firebase.ts`
- `frontend/lib/orgStore.ts`
- `backend/app/lexproof/services/auth.py`
- `backend/app/lexproof/services/firebase_auth.py`
- `backend/app/lexproof/services/organizations.py`
- `backend/app/lexproof/api/contracts.py`
- `backend/app/lexproof/api/findings.py`
- `backend/app/lexproof/api/redline_proposals.py`
- `backend/app/lexproof/services/redline_proposals.py`

**CODE CHANGES:** NONE
