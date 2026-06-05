/*
 * CARDEX Terminal — institutional price-index chart
 * lightweight-charts (TradingView's engine) on the cx-* palette, theme-reactive. Renders any
 * of the 53 indicators generically from indicators.ts (compute → IndSeries[]), routes separate
 * panes to their own price scale, hosts the full drawings.tsx engine (95 tools) and a unique
 * cross-border regional overlay.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries,
  ColorType, CrosshairMode,
  type IChartApi, type ISeriesApi, type CandlestickData,
} from 'lightweight-charts'
import type { TerminalPalette } from './theme'
import { MONO } from './theme'
import { priceSeries, MARKET_BY_CODE, type Instrument, type Bar } from './market'
import type { IndicatorDef } from './indicators'
import { DrawingLayer, type Drawing } from './drawings'

export type ChartType = 'candle' | 'line' | 'area'
export type RangeLabel = '1M' | '3M' | '6M' | '1Y' | 'ALL'
export interface ActiveIndicator { uid: string; def: IndicatorDef; params: Record<string, number> }

const RANGE_DAYS: Record<RangeLabel, number> = { '1M': 21, '3M': 63, '6M': 126, '1Y': 252, ALL: 0 }
const COMPARE_HUES = ['#60a5fa', '#fbbf24', '#2dd4bf', '#e879f9', '#f472b6']

function paneLayout(sepUids: string[]) {
  const VOL = 0.12, OSC = 0.15, GAP = 0.02
  let alloc = 0
  const m: Record<string, { top: number; bottom: number }> = {}
  for (const uid of [...sepUids].reverse()) { m[uid] = { top: 1 - (alloc + OSC), bottom: alloc }; alloc += OSC + GAP }
  m.vol = { top: 1 - (alloc + VOL), bottom: alloc }; alloc += VOL + GAP
  m.main = { top: 0, bottom: alloc }
  return m
}

interface MarketChartProps {
  p: TerminalPalette
  inst: Instrument
  market: string
  range: RangeLabel
  chartType: ChartType
  indicators: ActiveIndicator[]
  compare: string[]
  tool: string
  color: string
  drawings: Drawing[]
  onAddDrawing: (d: Drawing) => void
  onUpdateDrawing: (id: string, pts: Drawing['pts']) => void
  onDeleteDrawing: (id: string) => void
  hideDrawings: boolean
  lockDrawings: boolean
  magnet: boolean
  onCross: (b: CandlestickData | null) => void
}

export function MarketChart(props: MarketChartProps) {
  const { p, inst, market, range, chartType, indicators, compare, tool, color, drawings, onAddDrawing, onUpdateDrawing, onDeleteDrawing, hideDrawings, lockDrawings, magnet, onCross } = props
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceRef = useRef<ISeriesApi<any> | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volRef = useRef<ISeriesApi<any> | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const indRefs = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cmpRefs = useRef<Map<string, ISeriesApi<any>>>(new Map())
  const [chartH, setChartH] = useState(0)
  const [drawV, setDrawV] = useState(0)

  const data: Bar[] = useMemo(() => priceSeries(inst, market), [inst, market])
  const sepList = useMemo(() => indicators.filter(i => i.def.pane === 'separate'), [indicators])
  const indSig = useMemo(() => indicators.map(i => i.uid + ':' + JSON.stringify(i.params)).join('|'), [indicators])
  const layout = useMemo(() => paneLayout(sepList.map(i => i.uid)), [sepList])

  // Build chart once
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.offsetWidth, height: containerRef.current.offsetHeight || 400,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: p.chartText, fontSize: 10, fontFamily: MONO },
      grid: { vertLines: { color: p.chartGrid }, horzLines: { color: p.chartGrid } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: p.crosshair, labelBackgroundColor: p.accent }, horzLine: { color: p.crosshair, labelBackgroundColor: p.accent } },
      rightPriceScale: { borderColor: p.chartBorder },
      timeScale: { borderColor: p.chartBorder, timeVisible: false, secondsVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true }, handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    })
    chartRef.current = chart
    setTimeout(() => containerRef.current?.querySelectorAll('a').forEach(a => { (a as HTMLElement).style.display = 'none' }), 200)
    volRef.current = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false })
    const obs = new ResizeObserver(entries => {
      const e = entries[0]; if (!e || !chartRef.current) return
      chartRef.current.applyOptions({ width: e.contentRect.width, height: e.contentRect.height })
      setChartH(e.contentRect.height); setDrawV(n => n + 1)
    })
    obs.observe(containerRef.current)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const tsApi = chart.timeScale() as any
    const onRange = () => setDrawV(n => n + 1)
    tsApi.subscribeVisibleLogicalRangeChange?.(onRange)
    return () => { obs.disconnect(); tsApi.unsubscribeVisibleLogicalRangeChange?.(onRange); chart.remove(); chartRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Theme reactivity
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    chart.applyOptions({
      layout: { textColor: p.chartText },
      grid: { vertLines: { color: p.chartGrid }, horzLines: { color: p.chartGrid } },
      crosshair: { vertLine: { color: p.crosshair, labelBackgroundColor: p.accent }, horzLine: { color: p.crosshair, labelBackgroundColor: p.accent } },
      rightPriceScale: { borderColor: p.chartBorder }, timeScale: { borderColor: p.chartBorder },
    })
    setDrawV(n => n + 1)
  }, [p])

  // Price + volume series
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    if (priceRef.current) { try { chart.removeSeries(priceRef.current) } catch { /* */ } priceRef.current = null }
    let s
    if (chartType === 'candle') {
      s = chart.addSeries(CandlestickSeries, { upColor: p.up, downColor: p.down, borderUpColor: p.up, borderDownColor: p.down, wickUpColor: p.upGlow, wickDownColor: p.downGlow })
      s.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })))
    } else if (chartType === 'line') {
      s = chart.addSeries(LineSeries, { color: p.accentSoft, lineWidth: 2 })
      s.setData(data.map(d => ({ time: d.time, value: d.close })))
    } else {
      s = chart.addSeries(AreaSeries, { lineColor: p.accentSoft, topColor: `${p.accent}44`, bottomColor: `${p.accent}00`, lineWidth: 2 })
      s.setData(data.map(d => ({ time: d.time, value: d.close })))
    }
    priceRef.current = s
    chart.subscribeCrosshairMove(param => { onCross(param.seriesData?.has(s) ? (param.seriesData.get(s) as CandlestickData) : null) })
    if (volRef.current) volRef.current.setData(data.map(d => ({ time: d.time, value: d.volume, color: d.close >= d.open ? p.volUp : p.volDown })))
    chart.timeScale().fitContent()
    setDrawV(n => n + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartType, data, p.dark])

  // Indicators — generic render from IndSeries[]
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    for (const arr of indRefs.current.values()) arr.forEach(s => { try { chart.removeSeries(s) } catch { /* */ } })
    indRefs.current.clear()
    try { priceRef.current?.priceScale().applyOptions({ scaleMargins: layout.main }) } catch { /* */ }
    try { volRef.current?.priceScale().applyOptions({ scaleMargins: layout.vol }) } catch { /* */ }
    for (const ind of indicators) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const arr: ISeriesApi<any>[] = []
      const sep = ind.def.pane === 'separate'
      const pid = sep ? ind.uid : undefined
      let series: ReturnType<typeof ind.def.compute> = []
      try { series = ind.def.compute(data, ind.params) } catch { series = [] }
      for (const s of series) {
        const clean = s.data.filter(pt => Number.isFinite(pt.value))
        if (!clean.length) continue
        try {
          if (s.kind === 'hist') {
            const hs = chart.addSeries(HistogramSeries, { priceScaleId: pid, priceLineVisible: false, lastValueVisible: false })
            hs.setData(clean.map(pt => ({ time: pt.time, value: pt.value, color: pt.color ?? s.color }))); arr.push(hs)
          } else if (s.kind === 'area') {
            const as = chart.addSeries(AreaSeries, { priceScaleId: pid, lineColor: s.color, topColor: `${s.color}30`, bottomColor: `${s.color}00`, lineWidth: s.lineWidth ?? 2, priceLineVisible: false, lastValueVisible: false })
            as.setData(clean.map(pt => ({ time: pt.time, value: pt.value }))); arr.push(as)
          } else {
            const ls = chart.addSeries(LineSeries, { priceScaleId: pid, color: s.color, lineWidth: s.lineWidth ?? (s.kind === 'band' ? 1 : 2), lineStyle: s.lineStyle ?? (s.kind === 'band' ? 2 : 0), priceLineVisible: false, lastValueVisible: false })
            ls.setData(clean.map(pt => ({ time: pt.time, value: pt.value }))); arr.push(ls)
          }
        } catch { /* */ }
      }
      if (sep) {
        try { chart.priceScale(ind.uid).applyOptions({ scaleMargins: layout[ind.uid] ?? { top: 0.8, bottom: 0.02 } }) } catch { /* */ }
        if (ind.def.levels?.length && data.length) {
          for (const lv of ind.def.levels) {
            try {
              const gl = chart.addSeries(LineSeries, { priceScaleId: ind.uid, color: lv.color, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })
              gl.setData([{ time: data[0].time, value: lv.value }, { time: data.at(-1)!.time, value: lv.value }]); arr.push(gl)
            } catch { /* */ }
          }
        }
      }
      indRefs.current.set(ind.uid, arr)
    }
    setDrawV(n => n + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indSig, data, p.dark, layout])

  // Regional comparison overlay
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    const want = new Set(compare)
    for (const [code, s] of cmpRefs.current.entries()) {
      if (!want.has(code)) { try { chart.removeSeries(s) } catch { /* */ } cmpRefs.current.delete(code) }
    }
    compare.forEach((code, idx) => {
      if (cmpRefs.current.has(code)) return
      const series = chart.addSeries(LineSeries, { color: COMPARE_HUES[idx % COMPARE_HUES.length], lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: code })
      series.setData(priceSeries(inst, code).map(d => ({ time: d.time, value: d.close })))
      cmpRefs.current.set(code, series)
    })
    setDrawV(n => n + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compare, inst])

  // Range
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    if (range === 'ALL') { chart.timeScale().fitContent(); return }
    const from = new Date('2026-06-01'); from.setDate(from.getDate() - RANGE_DAYS[range])
    try { chart.timeScale().setVisibleRange({ from: from.toISOString().split('T')[0] as any, to: '2026-06-01' as any }) } catch { /* */ }
  }, [range])

  // Pane separators + labels
  const separators: number[] = []
  if (chartH > 0) {
    if (layout.vol) separators.push(chartH * layout.vol.top)
    sepList.forEach(i => { if (layout[i.uid]) separators.push(chartH * layout[i.uid].top) })
  }

  return (
    <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
      <DrawingLayer chart={chartRef.current} series={priceRef} p={p} drawings={drawings} onAdd={onAddDrawing} onUpdate={onUpdateDrawing} onDelete={onDeleteDrawing} tool={tool} color={color} version={drawV} height={chartH} lock={lockDrawings} hide={hideDrawings} magnet={magnet} bars={data} />
      {separators.map((y, i) => (
        <div key={i} style={{ position: 'absolute', left: 0, right: 0, top: y, height: 1, background: p.hairline, pointerEvents: 'none', zIndex: 5 }} />
      ))}
      {chartH > 0 && layout.vol && (
        <div style={{ position: 'absolute', left: 10, top: chartH * layout.vol.top + 5, fontSize: 9, fontWeight: 700, color: p.t4, letterSpacing: '0.10em', pointerEvents: 'none', zIndex: 5, fontFamily: 'Inter, system-ui' }}>SUPPLY VOL · {MARKET_BY_CODE[market]?.code}</div>
      )}
      {chartH > 0 && sepList.map(i => {
        const m = layout[i.uid]; if (!m) return null
        return <div key={i.uid} style={{ position: 'absolute', left: 10, top: chartH * m.top + 5, fontSize: 9, fontWeight: 700, color: p.t4, letterSpacing: '0.08em', pointerEvents: 'none', zIndex: 5, fontFamily: 'Inter, system-ui' }}>{i.def.name.toUpperCase()}</div>
      })}
    </div>
  )
}
