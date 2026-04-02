'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Bell, Trash2, CheckCheck, ArrowLeft, Loader2 } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

interface Notification {
  notification_ulid: string
  type: string
  title: string
  body: string
  action_url?: string
  read_at?: string
  created_at: string
}

const TYPE_ICON: Record<string, string> = {
  PRICE_ALERT:   '🔔',
  ARBITRAGE:     '⚡',
  VIN_RESULT:    '🔎',
  DEAL_UPDATE:   '🤝',
  RECON_DONE:    '🔧',
  GOAL_REACHED:  '🏆',
  NEW_LEAD:      '📥',
  INVENTORY_LOW: '⚠️',
  SYSTEM:        'ℹ️',
}

const TYPE_COLOR: Record<string, string> = {
  PRICE_ALERT:   'border-l-yellow-500',
  ARBITRAGE:     'border-l-green-500',
  VIN_RESULT:    'border-l-blue-500',
  DEAL_UPDATE:   'border-l-purple-500',
  RECON_DONE:    'border-l-orange-500',
  GOAL_REACHED:  'border-l-emerald-500',
  NEW_LEAD:      'border-l-cyan-500',
  INVENTORY_LOW: 'border-l-red-500',
  SYSTEM:        'border-l-surface-border',
}

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60)  return 'ahora mismo'
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`
  if (diff < 604800) return `hace ${Math.floor(diff / 86400)} d`
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })
}

const FILTERS = [
  { label: 'Todas',     value: '' },
  { label: 'Sin leer',  value: 'unread' },
  { label: 'Alertas',   value: 'PRICE_ALERT' },
  { label: 'Leads',     value: 'NEW_LEAD' },
  { label: 'Arbitraje', value: 'ARBITRAGE' },
  { label: 'Sistema',   value: 'SYSTEM' },
]

export default function NotificationsPage() {
  const router = useRouter()
  const [notifs, setNotifs] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [markingAll, setMarkingAll] = useState(false)

  const fetchNotifs = useCallback(async (pageNum = 1, reset = false) => {
    const params = new URLSearchParams({ limit: '30', offset: String((pageNum - 1) * 30) })
    if (filter === 'unread') params.set('unread', 'true')
    else if (filter) params.set('type', filter)

    try {
      const res = await fetch(`${API}/api/v1/dealer/notifications?${params}`, {
        headers: authHeader(),
      })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) return
      const data = await res.json()
      const incoming: Notification[] = data.notifications ?? []
      setNotifs(prev => reset ? incoming : [...prev, ...incoming])
      setHasMore(incoming.length === 30)
    } catch {
      /* ignore network errors */
    } finally {
      setLoading(false)
    }
  }, [filter, router])

  useEffect(() => {
    setLoading(true)
    setPage(1)
    setNotifs([])
    fetchNotifs(1, true)
  }, [filter, fetchNotifs])

  const markRead = async (ulid: string) => {
    await fetch(`${API}/api/v1/dealer/notifications/${ulid}/read`, {
      method: 'PATCH',
      headers: authHeader(),
    })
    setNotifs(prev => prev.map(n =>
      n.notification_ulid === ulid ? { ...n, read_at: new Date().toISOString() } : n
    ))
  }

  const deleteNotif = async (ulid: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    await fetch(`${API}/api/v1/dealer/notifications/${ulid}`, {
      method: 'DELETE',
      headers: authHeader(),
    })
    setNotifs(prev => prev.filter(n => n.notification_ulid !== ulid))
  }

  const markAllRead = async () => {
    setMarkingAll(true)
    await fetch(`${API}/api/v1/dealer/notifications/read-all`, {
      method: 'POST',
      headers: authHeader(),
    })
    setNotifs(prev => prev.map(n => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })))
    setMarkingAll(false)
  }

  const handleClick = (n: Notification) => {
    if (!n.read_at) markRead(n.notification_ulid)
    if (n.action_url) router.push(n.action_url)
  }

  const loadMore = () => {
    const next = page + 1
    setPage(next)
    fetchNotifs(next, false)
  }

  const unreadCount = notifs.filter(n => !n.read_at).length

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/dashboard" className="rounded-lg p-1.5 text-surface-muted hover:bg-surface-hover hover:text-white transition-colors">
            <ArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Bell size={22} className="text-brand-400" />
              Notificaciones
            </h1>
            {unreadCount > 0 && (
              <p className="text-sm text-surface-muted">{unreadCount} sin leer</p>
            )}
          </div>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={markAllRead}
            disabled={markingAll}
            className="flex items-center gap-2 rounded-xl border border-surface-border px-4 py-2 text-sm text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
          >
            {markingAll ? <Loader2 size={14} className="animate-spin" /> : <CheckCheck size={14} />}
            Marcar todo leído
          </button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.value
                ? 'bg-brand-500 text-white'
                : 'border border-surface-border text-surface-muted hover:border-brand-500/50 hover:text-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={28} className="animate-spin text-brand-400" />
        </div>
      ) : notifs.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-surface-border bg-surface-card py-16 text-center">
          <Bell size={40} className="text-surface-muted" strokeWidth={1.2} />
          <div>
            <p className="font-medium text-white">Sin notificaciones</p>
            <p className="mt-1 text-sm text-surface-muted">Cuando haya actividad, aparecerá aquí.</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {notifs.map(n => (
            <div
              key={n.notification_ulid}
              onClick={() => handleClick(n)}
              className={`relative flex cursor-pointer items-start gap-3 rounded-xl border border-surface-border bg-surface-card p-4 border-l-2 ${TYPE_COLOR[n.type] ?? 'border-l-surface-border'} hover:bg-surface-hover transition-colors ${!n.read_at ? 'bg-surface-hover/30' : ''}`}
            >
              {/* Unread dot */}
              {!n.read_at && (
                <div className="absolute right-4 top-4 h-2 w-2 rounded-full bg-brand-500" />
              )}

              <span className="text-xl" role="img">{TYPE_ICON[n.type] ?? 'ℹ️'}</span>

              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className={`font-medium text-sm ${n.read_at ? 'text-surface-muted' : 'text-white'}`}>
                    {n.title}
                  </p>
                  <span className="shrink-0 text-xs text-surface-muted">{timeAgo(n.created_at)}</span>
                </div>
                <p className="mt-0.5 text-xs text-surface-muted line-clamp-2">{n.body}</p>
                {n.action_url && (
                  <p className="mt-1.5 text-xs text-brand-400">Ver detalle →</p>
                )}
              </div>

              <button
                onClick={e => deleteNotif(n.notification_ulid, e)}
                className="shrink-0 rounded-lg p-1.5 text-surface-muted hover:bg-red-500/10 hover:text-red-400 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}

          {hasMore && (
            <button
              onClick={loadMore}
              className="mt-2 w-full rounded-xl border border-surface-border py-3 text-sm text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors"
            >
              Cargar más
            </button>
          )}
        </div>
      )}
    </div>
  )
}
