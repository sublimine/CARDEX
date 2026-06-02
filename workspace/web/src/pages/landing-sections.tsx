import React, { useEffect, useRef, useState } from 'react'
import {
  motion, useInView, useScroll, useTransform, animate, useReducedMotion,
  useMotionValue, useSpring, type Variants, type MotionValue,
} from 'framer-motion'
import { BRANDS } from '../data/catalog'
import LOGO_AR from '../data/logo-ar.json'

/* ─── tokens ─────────────────────────────────────────────────────────────── */
const EXPO = [0.16, 1, 0.3, 1] as const
const T1 = '#f8fafc', T2 = '#cbd5e1', T3 = '#94a3b8', T4 = '#64748b'
const HAIR = 'rgba(255,255,255,0.07)', HAIR_HI = 'rgba(255,255,255,0.12)'
const INDIGO = '#6366f1', INDIGO_SOFT = '#a5b4fc', EMERALD = '#34d399'
const MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', monospace"
const fmt = (n: number) => Math.round(n).toLocaleString('de-DE')

const eyebrow: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'rgba(196,181,253,0.85)', margin: 0 }
const lead: React.CSSProperties = { fontSize: 'clamp(1.02rem,0.96rem+0.4vw,1.22rem)', lineHeight: 1.6, color: T2, maxWidth: '52ch', margin: 0 }
const glassTile: React.CSSProperties = { background: 'rgba(255,255,255,0.035)', border: `1px solid ${HAIR}`, borderRadius: 20, backdropFilter: 'blur(20px) saturate(150%)', WebkitBackdropFilter: 'blur(20px) saturate(150%)' }

/* ─── motion primitives ──────────────────────────────────────────────────── */
function Reveal({ children, y = 26, delay = 0, style }: { children: React.ReactNode; y?: number; delay?: number; style?: React.CSSProperties }) {
  const r = useReducedMotion()
  return (
    <motion.div style={style} initial={r ? { opacity: 1 } : { opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-10% 0px', amount: 0.2 }} transition={{ duration: 0.75, ease: EXPO, delay }}>
      {children}
    </motion.div>
  )
}
/** Headline reveal: each line wiped up behind a mask, staggered — the agency move. */
function Kinetic({ lines, style, delay = 0 }: { lines: React.ReactNode[]; style?: React.CSSProperties; delay?: number }) {
  const r = useReducedMotion()
  return (
    <div style={style}>
      {lines.map((ln, i) => (
        <div key={i} style={{ overflow: 'hidden', paddingBottom: '0.04em' }}>
          <motion.div initial={r ? { y: 0 } : { y: '115%' }} whileInView={{ y: '0%' }} viewport={{ once: true, margin: '-12% 0px' }}
            transition={{ duration: 0.85, ease: EXPO, delay: delay + i * 0.09 }}>
            {ln}
          </motion.div>
        </div>
      ))}
    </div>
  )
}
const parentV: Variants = { hidden: {}, visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } } }
const childV: Variants = { hidden: { opacity: 0, y: 22 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EXPO } } }
function Stagger({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <motion.div style={style} variants={parentV} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-8% 0px', amount: 0.15 }}>{children}</motion.div>
}
function Counter({ to, suffix = '', duration = 1.8 }: { to: number; suffix?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const [v, setV] = useState(0)
  const r = useReducedMotion()
  useEffect(() => {
    if (!inView) return
    if (r) { setV(to); return }
    const c = animate(0, to, { duration, ease: EXPO, onUpdate: setV })
    return () => c.stop()
  }, [inView, to, r, duration])
  return <span ref={ref}>{fmt(v)}{suffix}</span>
}
function Marquee({ children, duration = 34, reverse = false }: { children: React.ReactNode; duration?: number; reverse?: boolean }) {
  return (
    <div style={{ overflow: 'hidden', WebkitMaskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)', maskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)' }}>
      <motion.div style={{ display: 'flex', alignItems: 'center', gap: 44, width: 'max-content', willChange: 'transform' }}
        animate={{ x: reverse ? ['-50%', '0%'] : ['0%', '-50%'] }} transition={{ duration, ease: 'linear', repeat: Infinity }}>
        {children}{children}
      </motion.div>
    </div>
  )
}
function Magnetic({ children, strength = 0.35, style }: { children: React.ReactNode; strength?: number; style?: React.CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null)
  const x = useMotionValue(0), y = useMotionValue(0)
  const sx = useSpring(x, { stiffness: 280, damping: 18 }), sy = useSpring(y, { stiffness: 280, damping: 18 })
  return (
    <motion.div ref={ref} style={{ x: sx, y: sy, display: 'inline-block', ...style }}
      onMouseMove={e => { const r = ref.current!.getBoundingClientRect(); x.set((e.clientX - r.left - r.width / 2) * strength); y.set((e.clientY - r.top - r.height / 2) * strength) }}
      onMouseLeave={() => { x.set(0); y.set(0) }}>
      {children}
    </motion.div>
  )
}
function Tilt({ children, style, max = 7 }: { children: React.ReactNode; style?: React.CSSProperties; max?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const rx = useMotionValue(0), ry = useMotionValue(0)
  const srx = useSpring(rx, { stiffness: 250, damping: 18 }), sry = useSpring(ry, { stiffness: 250, damping: 18 })
  return (
    <motion.div ref={ref} style={{ rotateX: srx, rotateY: sry, transformPerspective: 900, ...style }}
      onMouseMove={e => { const r = ref.current!.getBoundingClientRect(); ry.set(((e.clientX - r.left) / r.width - 0.5) * max * 2); rx.set(-((e.clientY - r.top) / r.height - 0.5) * max * 2) }}
      onMouseLeave={() => { rx.set(0); ry.set(0) }}>
      {children}
    </motion.div>
  )
}

/* ─── layout ─────────────────────────────────────────────────────────────── */
function Section({ id, children, bg = '#07070f', style }: { id?: string; children: React.ReactNode; bg?: string; style?: React.CSSProperties }) {
  return (
    <section id={id} style={{ background: bg, padding: 'clamp(80px,10vw,150px) clamp(20px,5vw,72px)', position: 'relative', overflow: 'hidden', ...style }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', position: 'relative' }}>{children}</div>
    </section>
  )
}
function Glow({ x = '50%', y = '50%', size = 520, color = 'rgba(99,102,241,0.16)' }: { x?: string; y?: string; size?: number; color?: string }) {
  return <motion.div aria-hidden style={{ position: 'absolute', left: x, top: y, width: size, height: size, marginLeft: -size / 2, marginTop: -size / 2, borderRadius: '50%', background: `radial-gradient(closest-side, ${color}, transparent)`, filter: 'blur(30px)', pointerEvents: 'none' }}
    animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 11, ease: 'easeInOut', repeat: Infinity }} />
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
  const b = BRANDS.find(x => x.name === name)
  if (!b?.logo) return null
  return <img src={b.logo} alt={b.name} style={logoStyle(b.logo, box)} loading="lazy" />
}
const MARQUEE_BRANDS = ['Volkswagen', 'BMW', 'Mercedes', 'Audi', 'Porsche', 'Renault', 'Peugeot', 'Citroën', 'SEAT', 'Skoda', 'Toyota', 'Ford', 'Fiat', 'Volvo', 'Tesla', 'Opel', 'Dacia', 'Nissan']

/* ─── data ───────────────────────────────────────────────────────────────── */
const PAISES = [
  { code: 'de', label: 'Alemania', flag: 'https://flagcdn.com/w40/de.png', x: 372, y: 120 },
  { code: 'nl', label: 'Países Bajos', flag: 'https://flagcdn.com/w40/nl.png', x: 300, y: 66 },
  { code: 'be', label: 'Bélgica', flag: 'https://flagcdn.com/w40/be.png', x: 252, y: 124 },
  { code: 'fr', label: 'Francia', flag: 'https://flagcdn.com/w40/fr.png', x: 206, y: 226 },
  { code: 'ch', label: 'Suiza', flag: 'https://flagcdn.com/w40/ch.png', x: 336, y: 244 },
  { code: 'es', label: 'España', flag: 'https://flagcdn.com/w40/es.png', x: 132, y: 344 },
]
const NODE = Object.fromEntries(PAISES.map(p => [p.code, p]))
const ROUTES: [string, string][] = [['nl', 'de'], ['be', 'de'], ['de', 'fr'], ['de', 'ch'], ['fr', 'ch'], ['fr', 'es'], ['de', 'es'], ['nl', 'be']]
const PORTALS = [
  { name: 'AutoScout24', favicon: 'https://www.google.com/s2/favicons?domain=autoscout24.com&sz=128', bg: '#111', border: '#FFCD00' },
  { name: 'mobile.de', favicon: 'https://www.google.com/s2/favicons?domain=mobile.de&sz=128', bg: '#ff6600' },
  { name: 'coches.net', favicon: 'https://www.google.com/s2/favicons?domain=coches.net&sz=128', bg: '#e30613' },
  { name: 'La Centrale', favicon: 'https://www.google.com/s2/favicons?domain=lacentrale.fr&sz=128', bg: '#c8102e' },
  { name: 'marktplaats', favicon: 'https://www.google.com/s2/favicons?domain=marktplaats.nl&sz=128', bg: '#002b5c' },
  { name: '2dehands', favicon: 'https://www.google.com/s2/favicons?domain=2dehands.be&sz=128', bg: '#003a78' },
  { name: 'tutti.ch', favicon: 'https://www.google.com/s2/favicons?domain=tutti.ch&sz=128', bg: '#1a1a1a' },
]
const STATS = [
  { to: 1_550_000, suffix: '', label: 'vehículos indexados' },
  { to: 28_000, suffix: '+', label: 'dealers cubiertos' },
  { to: 6, suffix: '', label: 'países UE' },
  { to: 9, suffix: '', label: 'secciones por dossier' },
]
const OPPS = [
  { car: 'BMW Serie 3 320d', from: 'de', to: 'es', delta: '+1.840 €' },
  { car: 'Audi A4 Avant 40 TDI', from: 'nl', to: 'fr', delta: '+2.310 €' },
  { car: 'Mercedes Clase C 220', from: 'de', to: 'fr', delta: '+1.560 €' },
  { car: 'VW Golf 2.0 TDI', from: 'be', to: 'es', delta: '+980 €' },
  { car: 'Porsche Macan', from: 'ch', to: 'de', delta: '+3.420 €' },
  { car: 'Renault Clio', from: 'fr', to: 'es', delta: '+640 €' },
]

/* ════════════════════════ SECTIONS ════════════════════════ */

/* 1 · Scale band */
function TrustScale() {
  return (
    <Section bg="#0a0a16">
      <Stagger style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 0 }}>
        {STATS.map((s, i) => (
          <motion.div key={s.label} variants={childV} style={{ padding: '6px 20px', borderLeft: i === 0 ? 'none' : `1px solid ${HAIR}`, textAlign: 'center' }}>
            <div style={{ fontFamily: MONO, fontVariantNumeric: 'tabular-nums', fontSize: 'clamp(1.9rem,1.2rem+2.4vw,3.4rem)', fontWeight: 600, color: T1, letterSpacing: '-0.02em' }}>
              <Counter to={s.to} suffix={s.suffix} />
            </div>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: T3, marginTop: 6 }}>{s.label}</div>
          </motion.div>
        ))}
      </Stagger>
      <Reveal delay={0.1} style={{ marginTop: 'clamp(40px,6vw,72px)' }}>
        <div style={{ textAlign: 'center', fontSize: 11, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', color: T4, marginBottom: 26 }}>Todas las fuentes, en un solo índice</div>
        <Marquee duration={30}>
          {PORTALS.map(p => (
            <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: 11, flexShrink: 0 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, background: p.bg, border: `1.5px solid ${p.border ?? 'rgba(255,255,255,0.1)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                <img src={p.favicon} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              </span>
              <span style={{ fontSize: 14, fontWeight: 600, color: T3 }}>{p.name}</span>
            </div>
          ))}
        </Marquee>
      </Reveal>
    </Section>
  )
}

/* 2 · Marketplace (scroll-scrubbed card stack) */
function FloatCard({ p, model, price, km, base, depth }: { p: typeof PORTALS[number]; model: string; price: string; km: string; base: number; depth: MotionValue<number> }) {
  const y = useTransform(depth, [0, 1], [base, base - 70 * (base / 60)])
  return (
    <motion.div style={{ position: 'absolute', left: `${20 + base * 0.9}px`, top: 0, y, width: 264, ...glassTile, background: 'rgba(16,15,34,0.85)', borderRadius: 16, padding: 15, boxShadow: '0 30px 70px rgba(0,0,0,0.55)' }}
      initial={{ opacity: 0, y: base + 30, rotate: -2 }} whileInView={{ opacity: 1, rotate: 0 }} viewport={{ once: true, margin: '-12%' }} transition={{ duration: 0.8, ease: EXPO }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11, fontWeight: 600, color: T3 }}>
          <span style={{ width: 16, height: 16, borderRadius: 4, background: p.bg, overflow: 'hidden', display: 'inline-flex' }}><img src={p.favicon} alt="" style={{ width: '100%', height: '100%' }} /></span>{p.name}
        </span>
        <span style={{ width: 7, height: 7, borderRadius: 999, background: EMERALD, boxShadow: `0 0 8px ${EMERALD}` }} />
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: T1, marginBottom: 9 }}>{model}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontFamily: MONO, fontSize: 18, fontWeight: 600, color: T1 }}>{price}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: T3 }}>{km}</span>
      </div>
    </motion.div>
  )
}
function Marketplace() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] })
  const reduced = useReducedMotion()
  const zero = useMotionValue(0)
  const depth = reduced ? zero : scrollYProgress
  return (
    <Section id="platform">
      <div ref={ref} style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.05fr)', gap: 'clamp(32px,5vw,72px)', alignItems: 'center' }}>
        <div>
          <Reveal><p style={{ ...eyebrow, marginBottom: 20 }}>El marketplace, unificado</p></Reveal>
          <Kinetic style={{ fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em', color: T1 }}
            lines={['Siete portales.', 'Seis idiomas.', <span key="u" style={{ color: INDIGO_SOFT }}>Una sola búsqueda.</span>]} />
          <Reveal delay={0.2} style={{ marginTop: 24 }}><p style={lead}>Deja de saltar entre AutoScout24, mobile.de, coches.net y cuatro pestañas más. CARDEX indexa el inventario de seis países, lo deduplica y te lleva al anuncio real con un deep-link directo.</p></Reveal>
        </div>
        <div style={{ position: 'relative', height: 340 }}>
          <Glow x="55%" y="45%" size={420} />
          <FloatCard p={PORTALS[1]} model="BMW Serie 3 320d" price="18.450 €" km="64.200 km" base={10} depth={depth} />
          <FloatCard p={PORTALS[0]} model="Audi A4 Avant 40 TDI" price="24.900 €" km="41.800 km" base={70} depth={depth} />
          <FloatCard p={PORTALS[2]} model="Mercedes Clase C 220" price="27.300 €" km="38.500 km" base={150} depth={depth} />
        </div>
      </div>
    </Section>
  )
}

/* 3 · Brand marquee */
function BrandStrip() {
  return (
    <Section bg="#07070f" style={{ padding: 'clamp(44px,5vw,72px) clamp(20px,5vw,72px)' }}>
      <Reveal>
        <div style={{ textAlign: 'center', fontSize: 11, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', color: T4, marginBottom: 30 }}>Toda marca. Todo modelo. Todo el catálogo europeo.</div>
        <Marquee duration={44}>
          {MARQUEE_BRANDS.map(n => <span key={n} style={{ display: 'flex', alignItems: 'center', height: 30, flexShrink: 0 }}><BrandMark name={n} box={26} /></span>)}
        </Marquee>
      </Reveal>
    </Section>
  )
}

/* 4 · Intelligence bento (looping micro-motion) */
function Pill({ live }: { live?: boolean }) {
  return <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '3px 8px', borderRadius: 999, color: live ? EMERALD : INDIGO_SOFT, background: live ? 'rgba(52,211,153,0.1)' : 'rgba(99,102,241,0.12)', border: `1px solid ${live ? 'rgba(52,211,153,0.25)' : 'rgba(99,102,241,0.25)'}` }}>{live ? 'En vivo' : 'Pronto'}</span>
}
function Tile({ children, style, live, label }: { children: React.ReactNode; style?: React.CSSProperties; live?: boolean; label: string }) {
  return (
    <motion.div variants={childV}>
      <Tilt style={{ height: '100%' }}>
        <div style={{ ...glassTile, padding: 22, display: 'flex', flexDirection: 'column', position: 'relative', height: '100%', boxSizing: 'border-box', ...style }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.04em', color: T2 }}>{label}</span><Pill live={live} />
          </div>
          {children}
        </div>
      </Tilt>
    </motion.div>
  )
}
function Sparkline() {
  return (
    <svg width="100%" height="34" viewBox="0 0 120 34" preserveAspectRatio="none" style={{ marginTop: 10 }}>
      <motion.path d="M0 26 L20 22 L40 24 L60 14 L80 17 L100 8 L120 11" fill="none" stroke={INDIGO_SOFT} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1.4, ease: EXPO }} />
    </svg>
  )
}
function IntelligenceBento() {
  const [fi, setFi] = useState(0)
  useEffect(() => { const id = setInterval(() => setFi(f => (f + 1) % PAISES.length), 1700); return () => clearInterval(id) }, [])
  return (
    <Section bg="#0a0a16">
      <Glow x="80%" y="20%" size={560} color="rgba(124,58,237,0.1)" />
      <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>Inteligencia, no solo listados</p></Reveal>
      <Kinetic style={{ fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em', color: T1, maxWidth: '20ch' }}
        lines={['La capa que un', <span key="v" style={{ color: INDIGO_SOFT }}>valuador no te da.</span>]} />
      <Reveal delay={0.18} style={{ marginTop: 18 }}><p style={lead}>El expediente del vehículo ya está en vivo. La inteligencia de arbitraje y fiscalidad llega después — diseñada desde el primer día.</p></Reveal>

      <Stagger style={{ marginTop: 44, display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gridAutoRows: 'minmax(158px,auto)', gap: 16 }}>
        <Tile label="CARDEX Check · Expediente" live style={{ gridColumn: 'span 2', gridRow: 'span 2' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div style={{ fontSize: 'clamp(1.2rem,1rem+0.7vw,1.5rem)', fontWeight: 650, color: T1, letterSpacing: '-0.02em', lineHeight: 1.15 }}>Una matrícula. El historial completo.</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 18 }}>
              {['Identidad VIN', 'ITV e inspecciones', 'EuroNCAP', 'Recalls UE (RAPEX)', 'Titulares y bajas', 'Embargo / robo'].map((x, i) => (
                <motion.div key={x} initial={{ opacity: 0, x: -8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.3 + i * 0.07, duration: 0.5, ease: EXPO }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T2 }}>
                  <svg width={13} height={13} viewBox="0 0 14 14"><path d="M11.5 4L5.8 10 2.5 6.8" stroke={EMERALD} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>{x}
                </motion.div>
              ))}
            </div>
            <div style={{ marginTop: 18, fontSize: 11.5, color: T4 }}>NL · ES · FR · BE · DE · CH · enriquecido con DGT MATRABA en España</div>
          </div>
        </Tile>

        <Tile label="Net Landed Cost" style={{ gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: T3, marginBottom: 8 }}>Coste real de importar a</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {PAISES.map((p, i) => (
                  <span key={p.code} style={{ width: 26, height: 18, borderRadius: 4, overflow: 'hidden', border: `1.5px solid ${i === fi ? INDIGO : 'transparent'}`, opacity: i === fi ? 1 : 0.45, transition: 'opacity 0.4s, border-color 0.4s' }}>
                    <img src={p.flag} alt={p.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </span>
                ))}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <motion.div key={fi} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EXPO }} style={{ fontFamily: MONO, fontSize: 26, fontWeight: 600, color: T1 }}>{fmt(19850 + fi * 640)} €</motion.div>
              <div style={{ fontSize: 11, color: EMERALD, fontFamily: MONO }}>margen estimado</div>
            </div>
          </div>
        </Tile>

        <Tile label="Régimen fiscal">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <motion.span animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 3, repeat: Infinity, times: [0, 0.5, 1] }} style={{ alignSelf: 'flex-start', fontSize: 15, fontWeight: 700, color: INDIGO_SOFT, padding: '6px 12px', borderRadius: 10, background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.22)' }}>IVA deducible</motion.span>
            <span style={{ fontSize: 12, color: T3 }}>vs REBU · clasificación trazable</span>
          </div>
        </Tile>

        <Tile label="Seller Desperation Index">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <svg width={56} height={56} viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="23" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="5" />
              <motion.circle cx="28" cy="28" r="23" fill="none" stroke={INDIGO} strokeWidth="5" strokeLinecap="round" strokeDasharray="144" transform="rotate(-90 28 28)"
                initial={{ strokeDashoffset: 144 }} whileInView={{ strokeDashoffset: 44 }} viewport={{ once: true }} transition={{ duration: 1.4, ease: EXPO }} />
            </svg>
            <div><div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 600, color: T1 }}><Counter to={69} duration={1.4} /></div><div style={{ fontSize: 11, color: T3 }}>urgencia de venta</div><Sparkline /></div>
          </div>
        </Tile>
      </Stagger>
      <Reveal delay={0.1}><p style={{ fontSize: 11, color: T4, marginTop: 18 }}>La clasificación fiscal es orientativa. El régimen definitivo lo confirma el despacho aduanero.</p></Reveal>
    </Section>
  )
}

/* 5 · Arbitrage map (signature, animated) + live ticker */
function ArbitrageMap() {
  return (
    <Section id="coverage">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,0.82fr) minmax(0,1.18fr)', gap: 'clamp(32px,5vw,64px)', alignItems: 'center' }}>
        <div>
          <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>Cobertura · arbitraje</p></Reveal>
          <Kinetic style={{ fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em', color: T1 }}
            lines={['El margen vive', <span key="b" style={{ color: INDIGO_SOFT }}>en la frontera.</span>]} />
          <Reveal delay={0.18} style={{ marginTop: 22 }}><p style={lead}>CARDEX nace cubriendo seis mercados a la vez y midiendo el diferencial entre ellos. El mismo coche, comprado en un país y vendido en otro, cambia de margen.</p></Reveal>
          {/* live ticker */}
          <Reveal delay={0.3} style={{ marginTop: 28 }}>
            <div style={{ ...glassTile, padding: '12px 14px', overflow: 'hidden' }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: T4, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <motion.span style={{ width: 6, height: 6, borderRadius: 999, background: EMERALD }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.6, repeat: Infinity }} />Oportunidades detectadas
              </div>
              <div style={{ height: 96, overflow: 'hidden', position: 'relative' }}>
                <motion.div animate={{ y: ['0%', '-50%'] }} transition={{ duration: 12, ease: 'linear', repeat: Infinity }}>
                  {[...OPPS, ...OPPS].map((o, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 0', borderBottom: `1px solid ${HAIR}` }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T2 }}>
                        <img src={NODE[o.from].flag} alt="" style={{ width: 16, height: 11, borderRadius: 2 }} />
                        <svg width={12} height={12} viewBox="0 0 12 12"><path d="M2 6h7M6 3l3 3-3 3" stroke={T4} strokeWidth={1.4} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                        <img src={NODE[o.to].flag} alt="" style={{ width: 16, height: 11, borderRadius: 2 }} />
                        <span style={{ marginLeft: 4 }}>{o.car}</span>
                      </span>
                      <span style={{ fontFamily: MONO, fontSize: 13, fontWeight: 600, color: EMERALD }}>{o.delta}</span>
                    </div>
                  ))}
                </motion.div>
              </div>
            </div>
          </Reveal>
        </div>

        {/* animated map */}
        <Reveal delay={0.1}>
          <div style={{ position: 'relative' }}>
            <Glow x="50%" y="45%" size={520} color="rgba(99,102,241,0.14)" />
            <svg viewBox="0 0 500 420" style={{ width: '100%', height: 'auto', overflow: 'visible' }}>
              <defs>
                <linearGradient id="rl" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="rgba(165,180,252,0)" /><stop offset="0.5" stopColor="rgba(165,180,252,0.9)" /><stop offset="1" stopColor="rgba(165,180,252,0)" /></linearGradient>
              </defs>
              {ROUTES.map(([a, b], i) => {
                const A = NODE[a], B = NODE[b]
                return (
                  <g key={i}>
                    <motion.line x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke="rgba(255,255,255,0.1)" strokeWidth={1}
                      initial={{ pathLength: 0, opacity: 0 }} whileInView={{ pathLength: 1, opacity: 1 }} viewport={{ once: true }} transition={{ duration: 1, ease: EXPO, delay: 0.2 + i * 0.08 }} />
                    <motion.circle cx={A.x} cy={A.y} r={3} fill={INDIGO_SOFT} style={{ filter: `drop-shadow(0 0 5px ${INDIGO})` }}
                      initial={{ x: 0, y: 0, opacity: 0 }} animate={{ x: [0, B.x - A.x], y: [0, B.y - A.y], opacity: [0, 1, 1, 0] }}
                      transition={{ duration: 2.8, ease: 'easeInOut', repeat: Infinity, delay: i * 0.5 }} />
                  </g>
                )
              })}
              {PAISES.map((p, i) => (
                <g key={p.code}>
                  <motion.circle cx={p.x} cy={p.y} r={20} fill="rgba(99,102,241,0.12)" initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.1, type: 'spring', stiffness: 200, damping: 14 }}
                    style={{ transformOrigin: `${p.x}px ${p.y}px` }} />
                  <motion.circle cx={p.x} cy={p.y} r={20} fill="none" stroke={INDIGO} strokeWidth={1.5} style={{ transformOrigin: `${p.x}px ${p.y}px` }} animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }} transition={{ duration: 3, repeat: Infinity, delay: i * 0.4 }} />
                  <motion.circle cx={p.x} cy={p.y} r={13} fill="#0a0a16" stroke={INDIGO_SOFT} strokeWidth={1.5} initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.15 + i * 0.1, type: 'spring', stiffness: 220, damping: 14 }} style={{ transformOrigin: `${p.x}px ${p.y}px` }} />
                  <motion.text x={p.x} y={p.y + 38} textAnchor="middle" fill={T2} fontSize={11} fontWeight={600} initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: 0.4 + i * 0.1 }}>{p.label}</motion.text>
                </g>
              ))}
            </svg>
          </div>
        </Reveal>
      </div>
    </Section>
  )
}

/* 6 · Comparison */
const CMP_ROWS = [
  { f: 'Cobertura de 6 países en un índice', valuer: false, market: 'parcial', cardex: true },
  { f: 'Expediente completo del vehículo (VIN · ITV · NCAP · recalls)', valuer: false, market: false, cardex: true },
  { f: 'Deep-link al anuncio real, deduplicado', valuer: false, market: 'parcial', cardex: true },
  { f: 'Sindicación multi-portal desde un panel', valuer: false, market: false, cardex: true },
  { f: 'CRM operativo (inbox · deals · P&L)', valuer: false, market: false, cardex: true },
  { f: 'Coste aterrizado y fiscalidad cross-border', valuer: false, market: false, cardex: 'roadmap' },
]
function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <motion.svg width={18} height={18} viewBox="0 0 18 18" initial={{ scale: 0.5, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ once: true }} transition={{ type: 'spring', stiffness: 300, damping: 16 }}><circle cx="9" cy="9" r="9" fill="rgba(52,211,153,0.14)" /><path d="M13.5 6L7.8 12 4.5 8.8" stroke={EMERALD} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></motion.svg>
  if (v === 'parcial') return <span style={{ fontSize: 11.5, color: T4 }}>parcial</span>
  if (v === 'roadmap') return <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: INDIGO_SOFT }}>Pronto</span>
  return <span style={{ display: 'inline-block', width: 14, height: 1.5, background: 'rgba(255,255,255,0.18)' }} />
}
function Comparison() {
  return (
    <Section bg="#0a0a16">
      <Kinetic style={{ fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em', color: T1, maxWidth: '24ch', marginBottom: 44 }}
        lines={['Un valuador te da un número.', <span key="s" style={{ color: T3 }}>CARDEX te da el sistema.</span>]} />
      <Reveal delay={0.1}>
        <div style={{ ...glassTile, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr 1fr 1fr', padding: '16px 22px', borderBottom: `1px solid ${HAIR}`, alignItems: 'center' }}>
            <span />
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: T4, textAlign: 'center' }}>Valuador</span>
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: T4, textAlign: 'center' }}>Marketplace</span>
            <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', textAlign: 'center', background: 'linear-gradient(120deg,#c4b5fd,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>CARDEX</span>
          </div>
          {CMP_ROWS.map((r, i) => (
            <motion.div key={r.f} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-6% 0px' }} transition={{ duration: 0.5, ease: EXPO, delay: i * 0.05 }}
              style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr 1fr 1fr', padding: '15px 22px', borderBottom: i < CMP_ROWS.length - 1 ? `1px solid ${HAIR}` : 'none', alignItems: 'center' }}>
              <span style={{ fontSize: 13.5, color: T2 }}>{r.f}</span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.valuer} /></span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.market} /></span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Cell v={r.cardex} /></span>
            </motion.div>
          ))}
        </div>
      </Reveal>
    </Section>
  )
}

/* 7 · How it works */
const STEPS = [
  { n: '01', t: 'Indexamos', b: 'Indexación sitemap-first del inventario de cada dealer en seis países. Deep-links al anuncio real, deduplicados — sin atacar APIs frontales.' },
  { n: '02', t: 'Verificamos', b: 'Cada matrícula se convierte en un expediente: identidad VIN, ITV, EuroNCAP, recalls RAPEX y banderas legales. En España, enriquecido con el microdato oficial de la DGT.' },
  { n: '03', t: 'Operas', b: 'Gestiona leads, deals y P&L de flota en un solo panel, y publica a AutoScout24, mobile.de, coches.net y leboncoin desde un clic.' },
]
function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 70%', 'end 60%'] })
  const h = useTransform(scrollYProgress, [0, 1], ['0%', '100%'])
  return (
    <Section id="pricing">
      <Reveal style={{ marginBottom: 56 }}><p style={{ ...eyebrow, marginBottom: 18 }}>Cómo funciona</p><h2 style={{ fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.05, fontWeight: 700, letterSpacing: '-0.03em', color: T1, margin: 0, maxWidth: '16ch' }}>Del inventario crudo a la decisión.</h2></Reveal>
      <div ref={ref} style={{ position: 'relative', paddingLeft: 'clamp(40px,6vw,72px)' }}>
        <div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, bottom: 6, width: 2, background: HAIR }} />
        <motion.div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, width: 2, height: h, background: `linear-gradient(${INDIGO},${INDIGO_SOFT})`, transformOrigin: 'top', boxShadow: `0 0 12px ${INDIGO}` }} />
        {STEPS.map((s, i) => (
          <Reveal key={s.n} style={{ position: 'relative', paddingBottom: i < STEPS.length - 1 ? 'clamp(40px,5vw,64px)' : 0 }}>
            <div style={{ position: 'absolute', left: 'calc(clamp(15px,2.4vw,28px) - clamp(40px,6vw,72px) - 6px)', top: 2, width: 14, height: 14, borderRadius: 999, background: '#07070f', border: `2px solid ${INDIGO_SOFT}` }} />
            <div style={{ fontFamily: MONO, fontSize: 13, color: INDIGO_SOFT, marginBottom: 10 }}>{s.n}</div>
            <h3 style={{ fontSize: 'clamp(1.3rem,1rem+1vw,1.7rem)', fontWeight: 650, letterSpacing: '-0.02em', color: T1, margin: '0 0 10px' }}>{s.t}</h3>
            <p style={{ ...lead, fontSize: '1rem' }}>{s.b}</p>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* 8 · Final CTA */
function FinalCta({ onEnter }: { onEnter: () => void }) {
  return (
    <Section bg="#07070f" style={{ textAlign: 'center', paddingTop: 'clamp(110px,13vw,200px)', paddingBottom: 'clamp(110px,13vw,200px)' }}>
      <Glow x="50%" y="42%" size={760} color="rgba(99,102,241,0.16)" />
      <Kinetic style={{ fontSize: 'clamp(2.5rem,1.2rem+5vw,5.4rem)', lineHeight: 1.0, fontWeight: 700, letterSpacing: '-0.045em', color: T1, maxWidth: '15ch', margin: '0 auto', textAlign: 'center' }}
        lines={['Deja de buscar', <span key="x" style={{ background: 'linear-gradient(120deg,#c4b5fd,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>en siete sitios.</span>]} />
      <Reveal delay={0.2} style={{ marginTop: 24 }}><p style={{ ...lead, margin: '0 auto', textAlign: 'center' }}>La inteligencia del mercado europeo de usados, en un solo sistema. Empieza por un país, escala a los seis.</p></Reveal>
      <Reveal delay={0.3} style={{ marginTop: 40, display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}>
        <Magnetic>
          <motion.button onClick={onEnter} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }} transition={{ type: 'spring', stiffness: 300, damping: 18 }}
            style={{ padding: '16px 36px', borderRadius: 14, background: 'linear-gradient(120deg,#6366f1,#7c3aed)', border: 'none', color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 0 50px rgba(99,102,241,0.5)' }}>
            Solicitar acceso
          </motion.button>
        </Magnetic>
        <motion.a href="#coverage" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          style={{ padding: '16px 30px', borderRadius: 14, background: 'rgba(255,255,255,0.05)', border: `1px solid ${HAIR_HI}`, color: T2, fontSize: 15, fontWeight: 600, cursor: 'pointer', textDecoration: 'none', display: 'inline-block' }}>Ver cobertura</motion.a>
      </Reveal>
    </Section>
  )
}

/* 9 · Footer */
function Footer() {
  const cols = [
    { h: 'Producto', items: ['Marketplace', 'Check / Expediente', 'CRM', 'Sindicación'] },
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
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: T4, marginBottom: 14 }}>{c.h}</div>
                {c.items.map(it => (
                  <a key={it} href="#" style={{ display: 'block', fontSize: 13.5, color: T3, textDecoration: 'none', padding: '5px 0', transition: 'color 0.18s' }}
                    onMouseEnter={e => (e.currentTarget.style.color = T1)} onMouseLeave={e => (e.currentTarget.style.color = T3)}>{it}</a>
                ))}
              </div>
            ))}
          </div>
        </Reveal>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginTop: 'clamp(40px,5vw,64px)', paddingTop: 24, borderTop: `1px solid ${HAIR}` }}>
          <span style={{ fontSize: 12, color: T4 }}>© 2026 CARDEX · La clasificación fiscal es orientativa.</span>
          <div style={{ display: 'flex', gap: 7 }}>{PAISES.map(p => <img key={p.code} src={p.flag} alt={p.label} style={{ width: 22, height: 15, borderRadius: 2, objectFit: 'cover', opacity: 0.7 }} />)}</div>
        </div>
      </div>
    </footer>
  )
}

export default function LandingSections({ onEnter }: { onEnter: () => void }) {
  return (
    <>
      <TrustScale />
      <Marketplace />
      <BrandStrip />
      <IntelligenceBento />
      <ArbitrageMap />
      <Comparison />
      <HowItWorks />
      <FinalCta onEnter={onEnter} />
      <Footer />
    </>
  )
}
