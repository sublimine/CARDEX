'use client'

/**
 * Market Depth — order-book style bar chart.
 * X axis: price tiers (1 000 EUR buckets)
 * Y axis: listing count at that price tier
 * Visual: stacked bars coloured by relative density (heatmap gradient)
 */

import { useEffect, useRef } from 'react'
import {
  createChart,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  type Time,
} from 'lightweight-charts'
import type { MarketDepthTier } from '@/lib/api'
import { formatPrice, formatMileage } from '@/lib/format'

interface Props {
  tiers: MarketDepthTier[]
  height?: number
}

export function MarketDepthChart({ tiers, height = 300 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || tiers.length === 0) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#161b22' },
        textColor: '#8b949e',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#21262d' },
      timeScale: { borderColor: '#21262d', timeVisible: false },
      width: containerRef.current.clientWidth,
      height,
    })

    const maxCount = Math.max(...tiers.map(t => t.count))

    const series = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
    })

    // Each tier is a "bar" — use price_tier_eur as time (hack: epoch seconds)
    // We use a fake time axis where each bar = one price bucket
    const data = tiers.map((t, i) => ({
      time: (i + 1) as unknown as Time,
      value: t.count,
      // Gradient: low count = dim, high count = bright green
      color: `rgba(21, 181, 112, ${0.2 + (t.count / maxCount) * 0.8})`,
    }))

    series.setData(data)

    // Custom x-axis labels via markers
    series.setMarkers(
      tiers
        .filter((_, i) => i % 5 === 0) // every 5th bucket
        .map((t, i) => ({
          time: (i * 5 + 1) as unknown as Time,
          position: 'belowBar' as const,
          color: '#8b949e',
          shape: 'arrowDown' as const,
          text: formatPrice(t.price_tier_eur),
          size: 0,
        }))
    )

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(e => {
      chart.applyOptions({ width: e[0].contentRect.width })
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove() }
  }, [tiers, height])

  return (
    <div className="w-full rounded-xl overflow-hidden">
      {tiers.length === 0 ? (
        <div className="flex items-center justify-center border border-surface-border bg-surface-card text-surface-muted" style={{ height }}>
          No market depth data
        </div>
      ) : (
        <div ref={containerRef} style={{ height }} />
      )}
    </div>
  )
}
