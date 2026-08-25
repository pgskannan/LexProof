# LexProof Frontend Foundation

**Status:** Runnable Next.js TypeScript App Router foundation  
**Validated:** 2026-08-23

## Toolchain

- Next.js: `14.2.35`
- React: `18.3.1`
- Node.js: `v24.18.0` observed during validation
- Node.js requirement: `>=18.17.0`
- Package manager: npm
- TypeScript: `^5.6.3`
- Styling: Tailwind CSS v4 through `@tailwindcss/postcss`

Next.js 14 does not support `next.config.ts`, so the equivalent configuration is provided as `frontend/next.config.js`. This is a compatibility adjustment required by the selected Next.js version.

## Dependencies

### Runtime

- `next`
- `react`
- `react-dom`
- `lucide-react`
- `sonner`

### Development

- `typescript`
- `@types/node`
- `@types/react`
- `@types/react-dom`
- `tailwindcss`
- `@tailwindcss/postcss`

The local `components/ui` primitives are intentionally small and exist only because the preserved `AnchorProofButton` imports them.

## Commands

From `C:\Projects\LexProof\frontend`:

```bash
npm install
npm run dev
npm run typecheck
npm run build
npm start
```

- `npm run dev`: starts the local development server
- `npm run typecheck`: runs `tsc --noEmit`
- `npm run build`: creates the production build and runs Next.js lint/type validation
- `npm start`: serves the production build

## Route Structure

- `/public-verify`
- `/legal-passport`
- `/contract-time-machine`
- `/compliance-command-center`
- `/compliance-command-center/remediation`
- `/dashboard`
- `/dashboard/contracts`
- `/dashboard/contracts/reviews`
- `/dashboard/contracts/versions`
- `/dashboard/ai-analysis`
- `/dashboard/ai-analysis/risk`
- `/dashboard/ai-analysis/clauses`
- `/dashboard/ai-analysis/findings`
- `/dashboard/compliance`
- `/dashboard/compliance/policies`
- `/dashboard/compliance/violations`
- `/dashboard/compliance/monitoring`
- `/dashboard/legal-passport`
- `/dashboard/blockchain-proof`
- `/dashboard/verification`
- `/dashboard/reports`
- `/dashboard/administration`

The `(authenticated)` directory is a Next.js route group and does not appear in URLs.

## Environment Variables

- `NEXT_PUBLIC_API_URL`: optional browser-visible API base URL used by the contract time machine. It defaults to an empty string.

Existing pages also call relative `/api/...` endpoints. A same-origin proxy or deployment rewrite is required when the API is hosted separately. Authentication remains out of scope for this foundation task.

## Validation Results

- `npm install`: **PASS**
- `npm run typecheck`: **PASS**
- `npm run build`: **PASS**
- Build output: 25 static routes generated successfully.

## Known Issues

- The frontend source is runnable, but several dashboard destinations intentionally remain placeholders and were preserved as requested.
- No authentication provider or middleware is implemented.
- API calls cannot be fully smoke-tested without the LexProof backend running and configured.
- The seeded demo JSON is not automatically loaded into the frontend/API repositories.
- `npm audit` reports two high-severity transitive findings involving the Next.js/PostCSS dependency chain. `npm audit fix --force` requests a breaking upgrade to Next.js 16, so it was not applied during this Next.js 14 foundation task.
- The existing backend and Firebase configuration were not modified.
- No deployment was performed.
