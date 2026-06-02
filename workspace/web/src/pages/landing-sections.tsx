import React, { useEffect, useRef, useState } from 'react'
import {
  motion, useInView, useScroll, useTransform, animate, useReducedMotion,
  type Variants,
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

const eyebrow: React.CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'rgba(196,181,253,0.85)', margin: 0 }
const lead: React.CSSProperties = { fontSize: 'clamp(1.02rem,0.96rem+0.4vw,1.22rem)', lineHeight: 1.6, color: T2, maxWidth: '52ch', margin: 0 }
const h2: React.CSSProperties = { fontSize: 'clamp(1.9rem,1.1rem+2.4vw,3.1rem)', lineHeight: 1.06, fontWeight: 700, letterSpacing: '-0.03em', color: T1, margin: 0 }
const glassTile: React.CSSProperties = { background: 'rgba(255,255,255,0.035)', border: `1px solid ${HAIR}`, borderRadius: 20, backdropFilter: 'blur(20px) saturate(150%)', WebkitBackdropFilter: 'blur(20px) saturate(150%)' }

/* ─── motion primitives ──────────────────────────────────────────────────── */
function Reveal({ children, y = 24, delay = 0, style }: { children: React.ReactNode; y?: number; delay?: number; style?: React.CSSProperties }) {
  const r = useReducedMotion()
  return (
    <motion.div style={style}
      initial={r ? { opacity: 1 } : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-10% 0px', amount: 0.2 }}
      transition={{ duration: 0.7, ease: EXPO, delay }}>
      {children}
    </motion.div>
  )
}
function ClipReveal({ children, style, delay = 0 }: { children: React.ReactNode; style?: React.CSSProperties; delay?: number }) {
  const r = useReducedMotion()
  return (
    <motion.div style={style}
      initial={r ? { opacity: 1 } : { opacity: 0, clipPath: 'inset(0 0 100% 0)' }}
      whileInView={{ opacity: 1, clipPath: 'inset(0 0 0% 0)' }}
      viewport={{ once: true, margin: '-12% 0px' }}
      transition={{ duration: 0.85, ease: EXPO, delay }}>
      {children}
    </motion.div>
  )
}
const parentV: Variants = { hidden: {}, visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } } }
const childV: Variants = { hidden: { opacity: 0, y: 22 }, visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EXPO } } }
function Stagger({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <motion.div style={style} variants={parentV} initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-8% 0px', amount: 0.15 }}>
      {children}
    </motion.div>
  )
}
function Counter({ to, suffix = '', duration = 1.6 }: { to: number; suffix?: string; duration?: number }) {
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
function Marquee({ children, duration = 34 }: { children: React.ReactNode; duration?: number }) {
  return (
    <div style={{ overflow: 'hidden', WebkitMaskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)', maskImage: 'linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)' }}>
      <motion.div style={{ display: 'flex', alignItems: 'center', gap: 44, width: 'max-content', willChange: 'transform' }}
        animate={{ x: ['0%', '-50%'] }} transition={{ duration, ease: 'linear', repeat: Infinity }}>
        {children}{children}
      </motion.div>
    </div>
  )
}

/* ─── layout ─────────────────────────────────────────────────────────────── */
function Section({ id, children, bg = '#07070f', style }: { id?: string; children: React.ReactNode; bg?: string; style?: React.CSSProperties }) {
  return (
    <section id={id} style={{ background: bg, padding: 'clamp(72px,9vw,140px) clamp(20px,5vw,72px)', position: 'relative', overflow: 'hidden', ...style }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', position: 'relative' }}>{children}</div>
    </section>
  )
}

/* ─── brand mark (for marquee) ───────────────────────────────────────────── */
const AR = LOGO_AR as Record<string, number>
function logoStyle(logo: string, box: number): React.CSSProperties {
  const base: React.CSSProperties = { width: 'auto', height: 'auto', objectFit: 'contain', filter: 'brightness(0) invert(1)', opacity: 0.55 }
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
  { code: 'de', label: 'Alemania', flag: 'https://flagcdn.com/w40/de.png' },
  { code: 'es', label: 'España', flag: 'https://flagcdn.com/w40/es.png' },
  { code: 'fr', label: 'Francia', flag: 'https://flagcdn.com/w40/fr.png' },
  { code: 'nl', label: 'Países Bajos', flag: 'https://flagcdn.com/w40/nl.png' },
  { code: 'be', label: 'Bélgica', flag: 'https://flagcdn.com/w40/be.png' },
  { code: 'ch', label: 'Suiza', flag: 'https://flagcdn.com/w40/ch.png' },
]
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

/* ════════════════════════ SECTIONS ════════════════════════ */

/* 1 · Trust / scale */
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

/* 2 · All-in-one marketplace */
function ListingCard({ portal, model, price, km, rot, x, y }: { portal: typeof PORTALS[number]; model: string; price: string; km: string; rot: number; x: number; y: number }) {
  return (
    <motion.div variants={{ hidden: { opacity: 0, y: 24, rotate: rot - 1 }, visible: { opacity: 1, y: 0, rotate: rot, transition: { duration: 0.7, ease: EXPO } } }}
      style={{ position: 'absolute', left: x, top: y, width: 260, ...glassTile, background: 'rgba(16,15,34,0.82)', borderRadius: 16, padding: 14, boxShadow: '0 24px 60px rgba(0,0,0,0.5)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11, fontWeight: 600, color: T3 }}>
          <span style={{ width: 16, height: 16, borderRadius: 4, background: portal.bg, overflow: 'hidden', display: 'inline-flex' }}><img src={portal.favicon} alt="" style={{ width: '100%', height: '100%' }} /></span>
          {portal.name}
        </span>
        <span style={{ fontSize: 10, color: T4 }}>{['DE', 'ES', 'FR', 'NL'][((rot % 4) + 4) % 4]}</span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: T1, marginBottom: 8 }}>{model}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontFamily: MONO, fontSize: 17, fontWeight: 600, color: T1 }}>{price}</span>
        <span style={{ fontFamily: MONO, fontSize: 12, color: T3 }}>{km}</span>
      </div>
    </motion.div>
  )
}
function Marketplace() {
  return (
    <Section id="platform">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.05fr)', gap: 'clamp(32px,5vw,72px)', alignItems: 'center' }}>
        <div>
          <p style={{ ...eyebrow, marginBottom: 18 }}>El marketplace, unificado</p>
          <ClipReveal>
            <h2 style={h2}>Siete portales.<br />Seis idiomas.<br /><span style={{ color: INDIGO_SOFT }}>Una sola búsqueda.</span></h2>
          </ClipReveal>
          <Reveal delay={0.15} style={{ marginTop: 22 }}>
            <p style={lead}>Deja de saltar entre AutoScout24, mobile.de, coches.net y cuatro pestañas más. CARDEX indexa el inventario de seis países, lo deduplica y te lleva al anuncio real con un deep-link directo.</p>
          </Reveal>
        </div>
        <Stagger style={{ position: 'relative', height: 320 }}>
          <div style={{ position: 'absolute', inset: '8% 4%', borderRadius: 24, background: 'radial-gradient(closest-side, rgba(99,102,241,0.18), transparent)', filter: 'blur(8px)' }} />
          <ListingCard portal={PORTALS[1]} model="BMW Serie 3 320d" price="18.450 €" km="64.200 km" rot={-4} x={20} y={20} />
          <ListingCard portal={PORTALS[0]} model="Audi A4 Avant 40 TDI" price="24.900 €" km="41.800 km" rot={3} x={150} y={90} />
          <ListingCard portal={PORTALS[2]} model="Mercedes Clase C 220" price="27.300 €" km="38.500 km" rot={-1} x={70} y={170} />
        </Stagger>
      </div>
    </Section>
  )
}

/* 3 · Intelligence bento */
function Pill({ live }: { live?: boolean }) {
  return (
    <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', padding: '3px 8px', borderRadius: 999, color: live ? EMERALD : INDIGO_SOFT, background: live ? 'rgba(52,211,153,0.1)' : 'rgba(99,102,241,0.12)', border: `1px solid ${live ? 'rgba(52,211,153,0.25)' : 'rgba(99,102,241,0.25)'}` }}>
      {live ? 'En vivo' : 'Pronto'}
    </span>
  )
}
function Tile({ children, style, live, label }: { children: React.ReactNode; style?: React.CSSProperties; live?: boolean; label?: string }) {
  return (
    <motion.div variants={childV} whileHover={{ y: -3 }} transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      style={{ ...glassTile, padding: 22, display: 'flex', flexDirection: 'column', position: 'relative', ...style }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.04em', color: T2 }}>{label}</span>
        <Pill live={live} />
      </div>
      {children}
    </motion.div>
  )
}
function IntelligenceBento() {
  const flags = PAISES
  const [fi, setFi] = useState(1)
  return (
    <Section bg="#0a0a16">
      <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>Inteligencia, no solo listados</p></Reveal>
      <ClipReveal><h2 style={{ ...h2, maxWidth: '18ch' }}>La capa que un valuador no te da.</h2></ClipReveal>
      <Reveal delay={0.12} style={{ marginTop: 18 }}><p style={lead}>El expediente del vehículo ya está en vivo. La inteligencia de arbitraje y fiscalidad llega después — diseñada desde el primer día.</p></Reveal>

      <Stagger style={{ marginTop: 44, display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gridAutoRows: 'minmax(150px,auto)', gap: 16 }}>
        {/* Dossier — live, large */}
        <Tile label="CARDEX Check · Expediente" live style={{ gridColumn: 'span 2', gridRow: 'span 2' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div style={{ fontSize: 'clamp(1.2rem,1rem+0.7vw,1.5rem)', fontWeight: 650, color: T1, letterSpacing: '-0.02em', lineHeight: 1.15 }}>Una matrícula. El historial completo.</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 18 }}>
              {['Identidad VIN', 'ITV e inspecciones', 'EuroNCAP', 'Recalls UE (RAPEX)', 'Titulares y bajas', 'Embargo / robo'].map(x => (
                <div key={x} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: T2 }}>
                  <svg width={13} height={13} viewBox="0 0 14 14"><path d="M11.5 4L5.8 10 2.5 6.8" stroke={EMERALD} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  {x}
                </div>
              ))}
            </div>
            <div style={{ marginTop: 18, fontSize: 11.5, color: T4 }}>NL · ES · FR · BE · DE · CH · enriquecido con DGT MATRABA en España</div>
          </div>
        </Tile>

        {/* NLC — roadmap */}
        <Tile label="Net Landed Cost" style={{ gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: T3, marginBottom: 6 }}>Coste real de importar a</div>
              <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                {flags.map((p, i) => (
                  <button key={p.code} onClick={() => setFi(i)} style={{ width: 26, height: 18, borderRadius: 4, overflow: 'hidden', border: `1.5px solid ${i === fi ? INDIGO : 'transparent'}`, padding: 0, cursor: 'pointer', background: 'none', opacity: i === fi ? 1 : 0.5 }}>
                    <img src={p.flag} alt={p.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </button>
                ))}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: MONO, fontSize: 26, fontWeight: 600, color: T1 }}>{fmt(19850 + fi * 640)} €</div>
              <div style={{ fontSize: 11, color: EMERALD, fontFamily: MONO }}>+ margen estimado</div>
            </div>
          </div>
        </Tile>

        {/* Fiscal — roadmap */}
        <Tile label="Régimen fiscal">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ alignSelf: 'flex-start', fontSize: 15, fontWeight: 700, color: INDIGO_SOFT, padding: '6px 12px', borderRadius: 10, background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.22)' }}>IVA deducible</span>
            <span style={{ fontSize: 12, color: T3 }}>vs REBU · clasificación trazable</span>
          </div>
        </Tile>

        {/* SDI — roadmap */}
        <Tile label="Seller Desperation Index">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <svg width={56} height={56} viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="23" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="5" />
              <circle cx="28" cy="28" r="23" fill="none" stroke={INDIGO} strokeWidth="5" strokeLinecap="round" strokeDasharray="144" strokeDashoffset="44" transform="rotate(-90 28 28)" />
            </svg>
            <div><div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 600, color: T1 }}>69</div><div style={{ fontSize: 11, color: T3 }}>urgencia de venta</div></div>
          </div>
        </Tile>
      </Stagger>
      <Reveal delay={0.1}><p style={{ fontSize: 11, color: T4, marginTop: 18 }}>La clasificación fiscal es orientativa. El régimen definitivo lo confirma el despacho aduanero.</p></Reveal>
    </Section>
  )
}

/* 4 · Coverage */
function Coverage() {
  return (
    <Section id="coverage">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,0.9fr) minmax(0,1.1fr)', gap: 'clamp(32px,5vw,72px)', alignItems: 'center' }}>
        <div>
          <Reveal><p style={{ ...eyebrow, marginBottom: 18 }}>Cobertura</p></Reveal>
          <ClipReveal><h2 style={h2}>Seis países.<br /><span style={{ color: INDIGO_SOFT }}>Un solo mercado.</span></h2></ClipReveal>
          <Reveal delay={0.14} style={{ marginTop: 22 }}><p style={lead}>El margen vive en las fronteras. CARDEX nace cubriendo los seis mercados a la vez, para que veas el inventario completo del territorio — no una muestra de un país.</p></Reveal>
        </div>
        <Stagger style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
          {PAISES.map(p => (
            <motion.div key={p.code} variants={childV} whileHover={{ y: -3 }} transition={{ type: 'spring', stiffness: 300, damping: 26 }}
              style={{ ...glassTile, padding: 18, display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'flex-start' }}>
              <img src={p.flag} alt={p.label} style={{ width: 34, height: 24, borderRadius: 4, objectFit: 'cover', boxShadow: '0 2px 8px rgba(0,0,0,0.4)' }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T1 }}>{p.label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: EMERALD, marginTop: 4 }}>
                  <span style={{ width: 6, height: 6, borderRadius: 999, background: EMERALD, boxShadow: `0 0 8px ${EMERALD}` }} /> Indexado
                </div>
              </div>
            </motion.div>
          ))}
        </Stagger>
      </div>
    </Section>
  )
}

/* 5 · Comparison */
const CMP_ROWS = [
  { f: 'Cobertura de 6 países en un índice', valuer: false, market: 'parcial', cardex: true },
  { f: 'Expediente completo del vehículo (VIN · ITV · NCAP · recalls)', valuer: false, market: false, cardex: true },
  { f: 'Deep-link al anuncio real, deduplicado', valuer: false, market: 'parcial', cardex: true },
  { f: 'Sindicación multi-portal desde un panel', valuer: false, market: false, cardex: true },
  { f: 'CRM operativo (inbox · deals · P&L)', valuer: false, market: false, cardex: true },
  { f: 'Coste aterrizado y fiscalidad cross-border', valuer: false, market: false, cardex: 'roadmap' },
]
function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <svg width={18} height={18} viewBox="0 0 18 18"><circle cx="9" cy="9" r="9" fill="rgba(52,211,153,0.14)" /><path d="M13.5 6L7.8 12 4.5 8.8" stroke={EMERALD} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
  if (v === 'parcial') return <span style={{ fontSize: 11.5, color: T4 }}>parcial</span>
  if (v === 'roadmap') return <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: INDIGO_SOFT }}>Pronto</span>
  return <span style={{ display: 'inline-block', width: 14, height: 1.5, background: 'rgba(255,255,255,0.18)' }} />
}
function Comparison() {
  return (
    <Section bg="#0a0a16">
      <Reveal style={{ maxWidth: '24ch', marginBottom: 44 }}>
        <h2 style={h2}>Un valuador te da un número. <span style={{ color: T3 }}>CARDEX te da el sistema.</span></h2>
      </Reveal>
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
              style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr 1fr 1fr', padding: '15px 22px', borderBottom: i < CMP_ROWS.length - 1 ? `1px solid ${HAIR}` : 'none', alignItems: 'center', background: 'transparent' }}>
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

/* 6 · How it works */
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
      <Reveal style={{ marginBottom: 56 }}><p style={{ ...eyebrow, marginBottom: 18 }}>Cómo funciona</p><h2 style={{ ...h2, maxWidth: '16ch' }}>Del inventario crudo a la decisión.</h2></Reveal>
      <div ref={ref} style={{ position: 'relative', paddingLeft: 'clamp(40px,6vw,72px)' }}>
        <div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, bottom: 6, width: 2, background: HAIR }} />
        <motion.div style={{ position: 'absolute', left: 'clamp(15px,2.4vw,28px)', top: 6, width: 2, height: h, background: `linear-gradient(${INDIGO},${INDIGO_SOFT})`, transformOrigin: 'top', boxShadow: `0 0 12px ${INDIGO}` }} />
        {STEPS.map((s, i) => (
          <Reveal key={s.n} delay={0} style={{ position: 'relative', paddingBottom: i < STEPS.length - 1 ? 'clamp(40px,5vw,64px)' : 0 }}>
            <div style={{ position: 'absolute', left: 'calc(clamp(15px,2.4vw,28px) - clamp(40px,6vw,72px) - 6px)', top: 2, width: 14, height: 14, borderRadius: 999, background: '#0a0a16', border: `2px solid ${INDIGO_SOFT}` }} />
            <div style={{ fontFamily: MONO, fontSize: 13, color: INDIGO_SOFT, marginBottom: 10 }}>{s.n}</div>
            <h3 style={{ fontSize: 'clamp(1.3rem,1rem+1vw,1.7rem)', fontWeight: 650, letterSpacing: '-0.02em', color: T1, margin: '0 0 10px' }}>{s.t}</h3>
            <p style={{ ...lead, fontSize: '1rem' }}>{s.b}</p>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* 7 · Final CTA */
function FinalCta({ onEnter }: { onEnter: () => void }) {
  return (
    <Section bg="#07070f" style={{ textAlign: 'center', paddingTop: 'clamp(96px,12vw,180px)', paddingBottom: 'clamp(96px,12vw,180px)' }}>
      <motion.div aria-hidden style={{ position: 'absolute', top: '40%', left: '50%', width: 640, height: 640, marginLeft: -320, marginTop: -320, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(99,102,241,0.18), transparent)', filter: 'blur(20px)', pointerEvents: 'none' }}
        animate={{ scale: [1, 1.12, 1], opacity: [0.7, 1, 0.7] }} transition={{ duration: 9, ease: 'easeInOut', repeat: Infinity }} />
      <ClipReveal><h2 style={{ fontSize: 'clamp(2.4rem,1.2rem+4.6vw,5rem)', lineHeight: 1.02, fontWeight: 700, letterSpacing: '-0.04em', color: T1, margin: '0 auto', maxWidth: '14ch' }}>Deja de buscar en siete sitios.</h2></ClipReveal>
      <Reveal delay={0.15} style={{ marginTop: 20 }}><p style={{ ...lead, margin: '0 auto', textAlign: 'center' }}>La inteligencia del mercado europeo de usados, en un solo sistema. Empieza por un país, escala a los seis.</p></Reveal>
      <Reveal delay={0.25} style={{ marginTop: 36, display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
        <motion.button onClick={onEnter} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          style={{ padding: '15px 32px', borderRadius: 14, background: 'linear-gradient(120deg,#6366f1,#7c3aed)', border: 'none', color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 0 40px rgba(99,102,241,0.45)' }}>
          Solicitar acceso
        </motion.button>
        <motion.a href="#coverage" whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          style={{ padding: '15px 28px', borderRadius: 14, background: 'rgba(255,255,255,0.05)', border: `1px solid ${HAIR_HI}`, color: T2, fontSize: 15, fontWeight: 600, cursor: 'pointer', textDecoration: 'none', display: 'inline-block' }}>
          Ver cobertura
        </motion.a>
      </Reveal>
    </Section>
  )
}

/* 8 · Footer */
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
          <div style={{ display: 'flex', gap: 7 }}>
            {PAISES.map(p => <img key={p.code} src={p.flag} alt={p.label} style={{ width: 22, height: 15, borderRadius: 2, objectFit: 'cover', opacity: 0.7 }} />)}
          </div>
        </div>
      </div>
    </footer>
  )
}

/* ─── brand marquee strip ────────────────────────────────────────────────── */
function BrandStrip() {
  return (
    <Section bg="#07070f" style={{ paddingTop: 'clamp(40px,5vw,64px)', paddingBottom: 'clamp(40px,5vw,64px)' }}>
      <Reveal>
        <div style={{ textAlign: 'center', fontSize: 11, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', color: T4, marginBottom: 30 }}>Toda marca. Todo modelo. Todo el catálogo europeo.</div>
        <Marquee duration={42}>
          {MARQUEE_BRANDS.map(n => (
            <span key={n} style={{ display: 'flex', alignItems: 'center', height: 30, flexShrink: 0 }}><BrandMark name={n} box={26} /></span>
          ))}
        </Marquee>
      </Reveal>
    </Section>
  )
}

/* ─── exported composition ───────────────────────────────────────────────── */
export default function LandingSections({ onEnter }: { onEnter: () => void }) {
  return (
    <>
      <TrustScale />
      <Marketplace />
      <BrandStrip />
      <IntelligenceBento />
      <Coverage />
      <Comparison />
      <HowItWorks />
      <FinalCta onEnter={onEnter} />
      <Footer />
    </>
  )
}
