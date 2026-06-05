/*
 * CARDEX Terminal — decision intelligence layer
 * The data foundation of the elite "Decision Desk": for the selected instrument it computes a
 * grid of decision modules (each a KPI card with a headline value + delta + a detail payload for
 * the click-to-expand modal), a technical rating, a valuation read, and a deterministic news feed
 * with per-item sentiment. Pure + deterministic (seeded) so it serves identically whether a dealer
 * tracks 5 cars or 500,000. No I/O, no randomness across renders.
 *
 * Pattern audited from Plus500 +Insights, eToro asset page, TradingView symbol details and
 * Bloomberg: dense-but-organised modules, a buy/sell rating gauge, sentiment-tagged news, and a
 * "confidence/why" rationale behind every score.
 */
import type { Instrument } from './market'
import {
  quote, computeSdi, computeNlc, arbitrageRows, fundamentals, depthLadder, priceSeries,
  fmtPrice, fmtCompact, seedRng, hash, MARKET_BY_CODE,
} from './market'

export type Tone = 'up' | 'down' | 'neutral' | 'accent'

export interface DetailRow { label: string; value: string; tone?: Tone }
export interface IntelModule {
  id: string
  label: string                       // card title
  value: string                       // headline value (formatted)
  sub?: string                        // tiny caption under the value
  delta?: { text: string; tone: Tone }
  tone: Tone                          // accent of the headline
  spark?: number[]                    // optional mini sparkline
  gauge?: number                      // optional 0..100 ring fill
  why: string                         // one-line decision rationale (modal header)
  detail: DetailRow[]                 // sub-metric breakdown (modal body)
}

export type Sentiment = 'pos' | 'neg' | 'neu'
export interface NewsItem {
  id: string
  headline: string
  source: string
  ageMin: number
  sentiment: Sentiment
  tag: string
}

export interface TechRating {
  label: 'STRONG SELL' | 'SELL' | 'NEUTRAL' | 'BUY' | 'STRONG BUY'
  score: number        // -100..100
  tone: Tone
  rsi: number
  trend: 'up' | 'down' | 'flat'
  smaCross: 'golden' | 'death' | 'none'
}

// ── small technical helpers (self-contained, no indicators.ts coupling) ──────────
function sma(vals: number[], n: number): number {
  if (vals.length < n) return vals.reduce((s, v) => s + v, 0) / (vals.length || 1)
  const slice = vals.slice(-n)
  return slice.reduce((s, v) => s + v, 0) / n
}
function rsi(closes: number[], n = 14): number {
  if (closes.length < n + 1) return 50
  let gain = 0, loss = 0
  for (let i = closes.length - n; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1]
    if (d >= 0) gain += d; else loss -= d
  }
  const rs = loss === 0 ? 100 : gain / loss
  return Math.round(100 - 100 / (1 + rs))
}

export function technicalRating(inst: Instrument, market: string): TechRating {
  const closes = priceSeries(inst, market, 60).map(b => b.close)
  const last = closes.at(-1)!
  const s20 = sma(closes, 20), s50 = sma(closes, 50)
  const r = rsi(closes, 14)
  const mom = last - (closes.at(-11) ?? last)
  let score = 0
  score += last > s20 ? 25 : -25
  score += s20 > s50 ? 25 : -25
  score += r > 55 ? 25 : r < 45 ? -25 : 0
  score += mom > 0 ? 25 : -25
  const label: TechRating['label'] =
    score >= 75 ? 'STRONG BUY' : score >= 25 ? 'BUY' : score <= -75 ? 'STRONG SELL' : score <= -25 ? 'SELL' : 'NEUTRAL'
  return {
    label, score,
    tone: score > 0 ? 'up' : score < 0 ? 'down' : 'neutral',
    rsi: r,
    trend: mom > 0 ? 'up' : mom < 0 ? 'down' : 'flat',
    smaCross: s20 > s50 ? 'golden' : s20 < s50 ? 'death' : 'none',
  }
}

export interface Valuation {
  rangePos: number      // 0..100 position of last in 30d range
  fair: number          // fair-value estimate (€)
  gapPct: number        // (last - fair) / fair * 100  (>0 = rich, <0 = cheap)
}
export function valuation(inst: Instrument, market: string): Valuation {
  const q = quote(inst, market)
  const span = Math.max(1, q.high30 - q.low30)
  const rangePos = Math.round(((q.last - q.low30) / span) * 100)
  const closes = priceSeries(inst, market, 60).map(b => b.close)
  const fair = Math.round(sma(closes, 50))
  return { rangePos, fair, gapPct: +(((q.last - fair) / fair) * 100).toFixed(1) }
}

const pctTone = (v: number): Tone => (v > 0 ? 'up' : v < 0 ? 'down' : 'neutral')

/**
 * The decision-module grid for an instrument in a market. Every module carries a headline value
 * for the card and a detail breakdown for the modal — dense but organised.
 */
export function decisionModules(inst: Instrument, market: string): IntelModule[] {
  const q = quote(inst, market)
  const sdi = computeSdi(inst, market)
  const fund = fundamentals(inst, market)
  const depth = depthLadder(inst, market)
  const best = arbitrageRows(inst)[0]
  const nlc = computeNlc(inst, best.buy, best.sell)
  const tech = technicalRating(inst, market)
  const val = valuation(inst, market)
  const flag = (c: string) => MARKET_BY_CODE[c]?.flag ?? ''

  // Demand index: liquidity (turnover, low days-to-sell) net of supply glut — 0..100.
  const demandIdx = Math.round(Math.max(0, Math.min(100,
    fund.turnover * 2.4 + (100 - fund.daysToSell) * 0.4 - sdi.supplyGlut * 28 + 18)))
  // Sell-through proxy from turnover.
  const sellThrough = Math.round(Math.min(96, 38 + fund.turnover * 1.7))

  return [
    {
      id: 'edge',
      label: 'Cross-border edge',
      value: `${best.marginPct >= 0 ? '+' : ''}${best.marginPct.toFixed(1)}%`,
      sub: `${flag(best.buy)} ${best.buy} → ${flag(best.sell)} ${best.sell}`,
      delta: { text: `${best.margin >= 0 ? '+' : '−'}${fmtPrice(Math.abs(best.margin)).slice(1)}`, tone: pctTone(best.margin) },
      tone: pctTone(best.marginPct),
      why: 'Net margin on the best buy-low / sell-high route after transport, registration tax and fiscal treatment.',
      detail: nlc.lines.map(l => ({ label: l.label, value: fmtPrice(l.amount), tone: l.kind === 'net' ? 'accent' : 'neutral' as Tone }))
        .concat([{ label: `Sell · ${best.sell}`, value: fmtPrice(nlc.sellPrice), tone: 'neutral' },
                 { label: 'Net margin', value: `${fmtPrice(nlc.margin)} · ${nlc.marginPct.toFixed(1)}%`, tone: pctTone(nlc.margin) }]),
    },
    {
      id: 'sdi',
      label: 'Seller pressure · SDI',
      value: `${sdi.score}`,
      sub: sdi.band,
      gauge: sdi.score,
      tone: sdi.score >= 50 ? 'up' : 'neutral',
      why: 'Composite of days-on-market, price cuts, relist rate and supply glut. Higher = more buyer leverage.',
      detail: [
        { label: 'Band', value: sdi.band, tone: sdi.score >= 50 ? 'up' : 'neutral' },
        { label: 'Days on market', value: `${sdi.daysOnMarket}d` },
        { label: 'Avg price cut on relist', value: `−${sdi.priceCutPct}%`, tone: 'down' },
        { label: 'Relist rate', value: `${sdi.relistRate}%` },
        { label: 'Supply glut', value: `${Math.round(sdi.supplyGlut * 100)}%` },
      ],
    },
    {
      id: 'technical',
      label: 'Technical rating',
      value: tech.label,
      sub: `RSI ${tech.rsi}`,
      gauge: Math.round((tech.score + 100) / 2),
      tone: tech.tone,
      why: 'Aggregated trend, moving-average cross, RSI and momentum on the price index.',
      detail: [
        { label: 'Composite score', value: `${tech.score > 0 ? '+' : ''}${tech.score}`, tone: tech.tone },
        { label: 'RSI (14)', value: `${tech.rsi}`, tone: tech.rsi > 70 ? 'down' : tech.rsi < 30 ? 'up' : 'neutral' },
        { label: 'Trend (10d momentum)', value: tech.trend, tone: tech.trend === 'up' ? 'up' : tech.trend === 'down' ? 'down' : 'neutral' },
        { label: 'SMA 20/50', value: tech.smaCross === 'golden' ? 'golden cross' : tech.smaCross === 'death' ? 'death cross' : 'flat', tone: tech.smaCross === 'golden' ? 'up' : tech.smaCross === 'death' ? 'down' : 'neutral' },
      ],
    },
    {
      id: 'valuation',
      label: 'Valuation',
      value: `${val.gapPct >= 0 ? '+' : ''}${val.gapPct}%`,
      sub: 'vs fair value',
      tone: val.gapPct <= 0 ? 'up' : 'down',
      why: 'Index price versus 50-day fair value and its position in the 30-day range. Below fair = cheaper entry.',
      detail: [
        { label: 'Last', value: fmtPrice(q.last) },
        { label: 'Fair value (SMA50)', value: fmtPrice(val.fair), tone: 'accent' },
        { label: '30d high', value: fmtPrice(q.high30) },
        { label: '30d low', value: fmtPrice(q.low30) },
        { label: 'Range position', value: `${val.rangePos}%` },
      ],
    },
    {
      id: 'liquidity',
      label: 'Liquidity',
      value: `${fund.daysToSell}d`,
      sub: 'time to sell',
      delta: { text: `${sellThrough}% sell-through`, tone: sellThrough >= 60 ? 'up' : 'neutral' },
      tone: fund.daysToSell <= 35 ? 'up' : fund.daysToSell >= 60 ? 'down' : 'neutral',
      why: 'How fast the model clears at the index. Lower days-to-sell and higher turnover = liquid, lower carry risk.',
      detail: [
        { label: 'Days to sell', value: `${fund.daysToSell}d`, tone: fund.daysToSell <= 35 ? 'up' : fund.daysToSell >= 60 ? 'down' : 'neutral' },
        { label: 'Monthly turnover', value: `${fund.turnover}%` },
        { label: 'Sell-through', value: `${sellThrough}%` },
        { label: 'Pro dealers', value: fmtCompact(fund.dealerCount) },
      ],
    },
    {
      id: 'demand',
      label: 'Demand index',
      value: `${demandIdx}`,
      sub: demandIdx >= 60 ? 'strong' : demandIdx >= 40 ? 'steady' : 'soft',
      gauge: demandIdx,
      tone: demandIdx >= 60 ? 'up' : demandIdx >= 40 ? 'neutral' : 'down',
      why: 'Buyer appetite from turnover and time-to-sell, net of supply glut. High demand defends resale.',
      detail: [
        { label: 'Demand score', value: `${demandIdx}`, tone: demandIdx >= 60 ? 'up' : 'neutral' },
        { label: 'Turnover', value: `${fund.turnover}%` },
        { label: 'Supply glut', value: `${Math.round(sdi.supplyGlut * 100)}%`, tone: 'down' },
        { label: 'Days to sell', value: `${fund.daysToSell}d` },
      ],
    },
    {
      id: 'supply',
      label: 'Supply depth',
      value: fmtCompact(fund.supply),
      sub: 'active listings',
      delta: { text: `${depth.imbalance >= 0 ? '+' : ''}${Math.round(depth.imbalance * 100)}% imbalance`, tone: depth.imbalance >= 0 ? 'up' : 'down' },
      tone: 'neutral',
      why: 'Listings priced below vs above the index. Positive imbalance = thin cheap supply (seller-favourable).',
      detail: [
        { label: 'Active listings', value: fmtCompact(fund.supply) },
        { label: 'Below index (buy wall)', value: fmtCompact(depth.totalBelow), tone: 'up' },
        { label: 'Above index (overpriced)', value: fmtCompact(depth.totalAbove), tone: 'down' },
        { label: 'Imbalance', value: `${depth.imbalance >= 0 ? '+' : ''}${Math.round(depth.imbalance * 100)}%`, tone: depth.imbalance >= 0 ? 'up' : 'down' },
      ],
    },
    {
      id: 'volatility',
      label: 'Volatility',
      value: `${fund.volatility}%`,
      sub: fund.volatility >= 18 ? 'elevated' : fund.volatility >= 11 ? 'moderate' : 'low',
      tone: fund.volatility >= 18 ? 'down' : 'neutral',
      why: 'Price-index dispersion. Higher volatility widens entry/exit risk on the carry.',
      detail: [
        { label: 'Annualised vol', value: `${fund.volatility}%`, tone: fund.volatility >= 18 ? 'down' : 'neutral' },
        { label: '30d high', value: fmtPrice(q.high30) },
        { label: '30d low', value: fmtPrice(q.low30) },
        { label: 'Range width', value: `${(((q.high30 - q.low30) / q.last) * 100).toFixed(1)}%` },
      ],
    },
    {
      id: 'fiscal',
      label: 'Fiscal regime',
      value: inst.fiscal === 'REBU' ? 'REBU' : 'VAT-ded.',
      sub: inst.fiscal === 'REBU' ? 'margin scheme' : 'reverse charge',
      tone: inst.fiscal === 'REBU' ? 'neutral' : 'up',
      why: 'Tax treatment on resale. VAT-deductible reverse-charge preserves margin; REBU taxes only the margin.',
      detail: [
        { label: 'Regime', value: inst.fiscal, tone: inst.fiscal === 'REBU' ? 'neutral' : 'up' },
        { label: 'VAT deductible', value: inst.fiscal === 'REBU' ? 'No (margin only)' : 'Yes' },
        { label: `VAT · ${market}`, value: `${fund.vat}%` },
        { label: 'Treatment', value: nlc.vatTreatment },
      ],
    },
  ]
}

// ── News system ──────────────────────────────────────────────────────────────────
const NEWS_SOURCES = ['Autovista', 'INDICATA', 'JATO Dynamics', 'DAT', 'Schwacke', 'Eurotax', 'ACEA', 'Spotcar']
type NewsTemplate = { tmpl: (i: Instrument, m: string) => string; sentiment: Sentiment; tag: string }
const NEWS_TEMPLATES: NewsTemplate[] = [
  { tmpl: (i, m) => `${i.make} ${i.model} residuals firm in ${m} as ${i.fuel.toLowerCase()} supply tightens`, sentiment: 'pos', tag: 'Residuals' },
  { tmpl: (i, m) => `Cross-border flow into ${m} lifts ${i.make} ${i.model} ask prices`, sentiment: 'pos', tag: 'Arbitrage' },
  { tmpl: (i) => `${i.make} ${i.model} listing volume up 11% MoM — buyers gain leverage`, sentiment: 'neg', tag: 'Supply' },
  { tmpl: (i, m) => `${m} ${i.fuel.toLowerCase()} demand cools; days-on-market widen for ${i.segment.toLowerCase()}`, sentiment: 'neg', tag: 'Demand' },
  { tmpl: (i, m) => `${i.fiscal === 'REBU' ? 'REBU margin-scheme' : 'Intra-EU VAT'} guidance updated for ${m} dealers`, sentiment: 'neu', tag: 'Fiscal' },
  { tmpl: (i) => `${i.make} announces facelift — outgoing ${i.model} pricing softens`, sentiment: 'neg', tag: 'Product' },
  { tmpl: (i, m) => `Auction clearance for ${i.make} ${i.model} hits 3-month high in ${m}`, sentiment: 'pos', tag: 'Liquidity' },
  { tmpl: (i, m) => `Registration-tax review in ${m} could reprice imported ${i.segment.toLowerCase()}`, sentiment: 'neu', tag: 'Policy' },
  { tmpl: (i) => `Wholesale index for ${i.make} ${i.model} steadies after two-week slide`, sentiment: 'neu', tag: 'Index' },
  { tmpl: (i, m) => `${i.make} ${i.model} stock ages past 60 days at several ${m} dealers`, sentiment: 'neg', tag: 'Inventory' },
]

/** Deterministic recent-news feed for the instrument in a market. */
export function carNews(inst: Instrument, market: string, count = 6): NewsItem[] {
  const rng = seedRng(hash(inst.id + market + 'news'))
  const order = NEWS_TEMPLATES.map((t, i) => ({ t, k: rng() + i * 0.0001 })).sort((a, b) => a.k - b.k).map(x => x.t)
  const mkt = MARKET_BY_CODE[market]?.name ?? market
  const items: NewsItem[] = []
  let age = Math.round(8 + rng() * 30)
  for (let i = 0; i < Math.min(count, order.length); i++) {
    const tpl = order[i]
    items.push({
      id: `${inst.id}_${market}_n${i}`,
      headline: tpl.tmpl(inst, mkt),
      source: NEWS_SOURCES[Math.floor(rng() * NEWS_SOURCES.length)],
      ageMin: age,
      sentiment: tpl.sentiment,
      tag: tpl.tag,
    })
    age += Math.round(20 + rng() * 240)
  }
  return items
}

/** Net news sentiment + a confidence proxy (news volume backing the read) — Plus500 "Confidence Index" analog. */
export function newsSentiment(inst: Instrument, market: string): { score: number; pos: number; neg: number; neu: number; confidence: number } {
  const news = carNews(inst, market, 6)
  const pos = news.filter(n => n.sentiment === 'pos').length
  const neg = news.filter(n => n.sentiment === 'neg').length
  const neu = news.length - pos - neg
  const score = Math.round(((pos - neg) / (news.length || 1)) * 100)
  const confidence = Math.round(Math.min(100, 40 + news.length * 9))
  return { score, pos, neg, neu, confidence }
}
