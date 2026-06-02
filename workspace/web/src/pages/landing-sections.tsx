import React, { useEffect, useRef, useState } from 'react'
import {
  motion, useInView, useScroll, useTransform, useMotionTemplate, useMotionValueEvent,
  animate, useReducedMotion, useMotionValue, useSpring, type Variants,
} from 'framer-motion'
import { BRANDS } from '../data/catalog'
import LOGO_AR from '../data/logo-ar.json'

/* ─── tokens ─────────────────────────────────────────────────────────────── */
const EXPO = [0.16, 1, 0.3, 1] as const
const T1 = '#f8fafc', T2 = '#cbd5e1', T3 = '#94a3b8', T4 = '#64748b'
const HAIR = 'rgba(255,255,255,0.07)', HAIR_HI = 'rgba(255,255,255,0.12)', TICK = 'rgba(255,255,255,0.3)'
const INDIGO = '#6366f1', INDIGO_SOFT = '#a5b4fc', EMERALD = '#34d399', ROSE = '#fb7185'
const MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', monospace"
const fmt = (n: number) => Math.round(n).toLocaleString('de-DE')

const eyebrow: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'rgba(196,181,253,0.85)', margin: 0 }
const lead: React.CSSProperties = { fontSize: 'clamp(1.02rem,0.96rem+0.4vw,1.2rem)', lineHeight: 1.6, color: T2, maxWidth: '50ch', margin: 0 }
const h2: React.CSSProperties = { fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.04, fontWeight: 700, letterSpacing: '-0.035em', color: T1, margin: 0 }
const mono: React.CSSProperties = { fontFamily: MONO, fontVariantNumeric: 'tabular-nums' }
const coordLabel: React.CSSProperties = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: T4 }

/* ─── motion primitives ──────────────────────────────────────────────────── */
function Reveal({ children, y = 26, delay = 0, style }: { children: React.ReactNode; y?: number; delay?: number; style?: React.CSSProperties }) {
  const r = useReducedMotion()
  return <motion.div style={style} initial={r ? { opacity: 1 } : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-10% 0px', amount: 0.2 }} transition={{ duration: 0.75, ease: EXPO, delay }}>{children}</motion.div>
}
function Kinetic({ lines, style, delay = 0 }: { lines: React.ReactNode[]; style?: React.CSSProperties; delay?: number }) {
  const r = useReducedMotion()
  return (
    <div style={style}>
      {lines.map((ln, i) => (
        <div key={i} style={{ overflow: 'hidden', paddingBottom: '0.04em' }}>
          <motion.div initial={r ? { y: 0 } : { y: '115%' }} whileInView={{ y: '0%' }} viewport={{ once: true, margin: '-12% 0px' }} transition={{ duration: 0.85, ease: EXPO, delay: delay + i * 0.09 }}>{ln}</motion.div>
        </div>
      ))}
    </div>
  )
}
const parentV: Variants = { hidden: {}, visible: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } } }
const childV: Variants = { hidden: { opacity: 0, y: 18 }, visible: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EXPO } } }
function Stagger({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <motion.div style={style} variants={parentV} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-8% 0px', amount: 0.12 }}>{children}</motion.div>
}
function Counter({ to, suffix = '', prefix = '', duration = 1.6 }: { to: number; suffix?: string; prefix?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const [v, setV] = useState(0)
  const r = useReducedMotion()
  useEffect(() => { if (!inView) return; if (r) { setV(to); return } const c = animate(0, to, { duration, ease: EXPO, onUpdate: setV }); return () => c.stop() }, [inView, to, r, duration])
  return <span ref={ref}>{prefix}{fmt(v)}{suffix}</span>
}
function Marquee({ children, duration = 34, vertical = false, height }: { children: React.ReactNode; duration?: number; vertical?: boolean; height?: number }) {
  if (vertical) {
    return (
      <div style={{ overflow: 'hidden', height, WebkitMaskImage: 'linear-gradient(180deg,transparent,#000 12%,#000 88%,transparent)', maskImage: 'linear-gradient(180deg,transparent,#000 12%,#000 88%,transparent)' }}>
        <motion.div style={{ willChange: 'transform' }} animate={{ y: ['0%', '-50%'] }} transition={{ duration, ease: 'linear', repeat: Infinity }}>{children}{children}</motion.div>
      </div>
    )
  }
  return (
    <div style={{ overflow: 'hidden', WebkitMaskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)', maskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)' }}>
      <motion.div style={{ display: 'flex', alignItems: 'center', gap: 44, width: 'max-content', willChange: 'transform' }} animate={{ x: ['0%', '-50%'] }} transition={{ duration, ease: 'linear', repeat: Infinity }}>{children}{children}</motion.div>
    </div>
  )
}
function Magnetic({ children, strength = 0.35 }: { children: React.ReactNode; strength?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const x = useMotionValue(0), y = useMotionValue(0)
  const sx = useSpring(x, { stiffness: 280, damping: 18 }), sy = useSpring(y, { stiffness: 280, damping: 18 })
  return <motion.div ref={ref} style={{ x: sx, y: sy, display: 'inline-block' }} onMouseMove={e => { const r = ref.current!.getBoundingClientRect(); x.set((e.clientX - r.left - r.width / 2) * strength); y.set((e.clientY - r.top - r.height / 2) * strength) }} onMouseLeave={() => { x.set(0); y.set(0) }}>{children}</motion.div>
}
function Glow({ x = '50%', y = '50%', size = 520, color = 'rgba(99,102,241,0.14)' }: { x?: string; y?: string; size?: number; color?: string }) {
  return <motion.div aria-hidden style={{ position: 'absolute', left: x, top: y, width: size, height: size, marginLeft: -size / 2, marginTop: -size / 2, borderRadius: '50%', background: `radial-gradient(closest-side, ${color}, transparent)`, filter: 'blur(30px)', pointerEvents: 'none' }} animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 11, ease: 'easeInOut', repeat: Infinity }} />
}
/** Scroll-driven 3D emergence — transform/opacity/filter only, will-change cleared on settle. */
function Emerge({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress: p } = useScroll({ target: ref, offset: ['start end', 'center center'] })
  const scale = useTransform(p, [0, 1], [0.93, 1])
  const opacity = useTransform(p, [0, 0.55], [0, 1])
  const blur = useTransform(p, [0, 0.8], [6, 0])
  const filter = useMotionTemplate`blur(${blur}px)`
  const [settled, setSettled] = useState(!!reduced)
  useMotionValueEvent(p, 'change', v => { if (v >= 0.98 && !settled) setSettled(true) })
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <motion.div style={reduced ? style : { scale, opacity, filter, willChange: settled ? 'auto' : 'transform, opacity, filter', ...style }}>{children}</motion.div>
    </div>
  )
}

/* ─── layout + brutalist frame ───────────────────────────────────────────── */
function Section({ id, children, bg = '#07070f', style }: { id?: string; children: React.ReactNode; bg?: string; style?: React.CSSProperties }) {
  return (
    <section id={id} style={{ background: bg, padding: 'clamp(80px,10vw,150px) clamp(20px,5vw,72px)', position: 'relative', overflow: 'hidden', ...style }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', position: 'relative' }}>{children}</div>
    </section>
  )
}
function Corner({ v, h }: { v: 'top' | 'bottom'; h: 'left' | 'right' }) {
  const s: React.CSSProperties = { position: 'absolute', width: 9, height: 9, zIndex: 3, pointerEvents: 'none', [v]: 6, [h]: 6 }
  if (v === 'top') s.borderTop = `1px solid ${TICK}`; else s.borderBottom = `1px solid ${TICK}`
  if (h === 'left') s.borderLeft = `1px solid ${TICK}`; else s.borderRight = `1px solid ${TICK}`
  return <span style={s} />
}
function Frame({ coord, idx, dark, scan, grid, children, style, right }: { coord?: string; idx?: string; dark?: boolean; scan?: boolean; grid?: boolean; children: React.ReactNode; style?: React.CSSProperties; right?: React.ReactNode }) {
  return (
    <div className={`cx-mil${dark ? ' cx-mil-dark' : ''}${scan ? ' cx-scan' : ''}`} style={{ position: 'relative', borderRadius: 10, ...style }}>
      {grid && <div className="cx-grid-bg" style={{ position: 'absolute', inset: 0, borderRadius: 'inherit', pointerEvents: 'none' }} />}
      <Corner v="top" h="left" /><Corner v="top" h="right" /><Corner v="bottom" h="left" /><Corner v="bottom" h="right" />
      {coord && (
        <div style={{ position: 'relative', zIndex: 2, display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px', borderBottom: `1px solid ${HAIR}` }}>
          {idx && <span style={{ ...coordLabel, color: INDIGO_SOFT }}>{idx}</span>}
          <span style={{ ...coordLabel, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{coord}</span>
          {right}
        </div>
      )}
      <div style={{ position: 'relative', zIndex: 2 }}>{children}</div>
    </div>
  )
}
function LiveDot({ color = EMERALD, label }: { color?: string; label?: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, ...coordLabel, color: T3 }}>
      <motion.span style={{ width: 6, height: 6, borderRadius: 999, background: color, boxShadow: `0 0 8px ${color}` }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.6, repeat: Infinity }} />{label}
    </span>
  )
}

/* ─── brand mark ─────────────────────────────────────────────────────────── */
const AR = LOGO_AR as Record<string, number>
function logoStyle(logo: string, box: number): React.CSSProperties {
  const base: React.CSSProperties = { width: 'auto', height: 'auto', objectFit: 'contain', filter: 'brightness(0) invert(1)', opacity: 0.5 }
  if (logo.includes('simpleicons')) return { ...base, maxWidth: box * 0.9, maxHeight: box }
  const ar = AR[logo.split('/').pop() || ''] ?? 1
  if (ar > 2.5) return { ...base, maxWidth: box * 1.6, maxHeight: box * 0.6 }
  if (ar > 1.4) return { ...base, maxWidth: box * 1.3, maxHeight: box * 0.8 }
  return { ...base, maxWidth: box, maxHeight: box }
}
function BrandMark({ name, box = 28 }: { name: string; box?: number }) {
  const b = BRANDS.find(x => x.name === name); if (!b?.logo) return null
  return <img src={b.logo} alt={b.name} style={logoStyle(b.logo, box)} loading="lazy" />
}
const MARQUEE_BRANDS = ['Volkswagen', 'BMW', 'Mercedes', 'Audi', 'Porsche', 'Renault', 'Peugeot', 'Citroën', 'SEAT', 'Skoda', 'Toyota', 'Ford', 'Fiat', 'Volvo', 'Tesla', 'Opel', 'Dacia', 'Nissan']

/* ─── data (all derivable from ephemeral pointers: url·brand·model·price·mileage·year·thumbnail) ── */
const PAISES = [
  { code: 'de', label: 'Alemania', flag: 'https://flagcdn.com/w40/de.png', x: 372, y: 120 },
  { code: 'nl', label: 'Países Bajos', flag: 'https://flagcdn.com/w40/nl.png', x: 300, y: 66 },
  { code: 'be', label: 'Bélgica', flag: 'https://flagcdn.com/w40/be.png', x: 252, y: 124 },
  { code: 'fr', label: 'Francia', flag: 'https://flagcdn.com/w40/fr.png', x: 206, y: 226 },
  { code: 'ch', label: 'Suiza', flag: 'https://flagcdn.com/w40/ch.png', x: 336, y: 244 },
  { code: 'es', label: 'España', flag: 'https://flagcdn.com/w40/es.png', x: 132, y: 344 },
]
const NODE: Record<string, typeof PAISES[number]> = Object.fromEntries(PAISES.map(p => [p.code, p]))
const ROUTES: [string, string][] = [['nl', 'de'], ['be', 'de'], ['de', 'fr'], ['de', 'ch'], ['fr', 'ch'], ['fr', 'es'], ['de', 'es'], ['nl', 'be']]
const PORTALS = [
  { name: 'AutoScout24', favicon: 'https://www.google.com/s2/favicons?domain=autoscout24.com&sz=128', bg: '#111' },
  { name: 'mobile.de', favicon: 'https://www.google.com/s2/favicons?domain=mobile.de&sz=128', bg: '#ff6600' },
  { name: 'coches.net', favicon: 'https://www.google.com/s2/favicons?domain=coches.net&sz=128', bg: '#e30613' },
  { name: 'leboncoin', favicon: 'https://www.google.com/s2/favicons?domain=leboncoin.fr&sz=128', bg: '#ff6e14' },
  { name: 'marktplaats', favicon: 'https://www.google.com/s2/favicons?domain=marktplaats.nl&sz=128', bg: '#002b5c' },
  { name: '2dehands', favicon: 'https://www.google.com/s2/favicons?domain=2dehands.be&sz=128', bg: '#003a78' },
  { name: 'tutti.ch', favicon: 'https://www.google.com/s2/favicons?domain=tutti.ch&sz=128', bg: '#1a1a1a' },
]
const STATS = [
  { to: 1_550_000, suffix: '', label: 'vehículos indexados' },
  { to: 28_000, suffix: '+', label: 'dealers cubiertos' },
  { to: 6, suffix: '', label: 'países UE' },
  { to: 9, suffix: '', label: 'fuentes en el índice' },
]
// 5-tier price rating (marketplace convergence pattern), derived from price vs cohort median
const TIERS = [
  { k: 'CHOLLO', c: EMERALD, bg: 'rgba(52,211,153,0.12)' },
  { k: 'BUEN PRECIO', c: '#6ee7b7', bg: 'rgba(110,231,183,0.1)' },
  { k: 'EN MERCADO', c: T3, bg: 'rgba(148,163,184,0.1)' },
  { k: 'ALGO ALTO', c: '#fda4af', bg: 'rgba(251,113,133,0.08)' },
  { k: 'CARO', c: ROSE, bg: 'rgba(251,113,133,0.12)' },
]
type Ptr = { brand: string; model: string; year: number; km: number; price: number; country: string; src: number; tier: number; dom: number }
const POINTERS: Ptr[] = [
  { brand: 'BMW', model: 'Serie 3 320d', year: 2019, km: 64200, price: 18450, country: 'de', src: 1, tier: 0, dom: 3 },
  { brand: 'Audi', model: 'A4 Avant 40 TDI', year: 2020, km: 41800, price: 24900, country: 'nl', src: 0, tier: 1, dom: 7 },
  { brand: 'Mercedes', model: 'Clase C 220 d', year: 2020, km: 38500, price: 27300, country: 'de', src: 1, tier: 2, dom: 12 },
  { brand: 'Volkswagen', model: 'Golf 2.0 TDI', year: 2018, km: 89400, price: 15200, country: 'be', src: 5, tier: 0, dom: 2 },
  { brand: 'Renault', model: 'Clio 1.5 dCi', year: 2021, km: 27600, price: 12900, country: 'fr', src: 3, tier: 2, dom: 9 },
  { brand: 'Porsche', model: 'Macan S', year: 2019, km: 52100, price: 48700, country: 'ch', src: 6, tier: 1, dom: 5 },
  { brand: 'SEAT', model: 'León 2.0 TDI', year: 2020, km: 61300, price: 17850, country: 'es', src: 2, tier: 3, dom: 21 },
  { brand: 'Toyota', model: 'Corolla 1.8 HEV', year: 2021, km: 33900, price: 21400, country: 'nl', src: 4, tier: 2, dom: 14 },
  { brand: 'Peugeot', model: '3008 1.5 BlueHDi', year: 2019, km: 78200, price: 16600, country: 'fr', src: 3, tier: 4, dom: 33 },
]
// residual band (value vs age months) per model — synthetic, from {year,km,price} aggregation
const RES_AGE = [0, 12, 24, 36, 48, 60, 72]
const RES = {
  p50: [46000, 38500, 33000, 28200, 24100, 20600, 17600],
  p90: [46000, 41200, 36400, 32100, 28200, 24700, 21600],
  p10: [46000, 35400, 29200, 24300, 20100, 16600, 13700],
}
const RES_SUBJECT = { ageMonths: 42, value: 23800 } // a BMW 320d pointer
const CORRIDOR = { min: 14900, p25: 17200, median: 19850, p75: 22400, max: 26800, n: 412, subject: 18450, deltaPct: -7 }
const INV = { total: 1_550_000, fresh: 1_184_000, stale: 366_000, medianDom: 31, domHist: [40, 66, 88, 74, 52, 33, 18], soldThrough7d: 41200, churnPct: 2.7 }
const SAVED = [
  { id: '01', label: 'AUDI·A4 AVANT', route: 'DE→ES', years: "'19–'22", km: '≤120k', price: '≤24.900€', status: 'triggered' },
  { id: '02', label: 'BMW·SERIE 3', route: 'NL→FR', years: "'18–'21", km: '≤100k', price: '≤21.000€', status: 'armed' },
  { id: '03', label: 'PORSCHE·MACAN', route: 'CH→DE', years: "'18–'22", km: '≤80k', price: '≤55.000€', status: 'armed' },
  { id: '04', label: 'VW·GOLF GTI', route: 'BE→ES', years: "'19–'23", km: '≤90k', price: '≤28.000€', status: 'triggered' },
]
const ARB = [
  { car: 'BMW Serie 3 320d', from: 'de', to: 'es', buy: 18450, sell: 20290, delta: 1840, sdi: 71 },
  { car: 'Audi A4 Avant 40 TDI', from: 'nl', to: 'fr', buy: 24900, sell: 27210, delta: 2310, sdi: 58 },
  { car: 'Mercedes Clase C 220', from: 'de', to: 'fr', buy: 27300, sell: 28860, delta: 1560, sdi: 64 },
  { car: 'VW Golf 2.0 TDI', from: 'be', to: 'es', buy: 15200, sell: 16180, delta: 980, sdi: 49 },
  { car: 'Porsche Macan S', from: 'ch', to: 'de', buy: 48700, sell: 52120, delta: 3420, sdi: 77 },
  { car: 'Renault Clio 1.5', from: 'fr', to: 'es', buy: 12900, sell: 13540, delta: 640, sdi: 38 },
]

/* ════════════════════════ MODULES ════════════════════════ */

/* 0 · Scale band (reskinned into the grid system) */
function ScaleBand() {
  return (
    <Section bg="#0a0a16">
      <div className="cx-grid-bg" style={{ position: 'absolute', inset: 0, opacity: 0.5, pointerEvents: 'none' }} />
      <Stagger style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 0 }}>
        {STATS.map((s, i) => (
          <motion.div key={s.label} variants={childV} style={{ padding: '6px 20px', borderLeft: i === 0 ? 'none' : `1px solid ${HAIR}`, textAlign: 'center' }}>
            <div style={{ ...mono, fontSize: 'clamp(1.9rem,1.2rem+2.4vw,3.4rem)', fontWeight: 600, color: T1, letterSpacing: '-0.02em' }}><Counter to={s.to} suffix={s.suffix} /></div>
            <div style={{ ...coordLabel, color: T3, marginTop: 8 }}>{s.label}</div>
          </motion.div>
        ))}
      </Stagger>
      <Reveal delay={0.1} style={{ marginTop: 'clamp(40px,6vw,72px)', position: 'relative' }}>
        <div style={{ ...coordLabel, textAlign: 'center', marginBottom: 26 }}>// Todas las fuentes, un solo índice</div>
        <Marquee duration={30}>
          {PORTALS.map(p => (
            <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 11, flexShrink: 0 }}>
              <span style={{ width: 30, height: 30, borderRadius: 4, background: p.bg, border: `1px solid ${HAIR_HI}`, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}><img src={p.favicon} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /></span>
              <span style={{ fontSize: 14, fontWeight: 600, color: T3 }}>{p.name}</span>
            </div>
          ))}
        </Marquee>
      </Reveal>
    </Section>
  )
}

/* 1 · Density grid — operator table of live pointers */
function RatingChip({ t }: { t: number }) {
  const tier = TIERS[t]
  return <span style={{ ...coordLabel, letterSpacing: '0.1em', fontSize: 9, color: tier.c, background: tier.bg, border: `1px solid ${tier.c}33`, padding: '3px 7px', borderRadius: 4, whiteSpace: 'nowrap' }}>{tier.k}</span>
}
function DensityGrid() {
  return (
    <Section id="platform">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,0.78fr) minmax(0,1.22fr)', gap: 'clamp(32px,5vw,64px)', alignItems: 'center' }}>
        <div>
          <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>El índice, en crudo</p></Reveal>
          <Kinetic style={h2} lines={['Siete portales.', 'Seis países.', <span key="u" style={{ color: INDIGO_SOFT }}>Una sola tabla.</span>]} />
          <Reveal delay={0.18} style={{ marginTop: 22 }}><p style={lead}>CARDEX deduplica el inventario de cada fuente y lo sirve como punteros efímeros — sin copiar el anuncio, solo el dato. Cada fila lleva su valoración de precio calculada contra el mercado.</p></Reveal>
          <Reveal delay={0.28} style={{ marginTop: 22, display: 'flex', gap: 18, flexWrap: 'wrap' }}>
            {TIERS.slice(0, 3).map(t => <span key={t.k} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, color: T3 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: t.c }} />{t.k}</span>)}
          </Reveal>
        </div>
        <Emerge>
          <Frame coord="Índice · vehículos · live" idx="//01" grid right={<LiveDot label="Sync" />}>
            <div style={{ display: 'grid', gridTemplateColumns: '24px 1.7fr 0.5fr 0.7fr 0.8fr 0.5fr 0.9fr', alignItems: 'center', gap: 10, padding: '9px 16px', borderBottom: `1px solid ${HAIR}`, ...coordLabel }}>
              <span /><span>Modelo</span><span>Año</span><span>KM</span><span>Precio</span><span>País</span><span style={{ textAlign: 'right' }}>Valoración</span>
            </div>
            <Stagger>
              {POINTERS.map((p, i) => (
                <motion.div key={i} variants={childV} className="cx-row" style={{ display: 'grid', gridTemplateColumns: '24px 1.7fr 0.5fr 0.7fr 0.8fr 0.5fr 0.9fr', alignItems: 'center', gap: 10, padding: '11px 16px', borderBottom: i < POINTERS.length - 1 ? `1px solid ${HAIR}` : 'none', background: i % 2 ? 'rgba(255,255,255,0.012)' : 'transparent', cursor: 'pointer' }}>
                  <span style={{ width: 18, height: 18, borderRadius: 3, background: PORTALS[p.src].bg, overflow: 'hidden', display: 'inline-flex' }}><img src={PORTALS[p.src].favicon} alt="" style={{ width: '100%', height: '100%' }} /></span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.model}</span>
                  <span style={{ ...mono, fontSize: 12.5, color: T3 }}>{p.year}</span>
                  <span style={{ ...mono, fontSize: 12.5, color: T3 }}>{fmt(p.km / 1000)}k</span>
                  <span style={{ ...mono, fontSize: 13.5, fontWeight: 600, color: T1 }}>{fmt(p.price)} €</span>
                  <span><img src={NODE[p.country].flag} alt="" style={{ width: 18, height: 12, borderRadius: 2 }} /></span>
                  <span style={{ textAlign: 'right' }}><RatingChip t={p.tier} /></span>
                </motion.div>
              ))}
            </Stagger>
          </Frame>
        </Emerge>
      </div>
    </Section>
  )
}

/* 2 · Trust strip — thin rhythm band */
function TrustStrip() {
  return (
    <Section bg="#07070f" style={{ padding: 'clamp(40px,5vw,64px) clamp(20px,5vw,72px)' }}>
      <Emerge>
        <Frame coord="Procedencia · verificación">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1.3fr' }}>
            <div style={{ padding: '20px 22px', borderRight: `1px solid ${HAIR}` }}>
              <div style={{ ...coordLabel, marginBottom: 12 }}>Dealer vs privado</div>
              <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
                <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EXPO }} style={{ width: '72%', background: INDIGO, transformOrigin: 'left' }} />
                <motion.div initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EXPO, delay: 0.1 }} style={{ width: '28%', background: 'rgba(255,255,255,0.12)', transformOrigin: 'left' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', ...mono, fontSize: 12, color: T3 }}><span style={{ color: INDIGO_SOFT }}>72% dealer</span><span>28% privado</span></div>
            </div>
            <div style={{ padding: '20px 22px', borderRight: `1px solid ${HAIR}` }}>
              <div style={{ ...coordLabel, marginBottom: 12 }}>Deduplicación</div>
              <div style={{ ...mono, fontSize: 22, fontWeight: 600, color: T1 }}>4,3 <span style={{ color: T4, fontSize: 14 }}>→ 1</span></div>
              <div style={{ fontSize: 12, color: T3, marginTop: 6 }}>anuncios por vehículo único</div>
            </div>
            <div style={{ padding: '20px 22px' }}>
              <div style={{ ...coordLabel, marginBottom: 12 }}>Cobertura de fuentes</div>
              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                {PORTALS.map(p => <span key={p.name} title={p.name} style={{ width: 26, height: 26, borderRadius: 4, background: p.bg, border: `1px solid ${HAIR_HI}`, overflow: 'hidden', display: 'inline-flex' }}><img src={p.favicon} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /></span>)}
              </div>
            </div>
          </div>
        </Frame>
      </Emerge>
    </Section>
  )
}

/* 3 · Pinned signature beat — residual curve + price corridor (one pin, scrubbed) */
function path(arr: number[], w = 520, h = 240, max = 48000) {
  return arr.map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i / (arr.length - 1)) * w} ${h - (v / max) * h}`).join(' ')
}
function area(top: number[], bot: number[], w = 520, h = 240, max = 48000) {
  const up = top.map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i / (top.length - 1)) * w} ${h - (v / max) * h}`).join(' ')
  const dn = bot.map((v, i) => `L ${((bot.length - 1 - i) / (bot.length - 1)) * w} ${h - (bot[bot.length - 1 - i] / max) * h}`).join(' ')
  return `${up} ${dn} Z`
}
function ResidualCorridor() {
  const wrap = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress: p } = useScroll({ target: wrap, offset: ['start start', 'end end'] })
  const draw = useTransform(p, [0.05, 0.42], [0, 1])
  const bandO = useTransform(p, [0.1, 0.4], [0, 1])
  const markS = useTransform(p, [0.4, 0.55], [0, 1])
  const corridorX = useTransform(p, [0.55, 0.85], ['8%', `${((CORRIDOR.subject - CORRIDOR.min) / (CORRIDOR.max - CORRIDOR.min)) * 100}%`])
  const subjPct = ((RES_SUBJECT.ageMonths) / 72) * 520
  const subjY = 240 - (RES_SUBJECT.value / 48000) * 240
  return (
    <div ref={wrap} style={{ height: reduced ? 'auto' : '230vh', position: 'relative', background: '#0a0a16' }}>
      <div style={{ position: reduced ? 'relative' : 'sticky', top: 0, minHeight: reduced ? 'auto' : '100dvh', display: 'flex', alignItems: 'center', padding: 'clamp(80px,10vw,120px) clamp(20px,5vw,72px)', overflow: 'hidden' }}>
        <div className="cx-grid-bg" style={{ position: 'absolute', inset: 0, opacity: 0.5, pointerEvents: 'none' }} />
        <Glow x="62%" y="38%" size={620} color="rgba(124,58,237,0.1)" />
        <div style={{ maxWidth: 1180, margin: '0 auto', width: '100%', position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0,0.8fr) minmax(0,1.2fr)', gap: 'clamp(28px,4vw,56px)', alignItems: 'center' }}>
          <div>
            <p style={{ ...eyebrow, marginBottom: 18 }}>La capa que un valuador no te da</p>
            <h2 style={h2}>Depreciación,<br /><span style={{ color: INDIGO_SOFT }}>no estimación.</span></h2>
            <p style={{ ...lead, marginTop: 22 }}>Cada modelo tiene su curva de retención. CARDEX sitúa el coche exacto sobre su banda residual y dentro del corredor de precio de mercado — para que sepas si compras bien antes de pujar.</p>
            <div style={{ display: 'flex', gap: 22, marginTop: 26 }}>
              {[['Valor hoy', '23.800 €'], ['Retención 36m', '61%'], ['Δ vs nuevo', '-48%']].map(([k, v]) => (
                <div key={k}><div style={{ ...mono, fontSize: 'clamp(1.1rem,0.9rem+0.6vw,1.5rem)', fontWeight: 600, color: T1 }}>{v}</div><div style={{ ...coordLabel, marginTop: 4 }}>{k}</div></div>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* residual curve terminal */}
            <Frame coord="Residual · BMW 320d · €/edad" idx="//03" scan>
              <div style={{ padding: 18 }}>
                <svg viewBox="0 0 520 260" style={{ width: '100%', height: 'auto' }}>
                  {[0, 0.25, 0.5, 0.75, 1].map(g => <line key={g} x1={0} y1={240 * g} x2={520} y2={240 * g} stroke="rgba(255,255,255,0.04)" strokeWidth={1} />)}
                  <motion.path d={area(RES.p90, RES.p10)} fill="rgba(99,102,241,0.1)" style={reduced ? { opacity: 1 } : { opacity: bandO }} />
                  <motion.path d={path(RES.p50)} fill="none" stroke={INDIGO_SOFT} strokeWidth={2} strokeLinecap="round" style={reduced ? { pathLength: 1 } : { pathLength: draw }} />
                  <motion.g style={reduced ? { scale: 1, transformOrigin: `${subjPct}px ${subjY}px` } : { scale: markS, transformOrigin: `${subjPct}px ${subjY}px` }}>
                    <line x1={subjPct} y1={subjY - 8} x2={subjPct} y2={subjY + 8} stroke={EMERALD} strokeWidth={1.5} />
                    <line x1={subjPct - 8} y1={subjY} x2={subjPct + 8} y2={subjY} stroke={EMERALD} strokeWidth={1.5} />
                    <circle cx={subjPct} cy={subjY} r={4} fill="none" stroke={EMERALD} strokeWidth={1.5} />
                  </motion.g>
                  {RES_AGE.map((a, i) => <text key={a} x={(i / (RES_AGE.length - 1)) * 520} y={256} fill={T4} fontSize={9} fontFamily={MONO} textAnchor="middle">{a}m</text>)}
                </svg>
              </div>
            </Frame>
            {/* price corridor terminal */}
            <Frame coord="Mercado · 320d · '19·64k" idx="//04">
              <div style={{ padding: '22px 20px 18px' }}>
                <div style={{ position: 'relative', height: 10, borderRadius: 5, background: 'rgba(255,255,255,0.05)' }}>
                  <motion.div style={{ position: 'absolute', left: `${((CORRIDOR.p25 - CORRIDOR.min) / (CORRIDOR.max - CORRIDOR.min)) * 100}%`, width: `${((CORRIDOR.p75 - CORRIDOR.p25) / (CORRIDOR.max - CORRIDOR.min)) * 100}%`, top: 0, bottom: 0, background: 'rgba(99,102,241,0.22)', borderRadius: 5, transformOrigin: 'center', scaleX: reduced ? 1 : draw }} />
                  <div style={{ position: 'absolute', left: `${((CORRIDOR.median - CORRIDOR.min) / (CORRIDOR.max - CORRIDOR.min)) * 100}%`, top: -3, bottom: -3, width: 2, background: INDIGO_SOFT }} />
                  <motion.div style={{ position: 'absolute', top: -16, left: reduced ? `${((CORRIDOR.subject - CORRIDOR.min) / (CORRIDOR.max - CORRIDOR.min)) * 100}%` : corridorX, width: 2, height: 42, background: EMERALD, boxShadow: `0 0 10px ${EMERALD}` }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 26, ...mono, fontSize: 10.5, color: T4 }}>
                  <span>{fmt(CORRIDOR.min / 1000)}k</span><span>{fmt(CORRIDOR.p25 / 1000)}k</span><span style={{ color: INDIGO_SOFT }}>med {fmt(CORRIDOR.median / 1000)}k</span><span>{fmt(CORRIDOR.p75 / 1000)}k</span><span>{fmt(CORRIDOR.max / 1000)}k</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, paddingTop: 14, borderTop: `1px solid ${HAIR}` }}>
                  <span style={{ ...coordLabel }}>≈ {CORRIDOR.n} comparables en 6 países</span>
                  <span style={{ ...mono, fontSize: 14, fontWeight: 600, color: EMERALD }}>Δ {fmt(CORRIDOR.median - CORRIDOR.subject)} € · {CORRIDOR.deltaPct}% bajo mercado</span>
                </div>
              </div>
            </Frame>
          </div>
        </div>
      </div>
    </div>
  )
}

/* 4 · Arbitrage terminal — signature live feed */
function ArbTerminal() {
  return (
    <Section id="coverage">
      <Glow x="50%" y="40%" size={560} color="rgba(99,102,241,0.1)" />
      <Reveal style={{ marginBottom: 36 }}><p style={{ ...eyebrow, marginBottom: 18 }}>Arbitraje cross-border</p><Kinetic style={h2} lines={['El margen vive', <span key="b" style={{ color: INDIGO_SOFT }}>en la frontera.</span>]} /></Reveal>
      <Emerge>
        <Frame coord="Arbitraje · DE·ES·FR·NL·BE·CH · live" idx="//05" dark scan right={<LiveDot label="En vivo" />}>
          <div style={{ display: 'grid', gridTemplateColumns: '0.9fr 1.6fr 0.9fr 0.9fr 0.9fr 0.7fr', gap: 10, padding: '10px 18px', borderBottom: `1px solid ${HAIR}`, ...coordLabel }}>
            <span>Ruta</span><span>Vehículo</span><span style={{ textAlign: 'right' }}>Compra</span><span style={{ textAlign: 'right' }}>Venta med</span><span style={{ textAlign: 'right' }}>Δ margen</span><span style={{ textAlign: 'right' }}>SDI</span>
          </div>
          <div style={{ position: 'relative' }}>
            <Marquee vertical height={300} duration={16}>
              {ARB.map((a, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '0.9fr 1.6fr 0.9fr 0.9fr 0.9fr 0.7fr', gap: 10, alignItems: 'center', padding: '13px 18px', borderBottom: `1px solid ${HAIR}` }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <img src={NODE[a.from].flag} alt="" style={{ width: 18, height: 12, borderRadius: 2 }} />
                    <svg width={12} height={12} viewBox="0 0 12 12"><path d="M2 6h7M6 3l3 3-3 3" stroke={T4} strokeWidth={1.4} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    <img src={NODE[a.to].flag} alt="" style={{ width: 18, height: 12, borderRadius: 2 }} />
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: T1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.car}</span>
                  <span style={{ ...mono, fontSize: 12.5, color: T3, textAlign: 'right' }}>{fmt(a.buy)} €</span>
                  <span style={{ ...mono, fontSize: 12.5, color: T3, textAlign: 'right' }}>{fmt(a.sell)} €</span>
                  <span style={{ ...mono, fontSize: 13.5, fontWeight: 600, color: EMERALD, textAlign: 'right' }}>+{fmt(a.delta)} €</span>
                  <span style={{ textAlign: 'right' }}><span style={{ ...mono, fontSize: 12, color: a.sdi > 65 ? ROSE : T3 }}>{a.sdi}</span></span>
                </div>
              ))}
            </Marquee>
          </div>
        </Frame>
      </Emerge>
      <Reveal delay={0.1}><p style={{ ...coordLabel, marginTop: 16 }}>// El margen aterrizado (NLC) y la clasificación fiscal son orientativos · en construcción</p></Reveal>
    </Section>
  )
}

/* 5 · Inventory health */
function Donut({ pct, label, val }: { pct: number; label: string; val: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <svg width={64} height={64} viewBox="0 0 64 64">
        <circle cx="32" cy="32" r="26" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="6" />
        <motion.circle cx="32" cy="32" r="26" fill="none" stroke={INDIGO} strokeWidth="6" strokeLinecap="round" strokeDasharray={163} transform="rotate(-90 32 32)" initial={{ strokeDashoffset: 163 }} whileInView={{ strokeDashoffset: 163 * (1 - pct) }} viewport={{ once: true }} transition={{ duration: 1.4, ease: EXPO }} />
      </svg>
      <div><div style={{ ...mono, fontSize: 20, fontWeight: 600, color: T1 }}>{val}</div><div style={{ ...coordLabel, marginTop: 4 }}>{label}</div></div>
    </div>
  )
}
function InventoryHealth() {
  return (
    <Section bg="#0a0a16">
      <Reveal style={{ marginBottom: 36 }}><p style={{ ...eyebrow, marginBottom: 18 }}>Salud del inventario</p><Kinetic style={h2} lines={['Un índice vivo,', <span key="n" style={{ color: INDIGO_SOFT }}>no un catálogo.</span>]} /></Reveal>
      <Emerge>
        <Frame coord="Inventario · 6 países · live" idx="//06" dark right={<LiveDot label="hace 4 min" />}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
            <div style={{ padding: '24px 22px', borderRight: `1px solid ${HAIR}` }}><Donut pct={0.764} label="Frescos / total" val="76%" /></div>
            <div style={{ padding: '24px 22px', borderRight: `1px solid ${HAIR}` }}>
              <div style={{ ...mono, fontSize: 'clamp(1.6rem,1.2rem+1.4vw,2.6rem)', fontWeight: 600, color: T1 }}><Counter to={INV.medianDom} /> <span style={{ fontSize: 13, color: T4 }}>días</span></div>
              <div style={{ ...coordLabel, margin: '8px 0 14px' }}>Mediana en mercado</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 36 }}>{INV.domHist.map((d, i) => <motion.div key={i} initial={{ scaleY: 0 }} whileInView={{ scaleY: 1 }} viewport={{ once: true }} transition={{ delay: i * 0.05, duration: 0.5, ease: EXPO }} style={{ flex: 1, height: `${d}%`, background: 'rgba(129,140,248,0.45)', borderRadius: '2px 2px 0 0', transformOrigin: 'bottom' }} />)}</div>
            </div>
            <div style={{ padding: '24px 22px', borderRight: `1px solid ${HAIR}` }}>
              <div style={{ ...mono, fontSize: 'clamp(1.6rem,1.2rem+1.4vw,2.6rem)', fontWeight: 600, color: T1 }}><Counter to={INV.soldThrough7d} /></div>
              <div style={{ ...coordLabel, margin: '8px 0 10px' }}>Rotados · 7d</div>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, ...mono, fontSize: 12, color: EMERALD }}><svg width={11} height={11} viewBox="0 0 11 11"><path d="M5.5 2v7M2.5 5l3-3 3 3" stroke={EMERALD} strokeWidth={1.4} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>+{INV.churnPct}% churn</span>
            </div>
            <div style={{ padding: '24px 22px', position: 'relative', overflow: 'hidden' }}>
              <motion.div aria-hidden style={{ position: 'absolute', left: 0, right: 0, height: 2, background: 'linear-gradient(90deg,transparent,rgba(165,180,252,0.5),transparent)' }} animate={{ y: [0, 120, 0] }} transition={{ duration: 4, ease: 'easeInOut', repeat: Infinity }} />
              <div style={{ ...coordLabel, marginBottom: 12 }}>Última sincronización</div>
              <motion.div style={{ width: 12, height: 12, borderRadius: 999, background: EMERALD, boxShadow: `0 0 14px ${EMERALD}`, marginBottom: 14 }} animate={{ opacity: [1, 0.3, 1], scale: [1, 1.15, 1] }} transition={{ duration: 1.8, repeat: Infinity }} />
              <div style={{ ...mono, fontSize: 13, color: T2 }}>hace 4 min</div>
              <div style={{ fontSize: 11, color: T4, marginTop: 4 }}>1,55M punteros activos</div>
            </div>
          </div>
        </Frame>
      </Emerge>
    </Section>
  )
}

/* 6 · Alert console — mirrors the frozen hero filter shape (does not import it) */
function AlertConsole() {
  return (
    <Section id="pricing">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,0.85fr) minmax(0,1.15fr)', gap: 'clamp(32px,5vw,64px)', alignItems: 'center' }}>
        <div>
          <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>Alertas · búsquedas guardadas</p></Reveal>
          <Kinetic style={h2} lines={['Arma una búsqueda.', <span key="p" style={{ color: INDIGO_SOFT }}>El mercado te avisa.</span>]} />
          <Reveal delay={0.18} style={{ marginTop: 22 }}><p style={lead}>Guarda los filtros del buscador como un vigía. Cuando un coche entra en tu rango — o un vendedor baja el precio — CARDEX dispara la alerta antes que nadie. La latencia es tu ventaja.</p></Reveal>
        </div>
        <Emerge>
          <Frame coord="Watchlist · armada" idx="//07" right={<LiveDot color={INDIGO_SOFT} label="4 activas" />}>
            <Stagger>
              {SAVED.map((s, i) => (
                <motion.div key={s.id} variants={childV} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: i < SAVED.length - 1 ? `1px solid ${HAIR}` : 'none' }}>
                  <span style={{ ...coordLabel, color: INDIGO_SOFT }}>{`//${s.id}`}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: T1 }}>{s.label}</span>
                      <span style={{ ...mono, fontSize: 11, color: INDIGO_SOFT }}>{s.route}</span>
                    </div>
                    <div style={{ ...mono, fontSize: 11, color: T4, marginTop: 4 }}>{s.years} · {s.km} · {s.price}</div>
                  </div>
                  {s.status === 'triggered'
                    ? <motion.span style={{ ...coordLabel, color: EMERALD, background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.25)', padding: '4px 9px', borderRadius: 4 }} animate={{ opacity: [1, 0.5, 1] }} transition={{ duration: 1.6, repeat: Infinity }}>● Match</motion.span>
                    : <span style={{ ...coordLabel, color: INDIGO_SOFT, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', padding: '4px 9px', borderRadius: 4 }}>Armada</span>}
                </motion.div>
              ))}
            </Stagger>
          </Frame>
        </Emerge>
      </div>
    </Section>
  )
}

/* 7 · Comparison */
const CMP_ROWS = [
  { f: 'Valoración de precio 5-tiers en cada anuncio', valuer: 'parcial', market: true, cardex: true },
  { f: 'Corredor de mercado + Δ vs mediana', valuer: true, market: false, cardex: true },
  { f: 'Cobertura de 6 países en un índice', valuer: false, market: 'parcial', cardex: true },
  { f: 'Alertas cross-border de nuevo match', valuer: false, market: 'parcial', cardex: true },
  { f: 'Expediente del vehículo (VIN · ITV · NCAP)', valuer: false, market: false, cardex: true },
  { f: 'Coste aterrizado y fiscalidad cross-border', valuer: false, market: false, cardex: 'roadmap' },
]
function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <motion.svg width={18} height={18} viewBox="0 0 18 18" initial={{ scale: 0.5, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ once: true }} transition={{ type: 'spring', stiffness: 300, damping: 16 }}><circle cx="9" cy="9" r="9" fill="rgba(52,211,153,0.14)" /><path d="M13.5 6L7.8 12 4.5 8.8" stroke={EMERALD} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></motion.svg>
  if (v === 'parcial') return <span style={{ fontSize: 11.5, color: T4 }}>parcial</span>
  if (v === 'roadmap') return <span style={{ ...coordLabel, color: INDIGO_SOFT }}>Pronto</span>
  return <span style={{ display: 'inline-block', width: 14, height: 1.5, background: 'rgba(255,255,255,0.18)' }} />
}
function Comparison() {
  return (
    <Section bg="#07070f">
      <Kinetic style={{ ...h2, maxWidth: '24ch', marginBottom: 40 }} lines={['Un valuador da un número.', <span key="s" style={{ color: T3 }}>CARDEX da el sistema.</span>]} />
      <Emerge>
        <Frame coord="Paridad · capacidades">
          <div style={{ display: 'grid', gridTemplateColumns: '1.7fr 1fr 1fr 1fr', padding: '14px 22px', borderBottom: `1px solid ${HAIR}`, alignItems: 'center' }}>
            <span /><span style={{ ...coordLabel, textAlign: 'center' }}>Valuador</span><span style={{ ...coordLabel, textAlign: 'center' }}>Marketplace</span><span style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', textAlign: 'center', background: 'linear-gradient(120deg,#c4b5fd,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>CARDEX</span>
          </div>
          {CMP_ROWS.map((r, i) => (
            <motion.div key={r.f} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-6% 0px' }} transition={{ duration: 0.5, ease: EXPO, delay: i * 0.04 }} style={{ display: 'grid', gridTemplateColumns: '1.7fr 1fr 1fr 1fr', padding: '15px 22px', borderBottom: i < CMP_ROWS.length - 1 ? `1px solid ${HAIR}` : 'none', alignItems: 'center' }}>
              <span style={{ fontSize: 13.5, color: T2 }}>{r.f}</span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.valuer} /></span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.market} /></span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.cardex} /></span>
            </motion.div>
          ))}
        </Frame>
      </Emerge>
    </Section>
  )
}

/* 8 · How it works */
const STEPS = [
  { n: '01', t: 'Indexamos', b: 'Indexación sitemap-first del inventario de cada dealer en seis países. Punteros efímeros al anuncio real, deduplicados — sin scraping profundo ni binarios.' },
  { n: '02', t: 'Valoramos', b: 'Cada puntero se compara con su cohorte de mercado: valoración 5-tiers, corredor de precio, días en mercado y curva residual del modelo.' },
  { n: '03', t: 'Operas', b: 'Arma búsquedas como vigías, recibe alertas de nuevo match y price-drop, y verifica cada matrícula con su expediente. La latencia es la ventaja.' },
]
function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 70%', 'end 60%'] })
  const h = useTransform(scrollYProgress, [0, 1], ['0%', '100%'])
  return (
    <Section bg="#0a0a16">
      <Reveal style={{ marginBottom: 56 }}><p style={{ ...eyebrow, marginBottom: 18 }}>Cómo funciona</p><h2 style={{ ...h2, maxWidth: '16ch' }}>Del puntero crudo a la decisión.</h2></Reveal>
      <div ref={ref} style={{ position: 'relative', paddingLeft: 'clamp(40px,6vw,72px)' }}>
        <div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, bottom: 6, width: 2, background: HAIR }} />
        <motion.div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, width: 2, height: h, background: `linear-gradient(${INDIGO},${INDIGO_SOFT})`, transformOrigin: 'top', boxShadow: `0 0 12px ${INDIGO}` }} />
        {STEPS.map((s, i) => (
          <Reveal key={s.n} style={{ position: 'relative', paddingBottom: i < STEPS.length - 1 ? 'clamp(40px,5vw,64px)' : 0 }}>
            <div style={{ position: 'absolute', left: 'calc(clamp(15px,2.4vw,28px) - clamp(40px,6vw,72px) - 6px)', top: 2, width: 14, height: 14, borderRadius: 999, background: '#0a0a16', border: `2px solid ${INDIGO_SOFT}` }} />
            <div style={{ ...mono, fontSize: 13, color: INDIGO_SOFT, marginBottom: 10 }}>{s.n}</div>
            <h3 style={{ fontSize: 'clamp(1.3rem,1rem+1vw,1.7rem)', fontWeight: 650, letterSpacing: '-0.02em', color: T1, margin: '0 0 10px' }}>{s.t}</h3>
            <p style={{ ...lead, fontSize: '1rem' }}>{s.b}</p>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* 9 · Final CTA */
function FinalCta({ onEnter }: { onEnter: () => void }) {
  return (
    <Section bg="#07070f" style={{ textAlign: 'center', paddingTop: 'clamp(110px,13vw,200px)', paddingBottom: 'clamp(110px,13vw,200px)' }}>
      <Glow x="50%" y="42%" size={760} color="rgba(99,102,241,0.16)" />
      <div className="cx-grid-bg" style={{ position: 'absolute', inset: 0, opacity: 0.4, pointerEvents: 'none' }} />
      <Kinetic style={{ fontSize: 'clamp(2.5rem,1.2rem+5vw,5.4rem)', lineHeight: 1.0, fontWeight: 700, letterSpacing: '-0.045em', color: T1, maxWidth: '15ch', margin: '0 auto', textAlign: 'center', position: 'relative' }} lines={['Deja de buscar', <span key="x" style={{ background: 'linear-gradient(120deg,#c4b5fd,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>en siete sitios.</span>]} />
      <Reveal delay={0.2} style={{ marginTop: 24, position: 'relative' }}><p style={{ ...lead, margin: '0 auto', textAlign: 'center' }}>La inteligencia del mercado europeo de usados, en un solo sistema. Empieza por un país, escala a los seis.</p></Reveal>
      <Reveal delay={0.3} style={{ marginTop: 40, display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap', position: 'relative' }}>
        <Magnetic><motion.button onClick={onEnter} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }} transition={{ type: 'spring', stiffness: 300, damping: 18 }} style={{ padding: '16px 36px', borderRadius: 12, background: 'linear-gradient(120deg,#6366f1,#7c3aed)', border: 'none', color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 0 50px rgba(99,102,241,0.5)' }}>Solicitar acceso</motion.button></Magnetic>
        <motion.a href="#coverage" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} style={{ padding: '16px 30px', borderRadius: 12, background: 'rgba(255,255,255,0.05)', border: `1px solid ${HAIR_HI}`, color: T2, fontSize: 15, fontWeight: 600, cursor: 'pointer', textDecoration: 'none', display: 'inline-block' }}>Ver el índice</motion.a>
      </Reveal>
    </Section>
  )
}

/* 10 · Footer */
function Footer() {
  const cols = [
    { h: 'Producto', items: ['Índice', 'Valoración', 'Alertas', 'Expediente'] },
    { h: 'Cobertura', items: ['Alemania', 'España', 'Francia', 'Países Bajos', 'Bélgica', 'Suiza'] },
    { h: 'Empresa', items: ['Sobre CARDEX', 'Acceso anticipado', 'Contacto'] },
    { h: 'Legal', items: ['Privacidad', 'Términos', 'Datos y fuentes'] },
  ]
  return (
    <footer style={{ background: '#0c0c1c', borderTop: `1px solid ${HAIR}`, padding: 'clamp(56px,7vw,88px) clamp(20px,5vw,72px) 36px' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto' }}>
        <Reveal>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) repeat(4,minmax(0,1fr))', gap: 'clamp(24px,3vw,48px)' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <div style={{ width: 26, height: 26, borderRadius: 8, background: 'linear-gradient(135deg,#6366f1,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><div style={{ width: 9, height: 9, borderRadius: 3, background: 'rgba(255,255,255,0.92)' }} /></div>
                <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.13em', background: 'linear-gradient(120deg,#c4b5fd,#818cf8,#67e8f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>CARDEX</span>
              </div>
              <p style={{ fontSize: 13, color: T3, lineHeight: 1.6, maxWidth: '34ch', margin: 0 }}>Inteligencia y verificación de vehículos usados para el trader profesional en seis países de la UE.</p>
            </div>
            {cols.map(c => (
              <div key={c.h}>
                <div style={{ ...coordLabel, marginBottom: 14 }}>{c.h}</div>
                {c.items.map(it => <a key={it} href="#" style={{ display: 'block', fontSize: 13.5, color: T3, textDecoration: 'none', padding: '5px 0', transition: 'color 0.18s' }} onMouseEnter={e => (e.currentTarget.style.color = T1)} onMouseLeave={e => (e.currentTarget.style.color = T3)}>{it}</a>)}
              </div>
            ))}
          </div>
        </Reveal>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginTop: 'clamp(40px,5vw,64px)', paddingTop: 24, borderTop: `1px solid ${HAIR}` }}>
          <span style={{ fontSize: 12, color: T4 }}>© 2026 CARDEX · Metabuscador pasivo · clasificación fiscal orientativa.</span>
          <div style={{ display: 'flex', gap: 7 }}>{PAISES.map(p => <img key={p.code} src={p.flag} alt={p.label} style={{ width: 22, height: 15, borderRadius: 2, objectFit: 'cover', opacity: 0.7 }} />)}</div>
        </div>
      </div>
    </footer>
  )
}

/* ─── brand marquee strip ────────────────────────────────────────────────── */
function BrandStrip() {
  return (
    <Section bg="#07070f" style={{ padding: 'clamp(40px,5vw,64px) clamp(20px,5vw,72px)' }}>
      <Reveal>
        <div style={{ ...coordLabel, textAlign: 'center', marginBottom: 30 }}>// Toda marca · todo modelo · todo el catálogo europeo</div>
        <Marquee duration={44}>{MARQUEE_BRANDS.map(n => <span key={n} style={{ display: 'flex', alignItems: 'center', height: 30, flexShrink: 0 }}><BrandMark name={n} box={26} /></span>)}</Marquee>
      </Reveal>
    </Section>
  )
}

export default function LandingSections({ onEnter }: { onEnter: () => void }) {
  return (
    <>
      <ScaleBand />
      <DensityGrid />
      <TrustStrip />
      <ResidualCorridor />
      <ArbTerminal />
      <InventoryHealth />
      <AlertConsole />
      <BrandStrip />
      <Comparison />
      <HowItWorks />
      <FinalCta onEnter={onEnter} />
      <Footer />
    </>
  )
}
