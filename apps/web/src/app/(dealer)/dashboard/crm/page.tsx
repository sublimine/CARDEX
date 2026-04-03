'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface DashboardData {
  inventory: {
    total: number
    by_status: Record<string, number>
  }
  pipeline: {
    open_deals: number
    pipeline_value_eur: number
  }
  mtd: {
    units_sold: number
    revenue_eur: number
    avg_margin_pct: number
    avg_dom: number
  }
  top_contacts: Array<{
    contact_ulid: string
    full_name: string
    lifetime_value_eur: number
    total_purchases: number
  }>
  risk_alerts: Array<{
    crm_vehicle_ulid: string
    make: string
    model: string
    year: number
    asking_price_eur: number
    floor_price_eur: number
  }>
  upcoming_closes: Array<{
    deal_ulid: string
    title: string
    contact_name: string
    deal_value_eur: number
    expected_close: string
  }>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatEur(value: number): string {
  return '€\u00a0' + value.toLocaleString('en-IE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function daysUntil(iso: string): number {
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000)
}

function formatCloseDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IE', { day: 'numeric', month: 'short' })
}

// ---------------------------------------------------------------------------
// Status bar segment config
// ---------------------------------------------------------------------------
const STATUS_COLORS: Record<string, string> = {
  SOURCING: 'bg-purple-500',
  PURCHASED: 'bg-blue-500',
  RECONDITIONING: 'bg-amber-500',
  READY: 'bg-cyan-400',
  LISTED: 'bg-brand-500',
  RESERVED: 'bg-yellow-400',
  SOLD: 'bg-surface-muted',
}

const STATUS_TEXT_COLORS: Record<string, string> = {
  SOURCING: 'text-purple-400',
  PURCHASED: 'text-blue-400',
  RECONDITIONING: 'text-amber-400',
  READY: 'text-cyan-400',
  LISTED: 'text-brand-400',
  RESERVED: 'text-yellow-400',
  SOLD: 'text-surface-muted',
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <p className="text-xs font-medium uppercase tracking-wider text-surface-muted">{label}</p>
      <p className="mt-2 font-mono text-2xl font-bold text-white">{value}</p>
      {sub && <p className="mt-1 text-xs text-surface-muted">{sub}</p>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8 animate-pulse">
      <div className="mb-8 h-8 w-40 rounded bg-surface-hover" />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 rounded-xl bg-surface-hover" />
        ))}
      </div>
      <div className="mb-6 h-16 rounded-xl bg-surface-hover" />
      <div className="grid gap-4 lg:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-64 rounded-xl bg-surface-hover" />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function CrmDashboardPage() {
  const router = useRouter()
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDashboard = useCallback(async () => {
    const token = localStorage.getItem('cardex_token')
    if (!token) {
      router.replace('/dashboard/login')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) {
        router.replace('/dashboard/login')
        return
      }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => { fetchDashboard() }, [fetchDashboard])

  if (loading) return <LoadingSkeleton />

  if (error) {
    return (
      <div className="mx-auto max-w-screen-xl px-4 py-8">
        <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-6 text-center">
          <p className="mb-3 text-red-400">{error}</p>
          <button
            onClick={fetchDashboard}
            className="rounded-lg bg-red-500/20 px-4 py-2 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  // Inventory status bar
  const statusTotal = Object.values(data.inventory.by_status).reduce((a, b) => a + b, 0)
  const STATUS_ORDER = ['SOURCING', 'PURCHASED', 'RECONDITIONING', 'READY', 'LISTED', 'RESERVED', 'SOLD']

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">CRM Dashboard</h1>
        <p className="mt-1 text-sm text-surface-muted">Overview of your inventory, pipeline and performance</p>
      </div>

      {/* ── Row 1: KPI cards ── */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Active Inventory"
          value={data.inventory.total.toString()}
          sub="vehicles across all stages"
        />
        <KpiCard
          label="Open Deals"
          value={data.pipeline.open_deals.toString()}
          sub={`${formatEur(data.pipeline.pipeline_value_eur)} pipeline value`}
        />
        <KpiCard
          label="MTD Revenue"
          value={formatEur(data.mtd.revenue_eur)}
          sub={`${data.mtd.units_sold} units · ${data.mtd.avg_margin_pct.toFixed(1)}% avg margin`}
        />
        <KpiCard
          label="Avg Days In Stock"
          value={data.mtd.avg_dom.toFixed(0) + ' d'}
          sub="month-to-date average"
        />
      </div>

      {/* ── Row 2: Inventory status breakdown bar ── */}
      <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5">
        <p className="mb-3 text-xs font-medium uppercase tracking-wider text-surface-muted">
          Inventory by Status
        </p>
        {statusTotal > 0 ? (
          <>
            {/* Segmented bar */}
            <div className="flex h-4 overflow-hidden rounded-full">
              {STATUS_ORDER.filter(s => (data.inventory.by_status[s] ?? 0) > 0).map(status => (
                <div
                  key={status}
                  className={`${STATUS_COLORS[status] ?? 'bg-surface-hover'} transition-all`}
                  style={{ width: `${((data.inventory.by_status[status] ?? 0) / statusTotal) * 100}%` }}
                  title={`${status}: ${data.inventory.by_status[status]}`}
                />
              ))}
            </div>
            {/* Legend */}
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
              {STATUS_ORDER.filter(s => (data.inventory.by_status[s] ?? 0) > 0).map(status => (
                <div key={status} className="flex items-center gap-1.5">
                  <span className={`inline-block h-2.5 w-2.5 rounded-full ${STATUS_COLORS[status] ?? 'bg-surface-hover'}`} />
                  <span className={`text-xs ${STATUS_TEXT_COLORS[status] ?? 'text-surface-muted'}`}>
                    {status}
                  </span>
                  <span className="font-mono text-xs text-white">{data.inventory.by_status[status]}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-surface-muted">No inventory data available.</p>
        )}
      </div>

      {/* ── Row 3: Risk Alerts / Upcoming Closes / Top Contacts ── */}
      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        {/* Risk Alerts */}
        <div className="rounded-xl border border-red-500/40 bg-surface-card p-5">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-red-400">
            Risk Alerts — Pricing
          </p>
          {data.risk_alerts.length === 0 ? (
            <p className="text-sm text-surface-muted">No risk alerts. All vehicles priced safely above floor.</p>
          ) : (
            <ul className="space-y-3">
              {data.risk_alerts.map(v => {
                const margin = ((v.asking_price_eur - v.floor_price_eur) / v.floor_price_eur) * 100
                return (
                  <li key={v.crm_vehicle_ulid} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                    <Link
                      href={`/dashboard/crm/vehicles/${v.crm_vehicle_ulid}`}
                      className="mb-1 block font-medium text-white hover:text-brand-400 transition-colors"
                    >
                      {v.year} {v.make} {v.model}
                    </Link>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-surface-muted">Asking</span>
                      <span className="font-mono text-red-400">{formatEur(v.asking_price_eur)}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-surface-muted">Floor</span>
                      <span className="font-mono text-surface-muted">{formatEur(v.floor_price_eur)}</span>
                    </div>
                    <div className="mt-1 text-xs text-red-400">
                      Only {margin.toFixed(1)}% above floor (min 5% required)
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Upcoming Closes */}
        <div className="rounded-xl border border-amber-500/40 bg-surface-card p-5">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-amber-400">
            Closing Within 7 Days
          </p>
          {data.upcoming_closes.length === 0 ? (
            <p className="text-sm text-surface-muted">No deals closing in the next 7 days.</p>
          ) : (
            <ul className="space-y-3">
              {data.upcoming_closes.map(deal => {
                const days = daysUntil(deal.expected_close)
                return (
                  <li key={deal.deal_ulid} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                    <Link
                      href={`/dashboard/crm/pipeline`}
                      className="mb-1 block font-medium text-white hover:text-brand-400 transition-colors"
                    >
                      {deal.title}
                    </Link>
                    <p className="text-xs text-surface-muted">{deal.contact_name}</p>
                    <div className="mt-1 flex items-center justify-between text-xs">
                      <span className="text-amber-400">
                        {formatCloseDate(deal.expected_close)} ({days === 0 ? 'today' : `${days}d`})
                      </span>
                      <span className="font-mono text-white">{formatEur(deal.deal_value_eur)}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Top Contacts */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-5">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-surface-muted">
            Top Contacts by Value
          </p>
          {data.top_contacts.length === 0 ? (
            <p className="text-sm text-surface-muted">No contact data yet.</p>
          ) : (
            <ul className="space-y-3">
              {data.top_contacts.map((c, idx) => (
                <li key={c.contact_ulid} className="flex items-center gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-hover font-mono text-xs text-surface-muted">
                    {idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/dashboard/crm/contacts`}
                      className="block truncate font-medium text-white hover:text-brand-400 transition-colors text-sm"
                    >
                      {c.full_name}
                    </Link>
                    <p className="text-xs text-surface-muted">{c.total_purchases} purchases</p>
                  </div>
                  <span className="font-mono text-sm text-brand-400">{formatEur(c.lifetime_value_eur)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── Bottom bar: Quick actions ── */}
      <div className="flex flex-wrap gap-3">
        <Link
          href="/dashboard/crm/inventory/new"
          className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-medium text-white hover:border-brand-500/50 hover:bg-surface-hover transition-colors"
        >
          <span className="text-brand-400">+</span> Add Vehicle
        </Link>
        <Link
          href="/dashboard/crm/contacts/new"
          className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-medium text-white hover:border-brand-500/50 hover:bg-surface-hover transition-colors"
        >
          <span className="text-brand-400">+</span> Add Contact
        </Link>
        <Link
          href="/dashboard/crm/communications/new"
          className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-medium text-white hover:border-brand-500/50 hover:bg-surface-hover transition-colors"
        >
          <span className="text-brand-400">+</span> Log Call
        </Link>
        <Link
          href="/dashboard/crm/pipeline"
          className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          Pipeline View →
        </Link>
      </div>
    </div>
  )
}
