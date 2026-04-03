'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Car, Users, BarChart2, TrendingUp, AlertCircle, Loader2,
  Plus, BarChart, Activity, Megaphone,
} from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

// ── MDS Types ─────────────────────────────────────────────────────────────────

interface MdsEntry {
  make: string
  model: string
  country: string
  mds_days: number
  demand_rating: string
}

function DemandBadge({ rating }: { rating: string }) {
  if (rating === 'HIGH') return (
    <span className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-400">ALTA</span>
  )
  if (rating === 'MEDIUM') return (
    <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-xs font-semibold text-amber-400">MEDIA</span>
  )
  return (
    <span className="rounded-md bg-red-500/15 px-2 py-0.5 text-xs font-semibold text-red-400">BAJA</span>
  )
}

function MdsWidget() {
  const [mdsData, setMdsData] = useState<MdsEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API}/api/v1/analytics/mds`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return
        const entries: MdsEntry[] = data.results ?? []
        const sorted = [...entries].sort((a, b) => a.mds_days - b.mds_days).slice(0, 5)
        setMdsData(sorted)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Market Days&apos; Supply</h2>
          <p className="mt-0.5 text-xs text-surface-muted">Días de stock por modelo · Top demanda</p>
        </div>
        <Link href="/analytics" className="text-xs text-brand-400 hover:text-brand-300 transition-colors">
          Ver análisis completo →
        </Link>
      </div>

      {loading ? (
        <div className="flex justify-center py-6">
          <Loader2 size={20} className="animate-spin text-brand-400" />
        </div>
      ) : mdsData.length === 0 ? (
        <p className="py-4 text-center text-sm text-surface-muted">No hay datos de mercado disponibles.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-left">
                <th className="pb-2.5 text-xs font-medium uppercase tracking-wider text-surface-muted">Marca · Modelo</th>
                <th className="pb-2.5 text-xs font-medium uppercase tracking-wider text-surface-muted hidden sm:table-cell">País</th>
                <th className="pb-2.5 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">MDS (días)</th>
                <th className="pb-2.5 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Demanda</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/60">
              {mdsData.map((entry, i) => (
                <tr key={i} className="hover:bg-surface-hover/50 transition-colors">
                  <td className="py-3">
                    <span className="font-medium text-white">{entry.make}</span>
                    <span className="ml-1.5 text-surface-muted">{entry.model}</span>
                  </td>
                  <td className="py-3 text-surface-muted hidden sm:table-cell">{entry.country}</td>
                  <td className="py-3 text-right font-mono font-bold text-white">{entry.mds_days}</td>
                  <td className="py-3 text-right">
                    <DemandBadge rating={entry.demand_rating} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Auth helper ───────────────────────────────────────────────────────────────

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Dashboard data ────────────────────────────────────────────────────────────

interface DashboardData {
  inventory?: { total: number; by_status: Record<string, number> }
  pipeline?: { open_deals: number; pipeline_value_eur: number }
  mtd?: { units_sold: number; revenue_eur: number; avg_margin_pct: number; avg_dom: number }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DealerDashboard() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [kpis, setKpis] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const t = localStorage.getItem('cardex_token')
    setToken(t)
    if (!t) { setLoading(false); return }

    fetch(`${API}/api/v1/dealer/crm/dashboard`, { headers: authHeader() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setKpis(data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [router])

  if (!token) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 px-4 text-center">
        <div className="mb-2">
          <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-brand-500">Cardex Intelligence Platform</p>
          <h1 className="text-3xl font-bold text-white">Portal del Concesionario</h1>
          <p className="mt-3 max-w-md text-sm text-surface-muted">
            Gestión de inventario, inteligencia de precios en tiempo real, seguimiento de leads y publicación multicanal.
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/dashboard/login"
            className="rounded-lg bg-brand-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 transition-colors"
          >
            Iniciar sesión
          </Link>
          <Link
            href="/dashboard/register"
            className="rounded-lg border border-surface-border px-6 py-2.5 text-sm font-medium text-surface-muted hover:text-white hover:border-surface-muted/50 transition-colors"
          >
            Registrarse gratis
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="mt-0.5 text-sm text-surface-muted">
            {new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <Link
          href="/dashboard/inventory/new"
          className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600 transition-colors"
        >
          <Plus size={15} /> Añadir vehículo
        </Link>
      </div>

      {/* KPI cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: 'Vehículos en stock',
            value: kpis?.inventory?.total,
            format: (v: number) => String(v),
            icon: Car,
            href: '/dashboard/inventory',
            sub: kpis?.inventory ? `${kpis.inventory.by_status?.LISTED ?? 0} publicados` : undefined,
          },
          {
            label: 'Deals activos',
            value: kpis?.pipeline?.open_deals,
            format: (v: number) => String(v),
            icon: Users,
            href: '/dashboard/crm',
            sub: kpis?.pipeline ? `${new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(kpis.pipeline.pipeline_value_eur)} en pipeline` : undefined,
          },
          {
            label: 'Vendidos este mes',
            value: kpis?.mtd?.units_sold,
            format: (v: number) => String(v),
            icon: TrendingUp,
            href: '/dashboard/crm',
            sub: kpis?.mtd ? `DOM medio: ${Math.round(kpis.mtd.avg_dom ?? 0)} días` : undefined,
          },
          {
            label: 'Facturación MTD',
            value: kpis?.mtd?.revenue_eur,
            format: (v: number) => new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v),
            icon: BarChart2,
            href: '/dashboard/crm',
            sub: kpis?.mtd ? `Margen medio: ${(kpis.mtd.avg_margin_pct ?? 0).toFixed(1)}%` : undefined,
          },
        ].map(({ label, value, format, icon: Icon, href, sub }) => (
          <Link
            key={label}
            href={href}
            className="group flex items-center gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/40 transition-all"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400 group-hover:bg-brand-500/20 transition-colors">
              <Icon size={19} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-surface-muted">{label}</p>
              {loading ? (
                <Loader2 size={15} className="mt-1 animate-spin text-surface-muted" />
              ) : (
                <>
                  <p className="font-mono text-2xl font-bold text-white">
                    {value != null ? format(value) : '—'}
                  </p>
                  {sub && <p className="mt-0.5 truncate text-xs text-surface-muted">{sub}</p>}
                </>
              )}
            </div>
          </Link>
        ))}
      </div>

      {/* Market Days' Supply widget */}
      <div className="mb-8">
        <MdsWidget />
      </div>

      {/* Quick actions */}
      <div className="mb-2">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Acciones rápidas</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <QuickAction
            href="/dashboard/inventory/new"
            icon={Plus}
            title="Añadir vehículo"
            desc="Entrada manual con generador de anuncios IA"
          />
          <QuickAction
            href="/analytics"
            icon={BarChart}
            title="Análisis de mercado"
            desc="Precios, demanda y arbitraje entre países"
          />
          <QuickAction
            href="/dashboard/audit"
            icon={Activity}
            title="Auditoría de marketing"
            desc="Puntuación de tus anuncios con recomendaciones IA"
          />
        </div>
      </div>
    </div>
  )
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function QuickAction({ href, icon: Icon, title, desc }: {
  href: string
  icon: React.FC<{ size?: number }>
  title: string
  desc: string
}) {
  return (
    <Link
      href={href}
      className="group flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/40 transition-all"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-hover text-surface-muted group-hover:bg-brand-500/10 group-hover:text-brand-400 transition-colors">
        <Icon size={17} />
      </div>
      <div>
        <p className="font-medium text-white">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-surface-muted">{desc}</p>
      </div>
    </Link>
  )
}
