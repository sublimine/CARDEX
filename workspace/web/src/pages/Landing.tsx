import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useScroll, useTransform, AnimatePresence, useMotionValue, useSpring } from 'framer-motion'
import {
  ArrowUpRight, Shield, Zap, Globe, TrendingUp,
  ChevronRight, MapPin, Activity, Check, Car,
  BarChart3, AlertCircle, Sparkles,
} from 'lucide-react'

// ─── Design tokens ────────────────────────────────────────────────────────────
const C = {
  bg:     '#020208',
  s1:     'rgba(255,255,255,0.03)',
  s2:     'rgba(255,255,255,0.06)',
  border: 'rgba(255,255,255,0.07)',
  borderHi: 'rgba(255,255,255,0.13)',
  blue:   '#3b82f6',
  indigo: '#6366f1',
  purple: '#a855f7',
  teal:   '#06b6d4',
  emerald:'#10b981',
  amber:  '#f59e0b',
  rose:   '#f43f5e',
  t1:     '#f1f5f9',
  t2:     '#94a3b8',
  t3:     '#475569',
  t4:     '#1e293b',
}

const EASE = [0.22, 1, 0.36, 1] as const

// ─── Data ─────────────────────────────────────────────────────────────────────
const VEHICLES = [
  {
    id: 1,
    photo: 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=700&q=85&auto=format&fit=crop',
    make: 'BMW', model: 'M3 Competition', year: 2022,
    city: 'Munich', flag: '🇩🇪', country: 'DE',
    price: '€ 58.900', km: '24.500 km',
    regime: 'IVA Deductible', regimeColor: C.emerald,
    nlc: '€ 62.340', dest: '🇪🇸 Spain',
    sdi: 8.2, sdiColor: C.rose,
  },
  {
    id: 2,
    photo: 'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=700&q=85&auto=format&fit=crop',
    make: 'Mercedes', model: 'C 220d AMG Line', year: 2021,
    city: 'Paris', flag: '🇫🇷', country: 'FR',
    price: '€ 28.400', km: '41.200 km',
    regime: 'REBU', regimeColor: C.amber,
    nlc: '€ 31.200', dest: '🇳🇱 Netherlands',
    sdi: 5.1, sdiColor: C.teal,
  },
  {
    id: 3,
    photo: 'https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=700&q=85&auto=format&fit=crop',
    make: 'Audi', model: 'A4 2.0 TDI S-Line', year: 2023,
    city: 'Amsterdam', flag: '🇳🇱', country: 'NL',
    price: '€ 34.500', km: '18.900 km',
    regime: 'IVA Deductible', regimeColor: C.emerald,
    nlc: '€ 36.800', dest: '🇧🇪 Belgium',
    sdi: 6.7, sdiColor: C.blue,
  },
  {
    id: 4,
    photo: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=700&q=85&auto=format&fit=crop',
    make: 'Porsche', model: '911 Carrera S', year: 2020,
    city: 'Zurich', flag: '🇨🇭', country: 'CH',
    price: '€ 89.900', km: '31.600 km',
    regime: 'IVA Deductible', regimeColor: C.emerald,
    nlc: '€ 94.100', dest: '🇩🇪 Germany',
    sdi: 9.1, sdiColor: C.rose,
  },
]

const STATS = [
  { value: 3_500_000, prefix: '', suffix: '+', label: 'Vehicles indexed', short: '3.5M+' },
  { value: 6, prefix: '', suffix: '', label: 'EU countries', short: '6' },
  { value: 2500, prefix: '', suffix: '+', label: 'Dealer sources', short: '2.5K+' },
  { value: 2, prefix: '< ', suffix: 's', label: 'Classification', short: '< 2s' },
]

const FEATURES = [
  {
    icon: TrendingUp, color: C.blue,
    title: 'Fiscal intelligence',
    desc: 'Automatic IVA / REBU classification for every listing. Full traceability to the prompt and model that produced each decision.',
  },
  {
    icon: Globe, color: C.purple,
    title: 'Pan-European coverage',
    desc: 'DE · ES · FR · NL · BE · CH. Sitemap-first indexing from every dealer. Nothing abandoned mid-pagination.',
  },
  {
    icon: Zap, color: C.teal,
    title: 'Real-time pipeline',
    desc: 'Redis Streams at-least-once delivery. Scraped → normalized → classified in under 2 seconds per listing.',
  },
  {
    icon: Shield, color: C.emerald,
    title: 'Arbitrage engine',
    desc: 'Net Landed Cost per destination country. Seller Desperation Index on every listing. Margin computed before you call.',
  },
  {
    icon: BarChart3, color: C.amber,
    title: 'Price intelligence',
    desc: 'Historical price tracking with delta events. Know the moment a dealer drops a price — before your competitors.',
  },
  {
    icon: Activity, color: C.rose,
    title: 'Risk scoring',
    desc: 'SDI scores rank urgency. MATRABA flags, EuroNCAP safety, EU RAPEX alerts wired into every dossier.',
  },
]

const COUNTRIES = [
  { flag: '🇩🇪', name: 'Germany',     code: 'DE', count: '890K+' },
  { flag: '🇫🇷', name: 'France',      code: 'FR', count: '640K+' },
  { flag: '🇪🇸', name: 'Spain',       code: 'ES', count: '720K+' },
  { flag: '🇳🇱', name: 'Netherlands', code: 'NL', count: '380K+' },
  { flag: '🇧🇪', name: 'Belgium',     code: 'BE', count: '290K+' },
  { flag: '🇨🇭', name: 'Switzerland', code: 'CH', count: '180K+' },
]

// ─── Animated counter ─────────────────────────────────────────────────────────
function AnimNum({ to, prefix = '', suffix = '' }: { to: number; prefix?: string; suffix?: string }) {
  const mv = useMotionValue(0)
  const sp = useSpring(mv, { stiffness: 50, damping: 12 })
  const display = useTransform(sp, v => {
    const n = Math.round(v)
    if (n >= 1_000_000) return `${prefix}${(n / 1_000_000).toFixed(1)}M${suffix}`
    if (n >= 1_000)     return `${prefix}${(n / 1000).toFixed(0)}K${suffix}`
    return `${prefix}${n}${suffix}`
  })
  useEffect(() => { mv.set(to) }, [to])
  return <motion.span>{display}</motion.span>
}

// ─── Glass pill ───────────────────────────────────────────────────────────────
function Pill({ color, label }: { color: string; label: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 999,
      background: `${color}15`, border: `1px solid ${color}35`,
      fontSize: 11, fontWeight: 700, color,
      letterSpacing: '0.04em', textTransform: 'uppercase',
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: color, display: 'block' }} />
      {label}
    </span>
  )
}

// ─── SDI bar ──────────────────────────────────────────────────────────────────
function SDIBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${value * 10}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: EASE, delay: 0.2 }}
          style={{ height: '100%', background: color, borderRadius: 2 }}
        />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 24 }}>{value}</span>
    </div>
  )
}

// ─── Vehicle card ─────────────────────────────────────────────────────────────
function VehicleCard({ v, delay }: { v: typeof VEHICLES[0]; delay: number }) {
  const [hovered, setHovered] = useState(false)
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay, duration: 0.55, ease: EASE }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      style={{
        borderRadius: 20, overflow: 'hidden', cursor: 'pointer',
        background: C.s1,
        border: `1px solid ${hovered ? 'rgba(255,255,255,0.13)' : C.border}`,
        boxShadow: hovered ? '0 24px 60px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.06) inset' : '0 8px 24px rgba(0,0,0,0.3)',
        transform: hovered ? 'translateY(-4px)' : 'translateY(0)',
        transition: 'all 0.3s cubic-bezier(0.22,1,0.36,1)',
      }}
    >
      {/* Photo */}
      <div style={{ position: 'relative', height: 180, overflow: 'hidden' }}>
        <img
          src={v.photo}
          alt={`${v.make} ${v.model}`}
          style={{ width: '100%', height: '100%', objectFit: 'cover',
            transform: hovered ? 'scale(1.05)' : 'scale(1)',
            transition: 'transform 0.5s cubic-bezier(0.22,1,0.36,1)',
          }}
        />
        {/* Dark gradient overlay */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(2,2,8,0.9) 0%, rgba(2,2,8,0.2) 50%, transparent 100%)' }} />

        {/* Country badge */}
        <div style={{
          position: 'absolute', top: 12, left: 12,
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '4px 10px', borderRadius: 999,
          background: 'rgba(2,2,8,0.7)', backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255,255,255,0.1)',
          fontSize: 11, color: C.t2, fontWeight: 600,
        }}>
          <span>{v.flag}</span> {v.city}
        </div>

        {/* SDI urgency */}
        {v.sdi >= 8 && (
          <div style={{
            position: 'absolute', top: 12, right: 12,
            padding: '4px 10px', borderRadius: 999,
            background: `${v.sdiColor}20`, backdropFilter: 'blur(12px)',
            border: `1px solid ${v.sdiColor}40`,
            fontSize: 10, color: v.sdiColor, fontWeight: 800,
            letterSpacing: '0.06em',
          }}>
            HOT
          </div>
        )}

        {/* Year */}
        <div style={{ position: 'absolute', bottom: 12, left: 12, fontSize: 20, fontWeight: 900, color: C.t1, letterSpacing: '-0.03em' }}>
          {v.make} <span style={{ color: C.t2, fontWeight: 500 }}>{v.model}</span>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: '16px 18px 18px' }}>
        {/* Price row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontSize: 22, fontWeight: 900, color: C.t1, letterSpacing: '-0.03em' }}>{v.price}</span>
          <span style={{ fontSize: 12, color: C.t3 }}>{v.km} · {v.year}</span>
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
          <Pill color={v.regimeColor} label={v.regime} />
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: 'rgba(255,255,255,0.05)', marginBottom: 12 }} />

        {/* NLC */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 11, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>NLC → {v.dest}</span>
          <span style={{ fontSize: 13, fontWeight: 800, color: C.t1 }}>{v.nlc}</span>
        </div>

        {/* SDI */}
        <div style={{ marginBottom: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <span style={{ fontSize: 10, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Seller Desperation</span>
          </div>
          <SDIBar value={v.sdi} color={v.sdiColor} />
        </div>
      </div>
    </motion.div>
  )
}

// ─── Intelligence panel (hero right side) ────────────────────────────────────
function IntelligencePanel() {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setActive(a => (a + 1) % 2), 4000)
    return () => clearInterval(t)
  }, [])

  const v = VEHICLES[0]
  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: 460 }}>
      {/* Main intelligence card */}
      <motion.div
        initial={{ opacity: 0, x: 40, rotateY: 8 }}
        animate={{ opacity: 1, x: 0, rotateY: 0 }}
        transition={{ delay: 0.4, duration: 0.8, ease: EASE }}
        style={{
          background: 'rgba(255,255,255,0.04)',
          backdropFilter: 'blur(32px)',
          WebkitBackdropFilter: 'blur(32px)',
          border: '1px solid rgba(255,255,255,0.09)',
          borderRadius: 24,
          overflow: 'hidden',
          boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.07) inset',
        }}
      >
        {/* Card header */}
        <div style={{ padding: '14px 18px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: C.emerald, boxShadow: `0 0 10px ${C.emerald}` }} />
            <span style={{ fontSize: 11, fontWeight: 700, color: C.t2, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Live Intelligence</span>
          </div>
          <span style={{ fontSize: 10, color: C.t3 }}>2s ago</span>
        </div>

        {/* Photo */}
        <div style={{ position: 'relative', height: 180, overflow: 'hidden' }}>
          <img src={v.photo} alt="BMW M3" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(2,2,8,0.95) 0%, transparent 60%)' }} />
          <div style={{ position: 'absolute', bottom: 14, left: 16 }}>
            <div style={{ fontSize: 18, fontWeight: 900, color: C.t1 }}>{v.make} {v.model}</div>
            <div style={{ fontSize: 12, color: C.t2, display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
              <MapPin style={{ width: 10, height: 10 }} />{v.flag} {v.city} · {v.year}
            </div>
          </div>
        </div>

        {/* Data */}
        <div style={{ padding: '16px 18px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
            {[
              { label: 'Asking price', val: v.price, color: C.t1 },
              { label: 'Mileage', val: v.km, color: C.t2 },
              { label: 'Fiscal regime', val: 'IVA Ded.', color: C.emerald },
              { label: 'Classification', val: '< 2s', color: C.blue },
            ].map(item => (
              <div key={item.label} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '10px 12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ fontSize: 9, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: item.color }}>{item.val}</div>
              </div>
            ))}
          </div>

          {/* NLC row */}
          <div style={{ background: `${C.indigo}10`, border: `1px solid ${C.indigo}25`, borderRadius: 12, padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 9, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 2 }}>Net Landed Cost → 🇪🇸</div>
              <div style={{ fontSize: 18, fontWeight: 900, color: C.t1, letterSpacing: '-0.03em' }}>{v.nlc}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 9, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 2 }}>SDI Score</div>
              <div style={{ fontSize: 18, fontWeight: 900, color: v.sdiColor }}>{v.sdi}</div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Floating notification */}
      <motion.div
        initial={{ opacity: 0, x: -20, y: 10 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        transition={{ delay: 1.2, duration: 0.6, ease: EASE }}
        style={{
          position: 'absolute', bottom: -20, left: -24,
          background: 'rgba(16,185,129,0.08)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: `1px solid ${C.emerald}25`,
          borderRadius: 14, padding: '10px 14px',
          display: 'flex', alignItems: 'center', gap: 10,
          boxShadow: `0 8px 30px rgba(0,0,0,0.4), 0 0 0 1px ${C.emerald}10`,
        }}
      >
        <div style={{ width: 28, height: 28, borderRadius: 8, background: `${C.emerald}15`, border: `1px solid ${C.emerald}30`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Car style={{ width: 14, height: 14, color: C.emerald }} />
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.t1 }}>+847 new listings</div>
          <div style={{ fontSize: 10, color: C.t3 }}>indexed in last hour</div>
        </div>
      </motion.div>

      {/* Second float - accuracy */}
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 1.6, duration: 0.6, ease: EASE }}
        style={{
          position: 'absolute', top: -16, right: -20,
          background: `${C.blue}08`,
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: `1px solid ${C.blue}20`,
          borderRadius: 14, padding: '10px 14px',
          display: 'flex', alignItems: 'center', gap: 8,
          boxShadow: '0 8px 30px rgba(0,0,0,0.4)',
        }}
      >
        <Check style={{ width: 14, height: 14, color: C.blue }} strokeWidth={2.5} />
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: C.t1 }}>99.2% accuracy</div>
          <div style={{ fontSize: 10, color: C.t3 }}>REBU classification</div>
        </div>
      </motion.div>
    </div>
  )
}

// ─── Orb ──────────────────────────────────────────────────────────────────────
function Orb({ x, y, color, size, delay = 0 }: { x: string; y: string; color: string; size: number; delay?: number }) {
  return (
    <motion.div
      aria-hidden
      animate={{ scale: [1, 1.15, 1], opacity: [0.08, 0.13, 0.08] }}
      transition={{ duration: 8 + delay, repeat: Infinity, ease: 'easeInOut', delay }}
      style={{
        position: 'absolute', left: x, top: y, width: size, height: size,
        borderRadius: '50%', background: color, filter: `blur(${size * 0.5}px)`,
        pointerEvents: 'none',
      }}
    />
  )
}

// ─── Section label ────────────────────────────────────────────────────────────
function SectionLabel({ color, text }: { color: string; text: string }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '5px 14px', borderRadius: 999, background: `${color}0d`, border: `1px solid ${color}25`, marginBottom: 20 }}>
      <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, animation: 'cxPulse 2s infinite' }} />
      <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color }}>{text}</span>
    </div>
  )
}

// ─── Landing ──────────────────────────────────────────────────────────────────
export default function Landing() {
  const nav = useNavigate()
  const { scrollY } = useScroll()
  const navBg = useTransform(scrollY, [0, 80], ['rgba(2,2,8,0)', 'rgba(2,2,8,0.92)'])
  const navBorder = useTransform(scrollY, [0, 80], ['rgba(255,255,255,0)', 'rgba(255,255,255,0.06)'])

  const font = '"Inter", "Plus Jakarta Sans", system-ui, sans-serif'

  return (
    <div style={{ background: C.bg, minHeight: '100dvh', fontFamily: font, overflowX: 'hidden', color: C.t1 }}>

      {/* Noise */}
      <div aria-hidden style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.018,
        backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.85\' numOctaves=\'4\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")',
        backgroundSize: '160px',
      }} />

      {/* ── NAVBAR ──────────────────────────────────────────────────────────── */}
      <motion.nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 clamp(20px, 4vw, 48px)', height: 64,
        background: navBg, borderBottom: `1px solid`, borderColor: navBorder,
        backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 10, background: `linear-gradient(135deg, ${C.blue}20, ${C.indigo}20)`, border: `1px solid ${C.blue}30`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 0 20px ${C.blue}15` }}>
            <div style={{ width: 12, height: 12, borderRadius: 4, background: `linear-gradient(135deg, ${C.blue}, ${C.indigo})`, boxShadow: `0 0 12px ${C.blue}60` }} />
          </div>
          <span style={{ fontSize: 15, fontWeight: 900, letterSpacing: '0.18em', background: `linear-gradient(120deg, ${C.t1}, ${C.t2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            CARDEX
          </span>
        </div>

        {/* Nav links */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {['Platform', 'Coverage', 'Pricing'].map(l => (
            <button key={l} style={{ padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 500, color: C.t3, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: font, transition: 'color 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.color = C.t1)}
              onMouseLeave={e => (e.currentTarget.style.color = C.t3)}
            >{l}</button>
          ))}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => nav('/login')}
            style={{ padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600, color: C.t2, background: 'transparent', border: `1px solid rgba(255,255,255,0.08)`, cursor: 'pointer', fontFamily: font, transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.color = C.t1; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)' }}
            onMouseLeave={e => { e.currentTarget.style.color = C.t2; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)' }}
          >Sign in</button>
          <motion.button
            onClick={() => nav('/login')}
            whileHover={{ scale: 1.02, boxShadow: `0 0 30px ${C.blue}35` }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 700, color: '#fff', background: `linear-gradient(135deg, ${C.blue}, ${C.indigo})`, border: 'none', cursor: 'pointer', fontFamily: font, boxShadow: `0 0 20px ${C.blue}25` }}
          >
            Get access
            <ArrowUpRight style={{ width: 14, height: 14 }} strokeWidth={2.5} />
          </motion.button>
        </div>
      </motion.nav>

      {/* ── HERO ────────────────────────────────────────────────────────────── */}
      <section style={{ position: 'relative', minHeight: '100dvh', display: 'flex', alignItems: 'center', padding: '100px clamp(20px,4vw,72px) 80px', overflow: 'hidden' }}>

        {/* Background orbs */}
        <Orb x="0%"  y="10%"  color={C.blue}   size={600} delay={0} />
        <Orb x="55%" y="0%"   color={C.purple}  size={500} delay={2} />
        <Orb x="30%" y="55%"  color={C.indigo}  size={300} delay={4} />

        {/* Grid */}
        <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.018,
          backgroundImage: 'linear-gradient(rgba(255,255,255,1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,1) 1px, transparent 1px)',
          backgroundSize: '72px 72px',
        }} />

        <div style={{ position: 'relative', zIndex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60, alignItems: 'center', maxWidth: 1200, margin: '0 auto', width: '100%' }}>

          {/* LEFT */}
          <div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
              <SectionLabel color={C.blue} text="B2B Vehicle Intelligence" />
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 24, filter: 'blur(10px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ delay: 0.1, duration: 0.7, ease: EASE }}
              style={{ fontSize: 'clamp(38px, 5vw, 68px)', fontWeight: 900, lineHeight: 1.04, letterSpacing: '-0.04em', marginBottom: 22, color: C.t1 }}
            >
              The fiscal edge for{' '}
              <span style={{ background: `linear-gradient(120deg, ${C.blue} 0%, ${C.purple} 55%, ${C.teal} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                EU vehicle arbitrage
              </span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.6, ease: EASE }}
              style={{ fontSize: 17, color: C.t2, lineHeight: 1.7, maxWidth: 480, marginBottom: 36 }}
            >
              3.5M classified listings. IVA/REBU auto-classification with full traceability.
              Net Landed Cost and Seller Desperation Index on every vehicle — across 6 EU markets.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.28, duration: 0.5, ease: EASE }}
              style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 44 }}
            >
              <motion.button
                onClick={() => nav('/login')}
                whileHover={{ scale: 1.03, boxShadow: `0 0 50px ${C.blue}40` }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 380, damping: 18 }}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 28px', borderRadius: 13, fontSize: 15, fontWeight: 700, color: '#fff', background: `linear-gradient(135deg, ${C.blue} 0%, ${C.indigo} 100%)`, border: 'none', cursor: 'pointer', fontFamily: font, boxShadow: `0 0 30px ${C.blue}25` }}
              >
                Open platform
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowUpRight style={{ width: 13, height: 13 }} strokeWidth={2.5} />
                </div>
              </motion.button>

              <button
                onClick={() => document.getElementById('vehicles')?.scrollIntoView({ behavior: 'smooth' })}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 24px', borderRadius: 13, fontSize: 15, fontWeight: 600, color: C.t2, background: C.s1, border: `1px solid ${C.border}`, cursor: 'pointer', fontFamily: font, transition: 'all 0.2s' }}
                onMouseEnter={e => { e.currentTarget.style.color = C.t1; e.currentTarget.style.background = C.s2 }}
                onMouseLeave={e => { e.currentTarget.style.color = C.t2; e.currentTarget.style.background = C.s1 }}
              >
                See live data <ChevronRight style={{ width: 14, height: 14 }} />
              </button>
            </motion.div>

            {/* Trust strip */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5, duration: 0.5 }}
              style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}
            >
              {[
                { icon: Check, text: 'No setup fee' },
                { icon: Shield, text: 'GDPR compliant' },
                { icon: Sparkles, text: 'AI-classified' },
              ].map(({ icon: Icon, text }) => (
                <div key={text} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: C.t3 }}>
                  <Icon style={{ width: 12, height: 12, color: C.teal }} strokeWidth={2.5} />
                  {text}
                </div>
              ))}
            </motion.div>
          </div>

          {/* RIGHT */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <IntelligencePanel />
          </div>
        </div>
      </section>

      {/* ── STATS ───────────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,72px) 100px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, background: 'rgba(255,255,255,0.05)', borderRadius: 20, overflow: 'hidden', border: `1px solid ${C.border}` }}>
          {STATS.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.5, ease: EASE }}
              style={{ padding: '32px 28px', textAlign: 'center', background: C.s1, position: 'relative' }}
            >
              <div style={{ fontSize: 40, fontWeight: 900, letterSpacing: '-0.04em', background: `linear-gradient(135deg, ${C.t1}, ${C.t2})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 6 }}>
                {s.short}
              </div>
              <div style={{ fontSize: 11, color: C.t3, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{s.label}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── VEHICLE PREVIEW ─────────────────────────────────────────────────── */}
      <section id="vehicles" style={{ padding: '0 clamp(20px,4vw,72px) 120px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, ease: EASE }} style={{ marginBottom: 52 }}>
            <SectionLabel color={C.purple} text="Live intelligence" />
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,48px)', fontWeight: 900, letterSpacing: '-0.03em', color: C.t1, marginBottom: 14 }}>
              Real listings. Real intelligence.
            </h2>
            <p style={{ fontSize: 16, color: C.t2, maxWidth: 540, lineHeight: 1.65 }}>
              Every vehicle classified with fiscal regime, Net Landed Cost, and Seller Desperation Index — automatically.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16 }}>
            {VEHICLES.map((v, i) => <VehicleCard key={v.id} v={v} delay={i * 0.08} />)}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3, duration: 0.5, ease: EASE }}
            style={{ textAlign: 'center', marginTop: 40 }}
          >
            <motion.button
              onClick={() => nav('/login')}
              whileHover={{ scale: 1.02, boxShadow: `0 0 40px ${C.indigo}30` }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 380, damping: 18 }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 28px', borderRadius: 12, fontSize: 14, fontWeight: 700, color: C.t1, background: C.s2, border: `1px solid ${C.borderHi}`, cursor: 'pointer', fontFamily: font, transition: 'box-shadow 0.3s' }}
            >
              Browse all 3.5M listings
              <ArrowUpRight style={{ width: 14, height: 14 }} strokeWidth={2.5} />
            </motion.button>
          </motion.div>
        </div>
      </section>

      {/* ── FEATURES ────────────────────────────────────────────────────────── */}
      <section id="features" style={{ padding: '0 clamp(20px,4vw,72px) 120px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, ease: EASE }} style={{ textAlign: 'center', marginBottom: 56 }}>
            <SectionLabel color={C.teal} text="Platform capabilities" />
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,48px)', fontWeight: 900, letterSpacing: '-0.03em', color: C.t1, marginBottom: 14 }}>
              Built for professional traders
            </h2>
            <p style={{ fontSize: 16, color: C.t2, maxWidth: 500, margin: '0 auto' }}>
              Every feature designed around the real friction in cross-border vehicle arbitrage.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.07, duration: 0.5, ease: EASE }}
                whileHover={{ y: -4, transition: { duration: 0.25 } }}
                style={{
                  padding: '28px', borderRadius: 20,
                  background: C.s1,
                  border: `1px solid ${C.border}`,
                  position: 'relative', overflow: 'hidden',
                  boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
                  cursor: 'default',
                  transition: 'border-color 0.25s, box-shadow 0.25s',
                }}
                onMouseEnter={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = `${f.color}35`
                  el.style.boxShadow = `0 12px 40px rgba(0,0,0,0.35), 0 0 0 1px ${f.color}15`
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = C.border
                  el.style.boxShadow = '0 4px 16px rgba(0,0,0,0.2)'
                }}
              >
                <div aria-hidden style={{ position: 'absolute', top: -30, right: -20, width: 120, height: 120, borderRadius: '50%', background: f.color, opacity: 0.06, filter: 'blur(36px)', pointerEvents: 'none' }} />
                <div style={{ width: 44, height: 44, borderRadius: 13, background: `${f.color}12`, border: `1px solid ${f.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }}>
                  <f.icon style={{ width: 20, height: 20, color: f.color }} strokeWidth={1.8} />
                </div>
                <h3 style={{ fontSize: 16, fontWeight: 800, color: C.t1, marginBottom: 10, letterSpacing: '-0.01em' }}>{f.title}</h3>
                <p style={{ fontSize: 13, color: C.t2, lineHeight: 1.7 }}>{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── EU COVERAGE ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,72px) 120px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, ease: EASE }} style={{ textAlign: 'center', marginBottom: 52 }}>
            <SectionLabel color={C.emerald} text="Coverage" />
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,48px)', fontWeight: 900, letterSpacing: '-0.03em', color: C.t1, marginBottom: 14 }}>
              6 countries. Every dealer.
            </h2>
            <p style={{ fontSize: 16, color: C.t2, maxWidth: 480, margin: '0 auto' }}>
              From AutoScout24 to the unknown dealer in rural France with a 3-car website. Nothing left behind.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 12 }}>
            {COUNTRIES.map((c, i) => (
              <motion.div
                key={c.code}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.06, duration: 0.4, ease: EASE }}
                whileHover={{ y: -4, scale: 1.04, transition: { duration: 0.2 } }}
                style={{
                  padding: '20px 12px', borderRadius: 16, textAlign: 'center',
                  background: C.s1, border: `1px solid ${C.border}`,
                  cursor: 'default',
                  transition: 'border-color 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.borderColor = C.borderHi}
                onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.borderColor = C.border}
              >
                <div style={{ fontSize: 32, marginBottom: 8 }}>{c.flag}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: C.t1, marginBottom: 4 }}>{c.name}</div>
                <div style={{ fontSize: 10, color: C.t3, fontWeight: 600 }}>{c.count}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,72px) 120px' }}>
        <div style={{ maxWidth: 1000, margin: '0 auto' }}>
          <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5, ease: EASE }} style={{ textAlign: 'center', marginBottom: 52 }}>
            <SectionLabel color={C.amber} text="How it works" />
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,48px)', fontWeight: 900, letterSpacing: '-0.03em', color: C.t1 }}>
              From scraped to decision-ready in 2 seconds
            </h2>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
            {[
              { step: '01', color: C.blue, icon: Globe, title: 'Index every listing', desc: 'Sitemap-first discovery across 2,500+ dealer sources. Every listing deep-linked, nothing at root domain.' },
              { step: '02', color: C.purple, icon: Zap, title: 'Classify in real time', desc: 'LLM-powered IVA/REBU classification with full traceability. Pipeline delivers in < 2 seconds per vehicle.' },
              { step: '03', color: C.emerald, icon: TrendingUp, title: 'Trade with confidence', desc: 'NLC per destination. SDI urgency score. Price delta alerts. Every number you need before you call.' },
            ].map((s, i) => (
              <motion.div
                key={s.step}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.55, ease: EASE }}
                style={{
                  padding: '32px 28px', borderRadius: 20,
                  background: C.s1, border: `1px solid ${C.border}`,
                  position: 'relative', overflow: 'hidden',
                }}
              >
                <div style={{ position: 'absolute', top: 20, right: 20, fontSize: 56, fontWeight: 900, color: 'rgba(255,255,255,0.03)', lineHeight: 1, letterSpacing: '-0.05em', userSelect: 'none' }}>{s.step}</div>
                <div style={{ width: 48, height: 48, borderRadius: 14, background: `${s.color}12`, border: `1px solid ${s.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                  <s.icon style={{ width: 22, height: 22, color: s.color }} strokeWidth={1.7} />
                </div>
                <h3 style={{ fontSize: 17, fontWeight: 800, color: C.t1, marginBottom: 12, letterSpacing: '-0.01em' }}>{s.title}</h3>
                <p style={{ fontSize: 14, color: C.t2, lineHeight: 1.68 }}>{s.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,72px) 140px' }}>
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EASE }}
          style={{ maxWidth: 760, margin: '0 auto', position: 'relative' }}
        >
          {/* Gradient glow behind */}
          <div aria-hidden style={{ position: 'absolute', inset: -2, borderRadius: 28, background: `linear-gradient(135deg, ${C.blue}40, ${C.purple}40, ${C.teal}20)`, filter: 'blur(1px)', zIndex: 0 }} />

          <div style={{ position: 'relative', zIndex: 1, background: C.bg, borderRadius: 26, padding: 'clamp(40px,5vw,64px)', textAlign: 'center', overflow: 'hidden', border: `1px solid rgba(255,255,255,0.06)` }}>
            <Orb x="5%"  y="15%" color={C.blue}   size={250} />
            <Orb x="65%" y="50%" color={C.purple}  size={200} />

            <div style={{ position: 'relative', zIndex: 1 }}>
              <SectionLabel color={C.teal} text="Get started" />
              <h2 style={{ fontSize: 'clamp(28px,3vw,44px)', fontWeight: 900, letterSpacing: '-0.03em', color: C.t1, marginBottom: 16 }}>
                Ready to trade smarter?
              </h2>
              <p style={{ fontSize: 16, color: C.t2, marginBottom: 36, lineHeight: 1.65, maxWidth: 480, margin: '0 auto 36px' }}>
                Access 3.5M classified vehicle listings across 6 EU markets. No guesswork on fiscal regimes. No hidden costs.
              </p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                <motion.button
                  onClick={() => nav('/login')}
                  whileHover={{ scale: 1.04, boxShadow: `0 0 60px ${C.blue}45` }}
                  whileTap={{ scale: 0.97 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 18 }}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '15px 34px', borderRadius: 14, fontSize: 16, fontWeight: 800, color: '#fff', background: `linear-gradient(135deg, ${C.blue} 0%, ${C.indigo} 100%)`, border: 'none', cursor: 'pointer', fontFamily: font, boxShadow: `0 0 30px ${C.blue}25` }}
                >
                  Enter workspace
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <ArrowUpRight style={{ width: 14, height: 14 }} strokeWidth={2.5} />
                  </div>
                </motion.button>
                <button
                  onClick={() => nav('/check')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 28px', borderRadius: 14, fontSize: 16, fontWeight: 700, color: C.t2, background: C.s1, border: `1px solid ${C.border}`, cursor: 'pointer', fontFamily: font, transition: 'all 0.2s' }}
                  onMouseEnter={e => { e.currentTarget.style.color = C.t1; e.currentTarget.style.borderColor = C.borderHi }}
                  onMouseLeave={e => { e.currentTarget.style.color = C.t2; e.currentTarget.style.borderColor = C.border }}
                >
                  Try VIN Check <ChevronRight style={{ width: 14, height: 14 }} />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── FOOTER ──────────────────────────────────────────────────────────── */}
      <footer style={{ borderTop: `1px solid rgba(255,255,255,0.05)`, padding: '28px clamp(20px,4vw,72px)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 24, height: 24, borderRadius: 7, background: `${C.blue}15`, border: `1px solid ${C.blue}25`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 9, height: 9, borderRadius: 3, background: `linear-gradient(135deg, ${C.blue}, ${C.indigo})` }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.18em', color: C.t2 }}>CARDEX</span>
        </div>
        <div style={{ display: 'flex', gap: 24 }}>
          {['Privacy', 'Terms', 'Contact'].map(l => (
            <button key={l} style={{ fontSize: 12, color: C.t3, background: 'none', border: 'none', cursor: 'pointer', fontFamily: font, transition: 'color 0.15s', padding: 0 }}
              onMouseEnter={e => (e.currentTarget.style.color = C.t2)}
              onMouseLeave={e => (e.currentTarget.style.color = C.t3)}
            >{l}</button>
          ))}
        </div>
        <span style={{ fontSize: 12, color: C.t4 }}>© 2026 CARDEX · B2B Vehicle Intelligence</span>
      </footer>

      <style>{`
        @keyframes cxPulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.45; transform: scale(0.85); }
        }
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
      `}</style>
    </div>
  )
}
