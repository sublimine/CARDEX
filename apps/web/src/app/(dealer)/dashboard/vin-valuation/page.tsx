'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const fmtEUR = (v: number) =>
  new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
const fmtNum = (v: number) => new Intl.NumberFormat('es-ES').format(v)

const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/

// ── Types ──────────────────────────────────────────────────────────────────────

interface ValuationResult {
  vin: string
  make: string
  model: string
  year: number
  fuel_type: string
  input_mileage_km: number
  market_sample_size: number
  distribution: { p10: number; p25: number; median: number; p75: number; p90: number; mean: number; std_dev: number }
  mileage_adjusted: { trade_in_eur: number; retail_low_eur: number; retail_high_eur: number; median_mileage_km: number; mileage_delta_km: number; mileage_adj_pct: number }
  market_velocity: { at_p25_dom_days: number; at_p50_dom_days: number; at_p75_dom_days: number }
  data_as_of: string
  methodology: string
}

// ── Verdict engine ─────────────────────────────────────────────────────────────
// Computes a buy/sell/negotiate verdict + risk level from distribution data.

type Verdict = { label: string; sublabel: string; color: string; bg: string; border: string; score: number }

function computeVerdict(result: ValuationResult): Verdict {
  const { distribution: d, mileage_adjusted: adj } = result
  const spreadPct = (d.p90 - d.p10) / d.median * 100
  const positionPct = adj.retail_low_eur > 0
    ? (adj.retail_low_eur - d.p25) / (d.p75 - d.p25) * 100
    : 50

  if (positionPct < 10) return {
    label: 'Oportunidad clara', sublabel: 'Precio muy por debajo de mercado — compra sin dudar',
    color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/40', score: 95,
  }
  if (positionPct < 35) return {
    label: 'Buen precio', sublabel: 'Por debajo del mercado — margen de negociación favorable',
    color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/40', score: 78,
  }
  if (positionPct < 65) return {
    label: 'Precio de mercado', sublabel: 'Alineado con la mediana — negocia en base a estado y km',
    color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/40', score: 55,
  }
  if (positionPct < 85) return {
    label: 'Precio alto', sublabel: 'Por encima de mercado — exige justificación técnica',
    color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/40', score: 30,
  }
  return {
    label: 'Sobrevaluado', sublabel: 'Significativamente por encima del mercado — alto riesgo de pérdida',
    color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/40', score: 10,
  }
}

function riskLevel(stdDev: number, median: number): { label: string; color: string; detail: string } {
  const cv = stdDev / median * 100
  if (cv < 8) return { label: 'Riesgo bajo', color: 'text-emerald-400', detail: `Mercado estable (CV ${cv.toFixed(0)}%)` }
  if (cv < 16) return { label: 'Riesgo medio', color: 'text-yellow-400', detail: `Volatilidad moderada (CV ${cv.toFixed(0)}%)` }
  return { label: 'Riesgo alto', color: 'text-red-400', detail: `Mercado volátil — precio difícil de defender (CV ${cv.toFixed(0)}%)` }
}

// ── Price gauge ────────────────────────────────────────────────────────────────

function PriceGauge({ distribution: d, retailLow }: { distribution: ValuationResult['distribution']; retailLow: number }) {
  const min = d.p10
  const max = d.p90
  const range = max - min || 1
  const pct = (v: number) => Math.max(0, Math.min(100, (v - min) / range * 100))

  const zones = [
    { from: pct(d.p10), to: pct(d.p25), color: '#ef4444', label: 'Barato' },
    { from: pct(d.p25), to: pct(d.median), color: '#f59e0b', label: 'Bajo' },
    { from: pct(d.median), to: pct(d.p75), color: '#3b82f6', label: 'Mercado' },
    { from: pct(d.p75), to: pct(d.p90), color: '#8b5cf6', label: 'Alto' },
  ]

  const needlePct = pct(retailLow)

  return (
    <div className="space-y-3">
      {/* Bar */}
      <div className="relative h-4 rounded-full overflow-hidden bg-surface-hover">
        {zones.map((z, i) => (
          <div
            key={i}
            className="absolute top-0 h-full opacity-60"
            style={{ left: `${z.from}%`, width: `${z.to - z.from}%`, backgroundColor: z.color }}
          />
        ))}
        {/* Needle — where this vehicle sits */}
        <div
          className="absolute top-0 h-full w-1 bg-white shadow-lg z-10"
          style={{ left: `${needlePct}%`, transform: 'translateX(-50%)' }}
        />
      </div>

      {/* Zone labels */}
      <div className="flex justify-between text-[10px] text-surface-muted px-0.5">
        <span style={{ color: '#ef4444' }}>P10 {fmtEUR(d.p10)}</span>
        <span style={{ color: '#f59e0b' }}>P25 {fmtEUR(d.p25)}</span>
        <span style={{ color: '#3b82f6' }}>P50 {fmtEUR(d.median)}</span>
        <span style={{ color: '#8b5cf6' }}>P75 {fmtEUR(d.p75)}</span>
        <span className="text-surface-muted">P90 {fmtEUR(d.p90)}</span>
      </div>

      {/* Needle label */}
      <div className="text-center">
        <span className="text-xs text-surface-muted">Este vehículo →{' '}</span>
        <span className="text-sm font-bold text-white">{fmtEUR(retailLow)}</span>
        <span className="ml-2 text-xs text-surface-muted">
          ({needlePct < 50 ? `${(50 - needlePct).toFixed(0)}% bajo mediana` : `${(needlePct - 50).toFixed(0)}% sobre mediana`})
        </span>
      </div>
    </div>
  )
}

// ── DOM scenario cards ─────────────────────────────────────────────────────────

function ScenarioCards({ result }: { result: ValuationResult }) {
  const { distribution: d, mileage_adjusted: adj, market_velocity: vel } = result

  const scenarios = [
    {
      key: 'aggressive',
      label: 'Precio agresivo',
      price: adj.trade_in_eur * 1.10,
      dom: vel.at_p25_dom_days,
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/5',
      border: 'border-emerald-500/25',
      tag: 'Rotación máxima',
      tagColor: 'bg-emerald-500/20 text-emerald-400',
    },
    {
      key: 'market',
      label: 'Precio de mercado',
      price: adj.retail_low_eur,
      dom: vel.at_p50_dom_days,
      color: 'text-blue-400',
      bg: 'bg-blue-500/5',
      border: 'border-blue-500/25',
      tag: 'Equilibrio',
      tagColor: 'bg-blue-500/20 text-blue-400',
    },
    {
      key: 'premium',
      label: 'Precio premium',
      price: adj.retail_high_eur,
      dom: vel.at_p75_dom_days,
      color: 'text-brand-400',
      bg: 'bg-brand-500/5',
      border: 'border-brand-500/25',
      tag: 'Margen máximo',
      tagColor: 'bg-brand-500/20 text-brand-400',
    },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {scenarios.map(s => (
        <div key={s.key} className={`rounded-xl border ${s.border} ${s.bg} p-5`}>
          <div className="mb-3 flex items-start justify-between gap-2">
            <span className="text-xs font-medium text-surface-muted">{s.label}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${s.tagColor}`}>{s.tag}</span>
          </div>
          <div className={`mb-1 font-mono text-2xl font-bold ${s.color}`}>{fmtEUR(s.price)}</div>
          <div className="text-xs text-surface-muted">
            Vende en ~<span className={`font-semibold ${s.color}`}>{s.dom}</span> días
          </div>
          <div className="mt-3 text-xs text-surface-muted">
            Margen bruto estimado:{' '}
            <span className="font-semibold text-white">
              {fmtEUR(s.price - result.mileage_adjusted.trade_in_eur)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

const LOADING_STEPS = [
  'Decodificando VIN…',
  'Consultando 2.000 anuncios del mercado…',
  'Calculando percentiles y ajuste por km…',
  'Generando informe de inteligencia…',
]

export default function VINValuationPage() {
  const router = useRouter()
  const [vin, setVin] = useState('')
  const [mileage, setMileage] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ValuationResult | null>(null)
  const [copied, setCopied] = useState(false)
  const stepInterval = useRef<ReturnType<typeof setInterval> | null>(null)

  function handleVinChange(val: string) {
    setVin(val.toUpperCase().replace(/[^A-HJ-NPR-Z0-9]/g, '').slice(0, 17))
    setError(null)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!VIN_RE.test(vin)) { setError('VIN inválido — 17 caracteres, sin I/O/Q'); return }

    setLoading(true)
    setLoadingStep(0)
    setError(null)
    setResult(null)

    // Cycle through loading steps for UX
    let step = 0
    stepInterval.current = setInterval(() => {
      step = Math.min(step + 1, LOADING_STEPS.length - 1)
      setLoadingStep(step)
    }, 900)

    try {
      const params = new URLSearchParams({ vin })
      if (mileage) params.set('mileage_km', mileage)
      const res = await fetch(`${API}/api/v1/analytics/vin-valuation?${params}`, { headers: authHeader() })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(
          d.error === 'insufficient_data'
            ? `Datos insuficientes para "${vin}" — no hay suficientes anuncios en el mercado para este vehículo.`
            : d.message ?? d.error ?? `Error ${res.status}`
        )
      }
      setResult(await res.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
    } finally {
      clearInterval(stepInterval.current!)
      setLoading(false)
    }
  }

  async function copyTradeIn() {
    if (!result) return
    await navigator.clipboard.writeText(String(Math.round(result.mileage_adjusted.trade_in_eur)))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const verdict = result ? computeVerdict(result) : null
  const risk = result ? riskLevel(result.distribution.std_dev, result.distribution.median) : null

  return (
    <div className="mx-auto max-w-4xl space-y-8">

      {/* ── Hero header ── */}
      <div className="relative overflow-hidden rounded-2xl border border-surface-border bg-gradient-to-br from-surface via-surface to-brand-500/5 px-8 py-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-brand-500/10 via-transparent to-transparent" />
        <div className="relative">
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded-full bg-brand-500/20 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-brand-400">
              Exclusivo Cardex · Tiempo real
            </span>
          </div>
          <h1 className="mt-2 text-3xl font-bold text-white">Motor de Valoración VIN</h1>
          <p className="mt-2 max-w-xl text-sm text-surface-muted leading-relaxed">
            Valoración instantánea basada en datos scraped en vivo de toda Europa.
            DATgroup actualiza mensualmente. Nosotros, a diario.
          </p>

          {/* ── Search form ── */}
          <form onSubmit={handleSubmit} className="mt-7">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              {/* VIN */}
              <div className="flex-1">
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-surface-muted">
                  Número VIN <span className="font-normal opacity-60">(17 caracteres)</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={vin}
                    onChange={e => handleVinChange(e.target.value)}
                    placeholder="WBA3A5C50CF256985"
                    maxLength={17}
                    spellCheck={false}
                    className="w-full rounded-xl border border-surface-border bg-surface-dark/80 px-4 py-3 pr-16 font-mono text-base text-white placeholder:text-surface-muted/50 focus:border-brand-500 focus:outline-none transition-colors"
                  />
                  <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs font-mono tabular-nums ${vin.length === 17 ? 'text-emerald-400' : 'text-surface-muted'}`}>
                    {vin.length}/17
                  </span>
                </div>
              </div>

              {/* Mileage */}
              <div className="w-36">
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-surface-muted">
                  Km <span className="font-normal opacity-60">(opc.)</span>
                </label>
                <input
                  type="number"
                  value={mileage}
                  onChange={e => setMileage(e.target.value)}
                  placeholder="85 000"
                  min={0}
                  max={999999}
                  className="w-full rounded-xl border border-surface-border bg-surface-dark/80 px-4 py-3 text-sm text-white placeholder:text-surface-muted/50 focus:border-brand-500 focus:outline-none transition-colors"
                />
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading || vin.length !== 17}
                className="flex h-[46px] items-center gap-2.5 rounded-xl bg-brand-500 px-7 text-sm font-semibold text-white hover:bg-brand-600 transition disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                ) : (
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                  </svg>
                )}
                Valorar
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* ── Loading ── */}
      {loading && (
        <div className="rounded-2xl border border-surface-border bg-surface p-8">
          <div className="flex flex-col items-center gap-6">
            <div className="relative h-12 w-12">
              <div className="absolute inset-0 animate-ping rounded-full bg-brand-500/20" />
              <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/10">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
              </div>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-white">{LOADING_STEPS[loadingStep]}</p>
              <p className="mt-1 text-xs text-surface-muted">Consultando la base de datos de Cardex…</p>
            </div>
            {/* Step dots */}
            <div className="flex gap-2">
              {LOADING_STEPS.map((_, i) => (
                <div
                  key={i}
                  className={`h-1.5 w-6 rounded-full transition-all duration-500 ${i <= loadingStep ? 'bg-brand-500' : 'bg-surface-hover'}`}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {error && !loading && (
        <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-400">
          <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* ── Results ── */}
      {result && !loading && verdict && risk && (() => {
        const adj = result.mileage_adjusted

        return (
          <div className="space-y-5">

            {/* Vehicle identity bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-surface-border bg-surface px-6 py-4">
              <div>
                <div className="text-xs text-surface-muted uppercase tracking-wider">Vehículo identificado</div>
                <div className="mt-1 text-xl font-bold text-white">
                  {result.make} {result.model}{' '}
                  <span className="text-surface-muted font-normal">{result.year}</span>
                  {result.fuel_type && (
                    <span className="ml-2 text-sm font-normal text-surface-muted">· {result.fuel_type}</span>
                  )}
                </div>
                <div className="mt-0.5 font-mono text-xs text-surface-muted">{result.vin}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-xs text-surface-muted">Muestra de mercado</div>
                  <div className="text-lg font-bold text-white">{fmtNum(result.market_sample_size)}</div>
                  <div className="text-xs text-surface-muted">anuncios</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-surface-muted">Datos a</div>
                  <div className="text-sm font-semibold text-white">
                    {new Date(result.data_as_of).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}
                  </div>
                </div>
              </div>
            </div>

            {/* Verdict + Risk in two columns */}
            <div className="grid gap-5 sm:grid-cols-2">

              {/* Verdict */}
              <div className={`rounded-xl border ${verdict.border} ${verdict.bg} p-6`}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-surface-muted">Veredicto Cardex</div>
                <div className={`mt-2 text-2xl font-bold ${verdict.color}`}>{verdict.label}</div>
                <div className="mt-1 text-sm text-surface-muted leading-snug">{verdict.sublabel}</div>
                {/* Score bar */}
                <div className="mt-5">
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="text-surface-muted">Puntuación de compra</span>
                    <span className={`font-bold ${verdict.color}`}>{verdict.score}/100</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-surface-hover">
                    <div
                      className={`h-full rounded-full transition-all duration-1000 ${
                        verdict.score >= 70 ? 'bg-emerald-500' : verdict.score >= 40 ? 'bg-blue-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${verdict.score}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Risk */}
              <div className="rounded-xl border border-surface-border bg-surface p-6">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-surface-muted">Análisis de riesgo</div>
                <div className={`mt-2 text-xl font-bold ${risk.color}`}>{risk.label}</div>
                <div className="mt-1 text-sm text-surface-muted">{risk.detail}</div>

                <div className="mt-5 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-surface-muted">Desviación estándar</span>
                    <span className="font-mono text-white">{fmtEUR(result.distribution.std_dev)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-surface-muted">Rango P10–P90</span>
                    <span className="font-mono text-white">
                      {fmtEUR(result.distribution.p10)} – {fmtEUR(result.distribution.p90)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-surface-muted">Km mediana del segmento</span>
                    <span className="font-mono text-white">{fmtNum(adj.median_mileage_km)} km</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Price gauge */}
            <div className="rounded-xl border border-surface-border bg-surface p-6">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-muted">
                  Posicionamiento en el mercado
                </h3>
                {result.input_mileage_km > 0 && (
                  <span className={`rounded-md border px-2.5 py-1 text-xs font-medium ${
                    adj.mileage_delta_km > 2000
                      ? 'border-red-500/30 bg-red-500/10 text-red-400'
                      : adj.mileage_delta_km < -2000
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                      : 'border-surface-border text-surface-muted'
                  }`}>
                    {adj.mileage_delta_km > 0 ? '↑' : '↓'}{fmtNum(Math.abs(adj.mileage_delta_km))} km vs. mediana
                    {' '}({adj.mileage_adj_pct > 0 ? '+' : ''}{adj.mileage_adj_pct.toFixed(1)}%)
                  </span>
                )}
              </div>
              <PriceGauge distribution={result.distribution} retailLow={adj.retail_low_eur} />
            </div>

            {/* 3 pricing scenarios */}
            <div className="rounded-xl border border-surface-border bg-surface p-6">
              <div className="mb-5 flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-muted">
                  Escenarios de precio · velocidad de venta
                </h3>
                <span className="rounded-full bg-brand-500/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-400 border border-brand-500/20">
                  Exclusivo Cardex
                </span>
              </div>
              <ScenarioCards result={result} />
              <p className="mt-4 text-xs text-surface-muted border-t border-surface-border pt-3">
                DATgroup y Eurotax no ofrecen datos de velocidad de venta por precio. Cardex calcula el DOM real por rango de precio usando los propios datos scraped.
              </p>
            </div>

            {/* Trade-in card + quick actions */}
            <div className="grid gap-5 sm:grid-cols-3">
              <div className="col-span-2 rounded-xl border border-brand-500/30 bg-brand-500/5 p-6">
                <div className="text-xs font-semibold uppercase tracking-wider text-brand-400">
                  Valor de tasación (trade-in)
                </div>
                <div className="mt-2 flex items-end gap-4">
                  <span className="font-mono text-4xl font-bold text-white">{fmtEUR(adj.trade_in_eur)}</span>
                  <span className="mb-1 text-sm text-surface-muted">= P25 × 0.92</span>
                </div>
                <div className="mt-1 text-xs text-surface-muted">
                  Precio máximo que deberías ofrecer como comprador para garantizar margen
                </div>
                <button
                  onClick={copyTradeIn}
                  className="mt-4 flex items-center gap-2 rounded-lg border border-brand-500/30 px-4 py-1.5 text-xs font-medium text-brand-400 hover:bg-brand-500/10 transition"
                >
                  {copied ? (
                    <>
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/>
                      </svg>
                      Copiado
                    </>
                  ) : (
                    <>
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                      </svg>
                      Copiar valor
                    </>
                  )}
                </button>
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex-1 rounded-xl border border-surface-border bg-surface p-4">
                  <div className="text-xs text-surface-muted">Precio mínimo venta</div>
                  <div className="mt-1 font-mono text-xl font-bold text-emerald-400">{fmtEUR(adj.retail_low_eur)}</div>
                </div>
                <div className="flex-1 rounded-xl border border-surface-border bg-surface p-4">
                  <div className="text-xs text-surface-muted">Precio máximo venta</div>
                  <div className="mt-1 font-mono text-xl font-bold text-blue-400">{fmtEUR(adj.retail_high_eur)}</div>
                </div>
              </div>
            </div>

          </div>
        )
      })()}
    </div>
  )
}
