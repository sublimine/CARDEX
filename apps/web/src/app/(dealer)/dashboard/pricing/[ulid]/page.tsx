'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, AlertCircle,
  Target, Zap, Clock, ShieldCheck, Loader2,
} from 'lucide-react'
import { getPricingIntelligence } from '@/lib/api'
import { formatPrice } from '@/lib/format'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

// ── Types ─────────────────────────────────────────────────────────────────────

interface PricingData {
  inventory_ulid: string
  your_price_eur: number
  market_p25: number
  market_median: number
  market_p75: number
  avg_dom_days: number
  market_sample: number
  market_position: string
  country: string
}

interface PricingOption {
  label: string
  price_eur: number
  estimated_dom_days: number
  margin_eur: number
  margin_pct: number
  constrained: boolean
}

interface OptimalPriceData {
  total_cost_eur: number
  floor_price_eur: number
  options: PricingOption[]
  market: {
    median: number
    p25: number
    p75: number
    avg_dom: number
    sample_count: number
  }
}

// ── Config ────────────────────────────────────────────────────────────────────

const POSITION_CONFIG: Record<string, { label: string; color: string; icon: React.FC<{ size?: number }> }> = {
  GREAT_DEAL:  { label: 'Gran oferta',   color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10', icon: TrendingDown },
  GOOD_DEAL:   { label: 'Buen precio',   color: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10', icon: TrendingDown },
  FAIR:        { label: 'Precio justo',  color: 'text-blue-400 border-blue-500/30 bg-blue-500/10',          icon: Minus },
  EXPENSIVE:   { label: 'Caro',          color: 'text-orange-400 border-orange-500/30 bg-orange-500/10',    icon: TrendingUp },
  OVERPRICED:  { label: 'Muy caro',      color: 'text-red-400 border-red-500/30 bg-red-500/10',             icon: TrendingUp },
  UNKNOWN:     { label: 'Sin datos',     color: 'text-surface-muted border-surface-border bg-surface-hover', icon: AlertCircle },
}

const OPTION_META: Record<string, { icon: React.FC<{ size?: number; className?: string }>; color: string; desc: string }> = {
  'DOM-15 (aggressive)': { icon: Zap,        color: 'text-emerald-400', desc: 'Rotación rápida · venta en ~15 días' },
  'DOM-30 (market median)': { icon: Target,  color: 'text-blue-400',    desc: 'Equilibrio precio-tiempo · ~30 días' },
  'DOM-60 (premium)':    { icon: Clock,       color: 'text-amber-400',   desc: 'Maximizar margen · ~60 días' },
}

function useToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cardex_token')
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PricingIntelligencePage() {
  const { ulid } = useParams<{ ulid: string }>()
  const token = useToken()
  const [data, setData] = useState<PricingData | null>(null)
  const [optimal, setOptimal] = useState<OptimalPriceData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [optimalLoading, setOptimalLoading] = useState(true)

  useEffect(() => {
    if (!token || !ulid) {
      setError('authentication_required')
      setLoading(false)
      setOptimalLoading(false)
      return
    }

    // Market comparison
    getPricingIntelligence(token, ulid)
      .then(d => setData(d as PricingData))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))

    // Optimal price (CRM-based, 3 scenarios)
    fetch(`${API}/api/v1/dealer/pricing/${ulid}/optimal`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setOptimal(d) })
      .catch(() => {})
      .finally(() => setOptimalLoading(false))
  }, [token, ulid])

  if (!token) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <p className="text-surface-muted">Inicia sesión para ver la inteligencia de precios.</p>
        <Link href="/dashboard/login" className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-medium text-white hover:bg-brand-600">
          Iniciar sesión
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <Link href="/dashboard/inventory" className="flex items-center gap-1.5 text-sm text-surface-muted hover:text-white transition-colors">
          <ArrowLeft size={14} /> Inventario
        </Link>
        <span className="text-surface-border">/</span>
        <span className="text-sm text-surface-muted">Inteligencia de Precios</span>
      </div>

      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Inteligencia de Precios</h1>
        <p className="mt-1 text-sm text-surface-muted">
          Análisis de mercado en tiempo real y recomendaciones de precio óptimo basadas en tus costes.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-surface-border bg-surface-card p-10 text-surface-muted">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-sm">Analizando datos de mercado…</span>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-400">
          Error al cargar datos: {error}
        </div>
      )}

      {data && (() => {
        const pos = POSITION_CONFIG[data.market_position] ?? POSITION_CONFIG.UNKNOWN
        const Icon = pos.icon
        const rangeSize = (data.market_p75 - data.market_p25) || 1
        const clampedPrice = Math.max(data.market_p25, Math.min(data.market_p75, data.your_price_eur))
        const pct = ((clampedPrice - data.market_p25) / rangeSize * 100).toFixed(1)
        const pctDiff = data.market_median > 0
          ? ((data.your_price_eur - data.market_median) / data.market_median * 100)
          : 0

        return (
          <div className="space-y-5">
            {/* Position badge */}
            <div className={`flex items-center gap-4 rounded-xl border px-6 py-4 ${pos.color}`}>
              <Icon size={22} />
              <div>
                <p className="font-semibold">{pos.label}</p>
                <p className="text-sm opacity-75">
                  {pctDiff > 0 ? `+${pctDiff.toFixed(1)}%` : `${pctDiff.toFixed(1)}%`} vs. mediana de mercado
                </p>
              </div>
            </div>

            {/* Market comparison */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h2 className="mb-5 text-xs font-semibold uppercase tracking-wider text-surface-muted">
                Comparativa de mercado · {data.market_sample.toLocaleString()} anuncios · {data.country}
              </h2>

              <div className="mb-6 grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-xs text-surface-muted">Percentil 25</p>
                  <p className="mt-1 font-mono text-xl font-bold text-emerald-400">{formatPrice(data.market_p25)}</p>
                </div>
                <div>
                  <p className="text-xs text-surface-muted">Mediana</p>
                  <p className="mt-1 font-mono text-xl font-bold text-white">{formatPrice(data.market_median)}</p>
                </div>
                <div>
                  <p className="text-xs text-surface-muted">Percentil 75</p>
                  <p className="mt-1 font-mono text-xl font-bold text-orange-400">{formatPrice(data.market_p75)}</p>
                </div>
              </div>

              {data.market_median > 0 && (
                <div className="space-y-2">
                  <div className="relative h-2 rounded-full bg-surface-hover">
                    <div className="absolute inset-0 rounded-full bg-gradient-to-r from-emerald-500/30 via-blue-500/30 to-orange-500/30" />
                    <div
                      className="absolute top-1/2 h-4 w-4 -translate-y-1/2 -translate-x-1/2 rounded-full border-2 border-white bg-brand-500 shadow-lg shadow-brand-500/50 transition-all"
                      style={{ left: `${pct}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-surface-muted">
                    <span>Más barato</span>
                    <span className="font-medium text-brand-400">Tu precio: {formatPrice(data.your_price_eur)}</span>
                    <span>Más caro</span>
                  </div>
                </div>
              )}

              <dl className="mt-5 grid grid-cols-2 gap-y-2 border-t border-surface-border pt-4 text-sm">
                <dt className="text-surface-muted">Días medios en mercado</dt>
                <dd className="text-right font-medium text-white">{data.avg_dom_days ? `${Math.round(data.avg_dom_days)} días` : '—'}</dd>
              </dl>
            </div>

            {/* Market recommendation */}
            {data.market_position !== 'UNKNOWN' && data.market_position !== 'FAIR' && (
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
                <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-blue-400">
                  <ShieldCheck size={14} /> Recomendación de mercado
                </h2>
                {(data.market_position === 'EXPENSIVE' || data.market_position === 'OVERPRICED') && (
                  <p className="text-sm text-surface-muted">
                    Considera bajar el precio a{' '}
                    <span className="font-medium text-white">{formatPrice(data.market_median * 0.98)}</span>
                    {' '}(–2% bajo mediana) para vender antes. Tiempo medio a mediana: ~{Math.round(data.avg_dom_days || 30)} días.
                  </p>
                )}
                {(data.market_position === 'GREAT_DEAL' || data.market_position === 'GOOD_DEAL') && (
                  <p className="text-sm text-surface-muted">
                    Precio competitivo. Podrías subir hasta{' '}
                    <span className="font-medium text-white">{formatPrice(data.market_median)}</span>
                    {' '}(mediana de mercado) sin perder visibilidad.
                  </p>
                )}
              </div>
            )}
          </div>
        )
      })()}

      {/* ── Optimal Price Section ─────────────────────────────────────────── */}
      <div className="mt-8">
        <div className="mb-4">
          <h2 className="text-lg font-semibold text-white">Precio Óptimo por Objetivo</h2>
          <p className="mt-0.5 text-sm text-surface-muted">
            Calculado a partir de tus costes reales (CRM) y las condiciones actuales de mercado.
          </p>
        </div>

        {optimalLoading ? (
          <div className="flex items-center justify-center gap-3 rounded-xl border border-surface-border bg-surface-card p-8 text-surface-muted">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Calculando precio óptimo…</span>
          </div>
        ) : optimal ? (
          <div className="space-y-4">
            {/* Cost summary */}
            <div className="flex items-center justify-between rounded-xl border border-surface-border bg-surface-card px-5 py-4 text-sm">
              <div className="flex items-center gap-2 text-surface-muted">
                <ShieldCheck size={14} />
                <span>Coste total del vehículo</span>
              </div>
              <div className="text-right">
                <span className="font-mono text-lg font-bold text-white">{formatPrice(optimal.total_cost_eur)}</span>
                <span className="ml-3 text-xs text-surface-muted">Precio suelo: {formatPrice(optimal.floor_price_eur)}</span>
              </div>
            </div>

            {/* 3 pricing options */}
            <div className="grid gap-3 sm:grid-cols-3">
              {optimal.options.map((opt) => {
                const meta = OPTION_META[opt.label] ?? { icon: Target, color: 'text-surface-muted', desc: '' }
                const MetaIcon = meta.icon
                return (
                  <div
                    key={opt.label}
                    className="rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/40 transition-colors"
                  >
                    <div className={`mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${meta.color}`}>
                      <MetaIcon size={13} />
                      <span>{opt.label.split(' ')[0]}</span>
                    </div>
                    <p className="font-mono text-2xl font-bold text-white">{formatPrice(opt.price_eur)}</p>
                    <p className="mt-1 text-xs text-surface-muted">{meta.desc}</p>

                    <div className="mt-4 space-y-1.5 border-t border-surface-border pt-3 text-xs">
                      <div className="flex justify-between">
                        <span className="text-surface-muted">Margen</span>
                        <span className={`font-medium ${opt.margin_eur >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {formatPrice(opt.margin_eur)} ({opt.margin_pct > 0 ? '+' : ''}{opt.margin_pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-surface-muted">DOM estimado</span>
                        <span className="font-medium text-white">~{opt.estimated_dom_days} días</span>
                      </div>
                      {opt.constrained && (
                        <p className="mt-1 text-[10px] text-amber-400/80">
                          Ajustado al precio suelo (+5% sobre coste)
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Market context for optimal */}
            {optimal.market.sample_count > 0 && (
              <p className="text-center text-xs text-surface-muted">
                Basado en {optimal.market.sample_count.toLocaleString()} anuncios activos ·
                DOM medio de mercado: {Math.round(optimal.market.avg_dom)} días
              </p>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-center text-sm text-surface-muted">
            No hay datos de coste disponibles. Completa los costes del vehículo en el CRM para ver el precio óptimo.
          </div>
        )}
      </div>
    </div>
  )
}
