'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, TrendingUp, TrendingDown, Minus, AlertCircle } from 'lucide-react'
import { getPricingIntelligence } from '@/lib/api'
import { formatPrice } from '@/lib/format'

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

const POSITION_CONFIG: Record<string, { label: string; color: string; icon: React.FC<{ size?: number }> }> = {
  GREAT_DEAL:  { label: 'Great deal',  color: 'text-green-400 border-green-500/30 bg-green-500/10',  icon: TrendingDown },
  GOOD_DEAL:   { label: 'Good deal',   color: 'text-green-400 border-green-500/30 bg-green-500/10',  icon: TrendingDown },
  FAIR:        { label: 'Fair price',  color: 'text-blue-400 border-blue-500/30 bg-blue-500/10',      icon: Minus },
  EXPENSIVE:   { label: 'Expensive',   color: 'text-orange-400 border-orange-500/30 bg-orange-500/10', icon: TrendingUp },
  OVERPRICED:  { label: 'Overpriced',  color: 'text-brand-400 border-brand-500/30 bg-brand-500/10',  icon: TrendingUp },
  UNKNOWN:     { label: 'No data',     color: 'text-surface-muted border-surface-border bg-surface-hover', icon: AlertCircle },
}

function useToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cardex_token')
}

export default function PricingIntelligencePage() {
  const { ulid } = useParams<{ ulid: string }>()
  const token = useToken()
  const [data, setData] = useState<PricingData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token || !ulid) {
      setError('authentication_required')
      setLoading(false)
      return
    }
    getPricingIntelligence(token, ulid)
      .then(d => setData(d as PricingData))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, ulid])

  if (!token) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <p className="text-surface-muted">Please log in to view pricing intelligence.</p>
        <Link href="/dashboard/login" className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-medium text-white hover:bg-brand-600">
          Login
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6">
        <Link href="/dashboard/inventory" className="flex items-center gap-1.5 text-sm text-surface-muted hover:text-white">
          <ArrowLeft size={14} /> Back to inventory
        </Link>
      </div>

      <h1 className="mb-6 text-2xl font-bold text-white">Pricing Intelligence</h1>

      {loading && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-8 text-center text-surface-muted">
          Analysing market data…
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-red-400">
          Failed to load pricing data: {error}
        </div>
      )}

      {data && (() => {
        const pos = POSITION_CONFIG[data.market_position] ?? POSITION_CONFIG.UNKNOWN
        const Icon = pos.icon

        // Market position bar: shows where your price sits among p25–p75
        const rangeSize = (data.market_p75 - data.market_p25) || 1
        const clampedPrice = Math.max(data.market_p25, Math.min(data.market_p75, data.your_price_eur))
        const pct = ((clampedPrice - data.market_p25) / rangeSize * 100).toFixed(1)

        const pctDiff = data.market_median > 0
          ? ((data.your_price_eur - data.market_median) / data.market_median * 100)
          : 0

        return (
          <div className="space-y-5">
            {/* Position badge */}
            <div className={`flex items-center gap-3 rounded-xl border px-5 py-4 ${pos.color}`}>
              <Icon size={24} />
              <div>
                <p className="font-semibold">{pos.label}</p>
                <p className="text-sm opacity-80">
                  {pctDiff > 0 ? `+${pctDiff.toFixed(1)}%` : `${pctDiff.toFixed(1)}%`} vs. market median
                </p>
              </div>
            </div>

            {/* Price comparison */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Market comparison</h2>

              <div className="mb-6 grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-xs text-surface-muted">25th %ile</p>
                  <p className="mt-1 font-mono text-xl font-bold text-green-400">{formatPrice(data.market_p25)}</p>
                </div>
                <div>
                  <p className="text-xs text-surface-muted">Median</p>
                  <p className="mt-1 font-mono text-xl font-bold text-white">{formatPrice(data.market_median)}</p>
                </div>
                <div>
                  <p className="text-xs text-surface-muted">75th %ile</p>
                  <p className="mt-1 font-mono text-xl font-bold text-orange-400">{formatPrice(data.market_p75)}</p>
                </div>
              </div>

              {/* Position bar */}
              {data.market_median > 0 && (
                <div className="space-y-1">
                  <div className="relative h-2 rounded-full bg-surface-hover">
                    <div className="absolute inset-0 rounded-full bg-gradient-to-r from-green-500/40 via-blue-500/40 to-orange-500/40" />
                    <div
                      className="absolute top-1/2 h-4 w-4 -translate-y-1/2 -translate-x-1/2 rounded-full border-2 border-white bg-brand-500 shadow-lg shadow-brand-500/50"
                      style={{ left: `${pct}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-surface-muted">
                    <span>Cheapest</span>
                    <span className="text-brand-400">Your price: {formatPrice(data.your_price_eur)}</span>
                    <span>Most expensive</span>
                  </div>
                </div>
              )}
            </div>

            {/* Market stats */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Market statistics</h2>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-surface-muted">Sample size</dt>
                  <dd className="font-medium text-white">{data.market_sample.toLocaleString()} listings</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-surface-muted">Avg. days on market</dt>
                  <dd className="font-medium text-white">{data.avg_dom_days ? `${Math.round(data.avg_dom_days)} days` : '—'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-surface-muted">Country</dt>
                  <dd className="font-medium text-white">{data.country}</dd>
                </div>
              </dl>
            </div>

            {/* Recommendation */}
            {data.market_position !== 'UNKNOWN' && data.market_position !== 'FAIR' && (
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
                <h2 className="mb-2 text-sm font-semibold text-blue-400">Recommendation</h2>
                {(data.market_position === 'EXPENSIVE' || data.market_position === 'OVERPRICED') && (
                  <p className="text-sm text-surface-muted">
                    Consider lowering your price to <span className="font-medium text-white">{formatPrice(data.market_median * 0.98)}</span> (–2% below median) to sell faster.
                    Current avg. time to sell at median: ~{Math.round(data.avg_dom_days || 30)} days.
                  </p>
                )}
                {(data.market_position === 'GREAT_DEAL' || data.market_position === 'GOOD_DEAL') && (
                  <p className="text-sm text-surface-muted">
                    Your price is competitive. You could raise it up to <span className="font-medium text-white">{formatPrice(data.market_median)}</span> (market median) without losing visibility.
                  </p>
                )}
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
