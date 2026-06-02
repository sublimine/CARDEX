/*
 * CARDEX Terminal — Decision Desk
 * The product's paid surface: an elite, broker-grade read on the selected instrument. A single
 * verdict (ACQUIRE / ACCUMULATE / WATCH / AVOID) with a confidence dial, then a dense-but-organised
 * grid of decision modules (each a KPI card → detail modal on click) and a sentiment-tagged news
 * feed. Dense, minimal, glass, subtle cyan neon. Serves identically for 5 cars or 500,000.
 */
import React, { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Star, Bell } from 'lucide-react'
import type { TerminalPalette } from './theme'
import { MONO, SANS, EASE, EASE_ARR } from './theme'
import { quote, computeSdi, arbitrageRows, MARKET_BY_CODE, type Instrument } from './market'
import { decisionModules, newsSentiment, type IntelModule } from './intelligence'
import { FiscalBadge, Ring, CountUp } from './ui'
import { IntelModuleCard, IntelModal, NewsFeed } from './IntelModules'

function Section({ p, label, right, children, delay = 0 }: { p: TerminalPalette; label: string; right?: React.ReactNode; children: React.ReactNode; delay?: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.3, ease: EASE_ARR }}
      style={{ padding: '12px 14px', borderTop: `1px solid ${p.hairline}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: p.t4, fontFamily: SANS }}>{label}</span>
        {right}
      </div>
      {children}
    </motion.div>
  )
}

export function IntelRail({ p, inst, market, onAddWatch }: {
  p: TerminalPalette; inst: Instrument; market: string; onAddWatch?: () => void
}) {
  const q = useMemo(() => quote(inst, market), [inst, market])
  const sdi = useMemo(() => computeSdi(inst, market), [inst, market])
  const best = useMemo(() => arbitrageRows(inst)[0], [inst])
  const modules = useMemo(() => decisionModules(inst, market), [inst, market])
  const sent = useMemo(() => newsSentiment(inst, market), [inst, market])
  const [open, setOpen] = useState<IntelModule | null>(null)

  const verdict = useMemo(() => {
    const m = best.marginPct, s = sdi.score
    if (m >= 6 && s >= 50) return { label: 'ACQUIRE', tone: p.up, note: 'Wide cross-border edge with seller pressure.', conf: Math.min(96, 60 + m * 4) }
    if (m >= 3) return { label: 'ACCUMULATE', tone: p.up, note: 'Positive net-landed margin after fiscal.', conf: Math.min(85, 50 + m * 5) }
    if (m >= 0) return { label: 'WATCH', tone: p.t2, note: 'Thin edge — wait for a cleaner entry.', conf: 45 }
    return { label: 'AVOID', tone: p.down, note: 'Negative net-landed margin on the best route.', conf: Math.min(90, 55 + Math.abs(m) * 4) }
  }, [best, sdi, p])

  const up = q.changePct >= 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflowY: 'auto' }}>
      {/* Verdict hero — confidence dial + decisive call */}
      <div style={{ padding: '14px 14px 4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: p.t4 }}>Decision</span>
          <FiscalBadge p={p} regime={inst.fiscal} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <Ring p={p} value={verdict.conf} color={verdict.tone} size={74} stroke={6}>
            <CountUp value={Math.round(verdict.conf)} suffix="%" style={{ fontFamily: MONO, fontSize: 16.5, fontWeight: 700, color: p.t1, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }} />
            <span style={{ fontSize: 7.5, fontWeight: 700, letterSpacing: '0.1em', color: p.t4, textTransform: 'uppercase', marginTop: 2 }}>conf</span>
          </Ring>
          <div style={{ flex: 1, minWidth: 0 }}>
            <motion.div key={verdict.label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: EASE_ARR }}
              style={{ fontSize: 25, fontWeight: 800, letterSpacing: '-0.02em', color: verdict.tone, fontFamily: SANS, lineHeight: 1, textShadow: `0 0 18px ${verdict.tone}55` }}>{verdict.label}</motion.div>
            <p style={{ fontSize: 11, color: p.t3, lineHeight: 1.5, marginTop: 7, fontFamily: SANS }}>{verdict.note}</p>
          </div>
        </div>
      </div>

      {/* Index price */}
      <Section p={p} delay={0.04} label="Index" right={<span style={{ fontSize: 10, color: p.t4, fontFamily: MONO }}>{MARKET_BY_CODE[market]?.flag} {market}</span>}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <CountUp value={q.last} prefix="€" style={{ fontFamily: MONO, fontSize: 26, fontWeight: 700, color: p.t1, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }} />
          <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 700, color: up ? p.up : p.down, fontVariantNumeric: 'tabular-nums' }}>{up ? '+' : ''}{q.changePct.toFixed(2)}%</span>
        </div>
      </Section>

      {/* Decision modules — click any card for the full breakdown */}
      <Section p={p} delay={0.09} label="Decision modules" right={<span style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{modules.length} · tap to expand</span>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 7 }}>
          {modules.map((m, i) => <IntelModuleCard key={m.id} p={p} m={m} onOpen={setOpen} delay={0.1 + Math.min(i * 0.03, 0.3)} />)}
        </div>
      </Section>

      {/* News */}
      <Section p={p} delay={0.14} label="Recent news"
        right={<span style={{ fontSize: 10, fontWeight: 700, fontFamily: MONO, color: sent.score > 0 ? p.up : sent.score < 0 ? p.down : p.t4 }}>{sent.score > 0 ? '+' : ''}{sent.score} · {sent.confidence}% conf</span>}>
        <NewsFeed p={p} inst={inst} market={market} />
      </Section>

      {/* Actions */}
      <div style={{ padding: '12px 14px 16px', display: 'flex', gap: 8, marginTop: 'auto' }}>
        <button onClick={onAddWatch} style={{
          flex: 1, padding: '10px 0', borderRadius: 10, border: `1px solid ${p.borderHi}`, cursor: 'pointer',
          background: p.glass, color: p.t1, fontSize: 12, fontWeight: 700, fontFamily: SANS,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, transition: `background 140ms ${EASE}`,
        }}
          onMouseEnter={e => e.currentTarget.style.background = p.glassHi}
          onMouseLeave={e => e.currentTarget.style.background = p.glass}>
          <Star style={{ width: 13, height: 13 }} /> Track
        </button>
        <button style={{
          flex: 1, padding: '10px 0', borderRadius: 10, cursor: 'pointer', background: p.glass,
          border: `1px solid ${p.border}`, color: p.t2, fontSize: 12, fontWeight: 600, fontFamily: SANS,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
        }}>
          <Bell style={{ width: 13, height: 13 }} /> Alert
        </button>
      </div>

      {open && <IntelModal p={p} m={open} onClose={() => setOpen(null)} />}
    </div>
  )
}
