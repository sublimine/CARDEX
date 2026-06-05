/*
 * CARDEX Terminal — supply depth ladder
 * The institutional translation of an order book: live listings stacked by price level.
 * Below the index = the "bid wall" (undervalued supply / buying opportunity); above =
 * the "ask wall" (overpriced inventory). Imbalance reveals seller- vs buyer-market.
 */
import React, { useMemo } from 'react'
import { motion } from 'framer-motion'
import type { TerminalPalette } from './theme'
import { MONO, SANS } from './theme'
import { depthLadder, fmtPrice, fmtCompact, type Instrument } from './market'
import { Eyebrow } from './ui'

export function DepthLadder({ p, inst, market }: { p: TerminalPalette; inst: Instrument; market: string }) {
  const d = useMemo(() => depthLadder(inst, market), [inst, market])
  const maxListings = Math.max(...d.below.map(l => l.listings), ...d.above.map(l => l.listings), 1)
  const sellerMarket = d.imbalance < -0.06
  const buyerMarket = d.imbalance > 0.06

  const Row = ({ price, listings, side }: { price: number; listings: number; side: 'below' | 'above' }) => {
    const col = side === 'below' ? p.up : p.down
    const pct = (listings / maxListings) * 100
    return (
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', height: 22, padding: '0 12px', fontFamily: MONO, fontVariantNumeric: 'tabular-nums', overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          style={{ position: 'absolute', [side === 'below' ? 'left' : 'right']: 0, top: 0, bottom: 0, background: side === 'below' ? p.upDim : p.downDim }} />
        <span style={{ position: 'relative', flex: 1, fontSize: 10.5, color: col, fontWeight: 600 }}>{fmtPrice(price)}</span>
        <span style={{ position: 'relative', fontSize: 10.5, color: p.t2, fontWeight: 600 }}>{fmtCompact(listings)}</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Imbalance summary */}
      <div style={{ padding: '11px 12px 9px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <Eyebrow p={p}>Supply imbalance</Eyebrow>
          <span style={{
            fontSize: 9.5, fontWeight: 700, padding: '2px 7px', borderRadius: 6, fontFamily: SANS,
            color: sellerMarket ? p.up : buyerMarket ? p.down : p.t3,
            background: sellerMarket ? p.upDim : buyerMarket ? p.downDim : p.glass,
          }}>{sellerMarket ? "SELLER'S MARKET" : buyerMarket ? "BUYER'S MARKET" : 'BALANCED'}</span>
        </div>
        {/* dual bar */}
        <div style={{ display: 'flex', height: 7, borderRadius: 99, overflow: 'hidden', background: p.inset }}>
          <div style={{ width: `${(d.totalBelow / (d.totalBelow + d.totalAbove)) * 100}%`, background: p.up }} />
          <div style={{ flex: 1, background: p.down }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5, fontFamily: MONO, fontSize: 9.5 }}>
          <span style={{ color: p.up, fontWeight: 700 }}>{fmtCompact(d.totalBelow)} under</span>
          <span style={{ color: p.down, fontWeight: 700 }}>{fmtCompact(d.totalAbove)} over</span>
        </div>
      </div>

      {/* Column header */}
      <div style={{ display: 'flex', padding: '0 12px 5px', flexShrink: 0 }}>
        <Eyebrow p={p} style={{ flex: 1 }}>Price level</Eyebrow>
        <Eyebrow p={p}>Listings</Eyebrow>
      </div>

      {/* Ladder */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {[...d.above].reverse().map((l, i) => <Row key={`a${i}`} price={l.price} listings={l.listings} side="above" />)}
        {/* Mid (index) */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 30, padding: '0 12px', margin: '3px 0', background: p.accentDim, borderTop: `1px solid ${p.accent}55`, borderBottom: `1px solid ${p.accent}55` }}>
          <span style={{ fontSize: 9.5, fontWeight: 700, color: p.accentText, letterSpacing: '0.08em', fontFamily: SANS }}>CARDEX INDEX</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: p.accentText, fontFamily: MONO, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(d.mid)}</span>
        </div>
        {d.below.map((l, i) => <Row key={`b${i}`} price={l.price} listings={l.listings} side="below" />)}
      </div>
    </div>
  )
}
