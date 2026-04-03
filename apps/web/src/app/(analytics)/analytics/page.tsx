import type { Metadata } from 'next'
import { Suspense } from 'react'
import { getPriceIndex, getMarketDepth, getHeatmap } from '@/lib/api'
import { PriceChart } from '@/components/charts/PriceChart'
import { MarketDepthChart } from '@/components/charts/MarketDepthChart'
import { HeatmapLayer } from '@/components/map/HeatmapLayer'

export const metadata: Metadata = {
  title: 'Market Intelligence — Price Index, Depth & Heatmap',
  description: 'Real-time pan-European used car market intelligence: OHLCV price charts, market depth, geographic heatmap.',
}

interface PageProps {
  searchParams: { make?: string; model?: string; country?: string; interval?: string }
}

export default async function AnalyticsPage({ searchParams: sp }: PageProps) {
  const [priceData, depthData, heatmapData] = await Promise.all([
    getPriceIndex({ make: sp.make, model: sp.model, country: sp.country, interval: sp.interval }).catch(() => ({ series: [] })),
    getMarketDepth({ make: sp.make, model: sp.model, country: sp.country }).catch(() => ({ depth: [] })),
    getHeatmap({ make: sp.make, country: sp.country }).catch(() => ({ hexes: [] })),
  ])

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Market Intelligence</h1>
          <p className="mt-1 text-sm text-surface-muted">
            Pan-European used car market — real-time price index, depth & geographic distribution
          </p>
        </div>
        <FilterBar sp={sp} />
      </div>

      <div className="flex flex-col gap-6">
        {/* OHLCV Price Chart */}
        <section>
          <SectionHeader
            title="Price Index"
            subtitle={`open=p10 · high=p90 · low=p5 · close=median · volume=listings ${sp.make ? `— ${sp.make} ${sp.model ?? ''}` : '— All makes'}`}
          />
          <Suspense fallback={<ChartSkeleton height={420} />}>
            <PriceChart candles={priceData.series} height={420} />
          </Suspense>
        </section>

        {/* Market Depth + DOM side by side */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section>
            <SectionHeader title="Market Depth" subtitle="Listing count per €1k price bracket" />
            <Suspense fallback={<ChartSkeleton height={300} />}>
              <MarketDepthChart tiers={depthData.depth} height={300} />
            </Suspense>
          </section>

          <section>
            <SectionHeader title="Price Tiers Summary" subtitle="Distribution statistics" />
            <DepthTable tiers={depthData.depth} />
          </section>
        </div>

        {/* Geographic Heatmap */}
        <section>
          <SectionHeader
            title="Geographic Heatmap"
            subtitle="H3 hexagonal grid — height & colour = listing density. Rotate with right-click drag."
          />
          <Suspense fallback={<ChartSkeleton height={520} />}>
            <HeatmapLayer hexes={heatmapData.hexes} height={520} />
          </Suspense>
        </section>
      </div>
    </div>
  )
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-base font-semibold text-white">{title}</h2>
      <p className="text-xs text-surface-muted">{subtitle}</p>
    </div>
  )
}

function ChartSkeleton({ height }: { height: number }) {
  return (
    <div
      className="w-full animate-pulse rounded-xl bg-surface-card border border-surface-border"
      style={{ height }}
    />
  )
}

function FilterBar({ sp }: { sp: Record<string, string | undefined> }) {
  return (
    <form className="flex items-center gap-2 text-sm">
      <input name="make" defaultValue={sp.make ?? ''} placeholder="Make"
        className="w-28 rounded-md border border-surface-border bg-surface px-3 py-1.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
      <input name="model" defaultValue={sp.model ?? ''} placeholder="Model"
        className="w-28 rounded-md border border-surface-border bg-surface px-3 py-1.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
      <select name="country" defaultValue={sp.country ?? ''}
        className="rounded-md border border-surface-border bg-surface px-3 py-1.5 text-white focus:border-brand-500 focus:outline-none">
        <option value="">All countries</option>
        {['DE','ES','FR','NL','BE','CH'].map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <select name="interval" defaultValue={sp.interval ?? 'week'}
        className="rounded-md border border-surface-border bg-surface px-3 py-1.5 text-white focus:border-brand-500 focus:outline-none">
        <option value="day">Daily</option>
        <option value="week">Weekly</option>
        <option value="month">Monthly</option>
      </select>
      <button type="submit" className="rounded-md bg-brand-500 px-4 py-1.5 text-white hover:bg-brand-600 transition-colors">
        Apply
      </button>
    </form>
  )
}

function DepthTable({ tiers }: { tiers: { price_tier_eur: number; count: number; avg_mileage_km: number }[] }) {
  if (tiers.length === 0) return (
    <div className="flex h-[300px] items-center justify-center rounded-xl border border-surface-border bg-surface-card text-surface-muted text-sm">
      No data
    </div>
  )
  const top10 = [...tiers].sort((a, b) => b.count - a.count).slice(0, 10)
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden" style={{ height: 300 }}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-border text-xs text-surface-muted">
            <th className="px-4 py-2 text-left">Price range</th>
            <th className="px-4 py-2 text-right">Listings</th>
            <th className="px-4 py-2 text-right">Avg mileage</th>
          </tr>
        </thead>
        <tbody>
          {top10.map(t => (
            <tr key={t.price_tier_eur} className="border-b border-surface-border/50 hover:bg-surface-hover transition-colors">
              <td className="px-4 py-2 font-mono text-white">
                €{(t.price_tier_eur / 1000).toFixed(0)}k – €{((t.price_tier_eur + 1000) / 1000).toFixed(0)}k
              </td>
              <td className="px-4 py-2 text-right text-brand-400">{t.count.toLocaleString()}</td>
              <td className="px-4 py-2 text-right text-surface-muted">{Math.round(t.avg_mileage_km).toLocaleString()} km</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
