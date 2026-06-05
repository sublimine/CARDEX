/*
 * CARDEX Terminal — live signal tape
 * The institutional ticker: arbitrage windows, price cuts, supply spikes, fiscal
 * reclassifications scrolling continuously. The pulse of the EU used-car market.
 */
import React, { useMemo } from 'react'
import { motion } from 'framer-motion'
import type { TerminalPalette } from './theme'
import { MONO, SANS } from './theme'
import { signalFeed, agoLabel, MARKET_BY_CODE, type Signal, type SignalKind } from './market'

const KIND: Record<SignalKind, { glyph: string; hue: (p: TerminalPalette) => string }> = {
  ARB:    { glyph: '⇄', hue: p => p.up },
  CUT:    { glyph: '▼', hue: p => p.down },
  NEW:    { glyph: '＋', hue: p => p.blue },
  FISCAL: { glyph: '§', hue: p => p.amber },
  SUPPLY: { glyph: '≈', hue: p => p.accentText },
  SOLD:   { glyph: '✓', hue: p => p.t3 },
}

function Chip({ p, s }: { p: TerminalPalette; s: Signal }) {
  const col = KIND[s.kind].hue(p)
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '0 18px', height: '100%', borderRight: `1px solid ${p.hairline}` }}>
      <span style={{ color: col, fontSize: 12, fontWeight: 700, fontFamily: MONO }}>{KIND[s.kind].glyph}</span>
      <span style={{ fontSize: 10.5, color: MARKET_BY_CODE[s.market]?.flag ? p.t2 : p.t2, fontFamily: SANS, fontWeight: 500, whiteSpace: 'nowrap' }}>{s.text}</span>
      {s.value && <span style={{ fontSize: 10.5, fontWeight: 700, color: col, fontFamily: MONO, whiteSpace: 'nowrap' }}>{s.value}</span>}
      <span style={{ fontSize: 9.5, color: p.t4, fontFamily: MONO, whiteSpace: 'nowrap' }}>{agoLabel(s.minsAgo)}</span>
    </div>
  )
}

export function SignalTape({ p }: { p: TerminalPalette }) {
  const signals = useMemo(() => signalFeed(16), [])
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  return (
    <div style={{ display: 'flex', alignItems: 'stretch', height: 32, overflow: 'hidden', flexShrink: 0 }}>
      {/* Live label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '0 14px', flexShrink: 0, borderRight: `1px solid ${p.border}`, background: p.dark ? 'rgba(139,92,246,0.10)' : 'rgba(124,58,237,0.06)' }}>
        <motion.span style={{ width: 6, height: 6, borderRadius: '50%', background: p.up, boxShadow: `0 0 7px ${p.up}` }}
          animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.5, repeat: Infinity }} />
        <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.12em', color: p.accentText, fontFamily: SANS }}>SIGNAL TAPE</span>
      </div>
      {/* Marquee */}
      <div style={{ position: 'relative', flex: 1, overflow: 'hidden' }}>
        <motion.div
          style={{ display: 'flex', alignItems: 'center', height: '100%', position: 'absolute', whiteSpace: 'nowrap', willChange: 'transform' }}
          animate={reduced ? undefined : { x: ['0%', '-50%'] }}
          transition={reduced ? undefined : { duration: 64, ease: 'linear', repeat: Infinity }}>
          {[...signals, ...signals].map((s, i) => <Chip key={`${s.id}_${i}`} p={p} s={s} />)}
        </motion.div>
        {/* edge fades */}
        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 32, background: `linear-gradient(90deg, ${p.rail}, transparent)`, pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: 32, background: `linear-gradient(270deg, ${p.rail}, transparent)`, pointerEvents: 'none' }} />
      </div>
    </div>
  )
}
