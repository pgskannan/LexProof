'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Bell, CheckCheck, FileWarning, FileCheck2 } from 'lucide-react'
import { apiFetch } from '../lib/api'

type Notification = {
  id: string
  type: string
  title: string
  message: string
  contract_id?: string | null
  url?: string | null
  read: boolean
  created_at?: string | null
}

const TYPE_ICON: Record<string, typeof FileCheck2> = {
  analysis_complete: FileCheck2,
  analysis_failed: FileWarning,
}

function timeAgo(iso?: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function NotificationBell() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  async function refreshUnreadCount() {
    try {
      const response = await apiFetch('/api/notifications/unread-count')
      if (!response.ok) return
      const body = await response.json()
      setUnreadCount(body.count || 0)
    } catch {
      // Best-effort -- a failed poll just leaves the last known count.
    }
  }

  async function loadNotifications() {
    setLoading(true)
    try {
      const response = await apiFetch('/api/notifications?limit=20')
      if (response.ok) setNotifications(await response.json())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshUnreadCount()
    const interval = setInterval(() => void refreshUnreadCount(), 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    function onDocumentClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocumentClick)
    return () => document.removeEventListener('mousedown', onDocumentClick)
  }, [])

  function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next) void loadNotifications()
  }

  async function onNotificationClick(notification: Notification) {
    setOpen(false)
    if (!notification.read) {
      setNotifications((current) => current.map((item) => (item.id === notification.id ? { ...item, read: true } : item)))
      setUnreadCount((count) => Math.max(0, count - 1))
      void apiFetch(`/api/notifications/${encodeURIComponent(notification.id)}/read`, { method: 'POST' })
    }
    if (notification.url) router.push(notification.url)
  }

  async function onMarkAllRead() {
    setNotifications((current) => current.map((item) => ({ ...item, read: true })))
    setUnreadCount(0)
    await apiFetch('/api/notifications/read-all', { method: 'POST' })
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={toggleOpen}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Notifications"
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-700"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-20 mt-2 w-80 max-h-96 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg"
        >
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
            <p className="text-sm font-semibold text-gray-900">Notifications</p>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => void onMarkAllRead()}
                className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark all read
              </button>
            )}
          </div>
          {loading && <p className="px-3 py-6 text-center text-xs text-gray-400">Loading…</p>}
          {!loading && notifications.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-gray-400">No notifications yet.</p>
          )}
          {!loading &&
            notifications.map((notification) => {
              const Icon = TYPE_ICON[notification.type] || Bell
              return (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() => void onNotificationClick(notification)}
                  className={`flex w-full items-start gap-2 border-b border-gray-50 px-3 py-2.5 text-left last:border-b-0 hover:bg-gray-50 ${
                    notification.read ? '' : 'bg-blue-50/50'
                  }`}
                >
                  <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${notification.type === 'analysis_failed' ? 'text-red-500' : 'text-blue-600'}`} />
                  <div className="min-w-0 flex-1">
                    <p className={`truncate text-sm ${notification.read ? 'text-gray-700' : 'font-semibold text-gray-900'}`}>
                      {notification.title}
                    </p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-gray-500">{notification.message}</p>
                    <p className="mt-0.5 text-[10px] text-gray-400">{timeAgo(notification.created_at)}</p>
                  </div>
                  {!notification.read && <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-blue-600" />}
                </button>
              )
            })}
        </div>
      )}
    </div>
  )
}
