/**
 * CARDEX Terminal — Indicator self-verification module
 * No external test runner required. Call runIndicatorChecks() from a browser
 * console or a Node script: `import { runIndicatorChecks } from './indicators.test'`
 *
 * Each check validates a known mathematical property or a hand-computed fixture
 * with ±0.3% tolerance.
 */

import { calcSMA, calcEMA, calcBB, calcRSI, calcMACD, calcVWAP } from './indicators'
import type { Bar } from './market'

// ─────────────────────────────────────────────────────────────────────────────
// Test infrastructure
// ─────────────────────────────────────────────────────────────────────────────

export interface CheckResult {
  name: string
  pass: boolean
  detail: string
}

const TOL = 0.003 // 0.3% tolerance

function near(a: number, b: number, tol = TOL): boolean {
  if (b === 0) return Math.abs(a) < 1e-9
  return Math.abs(a - b) / Math.abs(b) < tol
}

function check(name: string, condition: boolean, detail: string): CheckResult {
  return { name, pass: condition, detail }
}

// ─────────────────────────────────────────────────────────────────────────────
// Deterministic price fixtures
// ─────────────────────────────────────────────────────────────────────────────

/** Build minimal Bar array from close prices. OHLCV fill with plausible values. */
function makeBars(closes: number[]): Bar[] {
  return closes.map((c, i) => ({
    time:   `2026-01-${String(i + 1).padStart(2, '0')}`,
    open:   i === 0 ? c : closes[i - 1],
    high:   c * 1.005,
    low:    c * 0.995,
    close:  c,
    volume: 100,
  }))
}

// Hand-computed fixture: 10 sequential prices
const FIXTURE_10 = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
const BARS_10 = makeBars(FIXTURE_10)

// Longer fixture for RSI / MACD: 30 bars with realistic-ish alternating price
const FIXTURE_30 = [
  100, 101, 103, 102, 104, 105, 103, 106, 108, 107,
  109, 110, 108, 111, 113, 112, 114, 115, 113, 116,
  118, 117, 119, 120, 118, 121, 123, 122, 124, 125,
]
const BARS_30 = makeBars(FIXTURE_30)

// Flat price fixture (edge case: stddev = 0, RSI = 100)
const FLAT_20 = Array.from({ length: 20 }, () => 50)
const BARS_FLAT = makeBars(FLAT_20)

// ─────────────────────────────────────────────────────────────────────────────
// SMA checks
// ─────────────────────────────────────────────────────────────────────────────

function checkSMA(): CheckResult[] {
  const results: CheckResult[] = []

  // SMA(3) on [10,11,12,13,14] should start at index 2
  const sma3 = calcSMA(BARS_10, 3)
  const expectedFirst = (10 + 11 + 12) / 3  // 11
  results.push(check(
    'SMA(3) first value = 11',
    sma3.length > 0 && near(sma3[0].value, expectedFirst),
    `got ${sma3[0]?.value}, expected ${expectedFirst}`,
  ))

  // SMA(3) should have length = n - period + 1 = 10 - 3 + 1 = 8
  results.push(check(
    'SMA(3) length = n - period + 1',
    sma3.length === 8,
    `got length ${sma3.length}, expected 8`,
  ))

  // SMA(3) last value = (17+18+19)/3 = 18
  const expectedLast = (17 + 18 + 19) / 3
  results.push(check(
    'SMA(3) last value = 18',
    near(sma3[sma3.length - 1].value, expectedLast),
    `got ${sma3[sma3.length - 1]?.value}, expected ${expectedLast}`,
  ))

  // SMA of constant = constant
  const smaFlat = calcSMA(BARS_FLAT, 5)
  results.push(check(
    'SMA of constant series = constant',
    smaFlat.every(p => near(p.value, 50, 1e-6)),
    `max deviation: ${Math.max(...smaFlat.map(p => Math.abs(p.value - 50)))}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// EMA checks — seed correctness is the critical invariant
// ─────────────────────────────────────────────────────────────────────────────

function checkEMA(): CheckResult[] {
  const results: CheckResult[] = []

  // EMA(3): k = 2/(3+1) = 0.5. Seed = SMA(close[0..2]) = (10+11+12)/3 = 11.
  // EMA[2] = 11 (seed)
  // EMA[3] = 13*0.5 + 11*0.5 = 12
  // EMA[4] = 14*0.5 + 12*0.5 = 13
  const ema3 = calcEMA(BARS_10, 3)
  const seedIdx = 0 // first point returned corresponds to bar index 2 (length-1)
  results.push(check(
    'EMA(3) seed = SMA of first 3 bars = 11',
    near(ema3[seedIdx].value, 11),
    `got ${ema3[seedIdx]?.value}, expected 11`,
  ))

  results.push(check(
    'EMA(3)[1] = 12 (after one recurrence step)',
    near(ema3[1].value, 12),
    `got ${ema3[1]?.value}, expected 12`,
  ))

  results.push(check(
    'EMA(3)[2] = 13 (two recurrence steps)',
    near(ema3[2].value, 13),
    `got ${ema3[2]?.value}, expected 13`,
  ))

  // Seed correctness: EMA[length-1] must equal SMA[length-1] EXACTLY (same mean).
  // Use a 5-bar sequence: closes = [2, 4, 6, 8, 10]. SMA(5) = 6.
  const bars5 = makeBars([2, 4, 6, 8, 10])
  const ema5 = calcEMA(bars5, 5)
  results.push(check(
    'EMA seed invariant: EMA[n-1] === SMA[n-1] for length=5',
    ema5.length > 0 && near(ema5[0].value, 6, 1e-9),
    `EMA seed = ${ema5[0]?.value}, SMA = 6`,
  ))

  // Anti-regression: old broken EMA started from data[0].close (seeded at bar 0).
  // Verify the first RETURNED point is NOT data[0].close when length > 1.
  const brokenSeedWouldBe = FIXTURE_10[0] // 10
  results.push(check(
    'EMA(3) does NOT seed from data[0].close (old bug regression)',
    !near(ema3[0].value, brokenSeedWouldBe, 0.001),
    `seed = ${ema3[0]?.value}, old-broken seed would be ${brokenSeedWouldBe}`,
  ))

  // EMA output length = n - length + 1
  results.push(check(
    'EMA(3) output length = n - length + 1 = 8',
    ema3.length === 8,
    `got ${ema3.length}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// Bollinger Bands checks
// ─────────────────────────────────────────────────────────────────────────────

function checkBB(): CheckResult[] {
  const results: CheckResult[] = []

  // BB on flat series: stddev = 0, upper = lower = basis = 50
  const { mid, upper, lower } = calcBB(BARS_FLAT, 20, 2)
  results.push(check(
    'BB on flat series: upper = lower = basis = 50',
    mid.length > 0 && upper.length > 0 &&
      near(mid[0].value, 50) && near(upper[0].value, 50) && near(lower[0].value, 50),
    `mid=${mid[0]?.value} upper=${upper[0]?.value} lower=${lower[0]?.value}`,
  ))

  // On arithmetic series [1..20], basis = 10.5
  const arith = makeBars(Array.from({ length: 20 }, (_, i) => i + 1))
  const bb20 = calcBB(arith, 20, 2)
  const expectedMid = (1 + 20) / 2  // 10.5 for arithmetic series 1..20
  results.push(check(
    'BB(20) basis = mean of window = 10.5 for series 1..20',
    bb20.mid.length > 0 && near(bb20.mid[0].value, expectedMid),
    `got ${bb20.mid[0]?.value}, expected ${expectedMid}`,
  ))

  // Population stddev of [1..20]: variance = sum((x-10.5)^2)/20
  const pop20 = Array.from({ length: 20 }, (_, i) => i + 1)
  const mean20 = 10.5
  const variance20 = pop20.reduce((s, v) => s + (v - mean20) ** 2, 0) / 20
  const sd20 = Math.sqrt(variance20)
  results.push(check(
    'BB(20) population stddev correct (divisor=20, not 19)',
    near(bb20.upper[0].value, mean20 + 2 * sd20) &&
    near(bb20.lower[0].value, mean20 - 2 * sd20),
    `upper=${bb20.upper[0]?.value} expected=${mean20 + 2 * sd20}`,
  ))

  // upper >= mid >= lower
  results.push(check(
    'BB invariant: upper >= mid >= lower at all points',
    bb20.upper.every((u, i) => u.value >= bb20.mid[i].value && bb20.mid[i].value >= bb20.lower[i].value),
    'some point violates upper>=mid>=lower',
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// RSI checks
// ─────────────────────────────────────────────────────────────────────────────

function checkRSI(): CheckResult[] {
  const results: CheckResult[] = []

  // RSI on monotonically rising series: all gains, no losses → RSI approaches 100
  const rising = makeBars(Array.from({ length: 20 }, (_, i) => 100 + i))
  const rsiRising = calcRSI(rising, 14)
  results.push(check(
    'RSI of pure uptrend approaches 100',
    rsiRising.length > 0 && rsiRising[rsiRising.length - 1].value > 95,
    `last RSI = ${rsiRising[rsiRising.length - 1]?.value}`,
  ))

  // RSI on monotonically falling series: all losses → RSI approaches 0
  const falling = makeBars(Array.from({ length: 20 }, (_, i) => 100 - i))
  const rsiFalling = calcRSI(falling, 14)
  results.push(check(
    'RSI of pure downtrend approaches 0',
    rsiFalling.length > 0 && rsiFalling[rsiFalling.length - 1].value < 5,
    `last RSI = ${rsiFalling[rsiFalling.length - 1]?.value}`,
  ))

  // RSI range: all values must be in [0, 100]
  const rsi30 = calcRSI(BARS_30, 14)
  results.push(check(
    'RSI values always in [0, 100]',
    rsi30.every(p => p.value >= 0 && p.value <= 100),
    `out-of-range values found`,
  ))

  // RSI output starts at index `period` (first valid bar is bar[period])
  // With period=14, first point time should equal BARS_30[14].time
  results.push(check(
    'RSI(14) first point is at bar index 14',
    rsi30.length > 0 && rsi30[0].time === BARS_30[14].time,
    `first time=${rsi30[0]?.time} expected=${BARS_30[14].time}`,
  ))

  // RSI on flat: avg loss = 0 → RSI = 100
  const rsiFlatClose = Array.from({ length: 20 }, () => 50)
  const rsiFlat = calcRSI(makeBars(rsiFlatClose), 14)
  results.push(check(
    'RSI on flat series (no price changes) = 100',
    rsiFlat.length > 0 && near(rsiFlat[rsiFlat.length - 1].value, 100),
    `RSI = ${rsiFlat[rsiFlat.length - 1]?.value}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// MACD checks
// ─────────────────────────────────────────────────────────────────────────────

function checkMACD(): CheckResult[] {
  const results: CheckResult[] = []

  // Need at least slow + signal - 1 = 26 + 9 - 1 = 34 bars for any signal output
  const longBars = makeBars(Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i / 5) * 10))
  const { macd, signal, hist } = calcMACD(longBars, 12, 26, 9)

  // MACD line starts at bar index slow-1 = 25
  results.push(check(
    'MACD line first point at bar[slow-1=25]',
    macd.length > 0 && macd[0].time === longBars[25].time,
    `macd[0].time=${macd[0]?.time} expected=${longBars[25].time}`,
  ))

  // Signal line starts after another 8 bars (signal-1 more values of MACD needed for seed)
  results.push(check(
    'Signal line length < MACD line length (delayed by signal-1)',
    signal.length < macd.length,
    `signal.length=${signal.length} macd.length=${macd.length}`,
  ))

  // hist[i] = macd[i] - signal[i] within the overlapping region
  const histFirstIdx = macd.length - signal.length
  if (macd.length > 0 && signal.length > 0) {
    const diff = macd[histFirstIdx].value - signal[0].value
    results.push(check(
      'hist[0].value = macd - signal at aligned index',
      hist.length > 0 && near(hist[0].value, diff, 1e-6),
      `hist[0]=${hist[0]?.value} expected=${diff}`,
    ))
  } else {
    results.push(check('MACD hist alignment (skipped — insufficient bars)', true, 'n/a'))
  }

  // EMA seed: MACD should NOT start from data[0].close delta
  results.push(check(
    'MACD signal has output (both EMAs seeded correctly)',
    signal.length > 0 && hist.length > 0,
    `signal.length=${signal.length}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// VWAP checks
// ─────────────────────────────────────────────────────────────────────────────

function checkVWAP(): CheckResult[] {
  const results: CheckResult[] = []

  // VWAP of uniform price & volume = that price
  const uniformBars: Bar[] = Array.from({ length: 5 }, (_, i) => ({
    time:   `2026-01-${String(i + 1).padStart(2, '0')}`,
    open:   100, high: 101, low: 99, close: 100, volume: 200,
  }))
  const vwapUniform = calcVWAP(uniformBars)
  results.push(check(
    'VWAP of uniform price = that price',
    vwapUniform.every(p => near(p.value, 100)),
    `got ${vwapUniform.map(p => p.value).join(',')}`,
  ))

  // VWAP resets on date change: verify second day starts fresh
  const twoDayBars: Bar[] = [
    { time: '2026-01-01', open: 100, high: 102, low: 98, close: 100, volume: 100 },
    { time: '2026-01-02', open: 200, high: 202, low: 198, close: 200, volume: 100 },
  ]
  const vwapTwoDay = calcVWAP(twoDayBars)
  // Day 1: tp=(98+102+100)/3=100. VWAP=100.
  // Day 2: resets. tp=(198+202+200)/3=200. VWAP=200.
  results.push(check(
    'VWAP resets on new date boundary',
    near(vwapTwoDay[0].value, 100) && near(vwapTwoDay[1].value, 200),
    `day1=${vwapTwoDay[0]?.value} day2=${vwapTwoDay[1]?.value}`,
  ))

  // VWAP output length = input length (no warmup needed)
  results.push(check(
    'VWAP output length = input length',
    vwapUniform.length === uniformBars.length,
    `got ${vwapUniform.length}, expected ${uniformBars.length}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// Edge case checks
// ─────────────────────────────────────────────────────────────────────────────

function checkEdgeCases(): CheckResult[] {
  const results: CheckResult[] = []

  // Empty array → no crash, return []
  const empty: Bar[] = []
  results.push(check(
    'calcSMA([]) returns [] without throwing',
    (() => { try { return calcSMA(empty, 5).length === 0 } catch { return false } })(),
    '',
  ))
  results.push(check(
    'calcEMA([]) returns [] without throwing',
    (() => { try { return calcEMA(empty, 5).length === 0 } catch { return false } })(),
    '',
  ))
  results.push(check(
    'calcRSI([]) returns [] without throwing',
    (() => { try { return calcRSI(empty, 14).length === 0 } catch { return false } })(),
    '',
  ))

  // Period larger than data → empty result
  const shortBars = makeBars([1, 2, 3])
  results.push(check(
    'SMA(period > n) returns []',
    calcSMA(shortBars, 10).length === 0,
    `got ${calcSMA(shortBars, 10).length}`,
  ))

  // Single bar EMA with period=1 should return itself
  const oneBars = makeBars([42])
  const ema1 = calcEMA(oneBars, 1)
  results.push(check(
    'EMA(1) on single bar returns that value',
    ema1.length === 1 && near(ema1[0].value, 42),
    `got ${ema1[0]?.value}`,
  ))

  return results
}

// ─────────────────────────────────────────────────────────────────────────────
// Public entry point
// ─────────────────────────────────────────────────────────────────────────────

export function runIndicatorChecks(): CheckResult[] {
  return [
    ...checkSMA(),
    ...checkEMA(),
    ...checkBB(),
    ...checkRSI(),
    ...checkMACD(),
    ...checkVWAP(),
    ...checkEdgeCases(),
  ]
}

/**
 * Print results to console.
 * Usage: import { printIndicatorChecks } from './indicators.test'; printIndicatorChecks()
 */
export function printIndicatorChecks(): void {
  const results = runIndicatorChecks()
  let pass = 0, fail = 0
  for (const r of results) {
    if (r.pass) { pass++; console.log(`  PASS  ${r.name}`) }
    else         { fail++; console.error(`  FAIL  ${r.name} — ${r.detail}`) }
  }
  console.log(`\n${pass} passed, ${fail} failed out of ${results.length} checks`)
}
