/*
 * CARDEX Terminal — Decision Desk widgets
 * The visible intelligence surface: compact KPI module cards (label + value + gauge/delta) that
 * open a detail modal on click, plus a sentiment-tagged news feed. Dense-but-organised, glass,
 * subtle cyan neon — audited against Plus500 +Insights / eToro / TradingView / Bloomberg.
 */
import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import type { TerminalPalette } from './theme'
import { MONO, SANS, EASE_ARR, getBlurLg } from './theme'
import type { IntelModule, Tone } from './intelligence'
import { carNews } from './intelligence'
import { agoLabel, type Instrument } from './market'
import { Ring } from './ui'

const toneColor = (p: TerminalPalette, t: Tone): string =>
  t === 'up' ? p.up : t === 'down' ? p.down : t === 'accent' ? p.accent : p.t2
// Detail values read as primary text unless they carry a decision tone.
const valueColor = (p: TerminalPalette, t?: Tone): string =>
  t && t !== 'neutral' ? toneColor(p, t) : p.t1
const sentColor = (p: TerminalPalette, s: 'pos' | 'neg' | 'neu'): string =>
  s === 'pos' ? p.up : s === 'neg' ? p.down : p.t4

// ── KPI module card (click → modal) ───────────────────────────────────────────
export function IntelModuleCard({ p, m, onOpen, delay = 0 }: {
  p: TerminalPalette; m: IntelModule; onOpen: (m: IntelModule) => void; delay?: number
}) {
  const c = toneColor(p, m.tone)
  return (
    <motion.button onClick={() => onOpen(m)} title={`${m.label} — details`}
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.3, ease: EASE_ARR }}
      style={{
        position: 'relative', display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 10px', borderRadius: 10,
        cursor: 'pointer', textAlign: 'left', background: p.glass, border: `1px solid ${p.border}`, minHeight: 60,
        transition: 'border-color 140ms ease, background 140ms ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = p.glassHi; e.currentTarget.style.borderColor = p.borderHi }}
      onMouseLeave={e => { e.currentTarget.style.background = p.glass; e.currentTarget.style.borderColor = p.border }}>
      <span style={{ fontSize: 8.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: p.t4, fontFamily: SANS, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {m.gauge != null && <Ring p={p} value={m.gauge} color={c} size={28} stroke={3.5} />}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontFamily: MONO, fontSize: 14.5, fontWeight: 700, color: c, letterSpacing: '-0.01em', fontVariantNumeric: 'tabular-nums', lineHeight: 1.05, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.value}</div>
          {m.sub && <div style={{ fontSize: 8.5, color: p.t4, fontFamily: SANS, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 1 }}>{m.sub}</div>}
        </div>
      </div>
      {m.delta && <span style={{ fontSize: 9, fontWeight: 700, color: toneColor(p, m.delta.tone), fontFamily: MONO, fontVariantNumeric: 'tabular-nums' }}>{m.delta.text}</span>}
    </motion.button>
  )
}

// ── Detail modal (portal to body) ─────────────────────────────────────────────
export function IntelModal({ p, m, onClose }: { p: TerminalPalette; m: IntelModule; onClose: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  const c = toneColor(p, m.tone)
  return createPortal(
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)' }}>
      <motion.div onClick={e => e.stopPropagation()}
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97 }}
        transition={{ duration: 0.2, ease: EASE_ARR }}
        style={{ width: 360, maxWidth: '92vw', maxHeight: '82vh', overflowY: 'auto', borderRadius: 16, background: p.panelHi, backdropFilter: getBlurLg(p), WebkitBackdropFilter: getBlurLg(p), border: `1px solid ${p.borderHi}`, boxShadow: p.shadowLg }}>
        <div style={{ padding: '14px 16px 12px', borderBottom: `1px solid ${p.hairline}`, position: 'relative' }}>
          <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: p.t4, fontFamily: SANS }}>{m.label}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginTop: 7 }}>
            {m.gauge != null && (
              <Ring p={p} value={m.gauge} color={c} size={46} stroke={4}>
                <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 700, color: p.t1, fontVariantNumeric: 'tabular-nums' }}>{m.gauge}</span>
              </Ring>
            )}
            <div style={{ fontFamily: MONO, fontSize: 25, fontWeight: 700, color: c, letterSpacing: '-0.02em', lineHeight: 1 }}>{m.value}</div>
          </div>
          <p style={{ fontSize: 11, color: p.t3, lineHeight: 1.55, marginTop: 10, fontFamily: SANS }}>{m.why}</p>
          <button onClick={onClose} title="Close"
            style={{ position: 'absolute', top: 12, right: 12, width: 24, height: 24, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', background: p.glass, border: `1px solid ${p.border}`, color: p.t3, cursor: 'pointer' }}>
            <X style={{ width: 13, height: 13 }} />
          </button>
        </div>
        <div style={{ padding: '6px 16px 16px' }}>
          {m.detail.map((d, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '8px 0', borderBottom: i < m.detail.length - 1 ? `1px solid ${p.hairline}` : 'none' }}>
              <span style={{ fontSize: 11, color: p.t3, fontFamily: SANS }}>{d.label}</span>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: valueColor(p, d.tone), fontFamily: MONO, fontVariantNumeric: 'tabular-nums', textAlign: 'right' }}>{d.value}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>,
    document.body,
  )
}

// ── News feed (sentiment-tagged) ──────────────────────────────────────────────
export function NewsFeed({ p, inst, market }: { p: TerminalPalette; inst: Instrument; market: string }) {
  const news = carNews(inst, market, 6)
  return (
    <div>
      {news.map((n, i) => (
        <motion.div key={n.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.05, 0.3), duration: 0.3, ease: EASE_ARR }}
          style={{ display: 'flex', gap: 9, padding: '8px 0', borderBottom: i < news.length - 1 ? `1px solid ${p.hairline}` : 'none' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: sentColor(p, n.sentiment), flexShrink: 0, marginTop: 4 }} title={n.sentiment} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, color: p.t2, lineHeight: 1.4, fontFamily: SANS }}>{n.headline}</div>
            <div style={{ fontSize: 8.5, color: p.t4, fontFamily: MONO, marginTop: 3, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span>{n.source}</span><span>·</span><span>{agoLabel(n.ageMin)}</span>
              <span style={{ color: sentColor(p, n.sentiment) }}>· {n.tag}</span>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  )
}
