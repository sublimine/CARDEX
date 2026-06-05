/*
 * CARDEX Terminal — cross-border arbitrage scanner
 * The core institutional surface: every market pair scored on Net Landed Cost. Buy where
 * cheap, sell where dear, net of transport + registration tax + fiscal regime. This is
 * the product's reason to exist, rendered as a sortable institutional blotter.
 */
import React, { useMemo } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import type { TerminalPalette } from './theme'
import { MONO, SANS } from './theme'
import {
  arbitrageRows, topArbitrage, MARKET_BY_CODE, fmtPrice,
  type Instrument, type ArbRow,
} from './market'
import { Eyebrow, FiscalBadge, BrandLogo } from './ui'

function Route({ p, buy, sell }: { p: TerminalPalette; buy: string; sell: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: SANS, fontSize: 11, fontWeight: 700, color: p.t2 }}>
      <span>{MARKET_BY_CODE[buy]?.flag} {buy}</span>
      <ArrowRight style={{ width: 11, height: 11, color: p.t4 }} />
      <span>{MARKET_BY_CODE[sell]?.flag} {sell}</span>
    </span>
  )
}

function MarginCell({ p, pct, value }: { p: TerminalPalette; pct: number; value: number }) {
  const up = pct >= 0
  const col = up ? p.up : p.down
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ fontFamily: MONO, fontVariantNumeric: 'tabular-nums', fontSize: 12, fontWeight: 700, color: col }}>{up ? '+' : ''}{pct.toFixed(1)}%</div>
      <div style={{ fontFamily: MONO, fontSize: 9.5, color: p.t4 }}>{up ? '+' : '−'}{fmtPrice(Math.abs(value)).slice(1)}</div>
    </div>
  )
}

/** Per-instrument arbitrage blotter (used in ARBITRAGE view + can be embedded). */
export function ArbitrageScanner({ p, inst }: { p: TerminalPalette; inst: Instrument }) {
  const rows = useMemo(() => arbitrageRows(inst).slice(0, 12), [inst])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', borderBottom: `1px solid ${p.hairline}`, flexShrink: 0 }}>
        <BrandLogo inst={inst} size={28} p={p} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: p.t1, fontFamily: SANS }}>{inst.make} {inst.model} <span style={{ color: p.t3, fontWeight: 500 }}>· {inst.variant}</span></div>
          <Eyebrow p={p}>Net-landed-cost arbitrage matrix · {rows.length} routes</Eyebrow>
        </div>
        <FiscalBadge p={p} regime={inst.fiscal} />
      </div>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 16px', gap: 12, flexShrink: 0 }}>
        <Eyebrow p={p} style={{ width: 130 }}>Route</Eyebrow>
        <Eyebrow p={p} style={{ flex: 1, textAlign: 'right' }}>Buy</Eyebrow>
        <Eyebrow p={p} style={{ flex: 1, textAlign: 'right' }}>Sell</Eyebrow>
        <Eyebrow p={p} style={{ flex: 1, textAlign: 'right' }}>Net landed</Eyebrow>
        <Eyebrow p={p} style={{ width: 84, textAlign: 'right' }}>Net margin</Eyebrow>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {rows.map((r, i) => (
          <motion.div key={`${r.buy}${r.sell}`} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.25) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '9px 16px', borderBottom: `1px solid ${p.hairline}`,
              background: i === 0 ? p.upDim : 'transparent',
            }}>
            <div style={{ width: 130 }}><Route p={p} buy={r.buy} sell={r.sell} /></div>
            <span style={{ flex: 1, textAlign: 'right', fontFamily: MONO, fontSize: 11.5, color: p.t2, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(r.buyPrice)}</span>
            <span style={{ flex: 1, textAlign: 'right', fontFamily: MONO, fontSize: 11.5, color: p.t2, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(r.sellPrice)}</span>
            <span style={{ flex: 1, textAlign: 'right', fontFamily: MONO, fontSize: 11.5, color: p.t3, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(r.nlc)}</span>
            <div style={{ width: 84 }}><MarginCell p={p} pct={r.marginPct} value={r.margin} /></div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

/** Universe-wide top opportunities (SCREENER view). */
export function ArbitrageScreener({ p, onSelect }: { p: TerminalPalette; onSelect: (inst: Instrument) => void }) {
  const rows: ArbRow[] = useMemo(() => topArbitrage(16), [])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', padding: '10px 16px', gap: 12, borderBottom: `1px solid ${p.hairline}`, flexShrink: 0 }}>
        <Eyebrow p={p} style={{ flex: 1 }}>Instrument</Eyebrow>
        <Eyebrow p={p} style={{ width: 130 }}>Best route</Eyebrow>
        <Eyebrow p={p} style={{ width: 86, textAlign: 'right' }}>Net landed</Eyebrow>
        <Eyebrow p={p} style={{ width: 92, textAlign: 'right' }}>Fiscal</Eyebrow>
        <Eyebrow p={p} style={{ width: 84, textAlign: 'right' }}>Net margin</Eyebrow>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {rows.map((r, i) => (
          <motion.button key={r.inst.id} onClick={() => onSelect(r.inst)}
            initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}
            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: `1px solid ${p.hairline}`, background: 'transparent', border: 'none', borderLeft: '2px solid transparent', cursor: 'pointer', textAlign: 'left' }}
            onMouseEnter={e => { e.currentTarget.style.background = p.glass }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
              <BrandLogo inst={r.inst} size={24} p={p} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: p.t1, fontFamily: SANS, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.inst.make} {r.inst.model}</div>
                <span style={{ fontSize: 9, color: p.t4, fontFamily: MONO, whiteSpace: 'nowrap' }}>{r.inst.variant}</span>
              </div>
            </div>
            <div style={{ width: 130 }}><Route p={p} buy={r.buy} sell={r.sell} /></div>
            <span style={{ width: 86, textAlign: 'right', fontFamily: MONO, fontSize: 11, color: p.t3, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(r.nlc)}</span>
            <div style={{ width: 92, display: 'flex', justifyContent: 'flex-end' }}><FiscalBadge p={p} regime={r.fiscal} /></div>
            <div style={{ width: 84 }}><MarginCell p={p} pct={r.marginPct} value={r.margin} /></div>
          </motion.button>
        ))}
      </div>
    </div>
  )
}
