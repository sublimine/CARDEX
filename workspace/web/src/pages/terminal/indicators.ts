/**
 * CARDEX Terminal — Technical Indicator Library
 * 53 indicators across 6 categories. Math is TradingView-compatible.
 *
 * EMA seed rule (invariant): SEED = SMA(close[0..length-1]) at index length-1.
 * Recurrence starts at index length, NOT from data[0].close.
 * This applies to every function that calls emaFromValues internally.
 *
 * RMA/SMMA (Wilder): alpha = 1/length, seed = SMA.
 * BB stddev: POPULATION divisor (÷ length, not ÷ length-1).
 * ATR: TrueRange = max(H-L, |H-Pc|, |L-Pc|), smoothed with RMA.
 */

// TYPE-ONLY import to avoid circular dependency:
// indicators.ts imports types from market.ts; market.ts re-exports calc* from here.
import type { Bar, PD } from './market'

// ─────────────────────────────────────────────────────────────────────────────
// Normalized output types (chart renderer consumes these generically)
// ─────────────────────────────────────────────────────────────────────────────

export interface IndPoint { time: string; value: number; color?: string }
export type IndSeriesKind = 'line' | 'hist' | 'area' | 'band'
export interface IndSeries {
  key: string
  kind: IndSeriesKind
  data: IndPoint[]
  color: string
  lineStyle?: 0 | 1 | 2   // 0=solid 1=dotted 2=dashed
  lineWidth?: 1 | 2
}
export interface IndicatorDef {
  id: string
  name: string
  category: string
  pane: 'overlay' | 'separate'
  inputs: { name: string; default: number }[]
  levels?: { value: number; color: string }[]
  compute: (bars: Bar[], params: Record<string, number>) => IndSeries[]
}

// ─────────────────────────────────────────────────────────────────────────────
// Brand color palette
// ─────────────────────────────────────────────────────────────────────────────

const C = {
  // Overlay (warm/cool alternation)
  gold:    '#fbbf24',
  blue:    '#60a5fa',
  teal:    '#2dd4bf',
  fuchsia: '#e879f9',
  violet:  '#a78bfa',
  rose:    '#fb7185',
  amber:   '#f59e0b',
  sky:     '#38bdf8',
  indigo:  '#818cf8',
  brown:   '#a16207',
  // Oscillator / separate pane
  oscPurple: '#7c3aed',
  oscAmber:  '#d97706',
  oscTeal:   '#0891b2',
  oscPink:   '#db2777',
  oscGreen:  '#059669',
  oscRed:    '#dc2626',
  oscBlue:   '#2563eb',
  oscGray:   '#64748b',
  // Signal colors
  up:   '#26A69A',
  down: '#EF5350',
  // Guide lines
  guide: 'rgba(100,116,139,0.5)',
} as const

// ─────────────────────────────────────────────────────────────────────────────
// Primitive math helpers (NOT exported individually — use calc* exports below)
// ─────────────────────────────────────────────────────────────────────────────

/** Simple moving average over a number array. Returns NaN for i < length-1. */
function smaArr(src: number[], length: number): number[] {
  const out = new Array<number>(src.length).fill(NaN)
  let sum = 0
  for (let i = 0; i < src.length; i++) {
    sum += src[i]
    if (i >= length) sum -= src[i - length]
    if (i >= length - 1) out[i] = sum / length
  }
  return out
}

/**
 * EMA with CORRECT TradingView seed.
 * Seed = SMA(src[0..length-1]) placed at index length-1.
 * Recurrence: ema[i] = src[i]*k + ema[i-1]*(1-k) for i >= length.
 * Returns NaN for i < length-1.
 */
function emaArr(src: number[], length: number): number[] {
  const out = new Array<number>(src.length).fill(NaN)
  if (src.length < length) return out
  const k = 2 / (length + 1)
  // Seed: SMA of first `length` values
  let seed = 0
  for (let i = 0; i < length; i++) seed += src[i]
  seed /= length
  out[length - 1] = seed
  for (let i = length; i < src.length; i++) {
    out[i] = src[i] * k + out[i - 1] * (1 - k)
  }
  return out
}

/**
 * Wilder RMA (SMMA). alpha = 1/length.
 * Seed = SMA(src[0..length-1]) placed at index length-1.
 * Recurrence: rma[i] = (rma[i-1]*(length-1) + src[i]) / length for i >= length.
 */
function rmaArr(src: number[], length: number): number[] {
  const out = new Array<number>(src.length).fill(NaN)
  if (src.length < length) return out
  let seed = 0
  for (let i = 0; i < length; i++) seed += src[i]
  seed /= length
  out[length - 1] = seed
  for (let i = length; i < src.length; i++) {
    out[i] = (out[i - 1] * (length - 1) + src[i]) / length
  }
  return out
}

/** WMA (linear weights 1..length, most recent = length). Returns NaN for i < length-1. */
function wmaArr(src: number[], length: number): number[] {
  const out = new Array<number>(src.length).fill(NaN)
  const denom = (length * (length + 1)) / 2
  for (let i = length - 1; i < src.length; i++) {
    let s = 0
    for (let j = 0; j < length; j++) s += src[i - length + 1 + j] * (j + 1)
    out[i] = s / denom
  }
  return out
}

/** True Range. tr[0] = high[0] - low[0]. */
function trArr(bars: Bar[]): number[] {
  return bars.map((b, i) => {
    if (i === 0) return b.high - b.low
    const pc = bars[i - 1].close
    return Math.max(b.high - b.low, Math.abs(b.high - pc), Math.abs(b.low - pc))
  })
}

/** ATR via Wilder RMA. Returns NaN for i < length-1. */
function atrArr(bars: Bar[], length: number): number[] {
  return rmaArr(trArr(bars), length)
}

/** Convert a number[] to IndPoint[] using bar times, skipping NaN. */
function toPoints(bars: Bar[], values: number[]): IndPoint[] {
  const out: IndPoint[] = []
  for (let i = 0; i < values.length; i++) {
    if (!isNaN(values[i])) out.push({ time: bars[i].time, value: values[i] })
  }
  return out
}

/** Bollinger Bands helper: returns { basis, upper, lower } as number arrays. */
function bbArrs(bars: Bar[], length: number, mult: number): { basis: number[]; upper: number[]; lower: number[] } {
  const close = bars.map(b => b.close)
  const basis = smaArr(close, length)
  const upper = new Array<number>(bars.length).fill(NaN)
  const lower = new Array<number>(bars.length).fill(NaN)
  for (let i = length - 1; i < bars.length; i++) {
    const m = basis[i]
    let v = 0
    for (let k = i - length + 1; k <= i; k++) v += (close[k] - m) ** 2
    const sd = Math.sqrt(v / length) // population stddev
    upper[i] = m + mult * sd
    lower[i] = m - mult * sd
  }
  return { basis, upper, lower }
}

/** Pivot point for previous session (uses last full bar as "previous" in flat series). */
function lastSessionHLC(bars: Bar[]): { h: number; l: number; c: number } {
  if (bars.length < 2) return { h: 0, l: 0, c: 0 }
  const b = bars[bars.length - 2]
  return { h: b.high, l: b.low, c: b.close }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public calc* API (backward-compat with MarketChart.tsx imports from market.ts)
// ─────────────────────────────────────────────────────────────────────────────

/** SMA — Bar[] → PD[]. */
export function calcSMA(data: Bar[], period: number): PD[] {
  const close = data.map(b => b.close)
  const vals = smaArr(close, period)
  const out: PD[] = []
  for (let i = 0; i < vals.length; i++) {
    if (!isNaN(vals[i])) out.push({ time: data[i].time, value: vals[i] })
  }
  return out
}

/** EMA — correct seed at index length-1. */
export function calcEMA(data: Bar[], period: number): PD[] {
  const close = data.map(b => b.close)
  const vals = emaArr(close, period)
  const out: PD[] = []
  for (let i = 0; i < vals.length; i++) {
    if (!isNaN(vals[i])) out.push({ time: data[i].time, value: vals[i] })
  }
  return out
}

/** Bollinger Bands — returns { mid, upper, lower } as PD[]. */
export function calcBB(data: Bar[], period = 20, mult = 2): { mid: PD[]; upper: PD[]; lower: PD[] } {
  const { basis, upper, lower } = bbArrs(data, period, mult)
  const toP = (arr: number[]): PD[] => {
    const out: PD[] = []
    for (let i = 0; i < arr.length; i++) {
      if (!isNaN(arr[i])) out.push({ time: data[i].time, value: arr[i] })
    }
    return out
  }
  return { mid: toP(basis), upper: toP(upper), lower: toP(lower) }
}

/** RSI — Wilder RMA. Returns PD[] starting at index `period`. */
export function calcRSI(data: Bar[], period = 14): PD[] {
  if (data.length < period + 1) return []
  // Build gain/loss arrays (index 0 unused, diffs start at 1)
  const gain: number[] = [0]
  const loss: number[] = [0]
  for (let i = 1; i < data.length; i++) {
    const d = data[i].close - data[i - 1].close
    gain.push(d > 0 ? d : 0)
    loss.push(d < 0 ? -d : 0)
  }
  // Seed: SMA of gain[1..period] and loss[1..period]
  let ag = 0, al = 0
  for (let i = 1; i <= period; i++) { ag += gain[i]; al += loss[i] }
  ag /= period; al /= period
  const out: PD[] = []
  for (let i = period; i < data.length; i++) {
    if (i > period) {
      ag = (ag * (period - 1) + gain[i]) / period
      al = (al * (period - 1) + loss[i]) / period
    }
    const rsi = al === 0 ? 100 : 100 - 100 / (1 + ag / al)
    out.push({ time: data[i].time, value: rsi })
  }
  return out
}

/** MACD — correct EMA seeds. Returns { macd, signal, hist }. */
export function calcMACD(
  data: Bar[],
  fast = 12,
  slow = 26,
  signal = 9,
): { macd: PD[]; signal: PD[]; hist: { time: string; value: number; color: string }[] } {
  const close = data.map(b => b.close)
  const eFast = emaArr(close, fast)
  const eSlow = emaArr(close, slow)
  // MACD line: defined where slow EMA is defined (i >= slow-1)
  const macdVals: PD[] = []
  for (let i = slow - 1; i < data.length; i++) {
    if (!isNaN(eFast[i]) && !isNaN(eSlow[i])) {
      macdVals.push({ time: data[i].time, value: eFast[i] - eSlow[i] })
    }
  }
  if (macdVals.length === 0) return { macd: [], signal: [], hist: [] }
  // Signal line: EMA of macd values with correct seed
  const macdNumeric = macdVals.map(p => p.value)
  const sigVals = emaArr(macdNumeric, signal)
  const signalPts: PD[] = []
  const histPts: { time: string; value: number; color: string }[] = []
  for (let i = 0; i < macdVals.length; i++) {
    if (!isNaN(sigVals[i])) {
      signalPts.push({ time: macdVals[i].time, value: sigVals[i] })
      const h = macdVals[i].value - sigVals[i]
      histPts.push({ time: macdVals[i].time, value: h, color: h >= 0 ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' })
    }
  }
  return { macd: macdVals, signal: signalPts, hist: histPts }
}

/** VWAP — cumulative from first bar, resets on date boundary. */
export function calcVWAP(data: Bar[]): PD[] {
  let cumPV = 0, cumVol = 0
  let lastDate = ''
  return data.map(b => {
    const date = b.time.slice(0, 10)
    if (date !== lastDate) { cumPV = 0; cumVol = 0; lastDate = date }
    const tp = (b.high + b.low + b.close) / 3
    cumPV += tp * b.volume
    cumVol += b.volume
    return { time: b.time, value: cumVol > 0 ? cumPV / cumVol : tp }
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// Indicator catalog — 53 entries in 6 categories
// ─────────────────────────────────────────────────────────────────────────────

// Helper: build a single-series overlay
function oneOverlay(key: string, color: string, data: IndPoint[], lineWidth: 1 | 2 = 1): IndSeries[] {
  return [{ key, kind: 'line', data, color, lineWidth }]
}

const INDICATOR_CATALOG_INTERNAL: IndicatorDef[] = [
  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Moving Averages
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'sma',
    name: 'Simple Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 9 }],
    compute(bars, p) {
      // SMA: sliding sum divided by period. NaN for i < length-1.
      const length = Math.round(p.length ?? 9)
      const close = bars.map(b => b.close)
      return oneOverlay('sma', C.blue, toPoints(bars, smaArr(close, length)), 1)
    },
  },
  {
    id: 'ema',
    name: 'Exponential Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 9 }],
    compute(bars, p) {
      // EMA seed = SMA(close[0..length-1]), recurrence from index length.
      const length = Math.round(p.length ?? 9)
      const close = bars.map(b => b.close)
      return oneOverlay('ema', C.gold, toPoints(bars, emaArr(close, length)), 1)
    },
  },
  {
    id: 'wma',
    name: 'Weighted Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 9 }],
    compute(bars, p) {
      // WMA: linear weights 1..length, most recent bar = weight length.
      const length = Math.round(p.length ?? 9)
      const close = bars.map(b => b.close)
      return oneOverlay('wma', C.teal, toPoints(bars, wmaArr(close, length)), 1)
    },
  },
  {
    id: 'vwma',
    name: 'Volume Weighted Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 20 }],
    compute(bars, p) {
      // VWMA: sum(close*vol, window) / sum(vol, window).
      const length = Math.round(p.length ?? 20)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        let numer = 0, denom = 0
        for (let k = i - length + 1; k <= i; k++) {
          numer += bars[k].close * bars[k].volume
          denom += bars[k].volume
        }
        out[i] = denom > 0 ? numer / denom : NaN
      }
      return oneOverlay('vwma', C.violet, toPoints(bars, out), 1)
    },
  },
  {
    id: 'hma',
    name: 'Hull Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 16 }],
    compute(bars, p) {
      // HMA = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
      const length = Math.round(p.length ?? 16)
      const half = Math.round(length / 2)
      const sqrtLen = Math.round(Math.sqrt(length))
      const close = bars.map(b => b.close)
      const wmaHalf = wmaArr(close, half)
      const wmaFull = wmaArr(close, length)
      const raw = wmaHalf.map((v, i) => isNaN(v) || isNaN(wmaFull[i]) ? NaN : 2 * v - wmaFull[i])
      const hma = wmaArr(raw, sqrtLen)
      return oneOverlay('hma', C.rose, toPoints(bars, hma), 1)
    },
  },
  {
    id: 'dema',
    name: 'Double Exponential Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 9 }],
    compute(bars, p) {
      // DEMA = 2*EMA1 - EMA2, where EMA2 = EMA(EMA1, length).
      const length = Math.round(p.length ?? 9)
      const close = bars.map(b => b.close)
      const ema1 = emaArr(close, length)
      const ema2 = emaArr(ema1, length) // NaN seeds propagate correctly
      const dema = ema1.map((v, i) => isNaN(v) || isNaN(ema2[i]) ? NaN : 2 * v - ema2[i])
      return oneOverlay('dema', C.amber, toPoints(bars, dema), 1)
    },
  },
  {
    id: 'tema',
    name: 'Triple Exponential Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 9 }],
    compute(bars, p) {
      // TEMA = 3*EMA1 - 3*EMA2 + EMA3.
      const length = Math.round(p.length ?? 9)
      const close = bars.map(b => b.close)
      const ema1 = emaArr(close, length)
      const ema2 = emaArr(ema1, length)
      const ema3 = emaArr(ema2, length)
      const tema = ema1.map((v, i) => {
        if (isNaN(v) || isNaN(ema2[i]) || isNaN(ema3[i])) return NaN
        return 3 * v - 3 * ema2[i] + ema3[i]
      })
      return oneOverlay('tema', C.sky, toPoints(bars, tema), 1)
    },
  },
  {
    id: 'smma_rma',
    name: 'Smoothed MA / Wilder RMA',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 14 }],
    compute(bars, p) {
      // RMA: alpha = 1/length, seed = SMA(close[0..length-1]).
      const length = Math.round(p.length ?? 14)
      const close = bars.map(b => b.close)
      return oneOverlay('rma', C.brown, toPoints(bars, rmaArr(close, length)), 1)
    },
  },
  {
    id: 'alma',
    name: 'Arnaud Legoux Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [
      { name: 'length', default: 9 },
      { name: 'offset', default: 0.85 },
      { name: 'sigma', default: 6 },
    ],
    compute(bars, p) {
      // ALMA: Gaussian-weighted MA. m = offset*(length-1), s = length/sigma.
      const length = Math.round(p.length ?? 9)
      const offset = p.offset ?? 0.85
      const sigma = p.sigma ?? 6
      const m = offset * (length - 1)
      const s = length / sigma
      const w: number[] = []
      for (let j = 0; j < length; j++) w.push(Math.exp(-((j - m) ** 2) / (2 * s * s)))
      const norm = w.reduce((a, b) => a + b, 0)
      const out: number[] = new Array(bars.length).fill(NaN)
      const close = bars.map(b => b.close)
      for (let i = length - 1; i < bars.length; i++) {
        let sum = 0
        for (let j = 0; j < length; j++) sum += close[i - length + 1 + j] * w[j]
        out[i] = sum / norm
      }
      return oneOverlay('alma', C.indigo, toPoints(bars, out), 1)
    },
  },
  {
    id: 'lsma',
    name: 'Least Squares Moving Average',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [
      { name: 'length', default: 25 },
      { name: 'offset', default: 0 },
    ],
    compute(bars, p) {
      // LSMA: linear regression endpoint. x=0..length-1 (0=oldest), value at x=length-1-offset.
      const length = Math.round(p.length ?? 25)
      const offset = p.offset ?? 0
      const close = bars.map(b => b.close)
      const out: number[] = new Array(bars.length).fill(NaN)
      const sumX = (length * (length - 1)) / 2
      const sumX2 = (length * (length - 1) * (2 * length - 1)) / 6
      const denom = length * sumX2 - sumX * sumX
      for (let i = length - 1; i < bars.length; i++) {
        let sumY = 0, sumXY = 0
        for (let j = 0; j < length; j++) {
          sumY += close[i - length + 1 + j]
          sumXY += j * close[i - length + 1 + j]
        }
        if (Math.abs(denom) < 1e-10) { out[i] = sumY / length; continue }
        const slope = (length * sumXY - sumX * sumY) / denom
        const intercept = (sumY - slope * sumX) / length
        out[i] = intercept + slope * (length - 1 - offset)
      }
      return oneOverlay('lsma', C.oscGray, toPoints(bars, out), 1)
    },
  },
  {
    id: 'vwap_ma',
    name: 'MA Cross (Fast / Slow SMA)',
    category: 'Moving Averages',
    pane: 'overlay',
    inputs: [
      { name: 'fast', default: 9 },
      { name: 'slow', default: 21 },
    ],
    compute(bars, p) {
      // Convenience: fast SMA and slow SMA for cross signals.
      const fast = Math.round(p.fast ?? 9)
      const slow = Math.round(p.slow ?? 21)
      const close = bars.map(b => b.close)
      return [
        { key: 'fast', kind: 'line', data: toPoints(bars, smaArr(close, fast)), color: C.up, lineWidth: 1 },
        { key: 'slow', kind: 'line', data: toPoints(bars, smaArr(close, slow)), color: C.down, lineWidth: 1 },
      ]
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Oscillators
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'rsi',
    name: 'Relative Strength Index',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    levels: [
      { value: 70, color: C.guide },
      { value: 50, color: C.guide },
      { value: 30, color: C.guide },
    ],
    compute(bars, p) {
      // RSI: Wilder RMA of gain/loss. avgGain seed = SMA(gain[1..length]).
      const length = Math.round(p.length ?? 14)
      const pts = calcRSI(bars, length)
      return [{ key: 'rsi', kind: 'line', data: pts, color: C.oscPurple, lineWidth: 2 }]
    },
  },
  {
    id: 'stochastic',
    name: 'Stochastic Oscillator',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'kLength', default: 14 },
      { name: 'kSmooth', default: 1 },
      { name: 'dSmooth', default: 3 },
    ],
    levels: [
      { value: 80, color: C.guide },
      { value: 20, color: C.guide },
    ],
    compute(bars, p) {
      // Stochastic %K = 100*(close-LL)/(HH-LL), smoothed with SMA(kSmooth); %D = SMA(%K, dSmooth).
      const kL = Math.round(p.kLength ?? 14)
      const kS = Math.round(p.kSmooth ?? 1)
      const dS = Math.round(p.dSmooth ?? 3)
      const rawK: number[] = new Array(bars.length).fill(NaN)
      for (let i = kL - 1; i < bars.length; i++) {
        let hh = -Infinity, ll = Infinity
        for (let k = i - kL + 1; k <= i; k++) {
          if (bars[k].high > hh) hh = bars[k].high
          if (bars[k].low < ll) ll = bars[k].low
        }
        rawK[i] = hh === ll ? 50 : 100 * (bars[i].close - ll) / (hh - ll)
      }
      const kVals = kS <= 1 ? rawK : smaArr(rawK, kS)
      const dVals = smaArr(kVals, dS)
      return [
        { key: 'k', kind: 'line', data: toPoints(bars, kVals), color: C.oscBlue, lineWidth: 2 },
        { key: 'd', kind: 'line', data: toPoints(bars, dVals), color: C.oscAmber, lineWidth: 1 },
      ]
    },
  },
  {
    id: 'stoch_rsi',
    name: 'Stochastic RSI',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'rsiLength', default: 14 },
      { name: 'stochLength', default: 14 },
      { name: 'kSmooth', default: 3 },
      { name: 'dSmooth', default: 3 },
    ],
    levels: [
      { value: 80, color: C.guide },
      { value: 20, color: C.guide },
    ],
    compute(bars, p) {
      // StochRSI: stochastic applied to RSI series.
      const rsiLen = Math.round(p.rsiLength ?? 14)
      const stochLen = Math.round(p.stochLength ?? 14)
      const kS = Math.round(p.kSmooth ?? 3)
      const dS = Math.round(p.dSmooth ?? 3)
      const rsiPts = calcRSI(bars, rsiLen)
      if (rsiPts.length < stochLen) return []
      const rsiVals = rsiPts.map(r => r.value)
      const stoch: number[] = new Array(rsiVals.length).fill(NaN)
      for (let i = stochLen - 1; i < rsiVals.length; i++) {
        let hh = -Infinity, ll = Infinity
        for (let k = i - stochLen + 1; k <= i; k++) {
          if (rsiVals[k] > hh) hh = rsiVals[k]
          if (rsiVals[k] < ll) ll = rsiVals[k]
        }
        stoch[i] = (hh - ll) === 0 ? 0 : 100 * (rsiVals[i] - ll) / (hh - ll)
      }
      const kVals = smaArr(stoch, kS)
      const dVals = smaArr(kVals, dS)
      // Map back to bar times via rsiPts offset
      const offset = bars.length - rsiPts.length
      const toBarPts = (arr: number[]): IndPoint[] => {
        const out: IndPoint[] = []
        for (let i = 0; i < arr.length; i++) {
          if (!isNaN(arr[i])) out.push({ time: bars[offset + i].time, value: arr[i] })
        }
        return out
      }
      return [
        { key: 'k', kind: 'line', data: toBarPts(kVals), color: C.oscBlue, lineWidth: 2 },
        { key: 'd', kind: 'line', data: toBarPts(dVals), color: C.oscAmber, lineWidth: 1 },
      ]
    },
  },
  {
    id: 'macd',
    name: 'MACD',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'fast', default: 12 },
      { name: 'slow', default: 26 },
      { name: 'signal', default: 9 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // MACD = EMA(fast) - EMA(slow); signal = EMA(MACD, signal); hist = MACD - signal.
      const { macd, signal: sig, hist } = calcMACD(bars, p.fast ?? 12, p.slow ?? 26, p.signal ?? 9)
      const histPts: IndPoint[] = hist.map(h => ({ time: h.time, value: h.value, color: h.color }))
      return [
        { key: 'macd',   kind: 'line', data: macd, color: C.oscBlue, lineWidth: 2 },
        { key: 'signal', kind: 'line', data: sig,  color: C.oscAmber, lineWidth: 1 },
        { key: 'hist',   kind: 'hist', data: histPts, color: C.up },
      ]
    },
  },
  {
    id: 'cci',
    name: 'Commodity Channel Index',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 20 }],
    levels: [
      { value: 100,  color: C.guide },
      { value: 0,    color: C.guide },
      { value: -100, color: C.guide },
    ],
    compute(bars, p) {
      // CCI = (tp - SMA(tp)) / (0.015 * meanDeviation)
      const length = Math.round(p.length ?? 20)
      const tp = bars.map(b => (b.high + b.low + b.close) / 3)
      const sma = smaArr(tp, length)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        const m = sma[i]
        let dev = 0
        for (let k = i - length + 1; k <= i; k++) dev += Math.abs(tp[k] - m)
        dev /= length
        out[i] = dev === 0 ? 0 : (tp[i] - m) / (0.015 * dev)
      }
      return [{ key: 'cci', kind: 'line', data: toPoints(bars, out), color: C.oscAmber, lineWidth: 2 }]
    },
  },
  {
    id: 'williams_r',
    name: 'Williams %R',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    levels: [
      { value: -20, color: C.guide },
      { value: -80, color: C.guide },
    ],
    compute(bars, p) {
      // Williams %R = -100*(HH-close)/(HH-LL). Range -100..0.
      const length = Math.round(p.length ?? 14)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        let hh = -Infinity, ll = Infinity
        for (let k = i - length + 1; k <= i; k++) {
          if (bars[k].high > hh) hh = bars[k].high
          if (bars[k].low < ll) ll = bars[k].low
        }
        out[i] = (hh - ll) === 0 ? -50 : -100 * (hh - bars[i].close) / (hh - ll)
      }
      return [{ key: 'wr', kind: 'line', data: toPoints(bars, out), color: '#AB47BC', lineWidth: 2 }]
    },
  },
  {
    id: 'mfi',
    name: 'Money Flow Index',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    levels: [
      { value: 80, color: C.guide },
      { value: 20, color: C.guide },
    ],
    compute(bars, p) {
      // MFI: volume-weighted RSI analog. posFlow/negFlow based on tp direction.
      const length = Math.round(p.length ?? 14)
      const tp = bars.map(b => (b.high + b.low + b.close) / 3)
      const posFlow: number[] = [0]
      const negFlow: number[] = [0]
      for (let i = 1; i < bars.length; i++) {
        const mfv = tp[i] * bars[i].volume
        if (tp[i] > tp[i - 1]) { posFlow.push(mfv); negFlow.push(0) }
        else if (tp[i] < tp[i - 1]) { posFlow.push(0); negFlow.push(mfv) }
        else { posFlow.push(0); negFlow.push(0) }
      }
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let ps = 0, ns = 0
        for (let k = i - length + 1; k <= i; k++) { ps += posFlow[k]; ns += negFlow[k] }
        if (ns === 0) out[i] = 100
        else out[i] = 100 - 100 / (1 + ps / ns)
      }
      return [{ key: 'mfi', kind: 'line', data: toPoints(bars, out), color: C.oscGreen, lineWidth: 2 }]
    },
  },
  {
    id: 'awesome_oscillator',
    name: 'Awesome Oscillator',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'fast', default: 5 },
      { name: 'slow', default: 34 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // AO = SMA(median, fast) - SMA(median, slow). Histogram color by direction.
      const fast = Math.round(p.fast ?? 5)
      const slow = Math.round(p.slow ?? 34)
      const med = bars.map(b => (b.high + b.low) / 2)
      const smaF = smaArr(med, fast)
      const smaS = smaArr(med, slow)
      const ao = smaF.map((v, i) => isNaN(v) || isNaN(smaS[i]) ? NaN : v - smaS[i])
      const pts: IndPoint[] = []
      for (let i = 0; i < ao.length; i++) {
        if (isNaN(ao[i])) continue
        const prev = pts.length > 0 ? pts[pts.length - 1].value : ao[i]
        pts.push({ time: bars[i].time, value: ao[i], color: ao[i] >= prev ? C.up : C.down })
      }
      return [{ key: 'ao', kind: 'hist', data: pts, color: C.up }]
    },
  },
  {
    id: 'momentum',
    name: 'Momentum',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 10 }],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // MOM = close[i] - close[i-length].
      const length = Math.round(p.length ?? 10)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) out[i] = bars[i].close - bars[i - length].close
      return [{ key: 'mom', kind: 'line', data: toPoints(bars, out), color: C.oscBlue, lineWidth: 2 }]
    },
  },
  {
    id: 'roc',
    name: 'Rate of Change',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 9 }],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // ROC = 100*(close[i]-close[i-length])/close[i-length].
      const length = Math.round(p.length ?? 9)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        const prev = bars[i - length].close
        out[i] = prev === 0 ? 0 : 100 * (bars[i].close - prev) / prev
      }
      return [{ key: 'roc', kind: 'line', data: toPoints(bars, out), color: '#EC407A', lineWidth: 2 }]
    },
  },
  {
    id: 'trix',
    name: 'TRIX',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'length', default: 18 },
      { name: 'signal', default: 9 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // TRIX = 100*(EMA3[i]-EMA3[i-1])/EMA3[i-1]; signal = SMA(TRIX, signal).
      const length = Math.round(p.length ?? 18)
      const sigLen = Math.round(p.signal ?? 9)
      const close = bars.map(b => b.close)
      const ema1 = emaArr(close, length)
      const ema2 = emaArr(ema1, length)
      const ema3 = emaArr(ema2, length)
      const trix: number[] = new Array(bars.length).fill(NaN)
      for (let i = 1; i < bars.length; i++) {
        if (!isNaN(ema3[i]) && !isNaN(ema3[i - 1]) && ema3[i - 1] !== 0) {
          trix[i] = 100 * (ema3[i] - ema3[i - 1]) / ema3[i - 1]
        }
      }
      const sigVals = smaArr(trix, sigLen)
      return [
        { key: 'trix',   kind: 'line', data: toPoints(bars, trix),    color: '#5C6BC0', lineWidth: 2 },
        { key: 'signal', kind: 'line', data: toPoints(bars, sigVals),  color: '#FFA726', lineWidth: 1 },
      ]
    },
  },
  {
    id: 'ultimate_oscillator',
    name: 'Ultimate Oscillator',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'fast',  default: 7 },
      { name: 'mid',   default: 14 },
      { name: 'slow',  default: 28 },
    ],
    levels: [
      { value: 70, color: C.guide },
      { value: 30, color: C.guide },
    ],
    compute(bars, p) {
      // UO = 100*(4*avg7 + 2*avg14 + avg28) / 7. avg_n = sum(bp)/sum(tr).
      const fast = Math.round(p.fast ?? 7)
      const mid  = Math.round(p.mid  ?? 14)
      const slow = Math.round(p.slow ?? 28)
      const bp: number[] = [0], tr2: number[] = [bars[0].high - bars[0].low]
      for (let i = 1; i < bars.length; i++) {
        const pc = bars[i - 1].close
        bp.push(bars[i].close - Math.min(bars[i].low, pc))
        tr2.push(Math.max(bars[i].high, pc) - Math.min(bars[i].low, pc))
      }
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = slow; i < bars.length; i++) {
        const avg = (n: number) => {
          let sb = 0, st = 0
          for (let k = i - n + 1; k <= i; k++) { sb += bp[k]; st += tr2[k] }
          return st === 0 ? 0 : sb / st
        }
        out[i] = 100 * (4 * avg(fast) + 2 * avg(mid) + avg(slow)) / 7
      }
      return [{ key: 'uo', kind: 'line', data: toPoints(bars, out), color: C.oscTeal, lineWidth: 2 }]
    },
  },
  {
    id: 'dmi_adx',
    name: 'DMI / ADX',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [
      { name: 'length',     default: 14 },
      { name: 'adxSmooth', default: 14 },
    ],
    levels: [
      { value: 25, color: C.guide },
    ],
    compute(bars, p) {
      // +DM/-DM/TR via RMA, then +DI/-DI, then DX, then ADX = RMA(DX).
      const length    = Math.round(p.length     ?? 14)
      const adxSmooth = Math.round(p.adxSmooth  ?? 14)
      const plusDM:  number[] = [0]
      const minusDM: number[] = [0]
      const tr: number[] = [bars[0].high - bars[0].low]
      for (let i = 1; i < bars.length; i++) {
        const up   = bars[i].high - bars[i - 1].high
        const down = bars[i - 1].low - bars[i].low
        plusDM.push(up > down && up > 0 ? up : 0)
        minusDM.push(down > up && down > 0 ? down : 0)
        const pc = bars[i - 1].close
        tr.push(Math.max(bars[i].high - bars[i].low, Math.abs(bars[i].high - pc), Math.abs(bars[i].low - pc)))
      }
      const rmaPlus  = rmaArr(plusDM,  length)
      const rmaMinus = rmaArr(minusDM, length)
      const rmaTR    = rmaArr(tr,      length)
      const plusDI:  number[] = new Array(bars.length).fill(NaN)
      const minusDI: number[] = new Array(bars.length).fill(NaN)
      const dx:      number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        if (rmaTR[i] === 0) continue
        plusDI[i]  = 100 * rmaPlus[i]  / rmaTR[i]
        minusDI[i] = 100 * rmaMinus[i] / rmaTR[i]
        const sum = plusDI[i] + minusDI[i]
        dx[i] = sum === 0 ? 0 : 100 * Math.abs(plusDI[i] - minusDI[i]) / sum
      }
      const adx = rmaArr(dx, adxSmooth)
      return [
        { key: 'plusDI',  kind: 'line', data: toPoints(bars, plusDI),  color: C.up,      lineWidth: 1 },
        { key: 'minusDI', kind: 'line', data: toPoints(bars, minusDI), color: C.down,    lineWidth: 1 },
        { key: 'adx',     kind: 'line', data: toPoints(bars, adx),     color: C.oscBlue, lineWidth: 2 },
      ]
    },
  },
  {
    id: 'chande_momentum',
    name: 'Chande Momentum Oscillator',
    category: 'Oscillators',
    pane: 'separate',
    inputs: [{ name: 'length', default: 9 }],
    levels: [
      { value:  50, color: C.guide },
      { value:   0, color: C.guide },
      { value: -50, color: C.guide },
    ],
    compute(bars, p) {
      // CMO = 100*(sumUp - sumDown)/(sumUp + sumDown). Rolling sum, length bars.
      const length = Math.round(p.length ?? 9)
      const up:   number[] = [0]
      const down: number[] = [0]
      for (let i = 1; i < bars.length; i++) {
        const d = bars[i].close - bars[i - 1].close
        up.push(d > 0 ? d : 0)
        down.push(d < 0 ? -d : 0)
      }
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let su = 0, sd = 0
        for (let k = i - length + 1; k <= i; k++) { su += up[k]; sd += down[k] }
        out[i] = (su + sd) === 0 ? 0 : 100 * (su - sd) / (su + sd)
      }
      return [{ key: 'cmo', kind: 'line', data: toPoints(bars, out), color: '#FF7043', lineWidth: 2 }]
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Volatility
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'bollinger_bands',
    name: 'Bollinger Bands',
    category: 'Volatility',
    pane: 'overlay',
    inputs: [
      { name: 'length', default: 20 },
      { name: 'mult',   default: 2  },
    ],
    compute(bars, p) {
      // BB: basis = SMA; stddev is POPULATION (÷ period).
      const length = Math.round(p.length ?? 20)
      const mult   = p.mult ?? 2
      const { basis, upper, lower } = bbArrs(bars, length, mult)
      return [
        { key: 'basis', kind: 'line', data: toPoints(bars, basis), color: '#FF6D00', lineWidth: 1 },
        { key: 'upper', kind: 'line', data: toPoints(bars, upper), color: '#2962FF', lineWidth: 1 },
        { key: 'lower', kind: 'line', data: toPoints(bars, lower), color: '#2962FF', lineWidth: 1 },
      ]
    },
  },
  {
    id: 'keltner_channels',
    name: 'Keltner Channels',
    category: 'Volatility',
    pane: 'overlay',
    inputs: [
      { name: 'length',    default: 20 },
      { name: 'mult',      default: 2  },
      { name: 'atrLength', default: 10 },
    ],
    compute(bars, p) {
      // Keltner: basis = EMA(close, length); upper/lower = basis ± mult*ATR.
      const length    = Math.round(p.length    ?? 20)
      const mult      = p.mult      ?? 2
      const atrLength = Math.round(p.atrLength ?? 10)
      const close = bars.map(b => b.close)
      const basis = emaArr(close, length)
      const atr   = atrArr(bars, atrLength)
      const upper = basis.map((v, i) => isNaN(v) || isNaN(atr[i]) ? NaN : v + mult * atr[i])
      const lower = basis.map((v, i) => isNaN(v) || isNaN(atr[i]) ? NaN : v - mult * atr[i])
      return [
        { key: 'basis', kind: 'line', data: toPoints(bars, basis), color: '#FF6D00', lineWidth: 1 },
        { key: 'upper', kind: 'line', data: toPoints(bars, upper), color: C.up,      lineWidth: 1 },
        { key: 'lower', kind: 'line', data: toPoints(bars, lower), color: C.up,      lineWidth: 1 },
      ]
    },
  },
  {
    id: 'donchian_channels',
    name: 'Donchian Channels',
    category: 'Volatility',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 20 }],
    compute(bars, p) {
      // Donchian: upper = max(high, length); lower = min(low, length); basis = midpoint.
      const length = Math.round(p.length ?? 20)
      const upper: number[] = new Array(bars.length).fill(NaN)
      const lower: number[] = new Array(bars.length).fill(NaN)
      const basis: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        let hh = -Infinity, ll = Infinity
        for (let k = i - length + 1; k <= i; k++) {
          if (bars[k].high > hh) hh = bars[k].high
          if (bars[k].low  < ll) ll = bars[k].low
        }
        upper[i] = hh; lower[i] = ll; basis[i] = (hh + ll) / 2
      }
      return [
        { key: 'upper', kind: 'line', data: toPoints(bars, upper), color: '#2962FF',  lineWidth: 1 },
        { key: 'lower', kind: 'line', data: toPoints(bars, lower), color: '#FF6D00',  lineWidth: 1 },
        { key: 'basis', kind: 'line', data: toPoints(bars, basis), color: C.oscGray,  lineWidth: 1, lineStyle: 1 },
      ]
    },
  },
  {
    id: 'atr',
    name: 'Average True Range',
    category: 'Volatility',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    compute(bars, p) {
      // ATR = RMA(TR, length). TR = max(H-L, |H-Pc|, |L-Pc|).
      const length = Math.round(p.length ?? 14)
      return [{ key: 'atr', kind: 'line', data: toPoints(bars, atrArr(bars, length)), color: '#B71C1C', lineWidth: 2 }]
    },
  },
  {
    id: 'standard_deviation',
    name: 'Standard Deviation',
    category: 'Volatility',
    pane: 'separate',
    inputs: [{ name: 'length', default: 20 }],
    compute(bars, p) {
      // StdDev: POPULATION (÷ length). Mean = SMA(close, length).
      const length = Math.round(p.length ?? 20)
      const close = bars.map(b => b.close)
      const mean  = smaArr(close, length)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        let v = 0
        for (let k = i - length + 1; k <= i; k++) v += (close[k] - mean[i]) ** 2
        out[i] = Math.sqrt(v / length)
      }
      return [{ key: 'sd', kind: 'line', data: toPoints(bars, out), color: '#455A64', lineWidth: 2 }]
    },
  },
  {
    id: 'bollinger_percent_b',
    name: 'Bollinger %B',
    category: 'Volatility',
    pane: 'separate',
    inputs: [
      { name: 'length', default: 20 },
      { name: 'mult',   default: 2  },
    ],
    levels: [
      { value: 1.0, color: C.guide },
      { value: 0.5, color: C.guide },
      { value: 0.0, color: C.guide },
    ],
    compute(bars, p) {
      // %B = (close - lower)/(upper - lower).
      const length = Math.round(p.length ?? 20)
      const mult   = p.mult ?? 2
      const { basis: _b, upper, lower } = bbArrs(bars, length, mult)
      const out: number[] = bars.map((b, i) => {
        if (isNaN(upper[i])) return NaN
        const bw = upper[i] - lower[i]
        return bw === 0 ? 0.5 : (b.close - lower[i]) / bw
      })
      return [{ key: 'pctB', kind: 'line', data: toPoints(bars, out), color: '#2962FF', lineWidth: 2 }]
    },
  },
  {
    id: 'bollinger_bandwidth',
    name: 'Bollinger Bandwidth',
    category: 'Volatility',
    pane: 'separate',
    inputs: [
      { name: 'length', default: 20 },
      { name: 'mult',   default: 2  },
    ],
    compute(bars, p) {
      // BW = (upper - lower) / basis.
      const length = Math.round(p.length ?? 20)
      const mult   = p.mult ?? 2
      const { basis, upper, lower } = bbArrs(bars, length, mult)
      const out: number[] = basis.map((m, i) =>
        isNaN(m) || m === 0 ? NaN : (upper[i] - lower[i]) / m,
      )
      return [{ key: 'bw', kind: 'line', data: toPoints(bars, out), color: '#7B1FA2', lineWidth: 2 }]
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Volume
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'obv',
    name: 'On Balance Volume',
    category: 'Volume',
    pane: 'separate',
    inputs: [],
    compute(bars) {
      // OBV: cumulative. +vol if close > prevClose, -vol if close < prevClose.
      const out: IndPoint[] = []
      let obv = 0
      for (let i = 0; i < bars.length; i++) {
        if (i > 0) {
          if (bars[i].close > bars[i - 1].close)      obv += bars[i].volume
          else if (bars[i].close < bars[i - 1].close) obv -= bars[i].volume
        }
        out.push({ time: bars[i].time, value: obv })
      }
      return [{ key: 'obv', kind: 'line', data: out, color: '#2962FF', lineWidth: 2 }]
    },
  },
  {
    id: 'volume',
    name: 'Volume',
    category: 'Volume',
    pane: 'separate',
    inputs: [{ name: 'maLength', default: 20 }],
    compute(bars, p) {
      // Volume bars colored by candle direction; MA overlay.
      const maLength = Math.round(p.maLength ?? 20)
      const volPts: IndPoint[] = bars.map(b => ({
        time:  b.time,
        value: b.volume,
        color: b.close >= b.open ? C.up : C.down,
      }))
      const volNums = bars.map(b => b.volume)
      const maPts = toPoints(bars, smaArr(volNums, maLength))
      return [
        { key: 'vol', kind: 'hist', data: volPts,  color: C.up      },
        { key: 'ma',  kind: 'line', data: maPts,   color: '#FF6D00', lineWidth: 1 },
      ]
    },
  },
  {
    id: 'vwap',
    name: 'VWAP',
    category: 'Volume',
    pane: 'overlay',
    inputs: [{ name: 'source', default: 0 }],
    compute(bars) {
      // VWAP: cumulative PV/V, resets on date change.
      return [{ key: 'vwap', kind: 'line', data: calcVWAP(bars), color: '#2962FF', lineWidth: 2 }]
    },
  },
  {
    id: 'accumulation_distribution',
    name: 'Accumulation / Distribution',
    category: 'Volume',
    pane: 'separate',
    inputs: [],
    compute(bars) {
      // ADL: cumulative Money Flow Volume. MFM = ((close-low)-(high-close))/(high-low).
      const out: IndPoint[] = []
      let adl = 0
      for (let i = 0; i < bars.length; i++) {
        const { high, low, close, volume } = bars[i]
        const rng = high - low
        const mfm = rng === 0 ? 0 : ((close - low) - (high - close)) / rng
        adl += mfm * volume
        out.push({ time: bars[i].time, value: adl })
      }
      return [{ key: 'adl', kind: 'line', data: out, color: '#00897B', lineWidth: 2 }]
    },
  },
  {
    id: 'chaikin_money_flow',
    name: 'Chaikin Money Flow',
    category: 'Volume',
    pane: 'separate',
    inputs: [{ name: 'length', default: 20 }],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // CMF = sum(MFV, length) / sum(volume, length). Range -1..1.
      const length = Math.round(p.length ?? 20)
      const mfv = bars.map(b => {
        const rng = b.high - b.low
        const mfm = rng === 0 ? 0 : ((b.close - b.low) - (b.high - b.close)) / rng
        return mfm * b.volume
      })
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length - 1; i < bars.length; i++) {
        let sumV = 0, sumMFV = 0
        for (let k = i - length + 1; k <= i; k++) { sumV += bars[k].volume; sumMFV += mfv[k] }
        out[i] = sumV === 0 ? 0 : sumMFV / sumV
      }
      return [{ key: 'cmf', kind: 'line', data: toPoints(bars, out), color: '#00897B', lineWidth: 2 }]
    },
  },
  {
    id: 'chaikin_oscillator',
    name: 'Chaikin Oscillator',
    category: 'Volume',
    pane: 'separate',
    inputs: [
      { name: 'fast', default: 3  },
      { name: 'slow', default: 10 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // Chaikin Osc = EMA(ADL, fast) - EMA(ADL, slow).
      const fast = Math.round(p.fast ?? 3)
      const slow = Math.round(p.slow ?? 10)
      let adl = 0
      const adlArr: number[] = []
      for (const b of bars) {
        const rng = b.high - b.low
        const mfm = rng === 0 ? 0 : ((b.close - b.low) - (b.high - b.close)) / rng
        adl += mfm * b.volume
        adlArr.push(adl)
      }
      const emaFast = emaArr(adlArr, fast)
      const emaSlow = emaArr(adlArr, slow)
      const out = emaFast.map((v, i) => isNaN(v) || isNaN(emaSlow[i]) ? NaN : v - emaSlow[i])
      return [{ key: 'chaikin', kind: 'line', data: toPoints(bars, out), color: '#5E35B1', lineWidth: 2 }]
    },
  },
  {
    id: 'ease_of_movement',
    name: 'Ease of Movement',
    category: 'Volume',
    pane: 'separate',
    inputs: [
      { name: 'length',  default: 14    },
      { name: 'divisor', default: 10000 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // EOM = SMA(distance/boxRatio, length). BoxRatio = (vol/divisor)/(H-L).
      const length  = Math.round(p.length  ?? 14)
      const divisor = p.divisor ?? 10000
      const emv: number[] = [0]
      for (let i = 1; i < bars.length; i++) {
        const dist = ((bars[i].high + bars[i].low) / 2) - ((bars[i - 1].high + bars[i - 1].low) / 2)
        const hl   = bars[i].high - bars[i].low
        const br   = hl === 0 ? 0 : (bars[i].volume / divisor) / hl
        emv.push(br === 0 ? 0 : dist / br)
      }
      return [{ key: 'eom', kind: 'line', data: toPoints(bars, smaArr(emv, length)), color: '#00ACC1', lineWidth: 2 }]
    },
  },
  {
    id: 'volume_oscillator',
    name: 'Volume Oscillator',
    category: 'Volume',
    pane: 'separate',
    inputs: [
      { name: 'fast', default: 5  },
      { name: 'slow', default: 10 },
    ],
    levels: [{ value: 0, color: C.guide }],
    compute(bars, p) {
      // VO = 100*(EMA(vol, fast) - EMA(vol, slow)) / EMA(vol, slow).
      const fast = Math.round(p.fast ?? 5)
      const slow = Math.round(p.slow ?? 10)
      const vol = bars.map(b => b.volume)
      const eFast = emaArr(vol, fast)
      const eSlow = emaArr(vol, slow)
      const out = eSlow.map((s, i) => {
        if (isNaN(s) || isNaN(eFast[i]) || s === 0) return NaN
        return 100 * (eFast[i] - s) / s
      })
      return [{ key: 'vo', kind: 'line', data: toPoints(bars, out), color: '#FB8C00', lineWidth: 2 }]
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Trend
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'ichimoku',
    name: 'Ichimoku Cloud',
    category: 'Trend',
    pane: 'overlay',
    inputs: [
      { name: 'conversion',   default: 9  },
      { name: 'base',         default: 26 },
      { name: 'spanB',        default: 52 },
      { name: 'displacement', default: 26 },
    ],
    compute(bars, p) {
      // Ichimoku: tenkan=(max+min)/2 over 9; kijun=26; senkouA shifted +26; senkouB=52 shifted +26; chikou=close shifted -26.
      const conv = Math.round(p.conversion   ?? 9)
      const base = Math.round(p.base         ?? 26)
      const spanB = Math.round(p.spanB       ?? 52)
      const disp  = Math.round(p.displacement ?? 26)

      const donchMid = (n: number): number[] => {
        const out: number[] = new Array(bars.length).fill(NaN)
        for (let i = n - 1; i < bars.length; i++) {
          let hh = -Infinity, ll = Infinity
          for (let k = i - n + 1; k <= i; k++) {
            if (bars[k].high > hh) hh = bars[k].high
            if (bars[k].low  < ll) ll = bars[k].low
          }
          out[i] = (hh + ll) / 2
        }
        return out
      }

      const tenkan = donchMid(conv)
      const kijun  = donchMid(base)
      const spanBraw = donchMid(spanB)

      // Shift forward by displacement (append NaN at end for shifted points)
      const shiftFwd = (arr: number[]): IndPoint[] => {
        const out: IndPoint[] = []
        for (let i = 0; i < arr.length; i++) {
          if (isNaN(arr[i])) continue
          const idx = i + disp
          if (idx < bars.length) out.push({ time: bars[idx].time, value: arr[i] })
        }
        return out
      }

      // SenkouA = (tenkan + kijun)/2 shifted forward
      const spanAraw = tenkan.map((t, i) =>
        isNaN(t) || isNaN(kijun[i]) ? NaN : (t + kijun[i]) / 2,
      )

      // Chikou = close shifted -displacement (into the past visually)
      const chikouPts: IndPoint[] = []
      for (let i = disp; i < bars.length; i++) {
        chikouPts.push({ time: bars[i - disp].time, value: bars[i].close })
      }

      return [
        { key: 'tenkan',  kind: 'line', data: toPoints(bars, tenkan),   color: '#2962FF', lineWidth: 1 },
        { key: 'kijun',   kind: 'line', data: toPoints(bars, kijun),    color: '#B71C1C', lineWidth: 1 },
        { key: 'senkouA', kind: 'line', data: shiftFwd(spanAraw),       color: C.up,      lineWidth: 1 },
        { key: 'senkouB', kind: 'line', data: shiftFwd(spanBraw),       color: C.down,    lineWidth: 1 },
        { key: 'chikou',  kind: 'line', data: chikouPts,                color: '#43A047', lineWidth: 1 },
      ]
    },
  },
  {
    id: 'parabolic_sar',
    name: 'Parabolic SAR',
    category: 'Trend',
    pane: 'overlay',
    inputs: [
      { name: 'start',     default: 0.02 },
      { name: 'increment', default: 0.02 },
      { name: 'max',       default: 0.2  },
    ],
    compute(bars, p) {
      // Parabolic SAR: flip when price crosses SAR; AF increments on new EP; caps at max.
      if (bars.length < 3) return []
      const start = p.start     ?? 0.02
      const inc   = p.increment ?? 0.02
      const maxAF = p.max       ?? 0.2

      let bull = bars[1].close > bars[0].close
      let sar  = bull ? bars[0].low  : bars[0].high
      let ep   = bull ? bars[0].high : bars[0].low
      let af   = start
      const pts: IndPoint[] = [{ time: bars[0].time, value: sar, color: bull ? C.up : C.down }]

      for (let i = 1; i < bars.length; i++) {
        let sarNew = sar + af * (ep - sar)

        if (bull) {
          sarNew = Math.min(sarNew, bars[Math.max(0, i - 1)].low, bars[Math.max(0, i - 2)].low)
          if (bars[i].low < sarNew) {
            // Flip to bearish
            bull = false; sarNew = ep; ep = bars[i].low; af = start
          } else {
            if (bars[i].high > ep) { ep = bars[i].high; af = Math.min(af + inc, maxAF) }
          }
        } else {
          sarNew = Math.max(sarNew, bars[Math.max(0, i - 1)].high, bars[Math.max(0, i - 2)].high)
          if (bars[i].high > sarNew) {
            // Flip to bullish
            bull = true; sarNew = ep; ep = bars[i].high; af = start
          } else {
            if (bars[i].low < ep) { ep = bars[i].low; af = Math.min(af + inc, maxAF) }
          }
        }
        sar = sarNew
        pts.push({ time: bars[i].time, value: sar, color: bull ? C.up : C.down })
      }
      return [{ key: 'psar', kind: 'line', data: pts, color: C.up, lineStyle: 1 }]
    },
  },
  {
    id: 'supertrend',
    name: 'SuperTrend',
    category: 'Trend',
    pane: 'overlay',
    inputs: [
      { name: 'atrLength', default: 10 },
      { name: 'mult',      default: 3  },
    ],
    compute(bars, p) {
      // SuperTrend: finalUpper/Lower bands based on ATR; color by trend direction.
      const atrLength = Math.round(p.atrLength ?? 10)
      const mult      = p.mult ?? 3
      const atr = atrArr(bars, atrLength)
      const pts: IndPoint[] = []

      let finalU = Infinity
      let finalL = -Infinity
      let trend  = 1 // 1=up, -1=down

      for (let i = atrLength - 1; i < bars.length; i++) {
        const hl2 = (bars[i].high + bars[i].low) / 2
        const bU  = hl2 + mult * atr[i]
        const bL  = hl2 - mult * atr[i]

        const prevFinalU = finalU
        const prevFinalL = finalL
        const prevClose  = i > 0 ? bars[i - 1].close : bars[i].close

        finalU = (bU < prevFinalU || prevClose > prevFinalU) ? bU : prevFinalU
        finalL = (bL > prevFinalL || prevClose < prevFinalL) ? bL : prevFinalL

        if (trend === 1  && bars[i].close < finalL) trend = -1
        else if (trend === -1 && bars[i].close > finalU) trend = 1

        const stVal = trend === 1 ? finalL : finalU
        pts.push({ time: bars[i].time, value: stVal, color: trend === 1 ? C.up : C.down })
      }
      return [{ key: 'st', kind: 'line', data: pts, color: C.up, lineWidth: 2 }]
    },
  },
  {
    id: 'zigzag',
    name: 'ZigZag',
    category: 'Trend',
    pane: 'overlay',
    inputs: [
      { name: 'deviation', default: 5  },
      { name: 'depth',     default: 10 },
    ],
    compute(bars, p) {
      // ZigZag: confirms pivot when price retraces deviation% from extreme, min depth bars apart.
      const dev   = p.deviation ?? 5
      const depth = Math.round(p.depth ?? 10)
      if (bars.length < depth * 2) return [{ key: 'zz', kind: 'line', data: [], color: '#2962FF' }]

      const pivots: { idx: number; price: number; type: 'H' | 'L' }[] = []
      let dir: 'up' | 'down' = bars[depth].close > bars[0].close ? 'up' : 'down'
      let extreme = dir === 'up' ? bars[0].high : bars[0].low
      let extremeIdx = 0

      for (let i = depth; i < bars.length; i++) {
        if (dir === 'up') {
          if (bars[i].high > extreme) { extreme = bars[i].high; extremeIdx = i }
          else if ((extreme - bars[i].low) / extreme * 100 >= dev) {
            if (i - extremeIdx >= depth) {
              pivots.push({ idx: extremeIdx, price: extreme, type: 'H' })
              dir = 'down'; extreme = bars[i].low; extremeIdx = i
            }
          }
        } else {
          if (bars[i].low < extreme) { extreme = bars[i].low; extremeIdx = i }
          else if ((bars[i].high - extreme) / extreme * 100 >= dev) {
            if (i - extremeIdx >= depth) {
              pivots.push({ idx: extremeIdx, price: extreme, type: 'L' })
              dir = 'up'; extreme = bars[i].high; extremeIdx = i
            }
          }
        }
      }
      // Add last extreme
      pivots.push({ idx: extremeIdx, price: extreme, type: dir === 'up' ? 'H' : 'L' })

      const pts: IndPoint[] = pivots.map(pv => ({ time: bars[pv.idx].time, value: pv.price }))
      return [{ key: 'zz', kind: 'line', data: pts, color: '#2962FF', lineWidth: 2 }]
    },
  },
  {
    id: 'aroon',
    name: 'Aroon',
    category: 'Trend',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    levels: [
      { value: 70, color: C.guide },
      { value: 30, color: C.guide },
    ],
    compute(bars, p) {
      // Aroon Up = 100*(length - barsSinceHigh)/length; Down = 100*(length - barsSinceLow)/length.
      const length = Math.round(p.length ?? 14)
      const up:   number[] = new Array(bars.length).fill(NaN)
      const down: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let highIdx = i, lowIdx = i
        for (let k = i - length; k <= i; k++) {
          if (bars[k].high >= bars[highIdx].high) highIdx = k
          if (bars[k].low  <= bars[lowIdx].low)   lowIdx  = k
        }
        up[i]   = 100 * (length - (i - highIdx)) / length
        down[i] = 100 * (length - (i - lowIdx))  / length
      }
      return [
        { key: 'up',   kind: 'line', data: toPoints(bars, up),   color: C.up,   lineWidth: 1 },
        { key: 'down', kind: 'line', data: toPoints(bars, down), color: C.down, lineWidth: 1 },
      ]
    },
  },
  {
    id: 'vortex',
    name: 'Vortex Indicator',
    category: 'Trend',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    compute(bars, p) {
      // VI+ = sum(|H[i]-L[i-1]|, n) / sum(TR, n); VI- = sum(|L[i]-H[i-1]|, n) / sum(TR).
      const length = Math.round(p.length ?? 14)
      const vmP: number[] = [0]
      const vmM: number[] = [0]
      const tr: number[] = [bars[0].high - bars[0].low]
      for (let i = 1; i < bars.length; i++) {
        vmP.push(Math.abs(bars[i].high - bars[i - 1].low))
        vmM.push(Math.abs(bars[i].low  - bars[i - 1].high))
        const pc = bars[i - 1].close
        tr.push(Math.max(bars[i].high - bars[i].low, Math.abs(bars[i].high - pc), Math.abs(bars[i].low - pc)))
      }
      const vip: number[] = new Array(bars.length).fill(NaN)
      const vim: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let st = 0, sp = 0, sm = 0
        for (let k = i - length + 1; k <= i; k++) { st += tr[k]; sp += vmP[k]; sm += vmM[k] }
        if (st > 0) { vip[i] = sp / st; vim[i] = sm / st }
      }
      return [
        { key: 'vip', kind: 'line', data: toPoints(bars, vip), color: C.up,   lineWidth: 1 },
        { key: 'vim', kind: 'line', data: toPoints(bars, vim), color: C.down, lineWidth: 1 },
      ]
    },
  },
  {
    id: 'linear_regression',
    name: 'Linear Regression Curve',
    category: 'Trend',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 100 }],
    compute(bars, p) {
      // LinReg = LSMA with offset=0. Reuses lsma compute logic.
      const length = Math.round(p.length ?? 100)
      const close = bars.map(b => b.close)
      const out: number[] = new Array(bars.length).fill(NaN)
      const sumX  = (length * (length - 1)) / 2
      const sumX2 = (length * (length - 1) * (2 * length - 1)) / 6
      const denom = length * sumX2 - sumX * sumX
      for (let i = length - 1; i < bars.length; i++) {
        let sumY = 0, sumXY = 0
        for (let j = 0; j < length; j++) {
          sumY  += close[i - length + 1 + j]
          sumXY += j * close[i - length + 1 + j]
        }
        if (Math.abs(denom) < 1e-10) { out[i] = sumY / length; continue }
        const slope = (length * sumXY - sumX * sumY) / denom
        const intercept = (sumY - slope * sumX) / length
        out[i] = intercept + slope * (length - 1)
      }
      return oneOverlay('linreg', '#FF6D00', toPoints(bars, out), 1)
    },
  },
  {
    id: 'envelopes',
    name: 'Moving Average Envelopes',
    category: 'Trend',
    pane: 'overlay',
    inputs: [
      { name: 'length',  default: 20 },
      { name: 'percent', default: 1  },
      { name: 'maType',  default: 0  },
    ],
    compute(bars, p) {
      // Envelopes: basis ± percent%. maType 0=SMA, 1=EMA.
      const length  = Math.round(p.length  ?? 20)
      const pct     = p.percent ?? 1
      const maType  = Math.round(p.maType  ?? 0)
      const close   = bars.map(b => b.close)
      const basis   = maType === 1 ? emaArr(close, length) : smaArr(close, length)
      const upper   = basis.map(v => isNaN(v) ? NaN : v * (1 + pct / 100))
      const lower   = basis.map(v => isNaN(v) ? NaN : v * (1 - pct / 100))
      return [
        { key: 'basis', kind: 'line', data: toPoints(bars, basis), color: '#FF6D00', lineWidth: 1 },
        { key: 'upper', kind: 'line', data: toPoints(bars, upper), color: '#2962FF', lineWidth: 1 },
        { key: 'lower', kind: 'line', data: toPoints(bars, lower), color: '#2962FF', lineWidth: 1 },
      ]
    },
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATEGORY: Bands & Other
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'pivot_points_standard',
    name: 'Pivot Points Standard',
    category: 'Bands & Other',
    pane: 'overlay',
    inputs: [{ name: 'type', default: 0 }],
    compute(bars) {
      // Traditional pivots from previous session: P, R1/R2/R3, S1/S2/S3 as horizontal lines.
      const { h, l, c } = lastSessionHLC(bars)
      const P  = (h + l + c) / 3
      const R1 = 2 * P - l
      const S1 = 2 * P - h
      const R2 = P + (h - l)
      const S2 = P - (h - l)
      const R3 = h + 2 * (P - l)
      const S3 = l - 2 * (h - P)
      const first = bars[0].time
      const last  = bars[bars.length - 1].time
      const hLine = (v: number): IndPoint[] => [{ time: first, value: v }, { time: last, value: v }]
      return [
        { key: 'P',  kind: 'line', data: hLine(P),  color: '#2962FF', lineWidth: 1 },
        { key: 'R1', kind: 'line', data: hLine(R1), color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'R2', kind: 'line', data: hLine(R2), color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'R3', kind: 'line', data: hLine(R3), color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'S1', kind: 'line', data: hLine(S1), color: C.up,      lineWidth: 1, lineStyle: 2 },
        { key: 'S2', kind: 'line', data: hLine(S2), color: C.up,      lineWidth: 1, lineStyle: 2 },
        { key: 'S3', kind: 'line', data: hLine(S3), color: C.up,      lineWidth: 1, lineStyle: 2 },
      ]
    },
  },
  {
    id: 'price_channel',
    name: 'Price Channel',
    category: 'Bands & Other',
    pane: 'overlay',
    inputs: [{ name: 'length', default: 20 }],
    compute(bars, p) {
      // Price Channel: upper = max(high[i-n..i-1]); lower = min(low[...]). Excludes current bar.
      const length = Math.round(p.length ?? 20)
      const upper: number[] = new Array(bars.length).fill(NaN)
      const lower: number[] = new Array(bars.length).fill(NaN)
      const center: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let hh = -Infinity, ll = Infinity
        for (let k = i - length; k < i; k++) {
          if (bars[k].high > hh) hh = bars[k].high
          if (bars[k].low  < ll) ll = bars[k].low
        }
        upper[i]  = hh; lower[i] = ll; center[i] = (hh + ll) / 2
      }
      return [
        { key: 'upper',  kind: 'line', data: toPoints(bars, upper),  color: '#2962FF', lineWidth: 1 },
        { key: 'lower',  kind: 'line', data: toPoints(bars, lower),  color: '#FF6D00', lineWidth: 1 },
        { key: 'center', kind: 'line', data: toPoints(bars, center), color: C.oscGray, lineWidth: 1, lineStyle: 1 },
      ]
    },
  },
  {
    id: 'fib_pivot_points',
    name: 'Fibonacci Pivot Points',
    category: 'Bands & Other',
    pane: 'overlay',
    inputs: [{ name: 'type', default: 1 }],
    compute(bars) {
      // Fibonacci pivots: P + Fib levels (0.382, 0.618, 1.0) × range.
      const { h, l, c } = lastSessionHLC(bars)
      const P   = (h + l + c) / 3
      const rng = h - l
      const first = bars[0].time
      const last  = bars[bars.length - 1].time
      const hLine = (v: number): IndPoint[] => [{ time: first, value: v }, { time: last, value: v }]
      return [
        { key: 'P',  kind: 'line', data: hLine(P),                color: '#2962FF', lineWidth: 1 },
        { key: 'R1', kind: 'line', data: hLine(P + 0.382 * rng),  color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'R2', kind: 'line', data: hLine(P + 0.618 * rng),  color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'R3', kind: 'line', data: hLine(P + 1.000 * rng),  color: C.down,    lineWidth: 1, lineStyle: 2 },
        { key: 'S1', kind: 'line', data: hLine(P - 0.382 * rng),  color: C.up,      lineWidth: 1, lineStyle: 2 },
        { key: 'S2', kind: 'line', data: hLine(P - 0.618 * rng),  color: C.up,      lineWidth: 1, lineStyle: 2 },
        { key: 'S3', kind: 'line', data: hLine(P - 1.000 * rng),  color: C.up,      lineWidth: 1, lineStyle: 2 },
      ]
    },
  },
  {
    id: 'atr_bands',
    name: 'ATR Trailing Bands',
    category: 'Bands & Other',
    pane: 'overlay',
    inputs: [
      { name: 'atrLength', default: 14 },
      { name: 'mult',      default: 3  },
    ],
    compute(bars, p) {
      // ATR bands: upper = close + mult*ATR; lower = close - mult*ATR.
      const atrLength = Math.round(p.atrLength ?? 14)
      const mult      = p.mult ?? 3
      const atr = atrArr(bars, atrLength)
      const upper = bars.map((b, i) => isNaN(atr[i]) ? NaN : b.close + mult * atr[i])
      const lower = bars.map((b, i) => isNaN(atr[i]) ? NaN : b.close - mult * atr[i])
      return [
        { key: 'upper', kind: 'line', data: toPoints(bars, upper), color: C.down, lineWidth: 1 },
        { key: 'lower', kind: 'line', data: toPoints(bars, lower), color: C.up,   lineWidth: 1 },
      ]
    },
  },
  {
    id: 'choppiness_index',
    name: 'Choppiness Index',
    category: 'Bands & Other',
    pane: 'separate',
    inputs: [{ name: 'length', default: 14 }],
    levels: [
      { value: 61.8, color: C.guide },
      { value: 38.2, color: C.guide },
    ],
    compute(bars, p) {
      // CHOP = 100*log10(sumTR/rangeHL)/log10(length). >61.8=choppy, <38.2=trending.
      const length = Math.round(p.length ?? 14)
      const tr = trArr(bars)
      const out: number[] = new Array(bars.length).fill(NaN)
      for (let i = length; i < bars.length; i++) {
        let sumTR = 0
        let hh = -Infinity, ll = Infinity
        for (let k = i - length + 1; k <= i; k++) {
          sumTR += tr[k]
          if (bars[k].high > hh) hh = bars[k].high
          if (bars[k].low  < ll) ll = bars[k].low
        }
        const rangeHL = hh - ll
        out[i] = rangeHL <= 0 ? 0 : 100 * Math.log10(sumTR / rangeHL) / Math.log10(length)
      }
      return [{ key: 'chop', kind: 'line', data: toPoints(bars, out), color: '#6A1B9A', lineWidth: 2 }]
    },
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

export const INDICATOR_CATALOG: IndicatorDef[] = INDICATOR_CATALOG_INTERNAL

export const INDICATORS_BY_ID: Record<string, IndicatorDef> = Object.fromEntries(
  INDICATOR_CATALOG.map(d => [d.id, d]),
)
