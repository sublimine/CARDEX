'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useRef, useState, useCallback } from 'react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Nav items ──────────────────────────────────────────────────────────────────
const NAV = [
  { href: '/dashboard',                label: 'Inicio',         icon: '⊞' },
  { href: '/dashboard/inventory',      label: 'Inventario',     icon: '🚗' },
  { href: '/dashboard/crm',            label: 'CRM',            icon: '👥' },
  { href: '/dashboard/leads',          label: 'Leads',          icon: '📥' },
  { href: '/dashboard/pricing',        label: 'Precios',        icon: '📊' },
  { href: '/dashboard/publish',        label: 'Publicación',    icon: '📡' },
  { href: '/dashboard/vin-valuation',  label: 'Valoración VIN', icon: '🔬' },
  { href: '/dashboard/audit',          label: 'Auditoría',      icon: '🔍' },
  { href: '/arbitrage',                label: 'Arbitraje',      icon: '⚡' },
  { href: '/analytics/tradingcar',     label: 'TradingCar',     icon: '📈' },
]

// ── Notification types → color ─────────────────────────────────────────────────
const TYPE_COLOR: Record<string, string> = {
  PRICE_ALERT:    'text-yellow-400',
  ARBITRAGE:      'text-green-400',
  VIN_RESULT:     'text-blue-400',
  DEAL_UPDATE:    'text-purple-400',
  RECON_DONE:     'text-orange-400',
  GOAL_REACHED:   'text-emerald-400',
  NEW_LEAD:       'text-cyan-400',
  INVENTORY_LOW:  'text-red-400',
  SYSTEM:         'text-surface-muted',
}

const TYPE_ICON: Record<string, string> = {
  PRICE_ALERT:    '🔔',
  ARBITRAGE:      '⚡',
  VIN_RESULT:     '🔎',
  DEAL_UPDATE:    '🤝',
  RECON_DONE:     '🔧',
  GOAL_REACHED:   '🏆',
  NEW_LEAD:       '📥',
  INVENTORY_LOW:  '⚠️',
  SYSTEM:         'ℹ️',
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

// ── Notification Bell ──────────────────────────────────────────────────────────
function NotificationBell() {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [notifs, setNotifs] = useState<Notification[]>([])
  const [loading, setLoading] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // Poll unread count every 30s
  const fetchCount = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/dealer/notifications/unread-count`, {
        headers: authHeader(),
      })
      if (!res.ok) return
      const data = await res.json()
      setUnread(data.unread_count ?? 0)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchCount()
    const id = setInterval(fetchCount, 30_000)
    return () => clearInterval(id)
  }, [fetchCount])

  // Fetch notifications when panel opens
  useEffect(() => {
    if (!open) return
    setLoading(true)
    fetch(`${API}/api/v1/dealer/notifications?limit=20`, { headers: authHeader() })
      .then(r => r.json())
      .then(data => {
        setNotifs(data.notifications ?? [])
        setUnread(data.unread_count ?? 0)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [open])

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  async function markAllRead() {
    await fetch(`${API}/api/v1/dealer/notifications/read-all`, {
      method: 'POST',
      headers: authHeader(),
    })
    setNotifs(prev => prev.map(n => ({ ...n, read_at: new Date().toISOString() })))
    setUnread(0)
  }

  async function markRead(ulid: string) {
    await fetch(`${API}/api/v1/dealer/notifications/${ulid}/read`, {
      method: 'PATCH',
      headers: authHeader(),
    })
    setNotifs(prev => prev.map(n =>
      n.notification_ulid === ulid ? { ...n, read_at: new Date().toISOString() } : n
    ))
    setUnread(prev => Math.max(0, prev - 1))
  }

  async function deleteNotif(e: React.MouseEvent, ulid: string) {
    e.stopPropagation()
    await fetch(`${API}/api/v1/dealer/notifications/${ulid}`, {
      method: 'DELETE',
      headers: authHeader(),
    })
    setNotifs(prev => prev.filter(n => n.notification_ulid !== ulid))
  }

  function handleClick(n: Notification) {
    if (!n.read_at) markRead(n.notification_ulid)
    if (n.action_url) router.push(n.action_url)
    setOpen(false)
  }

  function timeAgo(iso: string): string {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
    if (diff < 60) return 'ahora'
    if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`
    return `hace ${Math.floor(diff / 86400)}d`
  }

  return (
    <div className="relative" ref={panelRef}>
      {/* Bell button */}
      <button
        onClick={() => setOpen(v => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-surface-muted transition hover:bg-surface-hover hover:text-white"
        aria-label="Notificaciones"
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand-500 text-[10px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute right-0 top-11 z-50 w-96 rounded-xl border border-surface-border bg-surface shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
            <span className="text-sm font-semibold text-white">
              Notificaciones
              {unread > 0 && (
                <span className="ml-2 rounded-full bg-brand-500/20 px-2 py-0.5 text-xs text-brand-400">
                  {unread} sin leer
                </span>
              )}
            </span>
            {unread > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-brand-400 hover:text-brand-300 transition"
              >
                Marcar todo leído
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-[440px] overflow-y-auto">
            {loading && (
              <div className="space-y-2 p-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-hover" />
                ))}
              </div>
            )}
            {!loading && notifs.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <span className="mb-2 text-3xl">🔔</span>
                <p className="text-sm text-surface-muted">Sin notificaciones</p>
              </div>
            )}
            {!loading && notifs.map(n => (
              <div
                key={n.notification_ulid}
                onClick={() => handleClick(n)}
                className={`group flex cursor-pointer items-start gap-3 border-b border-surface-border/50 px-4 py-3 transition hover:bg-surface-hover ${!n.read_at ? 'bg-brand-500/5' : ''}`}
              >
                {/* Unread dot */}
                <div className="mt-1 flex-shrink-0">
                  {!n.read_at
                    ? <div className="h-2 w-2 rounded-full bg-brand-500" />
                    : <div className="h-2 w-2" />
                  }
                </div>

                {/* Icon + content */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{TYPE_ICON[n.type] ?? '🔔'}</span>
                    <span className={`text-xs font-medium ${TYPE_COLOR[n.type] ?? 'text-white'}`}>
                      {n.type.replace('_', ' ')}
                    </span>
                    <span className="ml-auto flex-shrink-0 text-xs text-surface-muted">
                      {timeAgo(n.created_at)}
                    </span>
                  </div>
                  <p className={`mt-0.5 text-sm leading-snug ${n.read_at ? 'text-surface-muted' : 'font-medium text-white'}`}>
                    {n.title}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-surface-muted">{n.body}</p>
                </div>

                {/* Delete button */}
                <button
                  onClick={e => deleteNotif(e, n.notification_ulid)}
                  className="mt-0.5 flex-shrink-0 opacity-0 transition group-hover:opacity-100 text-surface-muted hover:text-red-400"
                  aria-label="Eliminar"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>

          {/* Footer */}
          {notifs.length > 0 && (
            <div className="border-t border-surface-border px-4 py-2.5 text-center">
              <Link
                href="/dashboard/notifications"
                onClick={() => setOpen(false)}
                className="text-xs text-brand-400 hover:text-brand-300 transition"
              >
                Ver todas las notificaciones →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()

  function logout() {
    localStorage.removeItem('cardex_token')
    router.push('/dashboard/login')
  }

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-surface-border bg-surface">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2.5 border-b border-surface-border px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-500 text-xs font-bold text-white">
          C
        </div>
        <span className="text-sm font-bold tracking-wide text-white">CARDEX</span>
        <span className="ml-auto rounded bg-brand-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-brand-400">
          PRO
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV.map(item => {
          const active = pathname === item.href ||
            (item.href !== '/dashboard' && pathname.startsWith(item.href))
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition
                ${active
                  ? 'bg-brand-500/15 text-brand-400 font-medium'
                  : 'text-surface-muted hover:bg-surface-hover hover:text-white'}`}
            >
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* Bottom: logout */}
      <div className="border-t border-surface-border p-2">
        <button
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-surface-muted transition hover:bg-surface-hover hover:text-white"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Cerrar sesión
        </button>
      </div>
    </aside>
  )
}

// ── Dashboard Layout ───────────────────────────────────────────────────────────
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()

  // Redirect to login if no token (skip for login/register pages)
  useEffect(() => {
    const publicPaths = ['/dashboard/login', '/dashboard/register']
    if (publicPaths.includes(pathname)) return
    const token = localStorage.getItem('cardex_token')
    if (!token) router.replace('/dashboard/login')
  }, [pathname, router])

  // Don't render chrome on auth pages
  const isAuthPage = pathname === '/dashboard/login' || pathname === '/dashboard/register'
  if (isAuthPage) return <>{children}</>

  return (
    <div className="flex h-screen overflow-hidden bg-surface-dark">
      <Sidebar />

      {/* Main column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-surface-border bg-surface px-6">
          {/* Breadcrumb / page title from pathname */}
          <div className="text-sm text-surface-muted">
            {pathname.split('/').filter(Boolean).map((seg, i, arr) => (
              <span key={i}>
                <span className={i === arr.length - 1 ? 'text-white font-medium' : ''}>
                  {seg.charAt(0).toUpperCase() + seg.slice(1)}
                </span>
                {i < arr.length - 1 && <span className="mx-1.5 opacity-40">/</span>}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <NotificationBell />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
