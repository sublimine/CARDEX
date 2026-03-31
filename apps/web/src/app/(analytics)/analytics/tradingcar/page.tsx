'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import {
  createChart,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
  ColorType,
} from 'lightweight-charts'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  avg_mileage_km: number
}

interface TickerMeta {
  make: string
  model: string
  year: number
  country: string
  fuel: string
}

interface CandleResponse {
  ticker: string
  period: 'W' | 'M'
  candles: Candle[]
  meta: TickerMeta
}

interface TickerRow {
  ticker_id: string
  make: string
  model: string
  year: number
  country: string
  fuel_type: string
  last_price_eur: number
  change_1w_pct: number
  change_1m_pct: number
  volume_30d: number
  liquidity_score: number
}

interface ScannerRow {
  ticker_id: string
  make: string
  model: string
  year: number
  country: string
  change_1m_pct: number
  last_price_eur: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const TV_COLORS = {
  background: '#0d1117',
  grid: '#1c2128',
  border: '#21262d',
  upColor: '#26a69a',
  downColor: '#ef5350',
  wickUpColor: '#26a69a',
  wickDownColor: '#ef5350',
  textColor: '#8b949e',
  crosshair: '#758696',
  sma20Color: '#2196f3',
  sma50Color: '#ff9800',
  bbColor: '#4caf50',
  rsiColor: '#7b1fa2',
  macdFastColor: '#2196f3',
  macdSlowColor: '#ff6d00',
  macdSignalColor: '#e91e63',
  macdHistUpColor: '#26a69a',
  macdHistDownColor: '#ef5350',
}

const COUNTRY_FLAGS: Record<string, string> = {
  DE: '🇩🇪', ES: '🇪🇸', FR: '🇫🇷', NL: '🇳🇱', BE: '🇧🇪', CH: '🇨🇭',
}

const DEFAULT_WATCHLIST = [
  'BMW_3-Series_2020_DE_Gasoline',
  'Volkswagen_Golf_2021_DE_Gasoline',
  'Seat_Leon_2020_ES_Gasoline',
  'Renault_Clio_2020_FR_Gasoline',
  'Peugeot_308_2021_FR_Diesel',
]

const SCANNER_TYPES = [
  { value: 'most_depreciating', label: 'Most Depreciating' },
  { value: 'best_value', label: 'Best Value' },
  { value: 'most_liquid', label: 'Most Liquid' },
  { value: 'near_historic_low', label: 'Near Historic Low' },
  { value: 'momentum_up', label: 'Momentum Up' },
  { value: 'momentum_down', label: 'Momentum Down' },
]

// ─── Technical Indicators ────────────────────────────────────────────────────

function sma(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(null); continue }
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += data[j]
    result.push(sum / period)
  }
  return result
}

function ema(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  const k = 2 / (period + 1)
  let prev: number | null = null
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { result.push(null); continue }
    if (prev === null) {
      let sum = 0
      for (let j = 0; j < period; j++) sum += data[j]
      prev = sum / period
      result.push(prev)
    } else {
      prev = data[i] * k + prev * (1 - k)
      result.push(prev)
    }
  }
  return result
}

function bollingerBands(data: number[], period = 20, stddevMult = 2) {
  const mid = sma(data, period)
  const upper: (number | null)[] = []
  const lower: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (mid[i] === null) { upper.push(null); lower.push(null); continue }
    let variance = 0
    for (let j = i - period + 1; j <= i; j++) variance += Math.pow(data[j] - (mid[i] as number), 2)
    const sd = Math.sqrt(variance / period)
    upper.push((mid[i] as number) + stddevMult * sd)
    lower.push((mid[i] as number) - stddevMult * sd)
  }
  return { mid, upper, lower }
}

function rsi(data: number[], period = 14): (number | null)[] {
  const result: (number | null)[] = []
  if (data.length < period + 1) return data.map(() => null)
  let gains = 0, losses = 0
  for (let i = 1; i <= period; i++) {
    const diff = data[i] - data[i - 1]
    if (diff > 0) gains += diff
    else losses -= diff
  }
  let avgGain = gains / period
  let avgLoss = losses / period
  for (let i = 0; i < period; i++) result.push(null)
  result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))
  for (let i = period + 1; i < data.length; i++) {
    const diff = data[i] - data[i - 1]
    avgGain = (avgGain * (period - 1) + Math.max(diff, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-diff, 0)) / period
    result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))
  }
  return result
}

function macd(data: number[], fast = 12, slow = 26, signal = 9) {
  const fastEma = ema(data, fast)
  const slowEma = ema(data, slow)
  const macdLine: (number | null)[] = fastEma.map((f, i) =>
    f !== null && slowEma[i] !== null ? (f - slowEma[i]!) : null
  )
  const macdValues = macdLine.filter((v): v is number => v !== null)
  const signalRaw = ema(macdValues, signal)
  const signalLine: (number | null)[] = []
  let sigIdx = 0
  for (let i = 0; i < macdLine.length; i++) {
    if (macdLine[i] === null) { signalLine.push(null); continue }
    signalLine.push(sigIdx < signalRaw.length ? signalRaw[sigIdx] : null)
    sigIdx++
  }
  const histogram = macdLine.map((m, i) =>
    m !== null && signalLine[i] !== null ? m - signalLine[i]! : null
  )
  return { macdLine, signalLine, histogram }
}

// ─── Chart Options Factory ────────────────────────────────────────────────────

function baseChartOptions(height: number) {
  return {
    height,
    layout: {
      background: { type: ColorType.Solid, color: TV_COLORS.background },
      textColor: TV_COLORS.textColor,
      fontFamily: 'JetBrains Mono, monospace',
    },
    grid: {
      vertLines: { color: TV_COLORS.grid },
      horzLines: { color: TV_COLORS.grid },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: TV_COLORS.crosshair, style: LineStyle.Dashed },
      horzLine: { color: TV_COLORS.crosshair, style: LineStyle.Dashed },
    },
    rightPriceScale: {
      borderColor: TV_COLORS.border,
      textColor: TV_COLORS.textColor,
    },
    timeScale: {
      borderColor: TV_COLORS.border,
      timeVisible: true,
      secondsVisible: false,
    },
  }
}

// ─── Ticker Search Dropdown ──────────────────────────────────────────────────

function TickerSearch({
  value,
  onChange,
}: {
  value: string
  onChange: (ticker: string) => void
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TickerRow[]>([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (query.length < 2) { setResults([]); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/v1/tradingcar/tickers?q=${encodeURIComponent(query)}&limit=10`)
        const data = await res.json()
        setResults(data.tickers ?? [])
        setOpen(true)
      } catch {
        setResults([])
      }
    }, 300)
  }, [query])

  const displayLabel = (ticker: string) => {
    const parts = ticker.split('_')
    if (parts.length < 5) return ticker
    const country = parts[parts.length - 2]
    const year = parts[parts.length - 3]
    const model = parts.slice(1, parts.length - 3).join(' ')
    return `${parts[0]} ${model} ${year} ${COUNTRY_FLAGS[country] ?? country}`
  }

  return (
    <div className="relative">
      <div
        className="flex cursor-pointer items-center gap-2 rounded border border-surface-border bg-surface-card px-3 py-1.5 text-sm text-white hover:border-brand-500"
        onClick={() => setOpen(!open)}
      >
        <svg className="h-4 w-4 text-surface-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span className="max-w-[200px] truncate">{displayLabel(value)}</span>
        <svg className="h-3 w-3 text-surface-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-80 rounded border border-surface-border bg-surface-card shadow-xl">
          <div className="p-2">
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search make, model..."
              className="w-full rounded border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
          {results.length > 0 && (
            <ul className="max-h-64 overflow-y-auto">
              {results.map(t => (
                <li
                  key={t.ticker_id}
                  className="flex cursor-pointer items-center justify-between px-3 py-2 hover:bg-surface-hover"
                  onClick={() => { onChange(t.ticker_id); setOpen(false); setQuery('') }}
                >
                  <div>
                    <div className="text-sm text-white">
                      {COUNTRY_FLAGS[t.country] ?? t.country} {t.make} {t.model} {t.year}
                    </div>
                    <div className="text-xs text-surface-muted">{t.fuel_type}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-sm text-white">
                      €{Math.round(t.last_price_eur).toLocaleString()}
                    </div>
                    <div className={`text-xs font-mono ${t.change_1m_pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                      {t.change_1m_pct >= 0 ? '+' : ''}{t.change_1m_pct.toFixed(1)}%
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {query.length >= 2 && results.length === 0 && (
            <div className="px-3 py-4 text-center text-sm text-surface-muted">No results</div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TradingCarPage() {
  // ── State ──
  const [selectedTicker, setSelectedTicker] = useState('BMW_3-Series_2020_DE_Gasoline')
  const [period, setPeriod] = useState<'W' | 'M'>('M')
  const [activeIndicators, setActiveIndicators] = useState(['SMA20', 'SMA50', 'BB', 'Volume'])
  const [rsiEnabled, setRsiEnabled] = useState(true)
  const [macdEnabled, setMacdEnabled] = useState(true)
  const [watchlist, setWatchlist] = useState<string[]>(DEFAULT_WATCHLIST)
  const [scannerType, setScannerType] = useState('most_depreciating')
  const [compareMode, setCompareMode] = useState(false)
  const [compareTickers, setCompareTickers] = useState<string[]>([])
  const [candleData, setCandleData] = useState<CandleResponse | null>(null)
  const [scannerData, setScannerData] = useState<ScannerRow[]>([])
  const [watchlistData, setWatchlistData] = useState<Record<string, TickerRow>>({})
  const [loading, setLoading] = useState(false)
  const [indicatorsOpen, setIndicatorsOpen] = useState(false)
  const [compareInput, setCompareInput] = useState('')

  // ── Chart refs ──
  const mainRef = useRef<HTMLDivElement>(null)
  const rsiRef = useRef<HTMLDivElement>(null)
  const macdRef = useRef<HTMLDivElement>(null)
  const mainChart = useRef<IChartApi | null>(null)
  const rsiChart = useRef<IChartApi | null>(null)
  const macdChart = useRef<IChartApi | null>(null)

  // ── Fetch candles ──
  const fetchCandles = useCallback(async (ticker: string, per: 'W' | 'M') => {
    setLoading(true)
    try {
      const res = await fetch(
        `/api/v1/tradingcar/candles?ticker=${encodeURIComponent(ticker)}&period=${per}&limit=500`
      )
      const data: CandleResponse = await res.json()
      setCandleData(data)
    } catch {
      // noop
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchCandles(selectedTicker, period) }, [selectedTicker, period, fetchCandles])

  // ── Fetch scanner ──
  useEffect(() => {
    fetch(`/api/v1/tradingcar/scanner?type=${scannerType}&limit=8`)
      .then(r => r.json())
      .then(d => setScannerData(d.results ?? []))
      .catch(() => {})
  }, [scannerType])

  // ── Fetch watchlist ticker data ──
  useEffect(() => {
    watchlist.forEach(ticker => {
      fetch(`/api/v1/tradingcar/tickers?q=${encodeURIComponent(ticker.split('_')[0])}&limit=50`)
        .then(r => r.json())
        .then(d => {
          const found = (d.tickers ?? []).find((t: TickerRow) => t.ticker_id === ticker)
          if (found) setWatchlistData(prev => ({ ...prev, [ticker]: found }))
        })
        .catch(() => {})
    })
  }, [watchlist])

  // ── Build & render charts ──
  useEffect(() => {
    if (!candleData || !mainRef.current) return

    const candles = candleData.candles
    if (candles.length === 0) return

    const closes = candles.map(c => c.close)
    const times = candles.map(c => c.time)

    // ── Destroy old charts ──
    mainChart.current?.remove()
    rsiChart.current?.remove()
    macdChart.current?.remove()
    mainChart.current = null
    rsiChart.current = null
    macdChart.current = null

    // ── Main chart ──
    const mc = createChart(mainRef.current, {
      ...baseChartOptions(compareMode ? 400 : 500),
      width: mainRef.current.clientWidth,
    })
    mainChart.current = mc

    if (compareMode && compareTickers.length > 0) {
      // Compare mode: indexed line series
      const colors = ['#26a69a', '#2196f3', '#ff9800', '#e91e63', '#9c27b0']
      const baseLine = mc.addLineSeries({
        color: colors[0],
        lineWidth: 2,
        title: selectedTicker.split('_').slice(0, 2).join(' '),
      })
      baseLine.setData(candles.map((c, i) => ({
        time: c.time as any,
        value: i === 0 ? 100 : (c.close / candles[0].close) * 100,
      })))
    } else {
      // Normal candlestick
      const cs = mc.addCandlestickSeries({
        upColor: TV_COLORS.upColor,
        downColor: TV_COLORS.downColor,
        wickUpColor: TV_COLORS.wickUpColor,
        wickDownColor: TV_COLORS.wickDownColor,
        borderVisible: false,
      })
      cs.setData(candles.map(c => ({
        time: c.time as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })))

      // SMA 20
      if (activeIndicators.includes('SMA20')) {
        const sma20 = mc.addLineSeries({ color: TV_COLORS.sma20Color, lineWidth: 1, title: 'SMA 20' })
        sma20.setData(
          sma(closes, 20)
            .map((v, i) => v !== null ? { time: times[i] as any, value: v } : null)
            .filter((v): v is LineData => v !== null)
        )
      }

      // SMA 50
      if (activeIndicators.includes('SMA50')) {
        const sma50 = mc.addLineSeries({ color: TV_COLORS.sma50Color, lineWidth: 1, title: 'SMA 50' })
        sma50.setData(
          sma(closes, 50)
            .map((v, i) => v !== null ? { time: times[i] as any, value: v } : null)
            .filter((v): v is LineData => v !== null)
        )
      }

      // Bollinger Bands
      if (activeIndicators.includes('BB')) {
        const bb = bollingerBands(closes, 20, 2)
        const bbUpper = mc.addLineSeries({
          color: TV_COLORS.bbColor, lineWidth: 1, lineStyle: LineStyle.Dashed, title: 'BB Upper',
        })
        const bbMid = mc.addLineSeries({
          color: TV_COLORS.bbColor, lineWidth: 1, lineStyle: LineStyle.Dotted, title: 'BB Mid',
        })
        const bbLower = mc.addLineSeries({
          color: TV_COLORS.bbColor, lineWidth: 1, lineStyle: LineStyle.Dashed, title: 'BB Lower',
        })
        bbUpper.setData(bb.upper.map((v, i) => v !== null ? { time: times[i] as any, value: v } : null).filter((v): v is LineData => v !== null))
        bbMid.setData(bb.mid.map((v, i) => v !== null ? { time: times[i] as any, value: v } : null).filter((v): v is LineData => v !== null))
        bbLower.setData(bb.lower.map((v, i) => v !== null ? { time: times[i] as any, value: v } : null).filter((v): v is LineData => v !== null))
      }

      // Volume histogram (bottom pane via separate price scale)
      if (activeIndicators.includes('Volume')) {
        const vol = mc.addHistogramSeries({
          color: '#26a69a44',
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        })
        mc.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
        vol.setData(candles.map(c => ({
          time: c.time as any,
          value: c.volume,
          color: c.close >= c.open ? '#26a69a44' : '#ef535044',
        })))
      }
    }

    mc.timeScale().fitContent()

    // ── RSI panel ──
    if (rsiEnabled && rsiRef.current) {
      const rc = createChart(rsiRef.current, {
        ...baseChartOptions(100),
        width: rsiRef.current.clientWidth,
      })
      rsiChart.current = rc
      const rsiLine = rc.addLineSeries({ color: TV_COLORS.rsiColor, lineWidth: 1, title: 'RSI 14' })
      rsiLine.setData(
        rsi(closes, 14)
          .map((v, i) => v !== null ? { time: times[i] as any, value: v } : null)
          .filter((v): v is LineData => v !== null)
      )
      // Overbought / oversold lines
      const ob = rc.addLineSeries({ color: '#ef5350', lineWidth: 1, lineStyle: LineStyle.Dashed })
      const os = rc.addLineSeries({ color: '#26a69a', lineWidth: 1, lineStyle: LineStyle.Dashed })
      const tFirst = times[0] as any
      const tLast = times[times.length - 1] as any
      ob.setData([{ time: tFirst, value: 70 }, { time: tLast, value: 70 }])
      os.setData([{ time: tFirst, value: 30 }, { time: tLast, value: 30 }])
      rc.timeScale().fitContent()
    }

    // ── MACD panel ──
    if (macdEnabled && macdRef.current) {
      const macc = createChart(macdRef.current, {
        ...baseChartOptions(100),
        width: macdRef.current.clientWidth,
      })
      macdChart.current = macc
      const { macdLine, signalLine, histogram } = macd(closes, 12, 26, 9)
      const macdSeries = macc.addLineSeries({ color: TV_COLORS.macdFastColor, lineWidth: 1, title: 'MACD' })
      const signalSeries = macc.addLineSeries({ color: TV_COLORS.macdSignalColor, lineWidth: 1, title: 'Signal' })
      const histSeries = macc.addHistogramSeries({ title: 'Histogram' })
      macdSeries.setData(
        macdLine.map((v, i) => v !== null ? { time: times[i] as any, value: v } : null)
          .filter((v): v is LineData => v !== null)
      )
      signalSeries.setData(
        signalLine.map((v, i) => v !== null ? { time: times[i] as any, value: v } : null)
          .filter((v): v is LineData => v !== null)
      )
      histSeries.setData(
        histogram.map((v, i) => v !== null ? {
          time: times[i] as any,
          value: v,
          color: v >= 0 ? TV_COLORS.macdHistUpColor : TV_COLORS.macdHistDownColor,
        } : null).filter((v): v is HistogramData => v !== null)
      )
      macc.timeScale().fitContent()
    }

    // ── Responsive resize ──
    const handleResize = () => {
      if (mainRef.current) mc.applyOptions({ width: mainRef.current.clientWidth })
      if (rsiRef.current && rsiChart.current) rsiChart.current.applyOptions({ width: rsiRef.current.clientWidth })
      if (macdRef.current && macdChart.current) macdChart.current.applyOptions({ width: macdRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      mc.remove()
      rsiChart.current?.remove()
      macdChart.current?.remove()
      mainChart.current = null
      rsiChart.current = null
      macdChart.current = null
    }
  }, [candleData, activeIndicators, rsiEnabled, macdEnabled, compareMode, compareTickers, selectedTicker])

  // ── Helpers ──
  const toggleIndicator = (ind: string) => {
    setActiveIndicators(prev =>
      prev.includes(ind) ? prev.filter(i => i !== ind) : [...prev, ind]
    )
  }

  const addToWatchlist = (ticker: string) => {
    if (!watchlist.includes(ticker)) setWatchlist(prev => [...prev, ticker])
  }

  const addCompare = () => {
    const t = compareInput.trim()
    if (t && !compareTickers.includes(t) && compareTickers.length < 4) {
      setCompareTickers(prev => [...prev, t])
    }
    setCompareInput('')
  }

  const meta = candleData?.meta
  const latestCandle = candleData?.candles[candleData.candles.length - 1]
  const prevCandle = candleData?.candles[candleData.candles.length - 2]
  const changePct = latestCandle && prevCandle
    ? ((latestCandle.close - prevCandle.close) / prevCandle.close) * 100
    : null
  const changeUp = changePct !== null && changePct >= 0

  // ── Render ──
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#0d1117] font-mono text-sm text-[#8b949e]">

      {/* ── Top bar ── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-[#21262d] bg-[#161b22] px-4 py-2">
        {/* Logo */}
        <span className="mr-2 text-xs font-bold tracking-widest text-[#15b570]">CARDEX TRADINGCAR</span>

        {/* Ticker search */}
        <TickerSearch value={selectedTicker} onChange={t => { setSelectedTicker(t); setCompareMode(false) }} />

        {/* Period buttons */}
        <div className="flex rounded border border-[#21262d] overflow-hidden">
          {(['W', 'M'] as const).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 text-xs transition-colors ${period === p ? 'bg-[#21262d] text-white' : 'text-[#8b949e] hover:text-white'}`}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Indicators dropdown */}
        <div className="relative">
          <button
            onClick={() => setIndicatorsOpen(!indicatorsOpen)}
            className="flex items-center gap-1 rounded border border-[#21262d] px-3 py-1 text-xs hover:bg-[#1c2128] hover:text-white"
          >
            Indicators
            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {indicatorsOpen && (
            <div className="absolute left-0 top-full z-50 mt-1 w-48 rounded border border-[#21262d] bg-[#161b22] shadow-xl">
              {[
                { id: 'SMA20', label: 'SMA 20', color: TV_COLORS.sma20Color },
                { id: 'SMA50', label: 'SMA 50', color: TV_COLORS.sma50Color },
                { id: 'BB', label: 'Bollinger Bands', color: TV_COLORS.bbColor },
                { id: 'Volume', label: 'Volume', color: '#8b949e' },
              ].map(ind => (
                <label key={ind.id} className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-[#1c2128]">
                  <input
                    type="checkbox"
                    checked={activeIndicators.includes(ind.id)}
                    onChange={() => toggleIndicator(ind.id)}
                    className="accent-[#15b570]"
                  />
                  <span className="h-2 w-2 rounded-full" style={{ background: ind.color }} />
                  <span className="text-xs text-white">{ind.label}</span>
                </label>
              ))}
              <div className="border-t border-[#21262d] px-3 py-2">
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={rsiEnabled} onChange={e => setRsiEnabled(e.target.checked)} className="accent-[#15b570]" />
                  <span className="h-2 w-2 rounded-full" style={{ background: TV_COLORS.rsiColor }} />
                  <span className="text-xs text-white">RSI 14</span>
                </label>
                <label className="mt-1 flex cursor-pointer items-center gap-2">
                  <input type="checkbox" checked={macdEnabled} onChange={e => setMacdEnabled(e.target.checked)} className="accent-[#15b570]" />
                  <span className="h-2 w-2 rounded-full" style={{ background: TV_COLORS.macdFastColor }} />
                  <span className="text-xs text-white">MACD</span>
                </label>
              </div>
            </div>
          )}
        </div>

        {/* Compare */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCompareMode(!compareMode)}
            className={`flex items-center gap-1 rounded border px-3 py-1 text-xs transition-colors ${compareMode ? 'border-[#15b570] text-[#15b570]' : 'border-[#21262d] hover:bg-[#1c2128] hover:text-white'}`}
          >
            Compare +
          </button>
          {compareMode && (
            <div className="flex items-center gap-1">
              <input
                value={compareInput}
                onChange={e => setCompareInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addCompare()}
                placeholder="Ticker ID..."
                className="w-40 rounded border border-[#21262d] bg-[#161b22] px-2 py-1 text-xs text-white placeholder:text-[#8b949e] focus:border-[#15b570] focus:outline-none"
              />
              <button onClick={addCompare} className="rounded bg-[#15b570] px-2 py-1 text-xs text-black">Add</button>
              {compareTickers.map(t => (
                <span key={t} className="flex items-center gap-1 rounded bg-[#1c2128] px-2 py-0.5 text-xs text-white">
                  {t.split('_').slice(0, 2).join(' ')}
                  <button onClick={() => setCompareTickers(prev => prev.filter(x => x !== t))} className="text-[#ef5350]">×</button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button className="rounded border border-[#21262d] px-3 py-1 text-xs hover:bg-[#1c2128] hover:text-white">
            Fullscreen
          </button>
        </div>
      </div>

      {/* ── Ticker info bar ── */}
      <div className="flex shrink-0 items-center gap-6 border-b border-[#21262d] bg-[#0d1117] px-4 py-2">
        {meta && (
          <>
            <div className="flex items-center gap-2">
              <span className="text-base text-white">
                {COUNTRY_FLAGS[meta.country] ?? meta.country} {meta.make} {meta.model} {meta.year}
              </span>
              <span className="text-[#8b949e]">·</span>
              <span className="text-xs text-[#8b949e]">{meta.country} · {meta.fuel}</span>
              {changePct !== null && (
                <span className={`text-sm font-bold ${changeUp ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                  {changeUp ? '+' : ''}{changePct.toFixed(2)}% {changeUp ? '↑' : '↓'} This {period === 'M' ? 'month' : 'week'}
                </span>
              )}
            </div>
            {latestCandle && (
              <div className="flex items-center gap-4 text-xs">
                <span className="text-lg font-bold text-white">€{Math.round(latestCandle.close).toLocaleString()}</span>
                <span>H: <span className="text-[#26a69a]">€{Math.round(latestCandle.high).toLocaleString()}</span></span>
                <span>L: <span className="text-[#ef5350]">€{Math.round(latestCandle.low).toLocaleString()}</span></span>
                <span>V: <span className="text-white">{latestCandle.volume.toLocaleString()} listings</span></span>
              </div>
            )}
          </>
        )}
        {loading && <span className="text-xs text-[#15b570] animate-pulse">Loading...</span>}
      </div>

      {/* ── Main content ── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">

        {/* ── Chart area ── */}
        <div className="flex flex-1 flex-col overflow-y-auto">

          {/* Main price chart */}
          <div ref={mainRef} className="w-full" style={{ height: compareMode ? 400 : 500 }} />

          {/* RSI panel */}
          {rsiEnabled && (
            <div className="border-t border-[#21262d]">
              <div className="flex items-center gap-2 px-3 py-1 text-[10px] text-[#8b949e]">
                <span className="font-bold" style={{ color: TV_COLORS.rsiColor }}>RSI(14)</span>
                <span>— 30/70 levels</span>
              </div>
              <div ref={rsiRef} className="w-full" style={{ height: 100 }} />
            </div>
          )}

          {/* MACD panel */}
          {macdEnabled && (
            <div className="border-t border-[#21262d]">
              <div className="flex items-center gap-2 px-3 py-1 text-[10px] text-[#8b949e]">
                <span className="font-bold" style={{ color: TV_COLORS.macdFastColor }}>MACD(12,26,9)</span>
                <span className="text-[#e91e63]">Signal</span>
                <span className="text-[#8b949e]">Histogram</span>
              </div>
              <div ref={macdRef} className="w-full" style={{ height: 100 }} />
            </div>
          )}

          {/* ── Bottom panels: Watchlist + Scanner ── */}
          <div className="flex shrink-0 border-t border-[#21262d]">

            {/* Watchlist */}
            <div className="w-1/3 border-r border-[#21262d] bg-[#161b22]">
              <div className="flex items-center justify-between border-b border-[#21262d] px-3 py-2">
                <span className="text-xs font-bold text-white">WATCHLIST</span>
              </div>
              <ul>
                {watchlist.map(ticker => {
                  const td = watchlistData[ticker]
                  const parts = ticker.split('_')
                  const country = parts[parts.length - 2]
                  const year = parts[parts.length - 3]
                  const model = parts.slice(1, parts.length - 3).join(' ')
                  const label = `${parts[0]} ${model} ${year}`
                  return (
                    <li
                      key={ticker}
                      onClick={() => setSelectedTicker(ticker)}
                      className={`flex cursor-pointer items-center justify-between px-3 py-2 hover:bg-[#1c2128] ${selectedTicker === ticker ? 'bg-[#1c2128] border-l-2 border-[#15b570]' : ''}`}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="shrink-0">{COUNTRY_FLAGS[country] ?? country}</span>
                        <span className="truncate text-xs text-white">{label}</span>
                      </div>
                      {td && (
                        <span className={`shrink-0 text-xs font-mono ${td.change_1m_pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                          {td.change_1m_pct >= 0 ? '+' : ''}{td.change_1m_pct.toFixed(1)}%
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
              <div className="border-t border-[#21262d] px-3 py-2">
                <button
                  onClick={() => addToWatchlist(selectedTicker)}
                  className="text-xs text-[#15b570] hover:underline"
                >
                  + Add current to watchlist
                </button>
              </div>
            </div>

            {/* Scanner */}
            <div className="flex-1 bg-[#161b22]">
              <div className="flex items-center justify-between border-b border-[#21262d] px-3 py-2">
                <span className="text-xs font-bold text-white">MARKET SCANNER</span>
                <select
                  value={scannerType}
                  onChange={e => setScannerType(e.target.value)}
                  className="rounded border border-[#21262d] bg-[#0d1117] px-2 py-0.5 text-xs text-white focus:outline-none"
                >
                  {SCANNER_TYPES.map(st => (
                    <option key={st.value} value={st.value}>{st.label}</option>
                  ))}
                </select>
              </div>
              <ul>
                {scannerData.map(row => (
                  <li
                    key={row.ticker_id}
                    onClick={() => setSelectedTicker(row.ticker_id)}
                    className="flex cursor-pointer items-center justify-between px-3 py-2 hover:bg-[#1c2128]"
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="shrink-0">{COUNTRY_FLAGS[row.country] ?? row.country}</span>
                      <span className="truncate text-xs text-white">{row.make} {row.model} {row.year}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className={`text-xs font-mono ${row.change_1m_pct >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                        {row.change_1m_pct >= 0 ? '+' : ''}{row.change_1m_pct.toFixed(1)}%
                      </span>
                      <span className="text-xs text-[#8b949e]">→</span>
                    </div>
                  </li>
                ))}
                {scannerData.length === 0 && (
                  <li className="px-3 py-4 text-center text-xs text-[#8b949e]">No data</li>
                )}
              </ul>
            </div>

          </div>
        </div>
      </div>
    </div>
  )
}
