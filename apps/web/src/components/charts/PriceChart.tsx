'use client'

/**
 * TradingView Lightweight Charts wrapper for CARDEX price index.
 * Renders OHLCV candlestick chart + volume histogram + DOM overlay.
 * Uses financial-grade rendering — same library as TradingView.
 */

import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
} from 'lightweight-charts'
import type { PriceCandle } from '@/lib/api'
import { formatPrice } from '@/lib/format'

interface Props {
  candles: PriceCandle[]
  height?: number
}

export function PriceChart({ candles, height = 400 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return

    // Clean up previous instance
    chartRef.current?.remove()

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#161b22' },
        textColor: '#8b949e',
        fontSize: 11,
        fontFamily: 'JetBrains Mono, monospace',
      },
      grid: {
        vertLines: { color: '#21262d' },
        horzLines: { color: '#21262d' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#30363d', labelBackgroundColor: '#21262d' },
        horzLine: { color: '#30363d', labelBackgroundColor: '#21262d' },
      },
      rightPriceScale: {
        borderColor: '#21262d',
        scaleMargins: { top: 0.1, bottom: 0.3 },
      },
      timeScale: {
        borderColor: '#21262d',
        timeVisible: true,
      },
      width: containerRef.current.clientWidth,
      height,
    })

    // Candlestick series (open=p10, high=p90, low=p5, close=median)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:   '#15b570',
      downColor: '#f85149',
      borderUpColor:   '#15b570',
      borderDownColor: '#f85149',
      wickUpColor:     '#15b570',
      wickDownColor:   '#f85149',
      priceFormat: {
        type: 'custom',
        formatter: (price: number) => formatPrice(price),
        minMove: 100,
      },
    })

    // Volume histogram (listing count)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#15b57040',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.75, bottom: 0 },
    })

    const candleData: CandlestickData<Time>[] = candles.map(c => ({
      time: c.time as Time,
      open:  c.open,
      high:  c.high,
      low:   c.low,
      close: c.close,
    }))
    const volumeData: HistogramData<Time>[] = candles.map(c => ({
      time:  c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? '#15b57040' : '#f8514940',
    }))

    candleSeries.setData(candleData)
    volumeSeries.setData(volumeData)
    chart.timeScale().fitContent()

    // Crosshair tooltip
    chart.subscribeCrosshairMove(param => {
      if (!param.time || !param.seriesData) return
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    // Responsive resize
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [candles, height])

  if (candles.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-surface-border bg-surface-card text-surface-muted" style={{ height }}>
        No price data available
      </div>
    )
  }

  return <div ref={containerRef} className="w-full rounded-xl overflow-hidden" style={{ height }} />
}
