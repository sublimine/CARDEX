'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type LifecycleStatus =
  | 'SOURCING'
  | 'PURCHASED'
  | 'RECONDITIONING'
  | 'READY'
  | 'LISTED'
  | 'RESERVED'
  | 'SOLD'
  | 'ARCHIVED'

interface Vehicle {
  crm_vehicle_ulid: string
  make: string
  model: string
  year: number
  mileage_km: number
  lifecycle_status: LifecycleStatus
  asking_price_eur: number
  floor_price_eur: number
  total_cost_eur: number
  margin_pct: number
  days_in_stock: number
  main_photo_url: string | null
}

interface VehiclesResponse {
  vehicles: Vehicle[]
  total: number
  page: number
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const STATUS_BADGE: Record<LifecycleStatus, string> = {
  SOURCING: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  PURCHASED: 'bg-blue-900/40 text-blue-400 border border-blue-500/20',
  RECONDITIONING: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  READY: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30',
  LISTED: 'bg-brand-500/20 text-brand-400 border border-brand-500/30',
  RESERVED: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  SOLD: 'bg-surface-hover text-surface-muted border border-surface-border',
  ARCHIVED: 'bg-surface-hover text-surface-muted/60 border border-surface-border',
}

const FILTER_STATUSES = ['ALL', 'SOURCING', 'RECONDITIONING', 'LISTED', 'RESERVED', 'SOLD'] as const
type FilterStatus = (typeof FILTER_STATUSES)[number]

const SORT_OPTIONS = [
  { value: 'days_in_stock_desc', label: 'Days In Stock ↓' },
  { value: 'days_in_stock_asc', label: 'Days In Stock ↑' },
  { value: 'asking_price_desc', label: 'Price ↓' },
  { value: 'asking_price_asc', label: 'Price ↑' },
  { value: 'margin_desc', label: 'Margin ↓' },
  { value: 'margin_asc', label: 'Margin ↑' },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatEur(value: number): string {
  return '€\u00a0' + value.toLocaleString('en-IE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function domBadge(days: number): string {
  if (days > 60) return 'bg-red-500/20 text-red-400 border border-red-500/30'
  if (days > 30) return 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
  return 'bg-surface-hover text-surface-muted border border-surface-border'
}

function marginClass(pct: number): string {
  if (pct < 5) return 'text-red-400'
  if (pct < 10) return 'text-amber-400'
  return 'text-brand-400'
}

function sortVehicles(vehicles: Vehicle[], sort: string): Vehicle[] {
  const v = [...vehicles]
  switch (sort) {
    case 'days_in_stock_desc': return v.sort((a, b) => b.days_in_stock - a.days_in_stock)
    case 'days_in_stock_asc': return v.sort((a, b) => a.days_in_stock - b.days_in_stock)
    case 'asking_price_desc': return v.sort((a, b) => b.asking_price_eur - a.asking_price_eur)
    case 'asking_price_asc': return v.sort((a, b) => a.asking_price_eur - b.asking_price_eur)
    case 'margin_desc': return v.sort((a, b) => b.margin_pct - a.margin_pct)
    case 'margin_asc': return v.sort((a, b) => a.margin_pct - b.margin_pct)
    default: return v
  }
}

const PAGE_SIZE = 25

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------
function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="h-14 rounded-lg bg-surface-hover" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function CrmInventoryPage() {
  const router = useRouter()

  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filterStatus, setFilterStatus] = useState<FilterStatus>('ALL')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('days_in_stock_desc')

  const fetchVehicles = useCallback(async (pg: number) => {
    const token = localStorage.getItem('cardex_token')
    if (!token) { router.replace('/dashboard/login'); return }
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ page: pg.toString(), per_page: PAGE_SIZE.toString() })
      if (filterStatus !== 'ALL') params.set('status', filterStatus)
      if (search.trim()) params.set('q', search.trim())

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/vehicles?${params}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      if (res.status === 401) { router.replace('/dashboard/login'); return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json: VehiclesResponse = await res.json()
      setVehicles(json.vehicles)
      setTotal(json.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load inventory')
    } finally {
      setLoading(false)
    }
  }, [router, filterStatus, search])

  useEffect(() => {
    setPage(1)
    fetchVehicles(1)
  }, [filterStatus, search]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchVehicles(page)
  }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  const sorted = sortVehicles(vehicles, sort)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">CRM Inventory</h1>
          <p className="mt-1 text-sm text-surface-muted">{total} vehicles</p>
        </div>
        <Link
          href="/dashboard/crm/vehicles/new"
          className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          + Add Vehicle
        </Link>
      </div>

      {/* Filter bar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Status pills */}
        <div className="flex flex-wrap gap-1.5">
          {FILTER_STATUSES.map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filterStatus === s
                  ? 'bg-brand-500 text-white'
                  : 'border border-surface-border text-surface-muted hover:text-white'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Search */}
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search make, model…"
          className="w-48 rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
        />

        {/* Sort */}
        <select
          value={sort}
          onChange={e => setSort(e.target.value)}
          className="rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-xl border border-red-500/50 bg-red-500/10 p-4 text-center">
          <p className="mb-2 text-sm text-red-400">{error}</p>
          <button
            onClick={() => fetchVehicles(page)}
            className="rounded-lg bg-red-500/20 px-4 py-1.5 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
        {loading ? (
          <div className="p-4"><TableSkeleton /></div>
        ) : sorted.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-surface-muted">No vehicles found.</p>
            <Link
              href="/dashboard/crm/vehicles/new"
              className="mt-3 inline-block text-sm text-brand-400 hover:text-brand-300"
            >
              Add your first vehicle →
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-surface-border text-left">
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Photo</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Vehicle</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Status</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Days In Stock</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Asking Price</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Cost</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Margin %</th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {sorted.map(v => (
                  <tr
                    key={v.crm_vehicle_ulid}
                    onClick={() => router.push(`/dashboard/crm/vehicles/${v.crm_vehicle_ulid}`)}
                    className="cursor-pointer transition-colors hover:bg-surface-hover"
                  >
                    {/* Photo */}
                    <td className="px-4 py-3">
                      <div className="relative h-10 w-14 overflow-hidden rounded-md bg-surface-hover">
                        {v.main_photo_url ? (
                          <Image
                            src={v.main_photo_url}
                            alt={`${v.make} ${v.model}`}
                            fill
                            className="object-cover"
                            sizes="56px"
                          />
                        ) : (
                          <span className="flex h-full w-full items-center justify-center text-xs text-surface-muted">
                            —
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Vehicle */}
                    <td className="px-4 py-3">
                      <p className="font-medium text-white">
                        {v.year} {v.make} {v.model}
                      </p>
                      <p className="text-xs text-surface-muted">
                        {v.mileage_km.toLocaleString('en-IE')} km
                      </p>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_BADGE[v.lifecycle_status]}`}>
                        {v.lifecycle_status}
                      </span>
                    </td>

                    {/* Days in stock */}
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 font-mono text-xs font-medium ${domBadge(v.days_in_stock)}`}>
                        {v.days_in_stock}d
                      </span>
                    </td>

                    {/* Asking price */}
                    <td className="px-4 py-3 font-mono text-sm text-white">
                      {formatEur(v.asking_price_eur)}
                    </td>

                    {/* Cost */}
                    <td className="px-4 py-3 font-mono text-sm text-surface-muted">
                      {formatEur(v.total_cost_eur)}
                    </td>

                    {/* Margin */}
                    <td className="px-4 py-3 font-mono text-sm">
                      <span className={marginClass(v.margin_pct)}>
                        {v.margin_pct.toFixed(1)}%
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          router.push(`/dashboard/crm/vehicles/${v.crm_vehicle_ulid}`)
                        }}
                        className="rounded-lg border border-surface-border px-3 py-1 text-xs text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="text-sm text-surface-muted">
            Page {page} of {totalPages} · {total} vehicles
          </p>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white disabled:opacity-40 transition-colors"
            >
              ← Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white disabled:opacity-40 transition-colors"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
