export type ChatDelivery = {
  delivery_id: string
  org_id: string
  channel: string
  provider: string
  status: 'sent' | 'failed' | 'simulated'
  event_type: string
  title: string
  message: string
  url?: string | null
  detail?: string | null
  created_at: string
}

export function listChatDeliveriesPath(orgId: string, limit?: number): string {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : ''
  return `/api/orgs/${encodeURIComponent(orgId)}/chat-notifications/deliveries${query}`
}

export function testChatNotificationRequest(orgId: string) {
  return {
    path: `/api/orgs/${encodeURIComponent(orgId)}/chat-notifications/test`,
    method: 'POST' as const,
  }
}
