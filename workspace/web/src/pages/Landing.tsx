import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

const EXPO = [0.16, 1, 0.3, 1] as const

const HERO_IMG =
  'https://i.pinimg.com/originals/8f/67/ad/8f67ad9d7fef82b5943608def344573b.jpg'

/* Trader avatars — initials as placeholder */
const AVATARS = ['E', 'M', 'A', 'J']
const AVATAR_COLORS = ['#6366f1', '#7c3aed', '#0891b2', '#059669']

export default function Landing() {
  const nav = useNavigate()
  const { isAuthenticated } = useAuthContext()
  const [navScrolled, setNavScrolled] = useState(false)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const fn = () => setNavScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  function handleEnter() {
    nav(isAuthenticated ? '/dashboard' : '/login')
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (q) nav(`/check/${encodeURIComponent(q)}`)
    else nav('/check')
  }

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#07070f' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        height: 60, display: 'flex', alignItems: 'center',
        padding: '0 clamp(20px, 4vw, 48px)',
        transition: 'background 0.3s, border-color 0.3s',
        background: navScrolled ? 'rgba(7,7,15,0.75)' : 'transparent',
        backdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
        WebkitBackdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
        borderBottom: navScrolled ? '1px solid rgba(255,255,255,0.07)' : '1px solid transparent',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'linear-gradient(135deg,#6366f1,#7c3aed)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 14px rgba(99,102,241,0.4)',
          }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: 'rgba(255,255,255,0.92)' }} />
          </div>
          <span style={{
            fontSize: 13, fontWeight: 800, letterSpacing: '0.13em',
            background: 'linear-gradient(120deg,#c4b5fd,#818cf8,#67e8f9)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
          }}>CARDEX</span>
        </div>

        {/* Center nav */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 36 }}>
          {['Platform', 'Coverage', 'Pricing'].map(l => (
            <button key={l} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.55)',
              fontFamily: 'inherit', transition: 'color 0.18s',
            }}
              onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
              onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.55)')}
            >{l}</button>
          ))}
        </div>

        {/* Right */}
        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12 }}>
          <button
            onClick={handleEnter}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.55)',
              fontFamily: 'inherit', transition: 'color 0.18s',
            }}
            onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
            onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.55)')}
          >Log In</button>
          <motion.button
            onClick={handleEnter}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            transition={{ duration: 0.14, ease: EXPO }}
            style={{
              padding: '7px 20px', borderRadius: 999,
              background: 'rgba(255,255,255,0.10)',
              border: '1px solid rgba(255,255,255,0.18)',
              backdropFilter: 'blur(12px)',
              color: '#fff', fontSize: 14, fontWeight: 600,
              cursor: 'pointer', fontFamily: 'inherit',
            }}
          >Sign In</motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>

        {/* Photo */}
        <img
          src={HERO_IMG}
          alt=""
          fetchPriority="high"
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit: 'cover', objectPosition: 'center 40%',
          }}
        />

        {/* Gradient overlay — top subtle, bottom dark */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(to bottom, rgba(7,7,15,0.25) 0%, rgba(7,7,15,0.08) 30%, rgba(7,7,15,0.55) 70%, rgba(7,7,15,0.92) 100%)',
        }} />

        {/* Center content */}
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          padding: '0 24px',
          textAlign: 'center',
          paddingTop: 60,
        }}>

          {/* Social proof */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: EXPO, delay: 0.1 }}
            style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 24 }}
          >
            <div style={{ display: 'flex' }}>
              {AVATARS.map((a, i) => (
                <div key={i} style={{
                  width: 30, height: 30, borderRadius: '50%',
                  background: AVATAR_COLORS[i],
                  border: '2px solid rgba(7,7,15,0.6)',
                  marginLeft: i > 0 ? -8 : 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, fontWeight: 700, color: '#fff',
                  zIndex: AVATARS.length - i,
                  position: 'relative',
                }}>{a}</div>
              ))}
            </div>
            <span style={{ fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.75)' }}>
              1,550,000+ vehicles indexed across EU
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, ease: EXPO, delay: 0.2 }}
            style={{
              fontSize: 'clamp(2.6rem, 7vw, 5.5rem)',
              fontWeight: 900,
              lineHeight: 1.06,
              letterSpacing: '-0.04em',
              color: '#fff',
              margin: '0 0 20px',
              maxWidth: 800,
              textShadow: '0 2px 40px rgba(0,0,0,0.4)',
            }}
          >
            The intelligence layer<br />for EU vehicle arbitrage.
          </motion.h1>

          {/* Subline */}
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EXPO, delay: 0.32 }}
            style={{
              fontSize: 'clamp(0.95rem, 1.8vw, 1.15rem)',
              fontWeight: 400,
              lineHeight: 1.65,
              color: 'rgba(255,255,255,0.6)',
              margin: '0 0 36px',
              maxWidth: 500,
            }}
          >
            IVA vs REBU classified in under 2 seconds.<br />
            Net Landed Cost to any EU country, instantly.
          </motion.p>

          {/* ── SEARCH BAR ─────────────────────────────────────────────── */}
          <motion.form
            onSubmit={handleSearch}
            initial={{ opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.55, ease: EXPO, delay: 0.44 }}
            style={{
              display: 'flex', alignItems: 'center',
              width: '100%', maxWidth: 520,
              borderRadius: 999,
              background: 'rgba(255,255,255,0.10)',
              backdropFilter: 'blur(24px) saturate(180%)',
              WebkitBackdropFilter: 'blur(24px) saturate(180%)',
              border: '1px solid rgba(255,255,255,0.18)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.14)',
              padding: '5px 5px 5px 22px',
              gap: 8,
            }}
          >
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Enter a VIN or plate number..."
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                fontSize: 15, fontWeight: 400, color: '#fff',
                fontFamily: 'inherit',
                '::placeholder': { color: 'rgba(255,255,255,0.4)' },
              } as React.CSSProperties}
            />
            <motion.button
              type="submit"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              transition={{ duration: 0.12, ease: EXPO }}
              style={{
                padding: '10px 22px', borderRadius: 999, flexShrink: 0,
                background: 'rgba(30,27,75,0.85)',
                border: '1px solid rgba(255,255,255,0.12)',
                color: '#fff', fontSize: 14, fontWeight: 600,
                cursor: 'pointer', fontFamily: 'inherit',
                letterSpacing: '-0.01em',
                backdropFilter: 'blur(8px)',
              }}
            >
              Check Now →
            </motion.button>
          </motion.form>

        </div>
      </div>

      <style>{`
        input::placeholder { color: rgba(255,255,255,0.38) !important; }
      `}</style>
    </div>
  )
}
