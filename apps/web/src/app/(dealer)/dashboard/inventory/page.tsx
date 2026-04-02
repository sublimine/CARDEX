'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Plus, Search, Car, MoreHorizontal, Loader2, RefreshCw, AlertCircle, BarChart2 } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

interface Vehicle {
  crm_vehicle_ulid: string
  make: string
  model: string
  year: number
  purchase_price_eur?: number
  asking_price_eur?: number
  mileage_km?: number
  vin?: string
  lifecycle_status: string
  fuel_type?: string
  transmission?: string
  color?: string
  created_at: string
}

const STATUS_BADGE: Record<string, string> = {
  SOURCING:       'bg-blue-500/20 text-blue-400',
  PURCHASED:      'bg-sky-500/20 text-sky-400',
  RECONDITIONING: 'bg-orange-500/20 text-orange-400',
  READY:          'bg-emerald-500/20 text-emerald-400',
  LISTED:         'bg-brand-500/20 text-brand-400',
  RESERVED:       'bg-yellow-500/20 text-yellow-400',
  SOLD:           'bg-surface-hover text-surface-muted',
  RETURNED:       'bg-red-500/20 text-red-400',
  ARCHIVED:       'bg-surface-hover text-surface-muted',
}

const STATUS_LABEL: Record<string, string> = {
  SOURCING:       'Adquisición',
  PURCHASED:      'Comprado',
  RECONDITIONING: 'En taller',
  READY:          'Listo',
  LISTED:         'Publicado',
  RESERVED:       'Reservado',
  SOLD:           'Vendido',
  RETURNED:       'Devuelto',
  ARCHIVED:       'Archivado',
}

// ── Turn-time badge ──────────────────────────────────────────────────────────
function TurnTimeBadge({ days }: { days: number }) {
  if (days <= 20)
    return <span className="rounded-md bg-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">~{days}d ↑</span>
  if (days <= 45)
    return <span className="rounded-md bg-yellow-500/20 px-2 py-0.5 text-xs font-semibold text-yellow-400">~{days}d</span>
  return <span className="rounded-md bg-red-500/20 px-2 py-0.5 text-xs font-semibold text-red-400">~{days}d ↓</span>
}

export default function InventoryPage() {
  const router = useRouter()
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [turnTimes, setTurnTimes] = useState<Record<string, number | null>>({})
  const [analyzingMarket, setAnalyzingMarket] = useState(false)
  const LIMIT = 30

  const fetchVehicles = useCallback(async (pageNum = 1, reset = false) => {
    const params = new URLSearchParams({
      limit: String(LIMIT),
      page: String(pageNum),
    })
    if (statusFilter) params.set('status', statusFilter)
    if (search.length >= 2) params.set('search', search)

    try {
      const res = await fetch(`${API}/api/v1/dealer/crm/vehicles?${params}`, {
        headers: authHeader(),
      })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.message ?? 'Error cargando inventario.')
        return
      }
      const data = await res.json()
      const incoming: Vehicle[] = data.vehicles ?? []
      setVehicles(prev => reset ? incoming : [...prev, ...incoming])
      setHasMore(incoming.length === LIMIT)
      setError('')
    } catch {
      setError('Error de red. Comprueba tu conexión.')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, router])

  useEffect(() => {
    setLoading(true)
    setPage(1)
    setVehicles([])
    const timer = setTimeout(() => fetchVehicles(1, true), search ? 350 : 0)
    return () => clearTimeout(timer)
  }, [search, statusFilter, fetchVehicles])

  const loadMore = () => {
    const next = page + 1
    setPage(next)
    fetchVehicles(next, false)
  }

  async function analyzeMarket() {
    if (vehicles.length === 0) return
    setAnalyzingMarket(true)
    const results: Record<string, number | null> = {}
    await Promise.allSettled(
      vehicles.map(async v => {
        const params = new URLSearchParams()
        if (v.make) params.set('make', v.make)
        if (v.model) params.set('model', v.model)
        if (v.year) params.set('year', String(v.year))
        if (v.asking_price_eur) params.set('price_eur', String(v.asking_price_eur))
        // country not available in vehicle object, skip it
        try {
          const res = await fetch(`${API}/api/v1/analytics/turn-time?${params}`)
          if (res.ok) {
            const data = await res.json()
            results[v.crm_vehicle_ulid] = data.predicted_turn_days ?? null
          } else {
            results[v.crm_vehicle_ulid] = null
          }
        } catch {
          results[v.crm_vehicle_ulid] = null
        }
      })
    )
    setTurnTimes(prev => ({ ...prev, ...results }))
    setAnalyzingMarket(false)
  }

  const filteredDisplay = vehicles // filtering already happens server-side

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Inventario</h1>
          <p className="mt-1 text-sm text-surface-muted">
            {loading ? 'Cargando…' : `${vehicles.length}${hasMore ? '+' : ''} vehículos`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={analyzeMarket}
            disabled={analyzingMarket || vehicles.length === 0}
            className="flex shrink-0 items-center gap-2 rounded-xl border border-surface-border px-4 py-2.5 text-sm font-medium text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
          >
            {analyzingMarket ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BarChart2 size={14} />
            )}
            Analizar mercado
          </button>
          <Link
            href="/dashboard/inventory/new"
            className="flex shrink-0 items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 font-medium text-white hover:bg-brand-600 transition-colors"
          >
            <Plus size={16} /> Añadir
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-muted" />
          <input
            type="text"
            placeholder="Buscar por marca, modelo, VIN…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full rounded-xl border border-surface-border bg-surface-card pl-9 pr-4 py-2.5 text-sm text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="rounded-xl border border-surface-border bg-surface-card px-4 py-2.5 text-sm text-white focus:border-brand-500 focus:outline-none"
        >
          <option value="">Todos los estados</option>
          <option value="SOURCING">Adquisición</option>
          <option value="PURCHASED">Comprado</option>
          <option value="RECONDITIONING">En taller</option>
          <option value="READY">Listo</option>
          <option value="LISTED">Publicado</option>
          <option value="RESERVED">Reservado</option>
          <option value="SOLD">Vendido</option>
          <option value="RETURNED">Devuelto</option>
        </select>
        <button
          onClick={() => { setLoading(true); fetchVehicles(1, true) }}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-surface-border px-4 py-2.5 text-sm text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Actualizar
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle size={16} className="shrink-0" />
          {error}
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
        {loading && vehicles.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={28} className="animate-spin text-brand-400" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="px-4 py-3 text-left font-medium text-surface-muted">Vehículo</th>
                <th className="px-4 py-3 text-right font-medium text-surface-muted">Precio venta</th>
                <th className="px-4 py-3 text-right font-medium text-surface-muted hidden sm:table-cell">Km</th>
                <th className="px-4 py-3 text-center font-medium text-surface-muted hidden md:table-cell">Estado</th>
                <th className="px-4 py-3 text-right font-medium text-surface-muted hidden lg:table-cell">Precio compra</th>
                <th className="px-4 py-3 text-center font-medium text-surface-muted hidden lg:table-cell">Turn-time</th>
                <th className="px-4 py-3 text-left font-medium text-surface-muted hidden xl:table-cell">VIN</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filteredDisplay.map((v, i) => (
                <tr
                  key={v.crm_vehicle_ulid}
                  className={`border-b border-surface-border hover:bg-surface-hover transition-colors cursor-pointer ${i === filteredDisplay.length - 1 ? 'border-0' : ''}`}
                  onClick={() => router.push(`/dashboard/crm/vehicles/${v.crm_vehicle_ulid}`)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-hover text-surface-muted">
                        <Car size={16} />
                      </div>
                      <div>
                        <p className="font-medium text-white">
                          {v.make} {v.model}
                        </p>
                        <p className="text-xs text-surface-muted">
                          {v.year}{v.fuel_type ? ` · ${v.fuel_type}` : ''}{v.transmission ? ` · ${v.transmission}` : ''}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-semibold text-white">
                    {v.asking_price_eur != null ? `€${v.asking_price_eur.toLocaleString('es-ES')}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-surface-muted hidden sm:table-cell">
                    {v.mileage_km != null ? `${v.mileage_km.toLocaleString('es-ES')} km` : '—'}
                  </td>
                  <td className="px-4 py-3 text-center hidden md:table-cell">
                    <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[v.lifecycle_status] ?? 'bg-surface-hover text-surface-muted'}`}>
                      {STATUS_LABEL[v.lifecycle_status] ?? v.lifecycle_status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-surface-muted hidden lg:table-cell">
                    {v.purchase_price_eur != null ? `€${v.purchase_price_eur.toLocaleString('es-ES')}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-center hidden lg:table-cell">
                    {analyzingMarket ? (
                      <Loader2 size={12} className="mx-auto animate-spin text-surface-muted" />
                    ) : turnTimes[v.crm_vehicle_ulid] != null ? (
                      <TurnTimeBadge days={turnTimes[v.crm_vehicle_ulid]!} />
                    ) : (
                      <span className="text-xs text-surface-muted">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden xl:table-cell">
                    <span className="font-mono text-xs text-surface-muted">{v.vin ?? '—'}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={e => e.stopPropagation()}
                      className="rounded-lg p-1.5 text-surface-muted hover:bg-surface-hover hover:text-white transition-colors"
                    >
                      <MoreHorizontal size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && filteredDisplay.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center">
                    <Car size={32} className="mx-auto mb-3 text-surface-muted" strokeWidth={1.2} />
                    <p className="text-surface-muted">
                      {search || statusFilter ? 'No se encontraron vehículos con ese filtro.' : 'Tu inventario está vacío.'}
                    </p>
                    {!search && !statusFilter && (
                      <Link
                        href="/dashboard/inventory/new"
                        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
                      >
                        <Plus size={14} /> Añadir primer vehículo
                      </Link>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Load more */}
      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loading}
          className="mt-4 w-full rounded-xl border border-surface-border py-3 text-sm text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="mx-auto animate-spin" /> : 'Cargar más'}
        </button>
      )}
    </div>
  )
}
