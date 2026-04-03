'use client'

import { useState } from 'react'
import { AlertCircle, Loader2, Search, TrendingDown, TrendingUp, BarChart2, Zap, Clock } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Types ──────────────────────────────────────────────────────────────────────

interface VINValuationResponse {
  vin: string
  make: string
  model: string
  year: number
  fuel_type: string
  input_mileage_km: number
  market_sample_size: number
  distribution: {
    p10: number
    p25: number
    median: number
    p75: number
    p90: number
    mean: number
    std_dev: number
  }
  mileage_adjusted: {
    trade_in_eur: number
    retail_low_eur: number
    retail_high_eur: number
    median_mileage_km: number
    mileage_delta_km: number
    mileage_adj_pct: number
  }
  market_velocity: {
    at_p25_dom_days: number
    at_p50_dom_days: number
    at_p75_dom_days: number
  }
  data_as_of: string
  methodology: string
}

// ── Formatters ─────────────────────────────────────────────────────────────────

const fmtEUR = (value: number) =>
  new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)

const fmtNum = (value: number) =>
  new Intl.NumberFormat('es-ES').format(value)

// ── VIN regex ──────────────────────────────────────────────────────────────────

const VIN_REGEX = /^[A-HJ-NPR-Z0-9]{17}$/

// ── Price distribution bar ────────────────────────────────────────────────────

function DistributionBar({ distribution }: { distribution: VINValuationResponse['distribution'] }) {
  const min = distribution.p10
  const max = distribution.p90
  const range = max - min || 1

  const pct = (val: number) => ((val - min) / range) * 100

  const points = [
    { key: 'p10',    label: 'P10 · Mínimo',   value: distribution.p10,    color: 'text-red-400',    bg: 'bg-red-500' },
    { key: 'p25',    label: 'P25 · Bajo',      value: distribution.p25,    color: 'text-orange-400', bg: 'bg-orange-500' },
    { key: 'median', label: 'P50 · Mercado',   value: distribution.median, color: 'text-emerald-400',bg: 'bg-emerald-500' },
    { key: 'p75',    label: 'P75 · Alto',      value: distribution.p75,    color: 'text-blue-400',   bg: 'bg-blue-500' },
    { key: 'p90',    label: 'P90 · Máximo',    value: distribution.p90,    color: 'text-surface-muted', bg: 'bg-gray-500' },
  ]

  return (
    <div className="space-y-3">
      {/* Visual bar */}
      <div className="relative h-3 rounded-full bg-surface-hover overflow-visible">
        <div className="absolute inset-0 rounded-full bg-gradient-to-r from-red-500/30 via-emerald-500/30 to-gray-500/30" />
        {points.map(p => (
          <div
            key={p.key}
            className={`absolute top-1/2 h-4 w-1.5 -translate-y-1/2 -translate-x-1/2 rounded-full ${p.bg}`}
            style={{ left: `${pct(p.value)}%` }}
            title={`${p.label}: ${fmtEUR(p.value)}`}
          />
        ))}
      </div>

      {/* Labels */}
      <div className="space-y-1.5">
        {points.map(p => (
          <div key={p.key} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${p.bg} shrink-0`} />
              <span className={`text-xs font-medium ${p.color}`}>{p.label}</span>
            </div>
            <span className={`font-mono font-semibold ${p.color}`}>{fmtEUR(p.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function VINValuationPage() {
  const [vin, setVin] = useState('')
  const [mileage, setMileage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<VINValuationResponse | null>(null)
  const [vinError, setVinError] = useState<string | null>(null)

  function handleVinChange(val: string) {
    const upper = val.toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g, '')
    setVin(upper)
    if (upper.length > 0 && upper.length < 17) {
      setVinError(`El VIN debe tener exactamente 17 caracteres (${upper.length}/17)`)
    } else if (upper.length === 17 && !VIN_REGEX.test(upper)) {
      setVinError('VIN inválido: solo se permiten caracteres A-H, J-N, P-R, Z y dígitos 0-9')
    } else {
      setVinError(null)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!VIN_REGEX.test(vin)) {
      setVinError('VIN inválido. Debe tener 17 caracteres alfanuméricos válidos.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const params = new URLSearchParams({ vin })
      if (mileage) params.set('mileage_km', mileage)

      const res = await fetch(`${API}/api/v1/analytics/vin-valuation?${params}`, {
        headers: authHeader(),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        if (data.error === 'insufficient_data') {
          throw new Error('Datos insuficientes: no hay suficientes anuncios de mercado para valorar este VIN.')
        }
        throw new Error(data.message ?? data.error ?? `Error ${res.status}`)
      }

      const data: VINValuationResponse = await res.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al obtener la valoración')
    } finally {
      setLoading(false)
    }
  }

  const adj = result?.mileage_adjusted
  const vel = result?.market_velocity

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Valoración por VIN</h1>
        <p className="mt-1 text-sm text-surface-muted">
          Introduce un VIN para obtener la valoración de mercado en tiempo real basada en anuncios scraped.
        </p>
      </div>

      {/* Search form */}
      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-surface-border bg-surface-card p-6 mb-6"
      >
        <div className="grid gap-4 sm:grid-cols-[1fr_auto_auto]">
          {/* VIN input */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-surface-muted uppercase tracking-wider">
              VIN del vehículo
            </label>
            <input
              type="text"
              value={vin}
              onChange={e => handleVinChange(e.target.value)}
              placeholder="WBA3A5C50CF256985"
              maxLength={17}
              className={`w-full rounded-xl border px-4 py-2.5 font-mono text-sm text-white placeholder:text-surface-muted focus:outline-none bg-transparent transition-colors ${
                vinError
                  ? 'border-red-500/60 focus:border-red-500'
                  : 'border-surface-border focus:border-brand-500'
              }`}
            />
            {vinError && (
              <p className="text-xs text-red-400">{vinError}</p>
            )}
          </div>

          {/* Mileage input */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-surface-muted uppercase tracking-wider">
              Km actuales <span className="opacity-50">(opcional)</span>
            </label>
            <input
              type="number"
              value={mileage}
              onChange={e => setMileage(e.target.value)}
              placeholder="85000"
              min={0}
              className="w-full rounded-xl border border-surface-border bg-transparent px-4 py-2.5 text-sm text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none transition-colors"
            />
          </div>

          {/* Submit */}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={loading || !!vinError || vin.length !== 17}
              className="flex items-center gap-2 rounded-xl bg-brand-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {loading ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Search size={15} />
              )}
              Valorar
            </button>
          </div>
        </div>
      </form>

      {/* Error banner */}
      {error && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center gap-3 rounded-xl border border-surface-border bg-surface-card p-12 text-surface-muted">
          <Loader2 size={20} className="animate-spin text-brand-400" />
          <span className="text-sm">Consultando datos de mercado…</span>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-5">
          {/* Vehicle header */}
          <div className="rounded-xl border border-surface-border bg-surface-card px-6 py-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-bold text-white">
                  {result.make} {result.model} <span className="text-surface-muted font-normal">{result.year}</span>
                </h2>
                <p className="mt-1 font-mono text-sm text-surface-muted">{result.vin}</p>
                {result.fuel_type && (
                  <p className="mt-0.5 text-xs text-surface-muted">{result.fuel_type}</p>
                )}
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-brand-500/30 bg-brand-500/10 px-3 py-1.5 text-xs font-medium text-brand-400">
                <BarChart2 size={12} />
                Basado en {fmtNum(result.market_sample_size)} anuncios del mercado
              </span>
            </div>
          </div>

          {/* Price distribution */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-6">
            <h3 className="mb-5 text-xs font-semibold uppercase tracking-wider text-surface-muted">
              Distribución de precios de mercado
            </h3>
            <DistributionBar distribution={result.distribution} />
            <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-surface-border pt-4 text-sm">
              <dt className="text-surface-muted">Media</dt>
              <dd className="text-right font-mono font-medium text-white">{fmtEUR(result.distribution.mean)}</dd>
              <dt className="text-surface-muted">Desviación estándar</dt>
              <dd className="text-right font-mono font-medium text-white">{fmtEUR(result.distribution.std_dev)}</dd>
            </dl>
          </div>

          {/* Mileage-adjusted valuation */}
          {adj && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-surface-muted">
                Valoración para este vehículo
              </h3>

              {/* Mileage delta badge */}
              {result.input_mileage_km > 0 && (
                <div className="mb-4">
                  {adj.mileage_delta_km > 0 ? (
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-red-500/10 border border-red-500/20 px-2.5 py-1 text-xs text-red-400">
                      <TrendingUp size={11} />
                      ↑{fmtNum(adj.mileage_delta_km)} km sobre mediana → ajuste {adj.mileage_adj_pct.toFixed(1)}%
                    </span>
                  ) : adj.mileage_delta_km < 0 ? (
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 text-xs text-emerald-400">
                      <TrendingDown size={11} />
                      ↓{fmtNum(Math.abs(adj.mileage_delta_km))} km bajo mediana → ajuste +{Math.abs(adj.mileage_adj_pct).toFixed(1)}%
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-blue-500/10 border border-blue-500/20 px-2.5 py-1 text-xs text-blue-400">
                      Km en la mediana del mercado ({fmtNum(adj.median_mileage_km)} km)
                    </span>
                  )}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-lg bg-surface-hover px-4 py-3">
                  <p className="text-xs text-surface-muted">Valor de tasación (trade-in)</p>
                  <p className="mt-1 font-mono text-xl font-bold text-white">{fmtEUR(adj.trade_in_eur)}</p>
                </div>
                <div className="rounded-lg bg-surface-hover px-4 py-3">
                  <p className="text-xs text-surface-muted">Precio mínimo de venta</p>
                  <p className="mt-1 font-mono text-xl font-bold text-emerald-400">{fmtEUR(adj.retail_low_eur)}</p>
                </div>
                <div className="rounded-lg bg-surface-hover px-4 py-3">
                  <p className="text-xs text-surface-muted">Precio máximo de venta</p>
                  <p className="mt-1 font-mono text-xl font-bold text-blue-400">{fmtEUR(adj.retail_high_eur)}</p>
                </div>
              </div>
            </div>
          )}

          {/* Market velocity */}
          {vel && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <div className="mb-4 flex items-start justify-between gap-4 flex-wrap">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-muted">
                  Velocidad de mercado
                </h3>
                <span className="rounded-md bg-brand-500/10 border border-brand-500/20 px-2 py-0.5 text-[10px] font-medium text-brand-400 uppercase tracking-wider">
                  Exclusivo Cardex
                </span>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between rounded-lg bg-emerald-500/5 border border-emerald-500/20 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Zap size={14} className="text-emerald-400" />
                    <span className="text-sm text-emerald-400 font-medium">A precio bajo (P25)</span>
                  </div>
                  <span className="font-mono text-sm font-bold text-emerald-400">
                    {Math.round(vel.at_p25_dom_days)} días promedio
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-lg bg-blue-500/5 border border-blue-500/20 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <BarChart2 size={14} className="text-blue-400" />
                    <span className="text-sm text-blue-400 font-medium">A precio mediano (P50)</span>
                  </div>
                  <span className="font-mono text-sm font-bold text-blue-400">
                    {Math.round(vel.at_p50_dom_days)} días promedio
                  </span>
                </div>

                <div className="flex items-center justify-between rounded-lg bg-surface-hover border border-surface-border px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Clock size={14} className="text-surface-muted" />
                    <span className="text-sm text-surface-muted font-medium">A precio alto (P75)</span>
                  </div>
                  <span className="font-mono text-sm font-bold text-surface-muted">
                    {Math.round(vel.at_p75_dom_days)} días promedio
                  </span>
                </div>
              </div>

              <p className="mt-4 text-xs text-surface-muted border-t border-surface-border pt-3">
                Cardex usa datos scraped en tiempo real vs. bases estáticas mensuales de DATgroup
              </p>
            </div>
          )}

          {/* Footer */}
          <div className="rounded-xl border border-surface-border bg-surface-card px-6 py-4">
            <p className="text-xs text-surface-muted">
              <span className="font-medium text-white">Datos a:</span>{' '}
              {new Date(result.data_as_of).toLocaleDateString('es-ES', {
                day: '2-digit',
                month: 'long',
                year: 'numeric',
              })}
            </p>
            {result.methodology && (
              <p className="mt-1 text-xs text-surface-muted">{result.methodology}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
