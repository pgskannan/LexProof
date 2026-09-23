import { NextRequest } from 'next/server'

// Next.js rewrites() drop some upstream error statuses: a real backend 404
// on GET /api/contracts/{id} (cross-tenant isolation: same 404 as missing)
// was returned to the browser as 500 Internal Server Error. Forward the
// FastAPI response, including 404, instead of rewriting.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const HOP_BY_HOP = new Set(['connection', 'keep-alive', 'transfer-encoding', 'content-encoding'])

async function proxy(request: NextRequest, path: string[]) {
  const target = `${API_URL.replace(/\/$/, '')}/api/${path.join('/')}${request.nextUrl.search}`
  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (key === 'host' || HOP_BY_HOP.has(key)) return
    headers.set(key, value)
  })
  const init: RequestInit = { method: request.method, headers, cache: 'no-store' }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.arrayBuffer()
  }
  let upstream: Response
  try {
    upstream = await fetch(target, init)
  } catch {
    return Response.json({ detail: 'Upstream API unavailable' }, { status: 502 })
  }
  const responseHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    if (HOP_BY_HOP.has(key)) return
    responseHeaders.set(key, value)
  })
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

type Context = { params: { path: string[] } }

async function handle(request: NextRequest, context: Context) {
  return proxy(request, context.params.path)
}

export const GET = handle
export const POST = handle
export const PUT = handle
export const PATCH = handle
export const DELETE = handle
export const OPTIONS = handle

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'
