# Ask Lexi Voice Console

Ask Lexi is the in-app simulated Alexa+ voice experience. Browser speech APIs provide microphone input and spoken output; a server-side Google ADK agent handles the turn and connects to LexProof's own authenticated MCP endpoint as the signed-in user.

## Architecture

```text
+------------------------------+
| Browser                      |
| SpeechRecognition /           |
| speechSynthesis (en-US)       |
+---------------+--------------+
                | utterance, Firebase bearer, X-Org-Id
                v
+------------------------------+
| FastAPI                      |
| POST /api/voice/turn         |
| session + confirmation guard |
+---------------+--------------+
                | authenticated turn
                v
+------------------------------+
| Google ADK agent             |
| "Alexa+ simulation" on Vertex|
| MCP tool callbacks           |
+---------------+--------------+
                | MCP client / Streamable HTTP
                | initialize negotiates 2025-11-25
                v
+------------------------------+
| LexProof /mcp                |
| tools execute as this user   |
+---------------+--------------+
                | MCP tools -> REST / RBAC / audit
                v
+------------------------------+       +----------------------+
| Firestore                    |------>| Ethereum Sepolia     |
| contracts, workflows, audit  | roots | passport proof roots|
+------------------------------+       +----------------------+
```

The MCP protocol version above was observed in a local integration test using Google ADK's `McpToolset` against the LexProof Streamable HTTP server. It is the negotiated initialize-handshake version, not merely the server's advertised constant.

## Why This Is A Faithful Stand-In

- The microphone and speech output use the browser's native Web Speech APIs, rather than prerecorded audio or a scripted transcript.
- Each turn calls `POST /api/voice/turn`. The server-side ADK agent uses the caller's Firebase bearer and organization header to connect to the same first-party `/mcp` endpoint exposed to other clients.
- The agent receives the actual LexProof MCP tools and their results. Contract access, role checks, approval state changes, and audit behavior stay in the existing REST/MCP services.
- The server applies a deterministic confirmation guard before `confirm_decision`; the model cannot bypass that callback by changing its wording.

This is an Alexa+ simulation, not an Alexa+ device integration. It does not use Amazon voice services, Alexa accounts, Amazon branding, logos, or sounds. The simulated client is the browser UI; LexProof's MCP server and authorization path are real.

## Confirmation Guard

For a `confirm_decision` tool call to proceed, all conditions must hold:

1. An unexpired `prepare_decision` result with a valid short code was produced in the immediately preceding turn of this user's session.
2. The current utterance starts with `yes`, `yeah`, `confirm`, `approve it`, or `go ahead`, or contains that exact short code.
3. The code passed to `confirm_decision` equals the short code saved from the prepared result.

Preparing and confirming in one turn is blocked. A new preparation replaces the previous one; a preparation not confirmed in the next turn is discarded. A blocked call speaks: "I need you to say 'confirm' first. Nothing has changed." The underlying MCP decision tool independently checks its signed confirmation, expiry, user identity, current role, item state, and replay status.

The UI displays the prepared summary, six-character code, and expiry countdown. Confirm sends the word `confirm`; Cancel clears the card and sends `cancel` as a separate turn. Short codes may appear in the UI; bearer tokens and full signed confirmation tokens are not exposed in the tool trace.

## Judge Path

1. Sign in with the read-only judge account.
2. Open **Ask Lexi (voice)** from the account menu.
3. Try the four suggestion chips to list contracts, verify a passport, check due payments, and inspect pending approvals.
4. Say or type `approve the legal review` and review the prepared confirmation card.
5. Say or select **Confirm**. The read-only account receives the server's denial; no workflow or payment change is made.
6. Optionally open **Connect an AI assistant** and connect MCP Inspector with the same authenticated account.

Voice turns for configured read-only judge accounts use the judge interaction rate limiter. The MCP decision tools and REST authorization remain authoritative; the browser cannot elevate the account's permissions.

## Demo Data

The Alexa demo seed attaches two pending workflow approvals and three payment obligations to existing analyzed contracts in `LexProof Alexa Demo`. It chooses the analyzed contract whose name matches MSA/master services for legal review, another analyzed contract for finance review, and sources obligation amounts and verbatim quotes from each selected version's real `document_text`. One obligation is overdue and two are due within 30 days. It does not create synthetic contracts, versions, passports, or findings.

Run from `backend/`. Dry-run is the default and performs no Firestore writes; the owner email must already exist in Firebase Auth, and the judge UID must be in `LEXPROOF_READ_ONLY_UIDS`. The seed refuses to attach unless at least two analyzed contracts exist.

```powershell
python scripts/seed_alexa_demo.py --owner-email pgskannan@gmail.com --judge-uid <read-only-judge-uid> --dry-run
python scripts/seed_alexa_demo.py --owner-email pgskannan@gmail.com --judge-uid <read-only-judge-uid> --apply
python scripts/seed_alexa_demo.py --remove-synthetic --dry-run
python scripts/seed_alexa_demo.py --remove-synthetic --apply
```

Attach mode replaces only its deterministic workflow/payment rows and uses the read-only judge as creator so the owner can approve under separation-of-duties rules. `--remove-synthetic` removes only older deterministic synthetic IDs when their records belong to `lexproof-alexa-demo`; dry-run lists the exact records. Passport anchors are never read or deleted. Neither mode prints credentials or submits an anchor transaction. Use the Acme passport's Legal Passport UI action for the one real Sepolia anchor.

## Known Limits

- Speech recognition is available in supported Chrome and Edge builds. Other browsers keep the text input and show a type-instead notice. Speech synthesis depends on voices installed by the browser or operating system.
- Voice sessions are in memory, scoped by user and session ID, expire after 30 minutes of inactivity, and allow at most 20 turns. They are not shared between Cloud Run instances.
- The MCP server's short-code lookup is also process-local. A horizontally scaled production deployment needs shared session and confirmation state or reliable instance affinity.
- A voice turn has a 45-second server timeout. No audio is uploaded: recognition and synthesis happen in the browser, while utterance text and the Firebase bearer are sent to the authenticated API/MCP path.
- The current experience is not linked to a real Alexa+ account or device. Amazon-side account linking, wake-word behavior, and device audio routing are outside this simulation.
