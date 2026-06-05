/*
 * CARDEX Terminal — liquid glass material (6-layer)
 * Real liquid glass for web: a translucent surface the cx-* mesh transmits through, layered
 * with (1) backdrop blur+saturate+brightness, (2) refraction border with a violet mesh tint
 * on the flanks, (3) specular top highlight, (4) inner accent glow, (5) interactive pointer
 * sheen (framer-motion motion-values, no re-render), (6) fine noise to kill banding. Double
 * bezel for hero panels. ui.tsx GlassPanel composes the same layers so EVERY surface is glass.
 */
import React from 'react'
import { motion, useMotionValue, useMotionTemplate } from 'framer-motion'
import type { TerminalPalette } from './theme'
import { getBlur, getBlurLg, CHIP_BLUR, EASE } from './theme'

// Fine grain (anti-banding) — fractalNoise data-uri, blended over the surface
const NOISE_URL =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"

/** SVG refraction filter — mount once near the root. Available as `backdrop-filter: url(#cx-refraction)`
 *  for opt-in micro-surfaces; large panels rely on the cheaper 6-layer recipe to stay at 60fps. */
export function GlassFilterDefs() {
  return (
    <svg aria-hidden width="0" height="0" style={{ position: 'absolute', pointerEvents: 'none' }}>
      <defs>
        <filter id="cx-refraction" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012 0.012" numOctaves={2} seed={7} result="t" />
          <feDisplacementMap in="SourceGraphic" in2="t" scale={10} xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  )
}

// ── Static glass decoration layers ────────────────────────────────────────────
export function GlassLayers({ p, radius, glow = true, noise = true }: {
  p: TerminalPalette; radius: number; glow?: boolean; noise?: boolean
}) {
  return (
    <>
      {/* (2) refraction border — masked 1px gradient, white speculars + violet mesh tint on flanks */}
      <div aria-hidden style={{
        position: 'absolute', inset: 0, borderRadius: radius, padding: 1, pointerEvents: 'none', zIndex: 1,
        background: `linear-gradient(145deg, ${p.refractA} 0%, ${p.refractTint} 20%, ${p.refractB} 44%, transparent 60%, ${p.refractTint} 86%, ${p.refractB} 100%)`,
        WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
        WebkitMaskComposite: 'xor', maskComposite: 'exclude',
      }} />
      {/* (3) specular top highlight */}
      <div aria-hidden style={{
        position: 'absolute', left: 0, right: 0, top: 0, height: '48%', borderRadius: `${radius}px ${radius}px 0 0`,
        pointerEvents: 'none', zIndex: 1,
        background: `radial-gradient(120% 100% at 50% 0%, ${p.topHighlight} 0%, transparent 62%)`, opacity: 0.7,
      }} />
      {/* (4) inner accent glow */}
      {glow && (
        <div aria-hidden style={{
          position: 'absolute', inset: 0, borderRadius: radius, pointerEvents: 'none', zIndex: 0,
          boxShadow: `inset 0 0 52px ${p.glow}`,
        }} />
      )}
      {/* (6) noise / grain */}
      {noise && (
        <div aria-hidden style={{
          position: 'absolute', inset: 0, borderRadius: radius, pointerEvents: 'none', zIndex: 2,
          backgroundImage: NOISE_URL, opacity: p.noiseOpacity, mixBlendMode: 'overlay',
        }} />
      )}
    </>
  )
}

// ── (5) Pointer-following sheen (motion-value driven, zero re-render) ──────────
export function useSheen(p: TerminalPalette) {
  const mx = useMotionValue(-400)
  const my = useMotionValue(-400)
  const op = useMotionValue(0)
  const bg = useMotionTemplate`radial-gradient(240px circle at ${mx}px ${my}px, ${p.sheen}, transparent 60%)`
  const handlers = {
    onMouseMove: (e: React.MouseEvent<HTMLElement>) => {
      const r = e.currentTarget.getBoundingClientRect()
      mx.set(e.clientX - r.left); my.set(e.clientY - r.top)
    },
    onMouseEnter: () => op.set(1),
    onMouseLeave: () => op.set(0),
  }
  return { bg, op, handlers }
}

interface LiquidGlassProps {
  p: TerminalPalette
  children: React.ReactNode
  radius?: number
  elevated?: boolean
  interactive?: boolean
  glow?: boolean
  noise?: boolean
  bezel?: boolean
  style?: React.CSSProperties
  className?: string
  onClick?: () => void
}

export function LiquidGlass({
  p, children, radius = 16, elevated, interactive, glow = true, noise = true, bezel, style, className, onClick,
}: LiquidGlassProps) {
  const sheen = useSheen(p)
  const surface = (
    <div
      className={className}
      onClick={onClick}
      {...(interactive ? sheen.handlers : {})}
      style={{
        position: 'relative', borderRadius: radius, overflow: 'hidden',
        background: elevated ? p.panelHi : p.panel,
        backdropFilter: getBlur(p), WebkitBackdropFilter: getBlur(p),
        border: `1px solid ${p.border}`, boxShadow: elevated ? p.shadowLg : p.shadow,
        ...style,
      }}
    >
      <GlassLayers p={p} radius={radius} glow={glow} noise={noise} />
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
  if (!bezel) return surface
  return (
    <div style={{
      position: 'relative', borderRadius: radius + 4, padding: 3,
      background: p.dark ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.04)',
      boxShadow: `0 0 0 1px ${p.border}, ${elevated ? p.shadowLg : p.shadow}`, ...style,
    }}>
      <div style={{ borderRadius: radius, overflow: 'hidden', height: '100%' }}>{surface}</div>
    </div>
  )
}

// ── Glass button — tactile, optional sheen ────────────────────────────────────
export function GlassButton({
  p, children, active, onClick, title, sheen = true, tone = 'glass', radius = 9, style,
}: {
  p: TerminalPalette; children: React.ReactNode; active?: boolean; onClick?: () => void
  title?: string; sheen?: boolean; tone?: 'glass' | 'accent'; radius?: number; style?: React.CSSProperties
}) {
  const s = useSheen(p)
  const accent = tone === 'accent' || active
  return (
    <motion.button
      onClick={onClick} title={title} whileTap={{ scale: 0.97 }}
      {...(sheen ? s.handlers : {})}
      style={{
        position: 'relative', overflow: 'hidden', cursor: 'pointer', borderRadius: radius,
        border: `1px solid ${accent ? p.accent + '66' : p.border}`,
        background: accent ? p.accentDim : p.glass, color: accent ? p.accentText : p.t2,
        backdropFilter: CHIP_BLUR, WebkitBackdropFilter: CHIP_BLUR,
        transition: `border-color 160ms ${EASE}, color 160ms ${EASE}, background 160ms ${EASE}`, ...style,
      }}
      onMouseEnter={e => { if (!accent) { e.currentTarget.style.background = p.glassHi; e.currentTarget.style.color = p.t1 } }}
      onMouseLeave={e => { if (!accent) { e.currentTarget.style.background = p.glass; e.currentTarget.style.color = p.t2 } }}
    >
      {sheen && <motion.span aria-hidden style={{ position: 'absolute', inset: 0, borderRadius: radius, pointerEvents: 'none', background: s.bg, opacity: s.op }} />}
      <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 6 }}>{children}</span>
    </motion.button>
  )
}

// ── Floating glass dropdown surface ───────────────────────────────────────────
export function GlassMenu({ p, children, style }: { p: TerminalPalette; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      position: 'relative', borderRadius: 14, overflow: 'hidden', background: p.panelHi,
      backdropFilter: getBlurLg(p), WebkitBackdropFilter: getBlurLg(p),
      border: `1px solid ${p.borderHi}`, boxShadow: p.shadowLg, ...style,
    }}>
      <GlassLayers p={p} radius={14} glow={false} noise />
      <div style={{ position: 'relative', zIndex: 3 }}>{children}</div>
    </div>
  )
}
