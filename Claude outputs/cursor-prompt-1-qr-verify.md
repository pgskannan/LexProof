You are adding a "QR-Verify" feature to LexProof, an existing FastAPI + Next.js app. The goal: let anyone scan a QR code (on screen or printed) and land directly on a real, live, independently-verified result on `/public-verify` — no login, no LexProof server trust required beyond serving the static page. Do not touch the existing verification logic itself; it already works and is proven live.

Before writing code, read:
- `frontend/app/public-verify/page.tsx` — the existing independent verifier (client-side hash recompute + direct Sepolia read). Confirm it already supports a deep-link query param that auto-populates and auto-verifies (an evidence ID, or similar) — earlier testing confirmed a working deep link shape like `/public-verify?evidence_id=<id>`. Use that exact existing param shape; do not invent a new one.
- `frontend/app/(authenticated)/legal-passport/page.tsx` and its `components/AnchorProofButton.tsx` — where evidence IDs and anchor data are already displayed, so you know what data is available to build the link/QR from.
- Whatever the frontend's existing `package.json` dependency conventions look like (check for any lightweight canvas/SVG QR libraries already available before adding a new one).

## What to build

1. **A small `QrVerifyBadge` component**: given an evidence ID (or a passport ID that resolves to its primary evidence item), renders a QR code encoding the full `https://<current-origin>/public-verify?evidence_id=<id>` deep link. Generate the QR client-side (a small, dependency-light library — e.g. `qrcode` or `qrcode.react` from npm; pick whichever is lighter and matches this repo's existing React version) — do not call any external QR-generation API. Show the encoded URL as plain text beneath the QR for accessibility/manual entry.

2. **Wire it into the Legal Passport page**: add a "Scan to verify independently" section (Overview tab is fine) showing the `QrVerifyBadge` for that contract's primary anchored evidence item. If a passport has multiple evidence items, default to the first anchored one and let the user pick another from a small dropdown if there's more than one.

3. **A printable "Verification Certificate" view**: a new route (e.g. `/legal-passport/certificate?contractId=...&contractVersion=...`) that renders a clean, print-optimized single page: contract name, risk/compliance scores, passport ID, the evidence ID(s) with their transaction hash/block number, and the QR code(s) from step 1. Use print CSS (`@media print`) so it looks good both on-screen and printed/exported to PDF via the browser's own print dialog — do not add a new PDF-generation library or backend dependency for this; the browser's native print-to-PDF is sufficient. Add a "Print / Save as PDF" button that calls `window.print()`.

4. **A "Copy verification link" button** next to the QR wherever it appears, copying the same deep link to the clipboard — for sharing in a demo without a phone camera handy.

## Constraints

- Zero changes to the actual verification logic, the anchoring path, or any backend endpoint that currently works — this is purely additive UI plus one new lightweight client-side dependency.
- The QR must encode a URL that works standalone — test by opening the encoded URL in a fresh incognito/private browser tab (no auth) and confirming it lands on `/public-verify` already populated and shows a real VERIFIED result against Sepolia, exactly like the existing deep-link flow already does.
- Match this repo's existing component/styling conventions (check how other cards/buttons are built in `legal-passport/page.tsx` before inventing new patterns).
- No new backend endpoints should be required for this feature — everything needed (evidence ID, tx hash, block number, risk/compliance scores) is already returned by the passport/evidence endpoints the Legal Passport page already calls. If you find you need new backend data, say so explicitly rather than quietly adding a new endpoint — check with me first.

## Acceptance check

Before calling this done, manually verify: (a) the QR on the Legal Passport page, scanned or its URL pasted into a fresh browser context, produces a live VERIFIED result with no prior session state; (b) the printable certificate renders cleanly both on-screen and via the browser's print preview; (c) nothing on the existing Legal Passport, Evidence, or Public Verification pages changed behavior.
