/*
 * CARDEX Terminal — market intelligence model
 * Deterministic, seeded synthetic data that mirrors the real CARDEX domain:
 * price indices per segment·country, supply depth ladders, cross-border arbitrage
 * with Net Landed Cost (NLC), Seller Desperation Index (SDI), fiscal regimes
 * (REBU vs VAT-deductible) and a live signal tape. Wired to the real brand catalog
 * for logos/colors. When the backend lands, swap these generators for API calls —
 * the component contracts (types below) stay identical.
 */
import { BRANDS } from '../../data/catalog'

// ── Reference clock (fixed for deterministic series) ──────────────────────────
export const NOW = new Date('2026-06-01')

// ── Geography ─────────────────────────────────────────────────────────────────
export interface Market {
  code: string
  name: string
  flag: string
  ccy: string          // currency symbol
  vat: number          // standard VAT %
  regTax: string       // registration-tax regime label
  factor: number       // price-level factor vs DE baseline
  dealers: number      // active professional dealers (k-scale realism)
}
export const MARKETS: Market[] = [
  { code: 'DE', name: 'Germany',     flag: '🇩🇪', ccy: '€', vat: 19,  regTax: 'None',           factor: 1.00, dealers: 38_400 },
  { code: 'FR', name: 'France',      flag: '🇫🇷', ccy: '€', vat: 20,  regTax: 'Malus CO₂',       factor: 1.03, dealers: 27_100 },
  { code: 'ES', name: 'Spain',       flag: '🇪🇸', ccy: '€', vat: 21,  regTax: 'IEDMT',           factor: 0.94, dealers: 17_300 },
  { code: 'NL', name: 'Netherlands', flag: '🇳🇱', ccy: '€', vat: 21,  regTax: 'BPM',             factor: 1.09, dealers: 10_200 },
  { code: 'BE', name: 'Belgium',     flag: '🇧🇪', ccy: '€', vat: 21,  regTax: 'TMC',             factor: 1.02, dealers: 6_400  },
  { code: 'CH', name: 'Switzerland', flag: '🇨🇭', ccy: '€', vat: 8.1, regTax: 'Cantonal',        factor: 1.17, dealers: 6_100  },
]
export const MARKET_BY_CODE: Record<string, Market> =
  Object.fromEntries(MARKETS.map(m => [m.code, m]))

// ── Instrument universe (curated institutional breadth) ───────────────────────
export type Segment = 'Compact' | 'Premium Sedan' | 'SUV' | 'EV' | 'Sports' | 'Van' | 'Luxury'
export type Fuel = 'Diesel' | 'Petrol' | 'Hybrid' | 'Electric'
export type FiscalRegime = 'VAT-deductible' | 'REBU'

export interface Instrument {
  id: string
  make: string
  model: string
  variant: string
  segment: Segment
  fuel: Fuel
  basePrice: number    // DE-market reference, €
  vol: number          // annualised volatility proxy
  logo: string
  color: string
  fiscal: FiscalRegime
}

function brandMeta(make: string): { logo: string; color: string } {
  const b = BRANDS.find(x => x.name.toLowerCase() === make.toLowerCase())
  return { logo: b?.logo ?? `https://cdn.simpleicons.org/${make.toLowerCase()}/ffffff`, color: b?.color ?? '#8b5cf6' }
}

interface InstrumentSeed {
  make: string; model: string; variant: string
  segment: Segment; fuel: Fuel; basePrice: number; vol: number; fiscal: FiscalRegime
}
const SEEDS: InstrumentSeed[] = [
  { make: 'BMW',        model: 'Serie 3',  variant: '320d',          segment: 'Premium Sedan', fuel: 'Diesel',   basePrice: 28_450, vol: 0.9, fiscal: 'VAT-deductible' },
  { make: 'BMW',        model: 'M3',       variant: 'Competition',   segment: 'Sports',        fuel: 'Petrol',   basePrice: 78_900, vol: 2.1, fiscal: 'REBU' },
  { make: 'BMW',        model: 'Serie 5',  variant: '530e',          segment: 'Premium Sedan', fuel: 'Hybrid',   basePrice: 44_200, vol: 1.2, fiscal: 'VAT-deductible' },
  { make: 'Volkswagen', model: 'Golf',     variant: '2.0 TDI 150cv', segment: 'Compact',       fuel: 'Diesel',   basePrice: 22_800, vol: 0.7, fiscal: 'VAT-deductible' },
  { make: 'Volkswagen', model: 'Golf GTI', variant: 'GTI 245cv',     segment: 'Sports',        fuel: 'Petrol',   basePrice: 31_500, vol: 1.4, fiscal: 'VAT-deductible' },
  { make: 'Volkswagen', model: 'ID.4',     variant: 'Pro 77 kWh',    segment: 'EV',            fuel: 'Electric', basePrice: 35_900, vol: 1.7, fiscal: 'VAT-deductible' },
  { make: 'Audi',       model: 'A4',       variant: '40 TDI',        segment: 'Premium Sedan', fuel: 'Diesel',   basePrice: 29_300, vol: 0.9, fiscal: 'VAT-deductible' },
  { make: 'Audi',       model: 'RS6',      variant: 'Avant',         segment: 'Sports',        fuel: 'Petrol',   basePrice: 98_500, vol: 2.4, fiscal: 'REBU' },
  { make: 'Audi',       model: 'Q5',       variant: '50 TFSIe',      segment: 'SUV',           fuel: 'Hybrid',   basePrice: 47_800, vol: 1.1, fiscal: 'VAT-deductible' },
  { make: 'Mercedes', model: 'Clase C', variant: 'C220d',      segment: 'Premium Sedan', fuel: 'Diesel',   basePrice: 34_600, vol: 1.0, fiscal: 'VAT-deductible' },
  { make: 'Mercedes', model: 'GLC',     variant: '300de',      segment: 'SUV',           fuel: 'Hybrid',   basePrice: 52_400, vol: 1.2, fiscal: 'VAT-deductible' },
  { make: 'Porsche',    model: '911',      variant: 'Carrera',       segment: 'Sports',        fuel: 'Petrol',   basePrice: 118_000, vol: 1.9, fiscal: 'REBU' },
  { make: 'Porsche',    model: 'Cayenne',  variant: 'E-Hybrid',      segment: 'Luxury',        fuel: 'Hybrid',   basePrice: 92_300, vol: 1.5, fiscal: 'REBU' },
  { make: 'Toyota',     model: 'Corolla',  variant: '1.8 HV',        segment: 'Compact',       fuel: 'Hybrid',   basePrice: 23_100, vol: 0.6, fiscal: 'VAT-deductible' },
  { make: 'Renault',    model: 'Clio',     variant: '1.6 E-Tech',    segment: 'Compact',       fuel: 'Hybrid',   basePrice: 18_900, vol: 0.6, fiscal: 'VAT-deductible' },
  { make: 'Tesla',      model: 'Model 3',  variant: 'Long Range',    segment: 'EV',            fuel: 'Electric', basePrice: 38_700, vol: 2.2, fiscal: 'VAT-deductible' },
  { make: 'Volkswagen', model: 'Tiguan',   variant: '2.0 TDI 150cv', segment: 'SUV',           fuel: 'Diesel',   basePrice: 30_400, vol: 0.8, fiscal: 'VAT-deductible' },
  { make: 'Mercedes', model: 'Clase V', variant: '300d',       segment: 'Van',           fuel: 'Diesel',   basePrice: 58_900, vol: 1.0, fiscal: 'REBU' },
]

export const INSTRUMENTS: Instrument[] = SEEDS.map(s => {
  const meta = brandMeta(s.make)
  // Only trust monochrome simpleicons SVGs (theme-invertible). Anything else falls back
  // to a designed initials chip so light/dark stay clean and no broken request fires.
  const logo = meta.logo.includes('simpleicons.org') ? meta.logo : ''
  return {
    id: `${s.make}:${s.model}:${s.variant}`.replace(/\s+/g, '_'),
    ...s,
    logo,
    color: meta.color === '#8a8a8a' ? '#9aa3b2' : meta.color,
  }
})
export const INSTRUMENT_BY_ID: Record<string, Instrument> =
  Object.fromEntries(INSTRUMENTS.map(i => [i.id, i]))

// ── Deterministic RNG ─────────────────────────────────────────────────────────
export function seedRng(seed: number) {
  let s = seed >>> 0
  return () => { s = (s * 1664525 + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
}
export function hash(str: string): number {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) }
  return h >>> 0
}

// ── Price-index series (OHLCV) ─────────────────────────────────────────────────
export interface Bar { time: string; open: number; high: number; low: number; close: number; volume: number }

export function priceSeries(inst: Instrument, marketCode: string, days = 400): Bar[] {
  const mkt = MARKET_BY_CODE[marketCode] ?? MARKETS[0]
  const base = inst.basePrice * mkt.factor
  const rng = seedRng(hash(inst.id + marketCode))
  const bars: Bar[] = []
  let price = base * (0.92 + rng() * 0.06)
  // Gentle macro trend so each market has a distinct character
  const trend = (rng() - 0.45) * inst.vol * (base / 9000)
  for (let i = days; i >= 0; i--) {
    const d = new Date(NOW); d.setDate(d.getDate() - i)
    const dow = d.getDay()
    if (dow === 0 || dow === 6) continue
    const time = d.toISOString().split('T')[0]
    const drift = (rng() - 0.5) * inst.vol * (base / 110) + trend
    const close = Math.max(base * 0.62, Math.min(base * 1.4, price + drift))
    const wick = rng() * inst.vol * (base / 320)
    const open = price
    bars.push({
      time,
      open,
      high: Math.max(open, close) + wick,
      low: Math.min(open, close) - wick,
      close,
      volume: Math.round(60 + rng() * 180),
    })
    price = close
  }
  return bars
}

export interface Quote {
  inst: Instrument
  market: string
  last: number
  prevClose: number
  changePct: number
  high30: number
  low30: number
  vol5: number
  spark: number[]
}
export function quote(inst: Instrument, marketCode: string): Quote {
  const bars = priceSeries(inst, marketCode, 60)
  const last = bars.at(-1)!, prev = bars.at(-2)!
  const recent = bars.slice(-30)
  return {
    inst, market: marketCode,
    last: last.close,
    prevClose: prev.close,
    changePct: prev.close ? ((last.close - prev.close) / prev.close) * 100 : 0,
    high30: Math.max(...recent.map(b => b.high)),
    low30: Math.min(...recent.map(b => b.low)),
    vol5: bars.slice(-5).reduce((s, b) => s + b.volume, 0),
    spark: bars.slice(-28).map(b => b.close),
  }
}

// ── Supply depth ladder (institutional order-book analog) ─────────────────────
export interface DepthLevel { price: number; listings: number; side: 'below' | 'above' }
export interface Depth {
  mid: number
  below: DepthLevel[]   // listings priced under the index (the "bid" wall — buying opportunity)
  above: DepthLevel[]   // listings priced over the index (the "ask" wall — overpriced supply)
  totalBelow: number
  totalAbove: number
  imbalance: number     // -1..1, positive = thin supply below (seller's market)
}
export function depthLadder(inst: Instrument, marketCode: string, levels = 8): Depth {
  const q = quote(inst, marketCode)
  const mid = q.last
  const rng = seedRng(hash(inst.id + marketCode + 'depth'))
  const step = Math.max(150, Math.round((mid * 0.012) / 50) * 50)
  const below: DepthLevel[] = []
  const above: DepthLevel[] = []
  for (let i = 1; i <= levels; i++) {
    const decay = 1 - i / (levels + 4)
    below.push({ price: mid - step * i, listings: Math.round((30 + rng() * 220) * decay), side: 'below' })
    above.push({ price: mid + step * i, listings: Math.round((25 + rng() * 200) * decay), side: 'above' })
  }
  const totalBelow = below.reduce((s, l) => s + l.listings, 0)
  const totalAbove = above.reduce((s, l) => s + l.listings, 0)
  const tot = totalBelow + totalAbove || 1
  return { mid, below, above, totalBelow, totalAbove, imbalance: (totalAbove - totalBelow) / tot }
}

// ── Seller Desperation Index ───────────────────────────────────────────────────
export type SdiBand = 'Cold' | 'Neutral' | 'Warm' | 'Hot' | 'Distressed'
export interface Sdi {
  score: number          // 0..100
  band: SdiBand
  daysOnMarket: number
  priceCutPct: number    // avg price drop on relist
  relistRate: number     // % relisted
  supplyGlut: number     // 0..1
}
export function sdiBand(score: number): SdiBand {
  if (score >= 80) return 'Distressed'
  if (score >= 62) return 'Hot'
  if (score >= 42) return 'Warm'
  if (score >= 24) return 'Neutral'
  return 'Cold'
}
export function computeSdi(inst: Instrument, marketCode: string): Sdi {
  const rng = seedRng(hash(inst.id + marketCode + 'sdi'))
  const daysOnMarket = Math.round(18 + rng() * 80)
  const priceCutPct = +(0.4 + rng() * 6.2).toFixed(1)
  const relistRate = Math.round(8 + rng() * 46)
  const supplyGlut = +(rng()).toFixed(2)
  // Weighted composite — higher = more desperate sellers = buyer leverage
  const score = Math.round(
    Math.min(100,
      (daysOnMarket / 110) * 34 +
      (priceCutPct / 7) * 30 +
      (relistRate / 55) * 18 +
      supplyGlut * 18),
  )
  return { score, band: sdiBand(score), daysOnMarket, priceCutPct, relistRate, supplyGlut }
}

// ── Cross-border arbitrage + Net Landed Cost ───────────────────────────────────
export interface NlcLine { label: string; amount: number; kind: 'cost' | 'base' | 'net' }
export interface Nlc {
  buy: string; sell: string
  grossBuy: number
  vatTreatment: string
  transport: number
  regTax: number
  homologation: number
  admin: number
  landed: number       // total cost to land in sell market
  sellPrice: number
  margin: number       // €
  marginPct: number
  lines: NlcLine[]
}
function transportCost(buy: string, sell: string, price: number): number {
  if (buy === sell) return 0
  // Distance proxy bands (€) + insurance scaling lightly with value
  const band: Record<string, number> = { DE: 0, FR: 1, ES: 2, NL: 1, BE: 1, CH: 1 }
  const dist = Math.abs((band[buy] ?? 1) - (band[sell] ?? 1)) + 1
  return Math.round(420 + dist * 280 + price * 0.004)
}
function registrationTax(sell: string, inst: Instrument, price: number): number {
  const mkt = MARKET_BY_CODE[sell]
  if (!mkt) return 0
  const evClean = inst.fuel === 'Electric'
  switch (sell) {
    case 'NL': return evClean ? 0 : Math.round(price * 0.07 + 1100)     // BPM (CO₂ heavy)
    case 'FR': return evClean ? 0 : Math.round(price * 0.03 + 600)       // Malus
    case 'ES': return evClean ? 0 : Math.round(price * 0.0475)           // IEDMT band
    case 'BE': return Math.round(495 + price * 0.005)                    // TMC
    case 'CH': return Math.round(300 + price * 0.004)                    // cantonal
    default:   return 0                                                  // DE none
  }
}
export function computeNlc(inst: Instrument, buy: string, sell: string): Nlc {
  const grossBuy = quote(inst, buy).last
  const sellPrice = quote(inst, sell).last
  const transport = transportCost(buy, sell, grossBuy)
  const regTax = registrationTax(sell, inst, grossBuy)
  const homologation = buy === sell ? 0 : (inst.fiscal === 'REBU' ? 280 : 180)
  const admin = buy === sell ? 90 : 240
  const vatTreatment = inst.fiscal === 'REBU'
    ? 'REBU — margin scheme, VAT non-deductible'
    : `VAT-deductible — reverse charge intra-EU`
  const landed = grossBuy + transport + regTax + homologation + admin
  const margin = sellPrice - landed
  const lines: NlcLine[] = [
    { label: `Gross buy · ${buy}`, amount: grossBuy, kind: 'base' },
    { label: 'Transport & insurance', amount: transport, kind: 'cost' },
    { label: `Registration tax · ${MARKET_BY_CODE[sell]?.regTax ?? sell}`, amount: regTax, kind: 'cost' },
    { label: 'Homologation', amount: homologation, kind: 'cost' },
    { label: 'Admin & compliance', amount: admin, kind: 'cost' },
    { label: `Net landed · ${sell}`, amount: landed, kind: 'net' },
  ]
  return {
    buy, sell, grossBuy, vatTreatment, transport, regTax, homologation, admin,
    landed, sellPrice, margin, marginPct: (margin / landed) * 100, lines,
  }
}

export interface ArbRow {
  inst: Instrument
  buy: string
  sell: string
  buyPrice: number
  sellPrice: number
  nlc: number
  margin: number
  marginPct: number
  fiscal: FiscalRegime
}
/** Scan every ordered market pair for an instrument, return best opportunities first. */
export function arbitrageRows(inst: Instrument): ArbRow[] {
  const rows: ArbRow[] = []
  for (const buy of MARKETS) {
    for (const sell of MARKETS) {
      if (buy.code === sell.code) continue
      const n = computeNlc(inst, buy.code, sell.code)
      rows.push({
        inst, buy: buy.code, sell: sell.code,
        buyPrice: n.grossBuy, sellPrice: n.sellPrice, nlc: n.landed,
        margin: n.margin, marginPct: n.marginPct, fiscal: inst.fiscal,
      })
    }
  }
  return rows.sort((a, b) => b.marginPct - a.marginPct)
}

/** Top arbitrage opportunities across the whole universe (screener). */
export function topArbitrage(limit = 14): ArbRow[] {
  const all: ArbRow[] = []
  for (const inst of INSTRUMENTS) all.push(arbitrageRows(inst)[0])
  return all.sort((a, b) => b.marginPct - a.marginPct).slice(0, limit)
}

// ── Fundamentals ────────────────────────────────────────────────────────────────
export interface Fundamentals {
  supply: number          // active listings
  daysToSell: number      // liquidity proxy
  turnover: number        // monthly %
  volatility: number      // %
  dealerCount: number
  fiscal: FiscalRegime
  vat: number
}
export function fundamentals(inst: Instrument, marketCode: string): Fundamentals {
  const rng = seedRng(hash(inst.id + marketCode + 'fund'))
  const mkt = MARKET_BY_CODE[marketCode] ?? MARKETS[0]
  return {
    supply: Math.round((900 + rng() * 9000) * mkt.factor),
    daysToSell: Math.round(22 + rng() * 60),
    turnover: +(6 + rng() * 22).toFixed(1),
    volatility: +(inst.vol * (10 + rng() * 6)).toFixed(1),
    dealerCount: Math.round((40 + rng() * 900) * (mkt.dealers / 38_400)),
    fiscal: inst.fiscal,
    vat: mkt.vat,
  }
}

// ── Market movers (heatmap) ─────────────────────────────────────────────────────
export interface Mover { inst: Instrument; market: string; changePct: number; last: number }
export function marketMovers(marketCode: string): { gainers: Mover[]; losers: Mover[] } {
  const all: Mover[] = INSTRUMENTS.map(i => {
    const q = quote(i, marketCode)
    return { inst: i, market: marketCode, changePct: q.changePct, last: q.last }
  })
  const sorted = [...all].sort((a, b) => b.changePct - a.changePct)
  return { gainers: sorted.slice(0, 5), losers: sorted.slice(-5).reverse() }
}

// ── Signal tape ─────────────────────────────────────────────────────────────────
export type SignalKind = 'NEW' | 'CUT' | 'ARB' | 'FISCAL' | 'SUPPLY' | 'SOLD'
export interface Signal {
  id: string
  kind: SignalKind
  inst: Instrument
  market: string
  text: string
  value?: string
  minsAgo: number
}
const SIGNAL_TEMPLATES: { kind: SignalKind; make: (i: Instrument, m: Market) => { text: string; value?: string } }[] = [
  { kind: 'ARB',    make: (i, m) => ({ text: `Arbitrage window ${i.make} ${i.model}`, value: `→ ${m.code} +6.8%` }) },
  { kind: 'CUT',    make: (i, m) => ({ text: `Price cut · ${i.make} ${i.model} · ${m.code}`, value: '−€1,240' }) },
  { kind: 'NEW',    make: (i, m) => ({ text: `New supply · ${i.make} ${i.model} · ${m.code}`, value: '+318 listings' }) },
  { kind: 'FISCAL', make: (i) => ({ text: `${i.make} ${i.model} reclassified`, value: i.fiscal }) },
  { kind: 'SUPPLY', make: (i, m) => ({ text: `Supply spike · ${i.make} ${i.model} · ${m.code}`, value: '+22%' }) },
  { kind: 'SOLD',   make: (i, m) => ({ text: `Cleared at index · ${i.make} ${i.model} · ${m.code}`, value: 'sold' }) },
]
export function signalFeed(count = 16): Signal[] {
  const rng = seedRng(hash('cardex-tape'))
  const out: Signal[] = []
  for (let i = 0; i < count; i++) {
    const inst = INSTRUMENTS[Math.floor(rng() * INSTRUMENTS.length)]
    const mkt = MARKETS[Math.floor(rng() * MARKETS.length)]
    const tpl = SIGNAL_TEMPLATES[Math.floor(rng() * SIGNAL_TEMPLATES.length)]
    const { text, value } = tpl.make(inst, mkt)
    out.push({ id: `sig_${i}`, kind: tpl.kind, inst, market: mkt.code, text, value, minsAgo: Math.round(1 + rng() * 240) })
  }
  return out.sort((a, b) => a.minsAgo - b.minsAgo)
}

// ── Indicator math ──────────────────────────────────────────────────────────────
// PD type stays here (used by this file and by indicators.ts via type import).
export type PD = { time: string; value: number }

// calc* functions live in indicators.ts (corrected EMA seed + full 53-indicator catalog).
// Re-exported here to preserve all existing imports in MarketChart.tsx.
export { calcSMA, calcEMA, calcBB, calcRSI, calcMACD, calcVWAP } from './indicators'

// ── Formatting helpers ────────────────────────────────────────────────────────
export function fmtPrice(n: number): string { return '€' + Math.round(n).toLocaleString('de-DE') }
export function fmtPct(n: number): string { return (n >= 0 ? '+' : '') + n.toFixed(2) + '%' }
export function fmtCompact(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k'
  return String(Math.round(n))
}
export function agoLabel(mins: number): string {
  if (mins < 60) return `${mins}m`
  const h = Math.floor(mins / 60)
  return h < 24 ? `${h}h` : `${Math.floor(h / 24)}d`
}
