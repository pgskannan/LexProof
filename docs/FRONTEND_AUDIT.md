# LexProof Frontend Audit

**Date:** 2026-08-23  
**Scope:** Existing files under `C:\Projects\LexProof\frontend` before foundation changes

## Summary

The source tree is clearly intended to be a Next.js 14 App Router TypeScript application, but it is missing the minimum project scaffold required to run: `package.json`, `tsconfig.json`, `next-env.d.ts`, `next.config.ts`, an App Router root layout, and a global stylesheet entrypoint.

The existing pages are preserved work and should remain in place. The foundation must be added around them rather than replacing routes.

## Route Structure

- `app/public-verify/page.tsx`: public verification portal
- `app/public-verify/README.md`: portal notes and API contract
- `app/(authenticated)/legal-passport/page.tsx`: passport detail view
- `app/(authenticated)/legal-passport/components/AnchorProofButton.tsx`: blockchain anchoring UI
- `app/(authenticated)/contract-time-machine/page.tsx`: version history/comparison UI
- `app/(authenticated)/compliance-command-center/page.tsx`: compliance monitoring UI
- `app/(authenticated)/compliance-command-center/remediation/page.tsx`: AI remediation review UI
- `app/(authenticated)/dashboard/page.tsx`: dashboard overview
- `app/(authenticated)/dashboard/**/page.tsx`: dashboard navigation destination placeholders

The `(authenticated)` folder is a route group and does not add a URL segment. No existing layout or authentication gate was found.

## Imports And Dependencies

### Runtime dependencies required by source

- `next`: App Router runtime/build tooling
- `react`, `react-dom`: React runtime
- `lucide-react`: icons used by passport and anchoring pages
- `sonner`: toast notifications used by `AnchorProofButton`

### Local imports

`AnchorProofButton.tsx` imports:

- `@/components/ui/button`
- `@/components/ui/card`
- `@/components/ui/badge`
- `@/components/ui/skeleton`

Those files do not currently exist in the LexProof frontend tree. Minimal local primitives are required to preserve the component without changing its implementation.

### Styling

Pages use Tailwind CSS utility classes extensively. No Tailwind, PostCSS, CSS entrypoint, or global stylesheet was present. The foundation therefore needs Tailwind CSS and a global CSS import. No alternate styling framework was detected.

### Authentication assumptions

There is no frontend authentication provider, middleware, token client, or authenticated layout. Existing authenticated routes assume the backend/API layer handles access, but the frontend does not currently attach auth credentials. Authentication is intentionally out of scope for this foundation task.

### API clients and environment variables

Pages use browser `fetch` directly. There is no shared API client.

The only frontend environment variable found is:

- `NEXT_PUBLIC_API_URL`: optional API base URL used by the contract time machine page; it defaults to an empty string.

Other pages use relative `/api/...` paths. A deployment rewrite or same-origin proxy will be needed for those calls; this task does not invent backend API behavior.

## Next.js Version Assessment

The code uses the App Router (`app/**/page.tsx`), `next/navigation`, client components, and `style jsx`, matching Next.js 13+ and most closely the existing ContractRiskEdge dependency baseline of Next.js `^14.2.0`. The foundation will pin Next.js 14-compatible packages without rewriting existing routes.

## Compile And Runtime Risks Found

- Missing project manifest and TypeScript configuration.
- Missing root `app/layout.tsx`.
- Missing global CSS import.
- Missing local UI primitives referenced by `AnchorProofButton`.
- `sonner` is imported but unavailable until installed.
- Several pages are intentionally placeholders or depend on backend services not configured in this frontend tree.
- Existing API calls cannot be fully smoke-tested without a running backend.
- No authentication implementation exists; it remains explicitly out of scope.
- No frontend tests were present in the inspected tree.

## Foundation Decision

Add the minimum Next.js App Router scaffold, Tailwind/PostCSS configuration, required package manifest, global CSS, and local UI primitives. Preserve all existing route files and do not modify Firebase configuration, backend code, or authentication/blockchain behavior.
