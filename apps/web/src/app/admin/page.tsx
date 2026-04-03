'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Types ──────────────────────────────────────────────────────────────────

interface AdminStats {
  total_entities: number
  total_users: number
  active_listings: number
  scrape_jobs_today: number
  notifications_24h: number
  entities_by_tier: Record<string, number>
}

interface AdminEntity {
  entity_ulid: string
  legal_name: string
  country_code: string
  subscription_tier: string
  user_count: number
  created_at: string
}

interface AdminUser {
  user_ulid: string
  email: string
  full_name: string
  entity_ulid: string
  is_dealer: boolean
  email_verified: boolean
  created_at: string
}

interface ScraperStatus {
  platform: string
  status: string
  record_count: number
  last_run_at: string | null
  lag_minutes: number | null
}

type Tab = 'stats' | 'entities' | 'users' | 'scrapers'

const TIERS = ['FREE', 'PRO', 'ENTERPRISE']

const SCRAPER_STATUS_BADGE: Record<string, string> = {
  RUNNING: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  DONE: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  FAILED: 'bg-red-500/20 text-red-400 border border-red-500/30',
  PENDING: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })
}

function StatCard({ label, value, big = false }: { label: string; value: string | number; big?: boolean }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <p className="text-xs text-surface-muted uppercase tracking-wider">{label}</p>
      <p className={`mt-2 font-mono font-bold text-white ${big ? 'text-4xl' : 'text-2xl'}`}>
        {typeof value === 'number' ? value.toLocaleString('es-ES') : value}
      </p>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AdminPage() {
  const router = useRouter()
  const [tab, setTab] = useState<Tab>('stats')
  const [accessDenied, setAccessDenied] = useState(false)

  // Stats
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)

  // Entities
  const [entities, setEntities] = useState<AdminEntity[]>([])
  const [entitiesTotal, setEntitiesTotal] = useState(0)
  const [entitiesPage, setEntitiesPage] = useState(0)
  const [entitiesLoading, setEntitiesLoading] = useState(false)
  const [entitiesError, setEntitiesError] = useState<string | null>(null)
  const [changingTier, setChangingTier] = useState<string | null>(null)
  const [tierError, setTierError] = useState<string | null>(null)

  // Users
  const [users, setUsers] = useState<AdminUser[]>([])
  const [usersTotal, setUsersTotal] = useState(0)
  const [usersPage, setUsersPage] = useState(0)
  const [usersLoading, setUsersLoading] = useState(false)
  const [usersError, setUsersError] = useState<string | null>(null)

  // Scrapers
  const [scrapers, setScrapers] = useState<ScraperStatus[]>([])
  const [scrapersLoading, setScrapersLoading] = useState(false)
  const [scrapersError, setScrapersError] = useState<string | null>(null)

  const LIMIT = 50

  // ── Auth check ────────────────────────────────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem('cardex_token')
    if (!token) router.replace('/dashboard/login')
  }, [router])

  // ── Fetch Stats ────────────────────────────────────────────────────────────
  const fetchStats = useCallback(async () => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      const res = await fetch(`${API}/api/v1/admin/stats`, { headers: authHeader() })
      if (res.status === 403) { setAccessDenied(true); return }
      if (!res.ok) throw new Error(`Error ${res.status}`)
      setStats(await res.json())
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'Error al cargar estadísticas')
    } finally {
      setStatsLoading(false)
    }
  }, [])

  // ── Fetch Entities ─────────────────────────────────────────────────────────
  const fetchEntities = useCallback(async (page = 0) => {
    setEntitiesLoading(true)
    setEntitiesError(null)
    try {
      const res = await fetch(`${API}/api/v1/admin/entities?limit=${LIMIT}&offset=${page * LIMIT}`, {
        headers: authHeader(),
      })
      if (res.status === 403) { setAccessDenied(true); return }
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setEntities(data.entities ?? data.items ?? [])
      setEntitiesTotal(data.total ?? 0)
    } catch (err) {
      setEntitiesError(err instanceof Error ? err.message : 'Error al cargar entidades')
    } finally {
      setEntitiesLoading(false)
    }
  }, [])

  // ── Fetch Users ─────────────────────────────────────────────────────────────
  const fetchUsers = useCallback(async (page = 0) => {
    setUsersLoading(true)
    setUsersError(null)
    try {
      const res = await fetch(`${API}/api/v1/admin/users?limit=${LIMIT}&offset=${page * LIMIT}`, {
        headers: authHeader(),
      })
      if (res.status === 403) { setAccessDenied(true); return }
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setUsers(data.users ?? data.items ?? [])
      setUsersTotal(data.total ?? 0)
    } catch (err) {
      setUsersError(err instanceof Error ? err.message : 'Error al cargar usuarios')
    } finally {
      setUsersLoading(false)
    }
  }, [])

  // ── Fetch Scrapers ──────────────────────────────────────────────────────────
  const fetchScrapers = useCallback(async () => {
    setScrapersLoading(true)
    setScrapersError(null)
    try {
      const res = await fetch(`${API}/api/v1/admin/scrapers`, { headers: authHeader() })
      if (res.status === 403) { setAccessDenied(true); return }
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setScrapers(data.scrapers ?? data.items ?? data ?? [])
    } catch (err) {
      setScrapersError(err instanceof Error ? err.message : 'Error al cargar scrapers')
    } finally {
      setScrapersLoading(false)
    }
  }, [])

  // Load data when tab changes
  useEffect(() => {
    if (tab === 'stats') fetchStats()
    if (tab === 'entities') fetchEntities(entitiesPage)
    if (tab === 'users') fetchUsers(usersPage)
    if (tab === 'scrapers') fetchScrapers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  // ── Change tier ─────────────────────────────────────────────────────────────
  async function changeTier(entityUlid: string, subscription_tier: string) {
    setChangingTier(entityUlid)
    setTierError(null)
    // Store previous tier for rollback
    const prev_tier = entities.find(e => e.entity_ulid === entityUlid)?.subscription_tier
    // Optimistic update
    setEntities(prev => prev.map(e => e.entity_ulid === entityUlid ? { ...e, subscription_tier } : e))
    try {
      const res = await fetch(`${API}/api/v1/admin/entities/${entityUlid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ subscription_tier }),
      })
      if (!res.ok) throw new Error(`Error ${res.status}`)
    } catch (err) {
      // Rollback to previous tier
      if (prev_tier) {
        setEntities(prev => prev.map(e => e.entity_ulid === entityUlid ? { ...e, subscription_tier: prev_tier } : e))
      }
      setTierError('No se pudo actualizar el tier. Inténtalo de nuevo.')
    } finally {
      setChangingTier(null)
    }
  }

  // ── Access denied ─────────────────────────────────────────────────────────
  if (accessDenied) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface p-8">
        <div className="max-w-md rounded-xl border border-red-500/30 bg-red-500/10 p-8 text-center">
          <p className="text-2xl font-bold text-red-400">Acceso restringido</p>
          <p className="mt-2 text-surface-muted">Solo administradores del sistema pueden acceder a este panel.</p>
          <button
            onClick={() => router.push('/dashboard')}
            className="mt-6 rounded-lg bg-surface-hover px-5 py-2 text-sm text-surface-muted hover:text-white transition-colors"
          >
            Volver al dashboard
          </button>
        </div>
      </div>
    )
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'stats', label: 'Stats' },
    { id: 'entities', label: 'Entidades' },
    { id: 'users', label: 'Usuarios' },
    { id: 'scrapers', label: 'Scrapers' },
  ]

  return (
    <div className="min-h-screen bg-surface">
      {/* Header */}
      <header className="border-b border-surface-border bg-surface-card px-6 py-4">
        <div className="mx-auto flex max-w-screen-xl items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg font-bold tracking-tight text-brand-400">CARDEX</span>
            <span className="text-surface-border">|</span>
            <span className="text-xs font-semibold uppercase tracking-widest text-surface-muted">Sistema · Admin</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400 sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Sistema operativo
            </span>
            <button
              onClick={() => router.push('/dashboard')}
              className="flex items-center gap-2 rounded-lg border border-surface-border px-4 py-1.5 text-sm text-surface-muted hover:text-white transition-colors"
            >
              <ChevronLeft size={14} /> Dashboard
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-screen-xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Panel de administración</h1>
          <p className="mt-1 text-sm text-surface-muted">Gestión de entidades, usuarios y monitorización del sistema.</p>
        </div>

        {/* Tabs */}
        <div className="mb-6 flex gap-1 border-b border-surface-border">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-5 py-2.5 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'border-b-2 border-brand-500 text-white'
                  : 'text-surface-muted hover:text-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── STATS TAB ── */}
        {tab === 'stats' && (
          <div>
            {statsError && (
              <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {statsError} — <button onClick={fetchStats} className="underline hover:no-underline">Reintentar</button>
              </div>
            )}
            {statsLoading ? (
              <div className="flex justify-center py-16">
                <Loader2 size={28} className="animate-spin text-brand-400" />
              </div>
            ) : stats ? (
              <>
                <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <StatCard label="Entidades activas" value={stats.total_entities} />
                  <StatCard label="Total usuarios" value={stats.total_users} />
                  <StatCard label="Listings activos" value={stats.active_listings} big />
                  <StatCard label="Scrape jobs hoy" value={stats.scrape_jobs_today} />
                  <StatCard label="Notificaciones (24h)" value={stats.notifications_24h} />
                </div>

                {/* Entidades por tier */}
                {stats.entities_by_tier && (
                  <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                    <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Entidades por tier</h3>
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-surface-border text-left">
                          <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Tier</th>
                          <th className="pb-2 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Entidades</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-border">
                        {Object.entries(stats.entities_by_tier).map(([tier, count]) => (
                          <tr key={tier} className="hover:bg-surface-hover transition-colors">
                            <td className="py-2.5">
                              <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
                                tier === 'ENTERPRISE' ? 'bg-brand-500/20 text-brand-400' :
                                tier === 'PRO' ? 'bg-purple-500/20 text-purple-400' :
                                'bg-surface-hover text-surface-muted'
                              }`}>
                                {tier}
                              </span>
                            </td>
                            <td className="py-2.5 text-right font-mono font-bold text-white">{count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <div className="py-16 text-center text-surface-muted">
                No se pudieron cargar las estadísticas.
                <button onClick={fetchStats} className="ml-2 text-brand-400 hover:underline">Reintentar</button>
              </div>
            )}
          </div>
        )}

        {/* ── ENTITIES TAB ── */}
        {tab === 'entities' && (
          <div>
            {entitiesError && (
              <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {entitiesError} — <button onClick={() => fetchEntities(entitiesPage)} className="underline hover:no-underline">Reintentar</button>
              </div>
            )}
            {tierError && (
              <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
                {tierError}
              </div>
            )}
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-surface-muted">{entitiesTotal} entidades en total</p>
              <button
                onClick={() => fetchEntities(entitiesPage)}
                disabled={entitiesLoading}
                className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white transition-colors disabled:opacity-50"
              >
                <RefreshCw size={13} className={entitiesLoading ? 'animate-spin' : ''} /> Actualizar
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
              {entitiesLoading ? (
                <div className="flex justify-center py-16">
                  <Loader2 size={24} className="animate-spin text-brand-400" />
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-left">
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Nombre legal</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">País</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Tier</th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Usuarios</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted hidden md:table-cell">Registro</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {entities.map(entity => (
                      <tr key={entity.entity_ulid} className="hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3 font-medium text-white">{entity.legal_name}</td>
                        <td className="px-4 py-3 text-surface-muted">{entity.country_code}</td>
                        <td className="px-4 py-3">
                          <select
                            value={entity.subscription_tier}
                            onChange={e => changeTier(entity.entity_ulid, e.target.value)}
                            disabled={changingTier === entity.entity_ulid}
                            className={`rounded-lg border px-2 py-1 text-xs font-semibold focus:outline-none cursor-pointer ${
                              entity.subscription_tier === 'ENTERPRISE' ? 'border-brand-500/30 bg-brand-500/10 text-brand-400' :
                              entity.subscription_tier === 'PRO' ? 'border-purple-500/30 bg-purple-500/10 text-purple-400' :
                              'border-surface-border bg-surface-hover text-surface-muted'
                            }`}
                          >
                            {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
                          </select>
                          {changingTier === entity.entity_ulid && (
                            <Loader2 size={12} className="ml-2 inline animate-spin text-brand-400" />
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-surface-muted">{entity.user_count}</td>
                        <td className="px-4 py-3 text-surface-muted hidden md:table-cell">{formatDate(entity.created_at)}</td>
                      </tr>
                    ))}
                    {entities.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-12 text-center text-surface-muted">No hay entidades.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>

            {/* Entities Pagination */}
            {entitiesTotal > LIMIT && (
              <div className="mt-4 flex items-center justify-between text-sm text-surface-muted">
                <span>
                  Mostrando {entitiesPage * LIMIT + 1}–{Math.min((entitiesPage + 1) * LIMIT, entitiesTotal)} de {entitiesTotal}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => { const p = entitiesPage - 1; setEntitiesPage(p); fetchEntities(p) }}
                    disabled={entitiesPage === 0 || entitiesLoading}
                    className="flex items-center gap-1 rounded-lg border border-surface-border px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
                  >
                    <ChevronLeft size={14} /> Anterior
                  </button>
                  <button
                    onClick={() => { const p = entitiesPage + 1; setEntitiesPage(p); fetchEntities(p) }}
                    disabled={(entitiesPage + 1) * LIMIT >= entitiesTotal || entitiesLoading}
                    className="flex items-center gap-1 rounded-lg border border-surface-border px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
                  >
                    Siguiente <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── USERS TAB ── */}
        {tab === 'users' && (
          <div>
            {usersError && (
              <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {usersError} — <button onClick={() => fetchUsers(usersPage)} className="underline hover:no-underline">Reintentar</button>
              </div>
            )}
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-surface-muted">{usersTotal} usuarios en total</p>
              <button
                onClick={() => fetchUsers(usersPage)}
                disabled={usersLoading}
                className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white transition-colors disabled:opacity-50"
              >
                <RefreshCw size={13} className={usersLoading ? 'animate-spin' : ''} /> Actualizar
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
              {usersLoading ? (
                <div className="flex justify-center py-16">
                  <Loader2 size={24} className="animate-spin text-brand-400" />
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-left">
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Email</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted hidden sm:table-cell">Nombre</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted hidden md:table-cell">Entidad</th>
                      <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-surface-muted">Dealer</th>
                      <th className="px-4 py-3 text-center text-xs font-medium uppercase tracking-wider text-surface-muted hidden lg:table-cell">Email verif.</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted hidden lg:table-cell">Registrado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {users.map(user => (
                      <tr key={user.user_ulid} className="hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3 font-mono text-xs text-white">{user.email}</td>
                        <td className="px-4 py-3 text-surface-muted hidden sm:table-cell">{user.full_name || '—'}</td>
                        <td className="px-4 py-3 font-mono text-xs text-surface-muted hidden md:table-cell">{user.entity_ulid || '—'}</td>
                        <td className="px-4 py-3 text-center">
                          <span className={`text-xs font-medium ${user.is_dealer ? 'text-brand-400' : 'text-surface-muted'}`}>
                            {user.is_dealer ? 'Sí' : 'No'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center hidden lg:table-cell">
                          <span className={`text-xs font-medium ${user.email_verified ? 'text-emerald-400' : 'text-red-400'}`}>
                            {user.email_verified ? '✓' : '✗'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-surface-muted hidden lg:table-cell">{formatDate(user.created_at)}</td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-12 text-center text-surface-muted">No hay usuarios.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>

            {/* Users Pagination */}
            {usersTotal > LIMIT && (
              <div className="mt-4 flex items-center justify-between text-sm text-surface-muted">
                <span>
                  Mostrando {usersPage * LIMIT + 1}–{Math.min((usersPage + 1) * LIMIT, usersTotal)} de {usersTotal}
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => { const p = usersPage - 1; setUsersPage(p); fetchUsers(p) }}
                    disabled={usersPage === 0 || usersLoading}
                    className="flex items-center gap-1 rounded-lg border border-surface-border px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
                  >
                    <ChevronLeft size={14} /> Anterior
                  </button>
                  <button
                    onClick={() => { const p = usersPage + 1; setUsersPage(p); fetchUsers(p) }}
                    disabled={(usersPage + 1) * LIMIT >= usersTotal || usersLoading}
                    className="flex items-center gap-1 rounded-lg border border-surface-border px-3 py-1.5 hover:text-white disabled:opacity-40 transition-colors"
                  >
                    Siguiente <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── SCRAPERS TAB ── */}
        {tab === 'scrapers' && (
          <div>
            {scrapersError && (
              <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                {scrapersError} — <button onClick={fetchScrapers} className="underline hover:no-underline">Reintentar</button>
              </div>
            )}
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm text-surface-muted">Estado de los scrapers del sistema</p>
              <button
                onClick={fetchScrapers}
                disabled={scrapersLoading}
                className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white transition-colors disabled:opacity-50"
              >
                <RefreshCw size={13} className={scrapersLoading ? 'animate-spin' : ''} /> Actualizar
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
              {scrapersLoading ? (
                <div className="flex justify-center py-16">
                  <Loader2 size={24} className="animate-spin text-brand-400" />
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-left">
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Plataforma</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Estado</th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Registros</th>
                      <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted hidden md:table-cell">Último run</th>
                      <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-surface-muted hidden md:table-cell">Lag (min)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-border">
                    {scrapers.map(scraper => (
                      <tr key={scraper.platform} className="hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3 font-medium text-white">{scraper.platform}</td>
                        <td className="px-4 py-3">
                          <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${SCRAPER_STATUS_BADGE[scraper.status] ?? 'bg-surface-hover text-surface-muted border border-surface-border'}`}>
                            {scraper.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-surface-muted">
                          {scraper.record_count.toLocaleString('es-ES')}
                        </td>
                        <td className="px-4 py-3 text-surface-muted hidden md:table-cell">
                          {formatDate(scraper.last_run_at)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono hidden md:table-cell">
                          {scraper.lag_minutes != null ? (
                            <span className={scraper.lag_minutes > 60 ? 'text-red-400' : scraper.lag_minutes > 30 ? 'text-amber-400' : 'text-emerald-400'}>
                              {scraper.lag_minutes}
                            </span>
                          ) : (
                            <span className="text-surface-muted">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {scrapers.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-12 text-center text-surface-muted">No hay datos de scrapers.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
