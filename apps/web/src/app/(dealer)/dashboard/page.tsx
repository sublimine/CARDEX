'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Car, Users, BarChart2, Megaphone, TrendingUp, AlertCircle, Loader2 } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

// ── MDS Types ───────────────────────────────────────────────────────────────
interface MdsEntry {
  make: string
  model: string
  country: string
  mds_days: number
}

function MdsDemandBadge({ mds }: { mds: number }) {
  if (mds <= 20) return (
    <span className="rounded-md bg-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">ALTA</span>
  )
  if (mds <= 45) return (
    <span className="rounded-md bg-yellow-500/20 px-2 py-0.5 text-xs font-semibold text-yellow-400">MEDIA</span>
  )
  return (
    <span className="rounded-md bg-red-500/20 px-2 py-0.5 text-xs font-semibold text-red-400">BAJA</span>
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
        const entries: MdsEntry[] = data.entries ?? data.results ?? data ?? []
        // sort by mds_days ascending (lowest = highest demand), take top 5
        const sorted = [...entries].sort((a, b) => a.mds_days - b.mds_days).slice(0, 5)
        setMdsData(sorted)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <h2 className="mb-4 text-base font-semibold text-white">
        📊 Demanda del Mercado — Días de Stock
      </h2>
      {loading ? (
        <div className="flex justify-center py-6">
          <Loader2 size={22} className="animate-spin text-brand-400" />
        </div>
      ) : mdsData.length === 0 ? (
        <p className="py-4 text-center text-sm text-surface-muted">No hay datos de mercado disponibles.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-left">
                <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Marca</th>
                <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Modelo</th>
                <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted hidden sm:table-cell">País</th>
                <th className="pb-2 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">MDS días</th>
                <th className="pb-2 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Demanda</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {mdsData.map((entry, i) => (
                <tr key={i} className="hover:bg-surface-hover transition-colors">
                  <td className="py-2.5 font-medium text-white">{entry.make}</td>
                  <td className="py-2.5 text-surface-muted">{entry.model}</td>
                  <td className="py-2.5 text-surface-muted hidden sm:table-cell">{entry.country}</td>
                  <td className="py-2.5 text-right font-mono font-bold text-white">{entry.mds_days}</td>
                  <td className="py-2.5 text-right">
                    <MdsDemandBadge mds={entry.mds_days} />
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

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

interface DashboardData {
  inventory?: { total: number; by_status: Record<string, number> }
  pipeline?: { open_deals: number; pipeline_value_eur: number }
  mtd?: { units_sold: number; revenue_eur: number; avg_margin_pct: number; avg_dom: number }
}

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
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center px-4">
        <h1 className="text-3xl font-bold text-white">Portal Dealer</h1>
        <p className="text-surface-muted max-w-md">
          Gestiona tu inventario, publica en todas las plataformas, sigue tus leads y obtén inteligencia de precios con IA.
        </p>
        <div className="flex gap-3">
          <Link href="/dashboard/login"
            className="rounded-lg bg-brand-500 px-6 py-2.5 font-medium text-white hover:bg-brand-600 transition-colors">
            Iniciar sesión
          </Link>
          <Link href="/dashboard/register"
            className="rounded-lg border border-surface-border px-6 py-2.5 font-medium text-surface-muted hover:text-white transition-colors">
            Registrarse gratis
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-white">Dashboard</h1>

      {/* KPI cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: 'Vehículos en stock',
            value: kpis?.inventory?.total,
            format: (v: number) => String(v),
            icon: Car,
            href: '/dashboard/inventory',
          },
          {
            label: 'Deals abiertos',
            value: kpis?.pipeline?.open_deals,
            format: (v: number) => String(v),
            icon: Users,
            href: '/dashboard/crm',
          },
          {
            label: 'Vendidos este mes',
            value: kpis?.mtd?.units_sold,
            format: (v: number) => String(v),
            icon: TrendingUp,
            href: '/dashboard/crm',
          },
          {
            label: 'Facturación este mes',
            value: kpis?.mtd?.revenue_eur,
            format: (v: number) => `€${v.toLocaleString('es-ES', { maximumFractionDigits: 0 })}`,
            icon: BarChart2,
            href: '/dashboard/crm',
          },
        ].map(({ label, value, format, icon: Icon, href }) => (
          <Link key={label} href={href}
            className="flex items-center gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/50 transition-colors group">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400 group-hover:bg-brand-500/20">
              <Icon size={20} />
            </div>
            <div>
              <p className="text-xs text-surface-muted">{label}</p>
              {loading ? (
                <Loader2 size={16} className="mt-1 animate-spin text-surface-muted" />
              ) : (
                <p className="font-mono text-2xl font-bold text-white">
                  {value != null ? format(value) : '—'}
                </p>
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
      <div className="grid gap-4 sm:grid-cols-3">
        <QuickAction href="/dashboard/inventory/new" icon={Car}
          title="Añadir vehículo" desc="Entrada manual o importar desde URL" />
        <QuickAction href="/dashboard/audit" icon={Megaphone}
          title="Multipublicación" desc="Publica en AutoScout24, mobile.de y más" />
        <QuickAction href="/dashboard/audit" icon={AlertCircle}
          title="Auditoría marketing" desc="Sugerencias de mejora con IA" />
      </div>
    </div>
  )
}

function QuickAction({ href, icon: Icon, title, desc }: {
  href: string
  icon: React.FC<{ size?: number }>
  title: string
  desc: string
}) {
  return (
    <Link href={href}
      className="flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/50 transition-colors group">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-hover text-surface-muted group-hover:bg-brand-500/10 group-hover:text-brand-400 transition-colors">
        <Icon size={18} />
      </div>
      <div>
        <p className="font-medium text-white">{title}</p>
        <p className="mt-0.5 text-xs text-surface-muted">{desc}</p>
      </div>
    </Link>
  )
}
