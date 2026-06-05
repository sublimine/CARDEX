/*
 * CARDEX Terminal — Decision Desk
 * The product's paid surface: an elite, broker-grade read on the selected instrument. A single
 * verdict (ACQUIRE / ACCUMULATE / WATCH / AVOID) with a confidence dial, a dense-but-organised grid
 * of decision modules (each a KPI card → detail modal on click) and a sentiment-tagged news feed.
 *
 * Two orientations:
 *   - 'dock'  → horizontal, full-width panel BELOW the chart (Revolut/Plus500 style): verdict block
 *               | modules grid | news, side by side.
 *   - 'rail'  → vertical column (legacy / narrow contexts).
 * Dense, minimal, glass, subtle cyan neon. Serves identically for 5 cars or 500,000.
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

function Eyebrow({ p, children }: { p: TerminalPalette; children: React.ReactNode }) {
  return <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: p.t4, fontFamily: SANS }}>{children}</span>
}

function VerdictHero({ p, verdict }: { p: TerminalPalette; verdict: { label: string; tone: string; note: string; conf: number } }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <Ring p={p} value={verdict.conf} color={verdict.tone} size={74} stroke={6}>
        <CountUp value={Math.round(verdict.conf)} suffix="%" style={{ fontFamily: MONO, fontSize: 16.5, fontWeight: 700, color: p.t1, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }} />
        <span style={{ fontSize: 7.5, fontWeight: 700, letterSpacing: '0.1em', color: p.t4, textTransform: 'uppercase', marginTop: 2 }}>conf</span>
      </Ring>
      <div style={{ flex: 1, minWidth: 0 }}>
        <motion.div key={verdict.label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: EASE_ARR }}
          style={{ fontSize: 25, fontWeight: 800, letterSpacing: '-0.02em', color: verdict.tone, fontFamily: SANS, lineHeight: 1, textShadow: `0 0 18px ${verdict.tone}55` }}>{verdict.label}</motion.div>
        <p style={{ fontSize: 11, color: p.t3, lineHeight: 1.45, marginTop: 7, fontFamily: SANS }}>{verdict.note}</p>
      </div>
    </div>
  )
}

export function IntelRail({ p, inst, market, onAddWatch, orientation = 'rail' }: {
  p: TerminalPalette; inst: Instrument; market: string; onAddWatch?: () => void; orientation?: 'rail' | 'dock'
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
  const newsRight = (
    <span style={{ fontSize: 10, fontWeight: 700, fontFamily: MONO, color: sent.score > 0 ? p.up : sent.score < 0 ? p.down : p.t4 }}>{sent.score > 0 ? '+' : ''}{sent.score} · {sent.confidence}%</span>
  )

  // ── DOCK: horizontal, full-width below the chart ────────────────────────────
  if (orientation === 'dock') {
    return (
      <div style={{ display: 'flex', height: '100%', minHeight: 0 }}>
        {/* Verdict + index */}
        <div style={{ width: 244, flexShrink: 0, padding: '12px 14px', borderRight: `1px solid ${p.hairline}`, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Eyebrow p={p}>Decision</Eyebrow>
            <FiscalBadge p={p} regime={inst.fiscal} />
          </div>
          <VerdictHero p={p} verdict={verdict} />
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', borderTop: `1px solid ${p.hairline}`, paddingTop: 10 }}>
            <div>
              <Eyebrow p={p}>Index · {MARKET_BY_CODE[market]?.flag} {market}</Eyebrow>
              <CountUp value={q.last} prefix="€" style={{ display: 'block', fontFamily: MONO, fontSize: 22, fontWeight: 700, color: p.t1, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums', lineHeight: 1.1, marginTop: 3 }} />
            </div>
            <span style={{ fontFamily: MONO, fontSize: 12.5, fontWeight: 700, color: up ? p.up : p.down, fontVariantNumeric: 'tabular-nums' }}>{up ? '+' : ''}{q.changePct.toFixed(2)}%</span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
            <button onClick={onAddWatch} style={actionBtn(p, true)}
              onMouseEnter={e => e.currentTarget.style.background = p.glassHi} onMouseLeave={e => e.currentTarget.style.background = p.glass}>
              <Star style={{ width: 12, height: 12 }} /> Track
            </button>
            <button style={actionBtn(p, false)}><Bell style={{ width: 12, height: 12 }} /> Alert</button>
          </div>
        </div>

        {/* Modules grid */}
        <div style={{ flex: 1, minWidth: 0, padding: '11px 14px', overflowY: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
            <Eyebrow p={p}>Decision modules</Eyebrow>
            <span style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{modules.length} · tap to expand</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(146px, 1fr))', gap: 8 }}>
            {modules.map((m, i) => <IntelModuleCard key={m.id} p={p} m={m} onOpen={setOpen} delay={Math.min(i * 0.03, 0.25)} />)}
          </div>
        </div>

        {/* News */}
        <div style={{ width: 318, flexShrink: 0, padding: '11px 14px', borderLeft: `1px solid ${p.hairline}`, overflowY: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <Eyebrow p={p}>Recent news</Eyebrow>{newsRight}
          </div>
          <NewsFeed p={p} inst={inst} market={market} />
        </div>

        {open && <IntelModal p={p} m={open} onClose={() => setOpen(null)} />}
      </div>
    )
  }

  // ── RAIL: vertical column (legacy / narrow) ─────────────────────────────────
  const Section = ({ label, right, children, delay = 0 }: { label: string; right?: React.ReactNode; children: React.ReactNode; delay?: number }) => (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.3, ease: EASE_ARR }}
      style={{ padding: '12px 14px', borderTop: `1px solid ${p.hairline}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}><Eyebrow p={p}>{label}</Eyebrow>{right}</div>
      {children}
    </motion.div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflowY: 'auto' }}>
      <div style={{ padding: '14px 14px 4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}><Eyebrow p={p}>Decision</Eyebrow><FiscalBadge p={p} regime={inst.fiscal} /></div>
        <VerdictHero p={p} verdict={verdict} />
      </div>
      <Section label="Decision modules" delay={0.09} right={<span style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{modules.length} · tap</span>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 7 }}>
          {modules.map((m, i) => <IntelModuleCard key={m.id} p={p} m={m} onOpen={setOpen} delay={0.1 + Math.min(i * 0.03, 0.3)} />)}
        </div>
      </Section>
      <Section label="Recent news" delay={0.14} right={newsRight}><NewsFeed p={p} inst={inst} market={market} /></Section>
      {open && <IntelModal p={p} m={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function actionBtn(p: TerminalPalette, primary: boolean): React.CSSProperties {
  return {
    flex: 1, padding: '8px 0', borderRadius: 9, cursor: 'pointer',
    background: p.glass, border: `1px solid ${primary ? p.borderHi : p.border}`, color: primary ? p.t1 : p.t2,
    fontSize: 11.5, fontWeight: primary ? 700 : 600, fontFamily: SANS,
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, transition: `background 140ms ${EASE}`,
  }
}
