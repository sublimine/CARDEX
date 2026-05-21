import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

/* ─── easing ─────────────────────────────────────────────────────────────── */
const EXPO = [0.16, 1, 0.3, 1] as const

/* ─── hero image — car in outdoor/landscape setting ─────────────────────── */
const HERO_IMG =
  'https://i.pinimg.com/originals/8f/67/ad/8f67ad9d7fef82b5943608def344573b.jpg'

/* ─── stat strip data ───────────────────────────────────────────────────── */
const STATS = [
  { value: '1.55M+', label: 'Vehicles indexed' },
  { value: '6',      label: 'EU countries' },
  { value: '< 2s',   label: 'IVA/REBU classification' },
  { value: '4.8%',   label: 'Avg EU6 margin' },
]

/* ─── Animated counter ──────────────────────────────────────────────────── */
function StatItem({ value, label, delay }: { value: string; label: string; delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: EXPO, delay }}
      style={{ textAlign: 'center' }}
    >
      <div style={{
        fontSize: 'clamp(1.35rem, 2.5vw, 1.75rem)',
        fontWeight: 800,
        color: '#f8fafc',
        letterSpacing: '-0.03em',
        lineHeight: 1,
        marginBottom: 5,
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 'clamp(0.65rem, 1vw, 0.75rem)',
        fontWeight: 500,
        color: 'rgba(255,255,255,0.45)',
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}>
        {label}
      </div>
    </motion.div>
  )
}

/* ─── Main ──────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { isAuthenticated } = useAuthContext()
  const heroRef = useRef<HTMLDivElement>(null)
  const [navScrolled, setNavScrolled] = useState(false)

  /* Navbar glass on scroll */
  useEffect(() => {
    const onScroll = () => setNavScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  /* Parallax: photo moves up slower than scroll */
  const { scrollY } = useScroll()
  const imgY = useTransform(scrollY, [0, 600], ['0%', '18%'])

  function handleEnter() {
    nav(isAuthenticated ? '/dashboard' : '/login')
  }

  return (
    <div style={{ background: '#07070f', minHeight: '100dvh', fontFamily: 'Inter, system-ui, sans-serif' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <motion.nav
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EXPO }}
        style={{
          position: 'fixed',
          top: 0, left: 0, right: 0,
          zIndex: 100,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 clamp(20px, 4vw, 48px)',
          height: 60,
          transition: 'background 0.35s ease, border-color 0.35s ease',
          background: navScrolled ? 'rgba(7,7,15,0.82)' : 'transparent',
          backdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
          WebkitBackdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
          borderBottom: navScrolled ? '1px solid rgba(255,255,255,0.07)' : '1px solid transparent',
        }}
      >
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'linear-gradient(135deg, #6366f1, #7c3aed)',
            boxShadow: '0 0 16px rgba(99,102,241,0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: 'rgba(255,255,255,0.9)' }} />
          </div>
          <span style={{
            fontSize: 14, fontWeight: 800, letterSpacing: '0.14em',
            background: 'linear-gradient(120deg, #c4b5fd, #818cf8, #67e8f9)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
          }}>
            CARDEX
          </span>
        </div>

        {/* Nav links */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          {['Platform', 'Coverage', 'Pricing'].map(link => (
            <button key={link} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.5)',
              letterSpacing: '0.01em', fontFamily: 'inherit',
              transition: 'color 0.2s',
            }}
              onMouseEnter={e => { (e.target as HTMLElement).style.color = 'rgba(255,255,255,0.9)' }}
              onMouseLeave={e => { (e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)' }}
            >
              {link}
            </button>
          ))}
        </div>

        {/* CTA */}
        <motion.button
          onClick={handleEnter}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          transition={{ duration: 0.15, ease: EXPO }}
          style={{
            padding: '8px 20px', borderRadius: 999,
            background: 'linear-gradient(135deg, #6366f1, #7c3aed)',
            border: 'none', cursor: 'pointer', color: '#fff',
            fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
            letterSpacing: '0.01em',
            boxShadow: '0 0 20px rgba(99,102,241,0.35)',
          }}
        >
          Enter Platform →
        </motion.button>
      </motion.nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div
        ref={heroRef}
        style={{
          position: 'relative',
          width: '100%',
          height: '100dvh',
          overflow: 'hidden',
        }}
      >
        {/* Photo with parallax */}
        <motion.div
          style={{
            position: 'absolute',
            inset: '-10% 0',
            y: imgY,
          }}
        >
          <img
            src={HERO_IMG}
            alt=""
            fetchPriority="high"
            style={{
              width: '100%', height: '100%',
              objectFit: 'cover',
              objectPosition: 'center 55%',
              display: 'block',
            }}
          />
        </motion.div>

        {/* Overlays — darken bottom & edges so text pops */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(to bottom, rgba(7,7,15,0.18) 0%, rgba(7,7,15,0.05) 35%, rgba(7,7,15,0.72) 75%, rgba(7,7,15,0.97) 100%)',
        }} />
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse at 60% 50%, rgba(7,7,15,0) 40%, rgba(7,7,15,0.55) 100%)',
        }} />

        {/* Text block — bottom left */}
        <div style={{
          position: 'absolute',
          bottom: 'clamp(80px, 10vh, 130px)',
          left: 'clamp(24px, 5vw, 72px)',
          maxWidth: 680,
        }}>

          {/* Eyebrow badge */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EXPO, delay: 0.15 }}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '5px 12px 5px 8px', borderRadius: 999, marginBottom: 22,
              background: 'rgba(255,255,255,0.07)',
              border: '1px solid rgba(255,255,255,0.12)',
              backdropFilter: 'blur(12px)',
            }}
          >
            <div style={{
              width: 6, height: 6, borderRadius: '50%', background: '#22c55e',
              boxShadow: '0 0 8px #22c55e',
              animation: 'pulse 2s ease-in-out infinite',
            }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: 'rgba(255,255,255,0.7)', letterSpacing: '0.06em' }}>
              EU MARKETS · LIVE
            </span>
          </motion.div>

          {/* Headline */}
          <div style={{ overflow: 'hidden' }}>
            {['The intelligence', 'layer for EU', 'vehicle arbitrage.'].map((line, i) => (
              <motion.div
                key={line}
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease: EXPO, delay: 0.25 + i * 0.08 }}
                style={{
                  fontSize: 'clamp(2.4rem, 6vw, 5rem)',
                  fontWeight: 900,
                  lineHeight: 1.05,
                  letterSpacing: '-0.04em',
                  color: '#f8fafc',
                  display: 'block',
                  textShadow: '0 2px 40px rgba(0,0,0,0.5)',
                }}
              >
                {line}
              </motion.div>
            ))}
          </div>

          {/* Subline */}
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EXPO, delay: 0.55 }}
            style={{
              marginTop: 20, marginBottom: 32,
              fontSize: 'clamp(0.9rem, 1.6vw, 1.1rem)',
              fontWeight: 400, lineHeight: 1.6,
              color: 'rgba(255,255,255,0.55)',
              maxWidth: 480,
            }}
          >
            IVA vs REBU classification in under 2 seconds.
            Net Landed Cost to any EU country, instantly.
          </motion.p>

          {/* CTAs */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: EXPO, delay: 0.68 }}
            style={{ display: 'flex', alignItems: 'center', gap: 12 }}
          >
            <motion.button
              onClick={handleEnter}
              whileHover={{ scale: 1.04, boxShadow: '0 0 36px rgba(99,102,241,0.6)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ duration: 0.15, ease: EXPO }}
              style={{
                padding: '13px 28px', borderRadius: 999,
                background: 'linear-gradient(135deg, #6366f1 0%, #7c3aed 100%)',
                border: 'none', cursor: 'pointer', color: '#fff',
                fontSize: 15, fontWeight: 700, fontFamily: 'inherit',
                letterSpacing: '-0.01em',
                boxShadow: '0 0 28px rgba(99,102,241,0.4)',
              }}
            >
              Enter Platform
            </motion.button>

            <motion.button
              onClick={() => nav('/check')}
              whileHover={{ borderColor: 'rgba(255,255,255,0.3)', color: 'rgba(255,255,255,0.9)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ duration: 0.15 }}
              style={{
                padding: '13px 28px', borderRadius: 999,
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.14)',
                backdropFilter: 'blur(12px)',
                cursor: 'pointer', color: 'rgba(255,255,255,0.65)',
                fontSize: 15, fontWeight: 600, fontFamily: 'inherit',
                letterSpacing: '-0.01em',
                transition: 'border-color 0.2s, color 0.2s',
              }}
            >
              Check a VIN →
            </motion.button>
          </motion.div>
        </div>

        {/* ── Stat strip — pinned at very bottom of hero ─────────────── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, ease: EXPO, delay: 0.9 }}
          style={{
            position: 'absolute',
            bottom: 0, left: 0, right: 0,
            display: 'flex',
            borderTop: '1px solid rgba(255,255,255,0.07)',
            background: 'rgba(7,7,15,0.65)',
            backdropFilter: 'blur(20px) saturate(180%)',
            WebkitBackdropFilter: 'blur(20px) saturate(180%)',
          }}
        >
          {STATS.map((s, i) => (
            <React.Fragment key={s.label}>
              <div style={{
                flex: 1, padding: '18px 0', display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <StatItem value={s.value} label={s.label} delay={0.9 + i * 0.06} />
              </div>
              {i < STATS.length - 1 && (
                <div style={{ width: 1, background: 'rgba(255,255,255,0.07)', alignSelf: 'stretch' }} />
              )}
            </React.Fragment>
          ))}
        </motion.div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.4; transform: scale(0.85); }
        }
      `}</style>
    </div>
  )
}
