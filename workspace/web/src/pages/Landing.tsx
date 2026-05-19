import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import {
  ArrowUpRight, Shield, Zap, Globe, TrendingUp,
  ChevronRight, MapPin, Activity, Check, Car,
  BarChart3, Sparkles,
} from 'lucide-react'

const EASE = [0.22, 1, 0.36, 1] as const
const FONT = '"Inter", system-ui, -apple-system, sans-serif'

/* ── Glass primitives (inline tokens — keep deps zero) ───────────────────── */
const GLASS_BG_MD     = 'rgba(255,255,255,0.10)'
const GLASS_BG_SM     = 'rgba(255,255,255,0.07)'
const GLASS_BG_XS     = 'rgba(255,255,255,0.04)'
const GLASS_BLUR      = 'blur(24px) saturate(180%)'
const GLASS_BLUR_LG   = 'blur(40px) saturate(200%)'
const GLASS_BORDER    = '1px solid rgba(255,255,255,0.15)'
const GLASS_BORDER_HI = '1px solid rgba(255,255,255,0.22)'
const GLASS_SHADOW    = '0 8px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.15)'
const GLASS_SHADOW_LG = '0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.18)'

const BMW_PHOTO = 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&q=90&auto=format&fit=crop'

interface VehicleDatum {
  src: string
  make: string
  model: string
  year: number
  city: string
  flag: string
  price: string
  km: string
  regime: string
  regColor: string
  nlc: string
  dest: string
  sdi: number
  sdiC: string
}

const CAR_PHOTOS: VehicleDatum[] = [
  { src: 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=700&q=85&auto=format&fit=crop', make: 'BMW',      model: 'M3 Competition',    year: 2022, city: 'Munich',     flag: 'DE', price: '€ 58.900', km: '24.500', regime: 'IVA Deductible', regColor: '#10b981', nlc: '€ 62.340', dest: 'ES', sdi: 8.2, sdiC: '#f43f5e' },
  { src: 'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=700&q=85&auto=format&fit=crop', make: 'Mercedes', model: 'C 220d AMG',        year: 2021, city: 'Paris',      flag: 'FR', price: '€ 28.400', km: '41.200', regime: 'REBU',          regColor: '#f59e0b', nlc: '€ 31.200', dest: 'NL', sdi: 5.1, sdiC: '#06b6d4' },
  { src: 'https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=700&q=85&auto=format&fit=crop', make: 'Audi',     model: 'A4 2.0 TDI S-Line', year: 2023, city: 'Amsterdam',  flag: 'NL', price: '€ 34.500', km: '18.900', regime: 'IVA Deductible', regColor: '#10b981', nlc: '€ 36.800', dest: 'BE', sdi: 6.7, sdiC: '#3b82f6' },
  { src: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=700&q=85&auto=format&fit=crop', make: 'Porsche',  model: '911 Carrera S',     year: 2020, city: 'Zurich',     flag: 'CH', price: '€ 89.900', km: '31.600', regime: 'IVA Deductible', regColor: '#10b981', nlc: '€ 94.100', dest: 'DE', sdi: 9.1, sdiC: '#f43f5e' },
]

interface FeatureDatum {
  icon: React.ElementType
  color: string
  title: string
  desc: string
}

const FEATURES: FeatureDatum[] = [
  { icon: TrendingUp, color: '#a78bfa', title: 'Fiscal intelligence',       desc: 'IVA / REBU auto-classification with full traceability to the prompt and model that produced each decision.' },
  { icon: Globe,      color: '#60a5fa', title: 'Pan-European coverage',     desc: 'DE · ES · FR · NL · BE · CH — sitemap-first indexing from every dealer. Nothing abandoned mid-pagination.' },
  { icon: Zap,        color: '#67e8f9', title: 'Real-time pipeline',        desc: 'Redis Streams at-least-once delivery. Scraped to classified in under 2 seconds per listing.' },
  { icon: Shield,     color: '#6ee7b7', title: 'Net Landed Cost',           desc: 'Total cost of importing any vehicle to any destination country — duties, transport, registration — computed automatically.' },
  { icon: BarChart3,  color: '#fcd34d', title: 'Price delta tracking',      desc: 'Instant alerts when a dealer drops price. Know before competitors. Historical timeline per listing.' },
  { icon: Activity,   color: '#fca5a5', title: 'Seller Desperation Index',  desc: 'SDI scores quantify seller urgency. MATRABA flags, EuroNCAP, EU RAPEX — every risk surfaced automatically.' },
]

interface CountryDatum {
  flag: string
  name: string
  n: string
  color: string
}

const COUNTRIES: CountryDatum[] = [
  { flag: 'DE', name: 'Germany',     n: '890K+', color: '#a78bfa' },
  { flag: 'FR', name: 'France',      n: '640K+', color: '#60a5fa' },
  { flag: 'ES', name: 'Spain',       n: '720K+', color: '#fca5a5' },
  { flag: 'NL', name: 'Netherlands', n: '380K+', color: '#fcd34d' },
  { flag: 'BE', name: 'Belgium',     n: '290K+', color: '#67e8f9' },
  { flag: 'CH', name: 'Switzerland', n: '180K+', color: '#6ee7b7' },
]

/* ─── SDI bar ─────────────────────────────────────────────────────────────── */
function SDIBar({ v, c }: { v: number; c: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.12)', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${v * 10}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.9, ease: EASE, delay: 0.1 }}
          style={{ height: '100%', background: `linear-gradient(90deg, ${c}80, ${c})`, borderRadius: 2 }}
        />
      </div>
      <span style={{ fontSize: 12, fontWeight: 800, color: c, minWidth: 24 }}>{v}</span>
    </div>
  )
}

/* ─── Vehicle card (real glass) ──────────────────────────────────────────── */
function VehicleCard({ d, i }: { d: VehicleDatum; i: number }) {
  const [hov, setHov] = useState(false)
  return (
    <motion.div
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay: i * 0.08, duration: 0.6, ease: EASE }}
      onHoverStart={() => setHov(true)}
      onHoverEnd={() => setHov(false)}
      style={{
        borderRadius: 22,
        overflow: 'hidden',
        cursor: 'pointer',
        background: hov ? GLASS_BG_MD : GLASS_BG_SM,
        border: hov ? GLASS_BORDER_HI : GLASS_BORDER,
        backdropFilter: GLASS_BLUR,
        WebkitBackdropFilter: GLASS_BLUR,
        boxShadow: hov ? GLASS_SHADOW_LG : GLASS_SHADOW,
        transform: hov ? 'translateY(-6px)' : 'none',
        transition: 'all 0.35s cubic-bezier(0.22,1,0.36,1)',
      }}
    >
      <div style={{ position: 'relative', height: 190, overflow: 'hidden' }}>
        <img
          src={d.src}
          alt={`${d.make} ${d.model}`}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: hov ? 'scale(1.07)' : 'scale(1)',
            transition: 'transform 0.5s cubic-bezier(0.22,1,0.36,1)',
          }}
        />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,26,0.95) 0%, rgba(10,10,26,0.25) 55%, transparent 100%)' }} />
        <div
          style={{
            position: 'absolute',
            top: 12,
            left: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 10px',
            borderRadius: 999,
            background: 'rgba(255,255,255,0.12)',
            backdropFilter: 'blur(14px) saturate(180%)',
            border: '1px solid rgba(255,255,255,0.20)',
            fontSize: 11,
            color: '#f8fafc',
            fontWeight: 600,
            letterSpacing: '0.04em',
          }}
        >
          {d.flag} · {d.city}
        </div>
        {d.sdi >= 8 && (
          <div
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              padding: '4px 10px',
              borderRadius: 999,
              background: `${d.sdiC}33`,
              backdropFilter: 'blur(14px) saturate(180%)',
              border: `1px solid ${d.sdiC}66`,
              fontSize: 10,
              color: d.sdiC,
              fontWeight: 800,
              letterSpacing: '0.08em',
            }}
          >
            HOT
          </div>
        )}
        <div style={{ position: 'absolute', bottom: 14, left: 14 }}>
          <div style={{ fontSize: 17, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.02em' }}>
            {d.make} <span style={{ fontWeight: 500, color: '#cbd5e1' }}>{d.model}</span>
          </div>
          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{d.year}</div>
        </div>
      </div>

      <div style={{ padding: '16px 18px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontSize: 22, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.03em' }}>{d.price}</span>
          <span style={{ fontSize: 12, color: '#94a3b8' }}>{d.km} km</span>
        </div>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            padding: '4px 10px',
            borderRadius: 999,
            background: `${d.regColor}1F`,
            border: `1px solid ${d.regColor}55`,
            fontSize: 10,
            fontWeight: 700,
            color: d.regColor,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            marginBottom: 14,
          }}
        >
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: d.regColor, display: 'block' }} />
          {d.regime}
        </div>
        <div style={{ height: 1, background: 'rgba(255,255,255,0.10)', marginBottom: 12 }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 10, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>NLC → {d.dest}</span>
          <span style={{ fontSize: 13, fontWeight: 800, color: '#f8fafc' }}>{d.nlc}</span>
        </div>
        <SDIBar v={d.sdi} c={d.sdiC} />
      </div>
    </motion.div>
  )
}

/* ─── Landing ─────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { scrollY } = useScroll()
  const navBg = useTransform(scrollY, [0, 60], ['rgba(10,10,26,0)', 'rgba(10,10,26,0.55)'])
  const navBorder = useTransform(scrollY, [0, 60], ['rgba(255,255,255,0)', 'rgba(255,255,255,0.10)'])

  return (
    <div
      style={{
        minHeight: '100dvh',
        fontFamily: FONT,
        overflowX: 'hidden',
        color: '#f8fafc',
        /* No background here — the global .cx-mesh provides the colored backdrop. */
      }}
    >
      {/* ── NAVBAR (real glass) ───────────────────────────────────────────── */}
      <motion.nav
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 clamp(20px,4vw,56px)',
          backgroundColor: navBg,
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid',
          borderColor: navBorder,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 12,
              background: 'linear-gradient(135deg, rgba(124,58,237,0.30), rgba(37,99,235,0.30))',
              border: '1px solid rgba(255,255,255,0.20)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backdropFilter: 'blur(12px)',
              boxShadow: '0 0 24px rgba(124,58,237,0.25), inset 0 1px 0 rgba(255,255,255,0.18)',
            }}
          >
            <div
              style={{
                width: 13,
                height: 13,
                borderRadius: 4,
                background: 'linear-gradient(135deg, #a78bfa, #60a5fa)',
                boxShadow: '0 0 14px rgba(167,139,250,0.7)',
              }}
            />
          </div>
          <span
            style={{
              fontSize: 15,
              fontWeight: 900,
              letterSpacing: '0.22em',
              color: '#f8fafc',
            }}
          >
            CARDEX
          </span>
        </div>

        <div style={{ display: 'flex', gap: 2 }}>
          {['Platform', 'Coverage', 'Pricing'].map(l => (
            <button
              key={l}
              style={{
                padding: '8px 16px',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 500,
                color: '#cbd5e1',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontFamily: FONT,
                transition: 'color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.color = '#f8fafc'
                e.currentTarget.style.background = 'rgba(255,255,255,0.06)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.color = '#cbd5e1'
                e.currentTarget.style.background = 'transparent'
              }}
            >
              {l}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={() => nav('/login')}
            style={{
              padding: '8px 18px',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 600,
              color: '#cbd5e1',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.12)',
              backdropFilter: 'blur(12px)',
              cursor: 'pointer',
              fontFamily: FONT,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.color = '#f8fafc'
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)'
              e.currentTarget.style.background = 'rgba(255,255,255,0.10)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.color = '#cbd5e1'
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)'
              e.currentTarget.style.background = 'rgba(255,255,255,0.06)'
            }}
          >
            Sign in
          </button>
          <motion.button
            onClick={() => nav('/login')}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              padding: '9px 20px',
              borderRadius: 10,
              fontSize: 13,
              fontWeight: 700,
              color: '#fff',
              background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
              border: '1px solid rgba(255,255,255,0.20)',
              cursor: 'pointer',
              fontFamily: FONT,
              boxShadow: '0 0 28px rgba(124,58,237,0.45), inset 0 1px 0 rgba(255,255,255,0.25)',
            }}
          >
            Get access <ArrowUpRight style={{ width: 13, height: 13 }} strokeWidth={2.5} />
          </motion.button>
        </div>
      </motion.nav>

      {/* ── HERO — no background image, the global mesh IS the backdrop ──── */}
      <section
        style={{
          position: 'relative',
          minHeight: '100dvh',
          display: 'flex',
          alignItems: 'center',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'relative',
            zIndex: 2,
            display: 'grid',
            gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)',
            gap: 48,
            alignItems: 'center',
            maxWidth: 1240,
            margin: '0 auto',
            width: '100%',
            padding: '110px clamp(20px,4vw,56px) 80px',
          }}
        >
          {/* LEFT — copy */}
          <div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 14px',
                  borderRadius: 999,
                  background: 'rgba(255,255,255,0.10)',
                  border: '1px solid rgba(255,255,255,0.20)',
                  marginBottom: 28,
                  backdropFilter: 'blur(20px) saturate(180%)',
                  WebkitBackdropFilter: 'blur(20px) saturate(180%)',
                  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.18)',
                }}
              >
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#67e8f9', animation: 'cxPulse 2s infinite', boxShadow: '0 0 10px #67e8f9' }} />
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f8fafc' }}>
                  B2B Vehicle Intelligence
                </span>
              </div>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 28, filter: 'blur(12px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ delay: 0.08, duration: 0.75, ease: EASE }}
              style={{
                fontSize: 'clamp(42px,5.4vw,76px)',
                fontWeight: 900,
                lineHeight: 1.03,
                letterSpacing: '-0.04em',
                marginBottom: 24,
                color: '#f8fafc',
              }}
            >
              The fiscal edge{' '}
              <br />
              <span
                style={{
                  background: 'linear-gradient(120deg, #c4b5fd 0%, #93c5fd 45%, #67e8f9 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                for EU arbitrage
              </span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18, duration: 0.6, ease: EASE }}
              style={{
                fontSize: 17,
                color: '#cbd5e1',
                lineHeight: 1.72,
                maxWidth: 480,
                marginBottom: 38,
              }}
            >
              3.5M listings across 6 EU countries. IVA/REBU auto-classification with full traceability.
              Net Landed Cost and Seller Desperation Index on every vehicle — before you call.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.26, duration: 0.5, ease: EASE }}
              style={{ display: 'flex', gap: 12, marginBottom: 44, flexWrap: 'wrap' }}
            >
              <motion.button
                onClick={() => nav('/login')}
                whileHover={{ scale: 1.04, boxShadow: '0 0 60px rgba(124,58,237,0.5)' }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 380, damping: 18 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '14px 30px',
                  borderRadius: 14,
                  fontSize: 15,
                  fontWeight: 800,
                  color: '#fff',
                  background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                  border: '1px solid rgba(255,255,255,0.22)',
                  cursor: 'pointer',
                  fontFamily: FONT,
                  boxShadow: '0 0 40px rgba(124,58,237,0.4), inset 0 1px 0 rgba(255,255,255,0.25)',
                }}
              >
                Open platform
                <div
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: '50%',
                    background: 'rgba(255,255,255,0.22)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <ArrowUpRight style={{ width: 13, height: 13 }} strokeWidth={2.5} />
                </div>
              </motion.button>
              <button
                onClick={() => document.getElementById('vehicles')?.scrollIntoView({ behavior: 'smooth' })}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '14px 24px',
                  borderRadius: 14,
                  fontSize: 15,
                  fontWeight: 600,
                  color: '#f8fafc',
                  background: GLASS_BG_MD,
                  border: GLASS_BORDER,
                  cursor: 'pointer',
                  fontFamily: FONT,
                  backdropFilter: GLASS_BLUR,
                  WebkitBackdropFilter: GLASS_BLUR,
                  boxShadow: GLASS_SHADOW,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.14)'
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = GLASS_BG_MD
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'
                }}
              >
                See live data <ChevronRight style={{ width: 14, height: 14 }} />
              </button>
            </motion.div>

            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} style={{ display: 'flex', gap: 22, flexWrap: 'wrap' }}>
              {[
                { Icon: Check,     t: 'No setup fee' },
                { Icon: Shield,    t: 'GDPR compliant' },
                { Icon: Sparkles,  t: 'AI-classified' },
              ].map(({ Icon, t }) => (
                <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#94a3b8' }}>
                  <Icon style={{ width: 13, height: 13, color: '#67e8f9' }} strokeWidth={2.5} />
                  {t}
                </div>
              ))}
            </motion.div>
          </div>

          {/* RIGHT — floating glass intelligence panel */}
          <motion.div
            initial={{ opacity: 0, x: 40, rotateY: 6 }}
            animate={{ opacity: 1, x: 0, rotateY: 0 }}
            transition={{ delay: 0.35, duration: 0.9, ease: EASE }}
            style={{ position: 'relative', display: 'flex', justifyContent: 'center' }}
          >
            {/* Main glass card — colors of the mesh shine through */}
            <div
              style={{
                width: '100%',
                maxWidth: 480,
                borderRadius: 26,
                overflow: 'hidden',
                background: GLASS_BG_MD,
                backdropFilter: GLASS_BLUR_LG,
                WebkitBackdropFilter: GLASS_BLUR_LG,
                border: GLASS_BORDER,
                boxShadow: GLASS_SHADOW_LG,
              }}
            >
              <div
                style={{
                  padding: '13px 18px',
                  borderBottom: '1px solid rgba(255,255,255,0.10)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  background: 'rgba(255,255,255,0.04)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 12px #10b981' }} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: '#cbd5e1', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                    Live Intelligence
                  </span>
                </div>
                <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 500 }}>2s ago</span>
              </div>

              <div style={{ position: 'relative', height: 210, overflow: 'hidden' }}>
                <img src={BMW_PHOTO} alt="BMW M3" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,26,0.95) 0%, rgba(10,10,26,0.10) 60%, transparent 100%)' }} />
                <div style={{ position: 'absolute', bottom: 14, left: 16 }}>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.02em' }}>BMW M3 Competition</div>
                  <div style={{ fontSize: 12, color: '#cbd5e1', display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}>
                    <MapPin style={{ width: 10, height: 10 }} /> DE · Munich · 2022
                  </div>
                </div>
              </div>

              <div style={{ padding: '16px 18px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
                  {[
                    { l: 'Asking price',   v: '€ 58.900', c: '#f8fafc' },
                    { l: 'Mileage',        v: '24.500 km', c: '#cbd5e1' },
                    { l: 'Fiscal regime',  v: 'IVA Ded.',  c: '#6ee7b7' },
                    { l: 'Classification', v: '< 2s',      c: '#93c5fd' },
                  ].map(item => (
                    <div
                      key={item.l}
                      style={{
                        background: 'rgba(255,255,255,0.08)',
                        borderRadius: 12,
                        padding: '11px 13px',
                        border: '1px solid rgba(255,255,255,0.14)',
                        backdropFilter: 'blur(16px)',
                        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)',
                      }}
                    >
                      <div style={{ fontSize: 9, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 5 }}>
                        {item.l}
                      </div>
                      <div style={{ fontSize: 15, fontWeight: 800, color: item.c }}>{item.v}</div>
                    </div>
                  ))}
                </div>

                <div
                  style={{
                    background: 'linear-gradient(135deg, rgba(124,58,237,0.22), rgba(37,99,235,0.22))',
                    border: '1px solid rgba(167,139,250,0.45)',
                    borderRadius: 14,
                    padding: '13px 16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backdropFilter: 'blur(16px) saturate(180%)',
                    boxShadow: '0 8px 24px rgba(124,58,237,0.15), inset 0 1px 0 rgba(255,255,255,0.18)',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 9, color: '#cbd5e1', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 4 }}>
                      Net Landed Cost → ES
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.03em' }}>€ 62.340</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 9, color: '#cbd5e1', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 4 }}>SDI Score</div>
                    <div style={{ fontSize: 22, fontWeight: 900, color: '#fca5a5', letterSpacing: '-0.03em' }}>8.2</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Floating glass tag — bottom-left */}
            <motion.div
              initial={{ opacity: 0, x: -20, y: 10 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{ delay: 1.2, duration: 0.7, ease: EASE }}
              style={{
                position: 'absolute',
                bottom: -22,
                left: -32,
                background: 'rgba(16,185,129,0.18)',
                backdropFilter: 'blur(28px) saturate(180%)',
                WebkitBackdropFilter: 'blur(28px) saturate(180%)',
                border: '1px solid rgba(110,231,183,0.5)',
                borderRadius: 16,
                padding: '11px 15px',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                boxShadow: '0 12px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.20)',
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 10,
                  background: 'rgba(16,185,129,0.25)',
                  border: '1px solid rgba(16,185,129,0.45)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Car style={{ width: 14, height: 14, color: '#6ee7b7' }} />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#f8fafc' }}>+847 new listings</div>
                <div style={{ fontSize: 10, color: '#cbd5e1' }}>indexed this hour</div>
              </div>
            </motion.div>

            {/* Floating glass tag — top-right */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 1.6, duration: 0.7, ease: EASE }}
              style={{
                position: 'absolute',
                top: -22,
                right: -24,
                background: 'rgba(96,165,250,0.18)',
                backdropFilter: 'blur(28px) saturate(180%)',
                WebkitBackdropFilter: 'blur(28px) saturate(180%)',
                border: '1px solid rgba(147,197,253,0.45)',
                borderRadius: 16,
                padding: '11px 15px',
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                boxShadow: '0 12px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.20)',
              }}
            >
              <Check style={{ width: 14, height: 14, color: '#93c5fd' }} strokeWidth={2.5} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#f8fafc' }}>99.2% accuracy</div>
                <div style={{ fontSize: 10, color: '#cbd5e1' }}>REBU classification</div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── STATS (glass strip) ───────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,56px) 110px', position: 'relative', zIndex: 2 }}>
        <div
          style={{
            maxWidth: 1140,
            margin: '0 auto',
            display: 'grid',
            gridTemplateColumns: 'repeat(4,1fr)',
            background: GLASS_BG_MD,
            backdropFilter: GLASS_BLUR_LG,
            WebkitBackdropFilter: GLASS_BLUR_LG,
            border: GLASS_BORDER,
            borderRadius: 26,
            overflow: 'hidden',
            boxShadow: GLASS_SHADOW_LG,
          }}
        >
          {[
            { v: '3.5M+', l: 'Vehicles indexed', c: '#a78bfa' },
            { v: '6',     l: 'EU countries',     c: '#60a5fa' },
            { v: '2.5K+', l: 'Dealer sources',   c: '#67e8f9' },
            { v: '< 2s',  l: 'Classification',   c: '#6ee7b7' },
          ].map((s, i) => (
            <motion.div
              key={s.l}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.5, ease: EASE }}
              style={{
                padding: '34px 28px',
                textAlign: 'center',
                borderRight: i < 3 ? '1px solid rgba(255,255,255,0.10)' : 'none',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              <div
                aria-hidden
                style={{
                  position: 'absolute',
                  top: -20,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  width: 140,
                  height: 90,
                  background: s.c,
                  opacity: 0.18,
                  filter: 'blur(40px)',
                  borderRadius: '50%',
                }}
              />
              <div
                style={{
                  position: 'relative',
                  fontSize: 40,
                  fontWeight: 900,
                  letterSpacing: '-0.04em',
                  color: s.c,
                  marginBottom: 7,
                  textShadow: `0 0 40px ${s.c}66`,
                }}
              >
                {s.v}
              </div>
              <div
                style={{
                  position: 'relative',
                  fontSize: 11,
                  color: '#cbd5e1',
                  fontWeight: 700,
                  letterSpacing: '0.10em',
                  textTransform: 'uppercase',
                }}
              >
                {s.l}
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── VEHICLE CARDS ─────────────────────────────────────────────────── */}
      <section id="vehicles" style={{ padding: '0 clamp(20px,4vw,56px) 130px', position: 'relative', zIndex: 2 }}>
        <div style={{ maxWidth: 1240, margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease: EASE }}
            style={{ marginBottom: 54 }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 14px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.10)',
                border: '1px solid rgba(255,255,255,0.20)',
                marginBottom: 20,
                backdropFilter: 'blur(20px) saturate(180%)',
                boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.18)',
              }}
            >
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#c4b5fd', animation: 'cxPulse 2s infinite', boxShadow: '0 0 10px #c4b5fd' }} />
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f8fafc' }}>
                Live intelligence
              </span>
            </div>
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,52px)', fontWeight: 900, letterSpacing: '-0.04em', color: '#f8fafc', marginBottom: 14 }}>
              Real listings. Real intelligence.
            </h2>
            <p style={{ fontSize: 16, color: '#cbd5e1', maxWidth: 540, lineHeight: 1.65 }}>
              Every vehicle auto-classified with fiscal regime, NLC and SDI — in under 2 seconds.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 18 }}>
            {CAR_PHOTOS.map((d, i) => (
              <VehicleCard key={d.make + d.model} d={d} i={i} />
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3, duration: 0.5, ease: EASE }}
            style={{ textAlign: 'center', marginTop: 44 }}
          >
            <motion.button
              onClick={() => nav('/login')}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '14px 30px',
                borderRadius: 14,
                fontSize: 14,
                fontWeight: 700,
                color: '#f8fafc',
                background: GLASS_BG_MD,
                border: GLASS_BORDER,
                cursor: 'pointer',
                fontFamily: FONT,
                backdropFilter: GLASS_BLUR,
                WebkitBackdropFilter: GLASS_BLUR,
                boxShadow: GLASS_SHADOW,
              }}
            >
              Browse all 3.5M listings <ArrowUpRight style={{ width: 14, height: 14 }} strokeWidth={2.5} />
            </motion.button>
          </motion.div>
        </div>
      </section>

      {/* ── FEATURES ──────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,56px) 130px', position: 'relative', zIndex: 2 }}>
        <div style={{ maxWidth: 1240, margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease: EASE }}
            style={{ textAlign: 'center', marginBottom: 60 }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 14px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.10)',
                border: '1px solid rgba(255,255,255,0.20)',
                marginBottom: 20,
                backdropFilter: 'blur(20px) saturate(180%)',
                boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.18)',
              }}
            >
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#67e8f9', animation: 'cxPulse 2s infinite', boxShadow: '0 0 10px #67e8f9' }} />
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f8fafc' }}>
                Platform capabilities
              </span>
            </div>
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,52px)', fontWeight: 900, letterSpacing: '-0.04em', color: '#f8fafc', marginBottom: 14 }}>
              Built for professional traders
            </h2>
            <p style={{ fontSize: 16, color: '#cbd5e1', maxWidth: 540, margin: '0 auto' }}>
              Every feature designed around real friction in cross-border vehicle arbitrage.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 18 }}>
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 22 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.07, duration: 0.55, ease: EASE }}
                whileHover={{ y: -6, transition: { duration: 0.25 } }}
                style={{
                  padding: '30px',
                  borderRadius: 22,
                  position: 'relative',
                  overflow: 'hidden',
                  cursor: 'default',
                  background: GLASS_BG_MD,
                  backdropFilter: GLASS_BLUR,
                  WebkitBackdropFilter: GLASS_BLUR,
                  border: GLASS_BORDER,
                  boxShadow: GLASS_SHADOW,
                  transition: 'all 0.3s cubic-bezier(0.22,1,0.36,1)',
                }}
                onMouseEnter={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = `${f.color}66`
                  el.style.boxShadow = `0 24px 60px rgba(0,0,0,0.45), 0 0 0 1px ${f.color}33, inset 0 1px 0 rgba(255,255,255,0.20)`
                  el.style.background = 'rgba(255,255,255,0.14)'
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = 'rgba(255,255,255,0.15)'
                  el.style.boxShadow = GLASS_SHADOW
                  el.style.background = GLASS_BG_MD
                }}
              >
                <div
                  aria-hidden
                  style={{
                    position: 'absolute',
                    top: -40,
                    right: -30,
                    width: 160,
                    height: 160,
                    borderRadius: '50%',
                    background: f.color,
                    opacity: 0.22,
                    filter: 'blur(45px)',
                    pointerEvents: 'none',
                  }}
                />
                <div
                  style={{
                    position: 'relative',
                    width: 50,
                    height: 50,
                    borderRadius: 14,
                    background: `${f.color}22`,
                    border: `1px solid ${f.color}55`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: 20,
                    backdropFilter: 'blur(12px)',
                    boxShadow: `0 0 24px ${f.color}33, inset 0 1px 0 rgba(255,255,255,0.18)`,
                  }}
                >
                  <f.icon style={{ width: 22, height: 22, color: f.color }} strokeWidth={1.9} />
                </div>
                <h3 style={{ position: 'relative', fontSize: 17, fontWeight: 800, color: '#f8fafc', marginBottom: 10, letterSpacing: '-0.01em' }}>
                  {f.title}
                </h3>
                <p style={{ position: 'relative', fontSize: 13, color: '#cbd5e1', lineHeight: 1.7 }}>{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── COUNTRIES ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,56px) 130px', position: 'relative', zIndex: 2 }}>
        <div style={{ maxWidth: 1060, margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease: EASE }}
            style={{ textAlign: 'center', marginBottom: 56 }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 14px',
                borderRadius: 999,
                background: 'rgba(255,255,255,0.10)',
                border: '1px solid rgba(255,255,255,0.20)',
                marginBottom: 20,
                backdropFilter: 'blur(20px) saturate(180%)',
                boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.18)',
              }}
            >
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#6ee7b7', animation: 'cxPulse 2s infinite', boxShadow: '0 0 10px #6ee7b7' }} />
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f8fafc' }}>
                Coverage
              </span>
            </div>
            <h2 style={{ fontSize: 'clamp(30px,3.5vw,52px)', fontWeight: 900, letterSpacing: '-0.04em', color: '#f8fafc', marginBottom: 14 }}>
              6 countries. Every dealer.
            </h2>
            <p style={{ fontSize: 16, color: '#cbd5e1', maxWidth: 540, margin: '0 auto' }}>
              From AutoScout24 to the unknown dealer in rural France with a 3-car website.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 14 }}>
            {COUNTRIES.map((c, i) => (
              <motion.div
                key={c.name}
                initial={{ opacity: 0, scale: 0.88 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.06, duration: 0.45, ease: EASE }}
                whileHover={{ y: -6, scale: 1.04, transition: { duration: 0.2 } }}
                style={{
                  padding: '24px 14px',
                  borderRadius: 20,
                  textAlign: 'center',
                  cursor: 'default',
                  background: GLASS_BG_MD,
                  backdropFilter: GLASS_BLUR,
                  WebkitBackdropFilter: GLASS_BLUR,
                  border: GLASS_BORDER,
                  boxShadow: GLASS_SHADOW,
                  position: 'relative',
                  overflow: 'hidden',
                  transition: 'all 0.25s cubic-bezier(0.22,1,0.36,1)',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = `${c.color}66`
                  ;(e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.14)'
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.15)'
                  ;(e.currentTarget as HTMLDivElement).style.background = GLASS_BG_MD
                }}
              >
                <div
                  aria-hidden
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background: `radial-gradient(circle at 50% 0%, ${c.color}33 0%, transparent 60%)`,
                    pointerEvents: 'none',
                  }}
                />
                <div
                  style={{
                    position: 'relative',
                    fontSize: 18,
                    fontWeight: 900,
                    marginBottom: 10,
                    letterSpacing: '0.12em',
                    color: c.color,
                    textShadow: `0 0 20px ${c.color}80`,
                  }}
                >
                  {c.flag}
                </div>
                <div style={{ position: 'relative', fontSize: 13, fontWeight: 700, color: '#f8fafc', marginBottom: 5 }}>{c.name}</div>
                <div style={{ position: 'relative', fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>{c.n}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 clamp(20px,4vw,56px) 140px', position: 'relative', zIndex: 2 }}>
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EASE }}
          style={{ maxWidth: 820, margin: '0 auto', position: 'relative' }}
        >
          <div
            style={{
              position: 'relative',
              background: GLASS_BG_MD,
              backdropFilter: GLASS_BLUR_LG,
              WebkitBackdropFilter: GLASS_BLUR_LG,
              border: GLASS_BORDER_HI,
              borderRadius: 30,
              padding: 'clamp(44px,5vw,72px)',
              textAlign: 'center',
              overflow: 'hidden',
              boxShadow: GLASS_SHADOW_LG,
            }}
          >
            <div
              aria-hidden
              style={{
                position: 'absolute',
                top: '15%',
                left: '12%',
                width: 240,
                height: 240,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(124,58,237,0.4) 0%, transparent 70%)',
                filter: 'blur(50px)',
                pointerEvents: 'none',
              }}
            />
            <div
              aria-hidden
              style={{
                position: 'absolute',
                bottom: '8%',
                right: '12%',
                width: 220,
                height: 220,
                borderRadius: '50%',
                background: 'radial-gradient(circle, rgba(37,99,235,0.35) 0%, transparent 70%)',
                filter: 'blur(45px)',
                pointerEvents: 'none',
              }}
            />
            <div style={{ position: 'relative', zIndex: 1 }}>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 14px',
                  borderRadius: 999,
                  background: 'rgba(255,255,255,0.10)',
                  border: '1px solid rgba(255,255,255,0.22)',
                  marginBottom: 22,
                  backdropFilter: 'blur(20px) saturate(180%)',
                  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.18)',
                }}
              >
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#67e8f9', animation: 'cxPulse 2s infinite', boxShadow: '0 0 10px #67e8f9' }} />
                <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#f8fafc' }}>
                  Get started
                </span>
              </div>
              <h2 style={{ fontSize: 'clamp(30px,3.5vw,48px)', fontWeight: 900, letterSpacing: '-0.04em', color: '#f8fafc', marginBottom: 16 }}>
                Ready to trade smarter?
              </h2>
              <p style={{ fontSize: 16, color: '#cbd5e1', marginBottom: 36, lineHeight: 1.65, maxWidth: 520, margin: '0 auto 36px' }}>
                Access 3.5M classified vehicle listings across 6 EU markets. No guesswork on fiscal regimes.
              </p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                <motion.button
                  onClick={() => nav('/login')}
                  whileHover={{ scale: 1.04, boxShadow: '0 0 70px rgba(124,58,237,0.6)' }}
                  whileTap={{ scale: 0.97 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 18 }}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '15px 36px',
                    borderRadius: 14,
                    fontSize: 16,
                    fontWeight: 800,
                    color: '#fff',
                    background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                    border: '1px solid rgba(255,255,255,0.22)',
                    cursor: 'pointer',
                    fontFamily: FONT,
                    boxShadow: '0 0 40px rgba(124,58,237,0.4), inset 0 1px 0 rgba(255,255,255,0.25)',
                  }}
                >
                  Enter workspace
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: 'rgba(255,255,255,0.22)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <ArrowUpRight style={{ width: 14, height: 14 }} strokeWidth={2.5} />
                  </div>
                </motion.button>
                <button
                  onClick={() => nav('/check')}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '15px 28px',
                    borderRadius: 14,
                    fontSize: 16,
                    fontWeight: 700,
                    color: '#f8fafc',
                    background: GLASS_BG_MD,
                    border: GLASS_BORDER,
                    cursor: 'pointer',
                    fontFamily: FONT,
                    backdropFilter: GLASS_BLUR,
                    WebkitBackdropFilter: GLASS_BLUR,
                    boxShadow: GLASS_SHADOW,
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.14)'
                    e.currentTarget.style.borderColor = 'rgba(255,255,255,0.22)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = GLASS_BG_MD
                    e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)'
                  }}
                >
                  Try VIN Check <ChevronRight style={{ width: 14, height: 14 }} />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────────── */}
      <footer
        style={{
          position: 'relative',
          zIndex: 2,
          borderTop: '1px solid rgba(255,255,255,0.08)',
          padding: '28px clamp(20px,4vw,56px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16,
          background: 'rgba(10,10,26,0.40)',
          backdropFilter: 'blur(20px) saturate(160%)',
          WebkitBackdropFilter: 'blur(20px) saturate(160%)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: 'linear-gradient(135deg, rgba(124,58,237,0.25), rgba(37,99,235,0.25))',
              border: '1px solid rgba(255,255,255,0.18)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backdropFilter: 'blur(10px)',
            }}
          >
            <div style={{ width: 10, height: 10, borderRadius: 3, background: 'linear-gradient(135deg,#a78bfa,#60a5fa)' }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 900, letterSpacing: '0.22em', color: '#cbd5e1' }}>CARDEX</span>
        </div>
        <div style={{ display: 'flex', gap: 28 }}>
          {['Privacy', 'Terms', 'Contact'].map(l => (
            <button
              key={l}
              style={{
                fontSize: 12,
                color: '#94a3b8',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontFamily: FONT,
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = '#f8fafc')}
              onMouseLeave={e => (e.currentTarget.style.color = '#94a3b8')}
            >
              {l}
            </button>
          ))}
        </div>
        <span style={{ fontSize: 12, color: '#64748b' }}>© 2026 CARDEX · B2B Vehicle Intelligence</span>
      </footer>
    </div>
  )
}
