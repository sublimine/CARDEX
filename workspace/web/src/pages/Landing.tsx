import React, { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useScroll, useTransform } from 'framer-motion'
import { ArrowUpRight, Shield, Zap, Globe, TrendingUp, ChevronRight } from 'lucide-react'

const STATS = [
  { value: '3.5M+', label: 'Vehicles indexed' },
  { value: '6',     label: 'EU countries' },
  { value: '2,500+', label: 'Dealer sources' },
  { value: '< 2s',  label: 'Classification time' },
]

const FEATURES = [
  {
    icon: TrendingUp,
    color: '#5b8df8',
    title: 'Fiscal intelligence',
    desc: 'Automatic IVA / REBU classification for every vehicle. Full traceability to the prompt and model that produced it.',
  },
  {
    icon: Globe,
    color: '#9b6dff',
    title: 'Pan-European coverage',
    desc: 'DE, ES, FR, NL, BE, CH — sitemap-first indexing. Every dealer, every listing, nothing abandoned mid-pagination.',
  },
  {
    icon: Zap,
    color: '#00d68a',
    title: 'Real-time pipeline',
    desc: 'Redis Streams at-least-once delivery. From scrape to classified vehicle in under 2 seconds.',
  },
  {
    icon: Shield,
    color: '#ffb347',
    title: 'Arbitrage engine',
    desc: 'Net Landed Cost computed per destination country. Seller Desperation Index quantified on every listing.',
  },
]

const ease = [0.32, 0.72, 0, 1] as const

function FloatingOrb({ x, y, color, size }: { x: string; y: string; color: string; size: number }) {
  return (
    <div
      aria-hidden
      style={{
        position: 'absolute', left: x, top: y,
        width: size, height: size, borderRadius: '50%',
        background: color, filter: `blur(${size * 0.55}px)`,
        opacity: 0.12, pointerEvents: 'none',
      }}
    />
  )
}

export default function Landing() {
  const navigate = useNavigate()
  const heroRef  = useRef<HTMLDivElement>(null)
  const { scrollY } = useScroll()
  const heroY    = useTransform(scrollY, [0, 400], [0, -60])
  const heroO    = useTransform(scrollY, [0, 300], [1, 0.4])

  return (
    <div style={{ background: '#05050a', minHeight: '100dvh', fontFamily: 'Plus Jakarta Sans', overflowX: 'hidden', color: '#f0f0fa' }}>

      {/* Fixed noise overlay */}
      <div aria-hidden style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.025,
        backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 256 256\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")',
        backgroundRepeat: 'repeat', backgroundSize: '128px',
      }} />

      {/* ── NAVBAR ─────────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px', height: 64,
        background: 'rgba(5,5,10,0.8)',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        backdropFilter: 'blur(20px)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(91,141,248,0.15)', border: '1px solid rgba(91,141,248,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: '#5b8df8', boxShadow: '0 0 10px #5b8df8' }} />
          </div>
          <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: '0.15em', background: 'linear-gradient(120deg,#5b8df8,#c8d8ff)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            CARDEX
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => navigate('/login')}
            style={{ padding: '8px 20px', borderRadius: 10, fontSize: 13, fontWeight: 600, color: '#7070a0', background: 'transparent', border: '1px solid rgba(255,255,255,0.08)', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#f0f0fa'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.16)' }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = '#7070a0'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.08)' }}
          >
            Sign in
          </button>
          <motion.button
            onClick={() => navigate('/login')}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 420, damping: 22 }}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 18px', borderRadius: 10, fontSize: 13, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg, #4f6ef0 0%, #6b45e8 100%)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 0 24px rgba(91,141,248,0.22)' }}
          >
            Get access
            <div style={{ width: 20, height: 20, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <ArrowUpRight style={{ width: 11, height: 11 }} />
            </div>
          </motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────────── */}
      <motion.section
        ref={heroRef}
        style={{ y: heroY, opacity: heroO }}
        initial={false}
      >
        <div style={{ position: 'relative', minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '120px 24px 80px', overflow: 'hidden' }}>

          {/* Orbs */}
          <FloatingOrb x="5%"  y="10%" color="#5b8df8" size={500} />
          <FloatingOrb x="65%" y="60%" color="#9b6dff" size={400} />
          <FloatingOrb x="40%" y="30%" color="#00d68a" size={200} />

          {/* Grid overlay */}
          <div aria-hidden style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none', opacity: 0.025,
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }} />

          <div style={{ position: 'relative', zIndex: 1, maxWidth: 820 }}>

            {/* Eyebrow pill */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 999, background: 'rgba(91,141,248,0.08)', border: '1px solid rgba(91,141,248,0.22)', marginBottom: 28 }}
            >
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#5b8df8', display: 'block', boxShadow: '0 0 8px #5b8df8', animation: 'pulse 2s infinite' }} />
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#5b8df8' }}>
                B2B vehicle intelligence platform
              </span>
            </motion.div>

            {/* H1 */}
            <motion.h1
              initial={{ opacity: 0, y: 20, filter: 'blur(8px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0)' }}
              transition={{ delay: 0.08, duration: 0.65, ease }}
              style={{ fontSize: 'clamp(42px, 7vw, 80px)', fontWeight: 900, lineHeight: 1.05, letterSpacing: '-0.035em', marginBottom: 24, color: '#f0f0fa' }}
            >
              The fiscal intelligence{' '}
              <span style={{ background: 'linear-gradient(120deg, #5b8df8 0%, #9b6dff 50%, #00d68a 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                layer for EU vehicle arbitrage
              </span>
            </motion.h1>

            {/* Sub */}
            <motion.p
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18, duration: 0.55, ease }}
              style={{ fontSize: 18, color: '#5050708', lineHeight: 1.7, maxWidth: 580, margin: '0 auto 40px', color: '#50507a' }}
            >
              3.5M listings. 6 EU countries. IVA/REBU auto-classification. Net Landed Cost per destination.
              The complete edge for professional used-vehicle traders.
            </motion.p>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.26, duration: 0.5, ease }}
              style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}
            >
              <motion.button
                onClick={() => navigate('/login')}
                whileHover={{ scale: 1.03, boxShadow: '0 0 40px rgba(91,141,248,0.35)' }}
                whileTap={{ scale: 0.97 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 28px', borderRadius: 12, fontSize: 15, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg, #4f6ef0 0%, #7b45e8 100%)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 0 30px rgba(91,141,248,0.2)', transition: 'box-shadow 0.3s' }}
              >
                Open platform
                <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowUpRight style={{ width: 13, height: 13 }} />
                </div>
              </motion.button>

              <button
                onClick={() => { const el = document.getElementById('features'); el?.scrollIntoView({ behavior: 'smooth' }) }}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 24px', borderRadius: 12, fontSize: 15, fontWeight: 600, color: '#7070a0', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.09)', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', transition: 'all 0.2s' }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = '#c0c0e0'; (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.06)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = '#7070a0'; (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.03)' }}
              >
                See how it works <ChevronRight style={{ width: 14, height: 14 }} />
              </button>
            </motion.div>
          </div>

          {/* Scroll hint */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1, duration: 1 }}
            style={{ position: 'absolute', bottom: 32, left: '50%', transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}
          >
            <span style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#2a2a4a' }}>Scroll</span>
            <motion.div
              animate={{ y: [0, 6, 0] }} transition={{ repeat: Infinity, duration: 1.6, ease: 'easeInOut' }}
              style={{ width: 1, height: 32, background: 'linear-gradient(to bottom, #2a2a4a, transparent)' }}
            />
          </motion.div>
        </div>
      </motion.section>

      {/* ── STATS ──────────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 24px 100px' }}>
        <div style={{ maxWidth: 900, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {STATS.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.5, ease }}
              style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 16, padding: '24px 20px', textAlign: 'center' }}
            >
              <div style={{ fontSize: 36, fontWeight: 900, letterSpacing: '-0.03em', background: 'linear-gradient(135deg, #f0f0fa, #9090b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', marginBottom: 6 }}>
                {s.value}
              </div>
              <div style={{ fontSize: 12, color: '#38385a', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                {s.label}
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── FEATURES ───────────────────────────────────────────────────────── */}
      <section id="features" style={{ padding: '0 24px 120px' }}>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, ease }}
            style={{ textAlign: 'center', marginBottom: 60 }}
          >
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 14px', borderRadius: 999, background: 'rgba(155,109,255,0.08)', border: '1px solid rgba(155,109,255,0.2)', marginBottom: 18 }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#9b6dff' }}>Platform capabilities</span>
            </div>
            <h2 style={{ fontSize: 38, fontWeight: 900, letterSpacing: '-0.03em', color: '#f0f0fa', marginBottom: 14 }}>
              Built for professional traders
            </h2>
            <p style={{ fontSize: 16, color: '#50507a', maxWidth: 500, margin: '0 auto' }}>
              Every feature designed around the real friction in cross-border vehicle arbitrage.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08, duration: 0.5, ease }}
                whileHover={{ y: -3 }}
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 18, padding: '28px 28px',
                  position: 'relative', overflow: 'hidden',
                  transition: 'border-color 0.3s',
                  cursor: 'default',
                }}
                onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.borderColor = `${f.color}40`}
                onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.07)'}
              >
                {/* Glow */}
                <div aria-hidden style={{ position: 'absolute', top: -40, right: -20, width: 120, height: 120, borderRadius: '50%', background: f.color, opacity: 0.07, filter: 'blur(40px)', pointerEvents: 'none' }} />

                <div style={{ width: 40, height: 40, borderRadius: 12, background: `${f.color}18`, border: `1px solid ${f.color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }}>
                  <f.icon style={{ width: 18, height: 18, color: f.color }} strokeWidth={1.8} />
                </div>
                <h3 style={{ fontSize: 16, fontWeight: 800, color: '#e0e0f0', marginBottom: 10, letterSpacing: '-0.01em' }}>{f.title}</h3>
                <p style={{ fontSize: 13, color: '#50507a', lineHeight: 1.65 }}>{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA BOTTOM ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '0 24px 120px' }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease }}
          style={{ maxWidth: 680, margin: '0 auto', textAlign: 'center', padding: '64px 48px', background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 24, position: 'relative', overflow: 'hidden' }}
        >
          <FloatingOrb x="10%"  y="20%" color="#5b8df8" size={200} />
          <FloatingOrb x="70%" y="50%" color="#9b6dff" size={150} />

          <div style={{ position: 'relative', zIndex: 1 }}>
            <h2 style={{ fontSize: 34, fontWeight: 900, letterSpacing: '-0.03em', color: '#f0f0fa', marginBottom: 14 }}>
              Ready to trade smarter?
            </h2>
            <p style={{ fontSize: 15, color: '#50507a', marginBottom: 32, lineHeight: 1.6 }}>
              Access 3.5M classified vehicle listings across 6 EU markets. No guesswork on fiscal regimes.
            </p>
            <motion.button
              onClick={() => navigate('/login')}
              whileHover={{ scale: 1.04, boxShadow: '0 0 50px rgba(91,141,248,0.4)' }}
              whileTap={{ scale: 0.97 }}
              transition={{ type: 'spring', stiffness: 400, damping: 20 }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '14px 32px', borderRadius: 12, fontSize: 15, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg, #4f6ef0 0%, #7b45e8 100%)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 0 30px rgba(91,141,248,0.2)' }}
            >
              Enter workspace
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'rgba(255,255,255,0.18)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <ArrowUpRight style={{ width: 13, height: 13 }} />
              </div>
            </motion.button>
          </div>
        </motion.div>
      </section>

      {/* ── FOOTER ─────────────────────────────────────────────────────────── */}
      <footer style={{ borderTop: '1px solid rgba(255,255,255,0.05)', padding: '24px 40px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.15em', background: 'linear-gradient(120deg,#5b8df8,#c8d8ff)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>CARDEX</span>
        <span style={{ fontSize: 12, color: '#1e1e38' }}>© 2026 · B2B Vehicle Intelligence</span>
      </footer>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
