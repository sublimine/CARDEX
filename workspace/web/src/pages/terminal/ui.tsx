/*
 * CARDEX Terminal — shared primitives
 * GlassPanel composes the full 6-layer liquid glass (same as glass.tsx LiquidGlass) so EVERY
 * surface in Terminal.tsx reads as real glass — this was the missing link (Terminal used a
 * thin GlassPanel, not LiquidGlass). Plus a 5-level type scale and cockpit-dense helpers.
 * All primitives take the resolved palette `p` (page owns one useTheme()).
 */
import React, { useEffect } from 'react'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'
import type { TerminalPalette } from './theme'
import { MONO, SANS, EASE, getBlur } from './theme'
import { GlassLayers, useSheen } from './glass'
import type { Instrument } from './market'

// ── Glass panel (full liquid stack) ───────────────────────────────────────────
export function panelStyle(p: TerminalPalette, elevated = false): React.CSSProperties {
  return {
    background: elevated ? p.panelHi : p.panel,
    backdropFilter: getBlur(p), WebkitBackdropFilter: getBlur(p),
    border: `1px solid ${p.border}`, boxShadow: elevated ? p.shadowLg : p.shadow,
  }
}

interface GlassPanelProps {
  p: TerminalPalette
  children: React.ReactNode
  style?: React.CSSProperties
  radius?: number
  elevated?: boolean
  interactive?: boolean
  /** Inner-edge accent glow (liquid-mirror depth). Default on; chart panels opt out. */
  glow?: boolean
  className?: string
}
export function GlassPanel({ p, children, style, radius = 16, elevated, interactive, glow = true, className }: GlassPanelProps) {
  const sheen = useSheen(p)
  return (
    <div
      className={className}
      {...(interactive ? sheen.handlers : {})}
      style={{
        position: 'relative', borderRadius: radius, overflow: 'hidden',
        background: elevated ? p.panelHi : p.panel,
        backdropFilter: getBlur(p), WebkitBackdropFilter: getBlur(p),
        border: `1px solid ${p.border}`, boxShadow: elevated ? p.shadowLg : p.shadow,
        ...style,
      }}
    >
      <GlassLayers p={p} radius={radius} glow={glow} noise />
      {interactive && (
        <motion.div aria-hidden style={{
          position: 'absolute', inset: 0, borderRadius: radius, pointerEvents: 'none', zIndex: 2,
          background: sheen.bg, opacity: sheen.op, mixBlendMode: 'soft-light',
        }} />
      )}
      <div style={{ position: 'relative', zIndex: 3, height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {children}
      </div>
    </div>
  )
}

// ── 5-level type scale ────────────────────────────────────────────────────────
export function Title({ p, children, style }: { p: TerminalPalette; children: React.ReactNode; style?: React.CSSProperties }) {
  return <span style={{ fontSize: 13.5, fontWeight: 800, letterSpacing: '-0.01em', lineHeight: 1.2, color: p.t1, fontFamily: SANS, ...style }}>{children}</span>
}
export function Subtitle({ p, children, style }: { p: TerminalPalette; children: React.ReactNode; style?: React.CSSProperties }) {
  return <span style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.2, color: p.t2, fontFamily: SANS, ...style }}>{children}</span>
}
export function Label({ p, children, style }: { p: TerminalPalette; children: React.ReactNode; style?: React.CSSProperties }) {
  return <span style={{ fontSize: 11, fontWeight: 600, color: p.t3, fontFamily: SANS, ...style }}>{children}</span>
}
export function Eyebrow({ p, children, style }: { p: TerminalPalette; children: React.ReactNode; style?: React.CSSProperties }) {
  return <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.13em', textTransform: 'uppercase', color: p.t4, fontFamily: SANS, ...style }}>{children}</span>
}
export function Mono({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <span style={{ fontFamily: MONO, fontVariantNumeric: 'tabular-nums', ...style }}>{children}</span>
}

export function PanelTitle({ p, label, sub, right, style }: {
  p: TerminalPalette; label: string; sub?: string; right?: React.ReactNode; style?: React.CSSProperties
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '9px 13px', borderBottom: `1px solid ${p.hairline}`, flexShrink: 0, ...style,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <Title p={p}>{label}</Title>
        {sub && <Eyebrow p={p} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</Eyebrow>}
      </div>
      {right}
    </div>
  )
}

// ── Delta tag ───────────────────────────────────────────────────────────────
export function DeltaTag({ p, value, size = 'sm', solid = false }: {
  p: TerminalPalette; value: number; size?: 'xs' | 'sm' | 'md'; solid?: boolean
}) {
  const up = value >= 0
  const fs = size === 'md' ? 12 : size === 'sm' ? 10.5 : 9.5
  const col = up ? p.up : p.down
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 2, fontFamily: MONO, fontVariantNumeric: 'tabular-nums',
      fontSize: fs, fontWeight: 700, color: solid ? '#fff' : col, background: solid ? col : (up ? p.upDim : p.downDim),
      padding: solid ? '2px 7px' : '1px 6px', borderRadius: 6, lineHeight: 1.4,
    }}>
      {up ? '▲' : '▼'} {Math.abs(value).toFixed(2)}%
    </span>
  )
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
export function Spark({ values, p, w = 64, h = 22, up }: { values: number[]; p: TerminalPalette; w?: number; h?: number; up?: boolean }) {
  if (!values.length) return <svg width={w} height={h} />
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1
  const isUp = up ?? values.at(-1)! >= values[0]
  const col = isUp ? p.up : p.down
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (w - 2) + 1, h - 2 - ((v - min) / span) * (h - 4)])
  const d = `M ${pts.map(pt => `${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' L ')}`
  const area = `${d} L ${w - 1},${h} L 1,${h} Z`
  const gid = `sg_${Math.round(values[0])}_${values.length}_${isUp ? 'u' : 'd'}`
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={col} stopOpacity={0.28} />
          <stop offset="100%" stopColor={col} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={col} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

// ── Brand logo (real simpleicons + graceful fallback) ─────────────────────────
export function BrandLogo({ inst, size = 22, p }: { inst: Instrument; size?: number; p: TerminalPalette }) {
  const [failed, setFailed] = React.useState(false)
  const initials = inst.make.replace(/[^A-Za-z]/g, '').slice(0, 2).toUpperCase()
  if (failed || !inst.logo) {
    return (
      <div style={{
        width: size, height: size, borderRadius: size * 0.28, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: `${inst.color}22`, border: `1px solid ${inst.color}55`,
        color: inst.color, fontSize: size * 0.4, fontWeight: 800, fontFamily: SANS,
      }}>{initials}</div>
    )
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: size * 0.28, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: p.dark ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.05)',
      border: `1px solid ${p.border}`, overflow: 'hidden',
    }}>
      <img src={inst.logo} alt={inst.make} width={size * 0.62} height={size * 0.62}
        style={{ objectFit: 'contain', filter: p.dark ? 'none' : 'invert(1) brightness(0.35)' }}
        onError={() => setFailed(true)} />
    </div>
  )
}

// ── Pills / badges ──────────────────────────────────────────────────────────
export function Pill({ p, children, tone = 'neutral' }: {
  p: TerminalPalette; children: React.ReactNode; tone?: 'neutral' | 'accent' | 'up' | 'down' | 'blue' | 'amber'
}) {
  const map = {
    neutral: { c: p.t3, bg: p.glass, b: p.border },
    accent: { c: p.accentText, bg: p.accentDim, b: 'transparent' },
    up: { c: p.up, bg: p.upDim, b: 'transparent' },
    down: { c: p.down, bg: p.downDim, b: 'transparent' },
    blue: { c: p.blue, bg: p.dark ? 'rgba(96,165,250,0.14)' : 'rgba(37,99,235,0.10)', b: 'transparent' },
    amber: { c: p.amber, bg: p.dark ? 'rgba(251,191,36,0.14)' : 'rgba(217,119,6,0.10)', b: 'transparent' },
  }[tone]
  return (
    <span style={{
      fontSize: 9.5, fontWeight: 700, letterSpacing: '0.02em', color: map.c, background: map.bg,
      border: `1px solid ${map.b}`, padding: '2px 7px', borderRadius: 6, fontFamily: SANS, whiteSpace: 'nowrap',
    }}>{children}</span>
  )
}

export function FiscalBadge({ p, regime }: { p: TerminalPalette; regime: string }) {
  const rebu = regime === 'REBU'
  return (
    <span title={rebu ? 'Régimen Especial de Bienes Usados — margin scheme' : 'Reverse-charge intra-EU, VAT deductible'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em',
        fontFamily: MONO, color: rebu ? p.amber : p.teal,
        background: rebu ? (p.dark ? 'rgba(251,191,36,0.12)' : 'rgba(217,119,6,0.10)') : (p.dark ? 'rgba(45,212,191,0.12)' : 'rgba(13,148,136,0.10)'),
        border: `1px solid ${rebu ? p.amber : p.teal}33`, padding: '2px 7px', borderRadius: 6,
      }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: rebu ? p.amber : p.teal }} />
      {rebu ? 'REBU' : 'VAT-DED'}
    </span>
  )
}

// ── Proportion bar ────────────────────────────────────────────────────────────
export function Bar({ p, value, max, color, height = 6 }: { p: TerminalPalette; value: number; max: number; color: string; height?: number }) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100))
  return (
    <div style={{ width: '100%', height, borderRadius: 99, background: p.inset, overflow: 'hidden' }}>
      <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        style={{ height: '100%', borderRadius: 99, background: color, boxShadow: `0 0 8px ${color}66` }} />
    </div>
  )
}

// ── Radial progress ring (cockpit dial) ──────────────────────────────────────
export function Ring({ p, value, color, size = 76, stroke = 7, children }: {
  p: TerminalPalette; value: number; color: string; size?: number; stroke?: number; children?: React.ReactNode
}) {
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const v = Math.max(0, Math.min(100, value))
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={p.inset} strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ * (1 - v / 100) }}
          transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
          style={{ filter: `drop-shadow(0 0 5px ${color}55)` }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>{children}</div>
    </div>
  )
}

// ── Animated count-up number (motion-value driven, no per-frame re-render) ─────
export function CountUp({ value, decimals = 0, prefix = '', suffix = '', style }: {
  value: number; decimals?: number; prefix?: string; suffix?: string; style?: React.CSSProperties
}) {
  const mv = useMotionValue(0)
  const text = useTransform(mv, (n) =>
    `${prefix}${n.toLocaleString('de-DE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`)
  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.7, ease: [0.22, 1, 0.36, 1] })
    return () => controls.stop()
  }, [value, mv])
  return <motion.span style={style}>{text}</motion.span>
}

// ── SDI semicircle gauge ────────────────────────────────────────────────────
export function Gauge({ p, value, color, size = 132, label, band }: {
  p: TerminalPalette; value: number; color: string; size?: number; label?: string; band?: string
}) {
  const r = size / 2 - 12
  const cx = size / 2, cy = size / 2
  const startA = Math.PI, endA = 0
  const valA = startA + (value / 100) * (endA - startA)
  const arc = (a0: number, a1: number) =>
    `M ${cx + r * Math.cos(a0)} ${cy + r * Math.sin(a0)} A ${r} ${r} 0 ${a1 - a0 < -Math.PI ? 1 : 0} 1 ${cx + r * Math.cos(a1)} ${cy + r * Math.sin(a1)}`
  return (
    <div style={{ position: 'relative', width: size, height: size / 2 + 22 }}>
      <svg width={size} height={size / 2 + 22}>
        <path d={arc(startA, endA)} fill="none" stroke={p.inset} strokeWidth={9} strokeLinecap="round" />
        <motion.path d={arc(startA, valA)} fill="none" stroke={color} strokeWidth={9} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color}88)` }}
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, top: 18, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: p.t1, letterSpacing: '-0.02em', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
        {band && <span style={{ fontSize: 10, fontWeight: 700, color, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 4 }}>{band}</span>}
        {label && <Eyebrow p={p} style={{ marginTop: 2 }}>{label}</Eyebrow>}
      </div>
    </div>
  )
}

// ── Icon button ───────────────────────────────────────────────────────────────
export function IconButton({ p, active, onClick, title, children, size = 30 }: {
  p: TerminalPalette; active?: boolean; onClick?: () => void; title?: string; children: React.ReactNode; size?: number
}) {
  return (
    <button onClick={onClick} title={title} style={{
      width: size, height: size, borderRadius: 8, cursor: 'pointer', flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: active ? p.accentDim : p.glass, border: `1px solid ${active ? p.accent + '66' : p.border}`,
      color: active ? p.accentText : p.t3, transition: `all 140ms ${EASE}`,
    }}
      onMouseEnter={e => { if (!active) { e.currentTarget.style.background = p.glassHi; e.currentTarget.style.color = p.t1 } }}
      onMouseLeave={e => { if (!active) { e.currentTarget.style.background = p.glass; e.currentTarget.style.color = p.t3 } }}
    >{children}</button>
  )
}

// ── Segmented control ───────────────────────────────────────────────────────
export function Segmented<T extends string>({ p, options, value, onChange, size = 'sm' }: {
  p: TerminalPalette; options: { id: T; label: React.ReactNode; title?: string }[]; value: T; onChange: (v: T) => void; size?: 'xs' | 'sm'
}) {
  const padY = size === 'xs' ? 3 : 4
  const fs = size === 'xs' ? 9.5 : 10.5
  return (
    <div style={{ display: 'flex', gap: 2, padding: 2, background: p.inset, borderRadius: 9, border: `1px solid ${p.border}` }}>
      {options.map(o => {
        const on = o.id === value
        return (
          <button key={o.id} onClick={() => onChange(o.id)} title={o.title}
            style={{ position: 'relative', padding: `${padY}px 9px`, borderRadius: 7, cursor: 'pointer', border: 'none',
              background: 'transparent', color: on ? p.accentText : p.t4, fontSize: fs, fontWeight: 700, fontFamily: SANS, letterSpacing: '0.02em', transition: `color 160ms ${EASE}` }}>
            {on && <motion.span layoutId={`seg_${options.map(x => x.id).join('')}`}
              style={{ position: 'absolute', inset: 0, borderRadius: 7, background: p.accentDim, border: `1px solid ${p.accent}55`, zIndex: 0 }}
              transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
            <span style={{ position: 'relative', zIndex: 1 }}>{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── Stat cell ───────────────────────────────────────────────────────────────
export function Stat({ p, label, value, accent, mono = true }: {
  p: TerminalPalette; label: string; value: React.ReactNode; accent?: string; mono?: boolean
}) {
  return (
    <div style={{ padding: '8px 10px', background: p.glass, border: `1px solid ${p.border}`, borderRadius: 10 }}>
      <Eyebrow p={p} style={{ display: 'block', marginBottom: 4 }}>{label}</Eyebrow>
      <div style={{ fontFamily: mono ? MONO : SANS, fontVariantNumeric: 'tabular-nums', fontSize: 13, fontWeight: 700, color: accent ?? p.t1, letterSpacing: '-0.01em' }}>{value}</div>
    </div>
  )
}
