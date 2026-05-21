/**
 * CARDEX Landing — Dark Organic Liquid Glass
 * 5-scene cinematic scroll: Hero → Stats → Device Showcase → Feature Bento → CTA Final
 * Emil Kowalski animation framework: scale(0.96)+opacity:0 origins, ease-out-expo physics.
 */
import React, { useRef, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  motion,
  useScroll,
  useTransform,
  useSpring,
  useInView,
  AnimatePresence,
} from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

/* ─── Easing constants ──────────────────────────────────────────────────────── */
const EXPO   = [0.16, 1, 0.3, 1]  as const
const SPRING = [0.23, 1, 0.32, 1] as const
const BOUNCE = [0.34, 1.56, 0.64, 1] as const

/* ─── Animation variants ────────────────────────────────────────────────────── */
const fadeUp = {
  hidden: { opacity: 0, y: 22, scale: 0.97 },
  show:   { opacity: 1, y: 0,  scale: 1, transition: { duration: 0.6, ease: EXPO } },
}

const fadeUpFast = {
  hidden: { opacity: 0, y: 14, scale: 0.97 },
  show:   { opacity: 1, y: 0,  scale: 1, transition: { duration: 0.45, ease: EXPO } },
}

const staggerContainer = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.09, delayChildren: 0.1 } },
}

const wordReveal = {
  hidden: { opacity: 0, y: 28 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.65, ease: EXPO } },
}

/* ─── Glass surface styles ──────────────────────────────────────────────────── */
const glass = (alpha = 0.10, blur = 32, glow?: string): React.CSSProperties => ({
  background:       `rgba(255,255,255,${alpha})`,
  backdropFilter:   `blur(${blur}px) saturate(200%)`,
  WebkitBackdropFilter: `blur(${blur}px) saturate(200%)`,
  border:           '1px solid rgba(255,255,255,0.15)',
  boxShadow:        [
    '0 8px 32px rgba(0,0,0,0.4)',
    'inset 0 1px 0 rgba(255,255,255,0.18)',
    glow ?? '',
  ].filter(Boolean).join(', '),
})

const glassCard = (glow?: string): React.CSSProperties => ({
  ...glass(0.10, 40, glow),
  borderRadius: 24,
  overflow: 'hidden',
  position: 'relative',
})

/* ─── Animated counter hook ─────────────────────────────────────────────────── */
function useCounter(target: number, duration = 1.8, delay = 0): number {
  const [value, setValue] = useState(0)
  const ref = useRef(false)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (ref.current) return
    const timeout = setTimeout(() => {
      ref.current = true
      const start = performance.now()
      startRef.current = start
      const tick = (now: number) => {
        const elapsed = (now - start) / 1000
        const progress = Math.min(elapsed / duration, 1)
        // ease-out-expo
        const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)
        setValue(Math.round(eased * target))
        if (progress < 1) requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    }, delay * 1000)
    return () => clearTimeout(timeout)
  }, [target, duration, delay])

  return value
}

/* ─── Scroll-aware counter ───────────────────────────────────────────────────── */
interface CounterProps {
  target: number
  duration?: number
  delay?: number
  format?: (n: number) => string
}
function Counter({ target, duration = 1.8, delay = 0, format }: CounterProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-80px' })
  const [started, setStarted] = useState(false)
  const value = useCounter(started ? target : 0, duration, delay)

  useEffect(() => {
    if (inView) setStarted(true)
  }, [inView])

  return <span ref={ref}>{format ? format(value) : value.toLocaleString('en-US')}</span>
}

/* ─── Organic blob mesh (scene-local) ───────────────────────────────────────── */
function OrgMesh() {
  return (
    <div aria-hidden style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none', zIndex: 0 }}>
      <div style={{
        position: 'absolute', top: '-10%', right: '-5%',
        width: 900, height: 900,
        background: 'radial-gradient(ellipse 60% 70% at 60% 40%, rgba(124,58,237,0.28) 0%, rgba(124,58,237,0) 70%)',
        filter: 'blur(60px)',
        animation: 'cxFloat1 18s ease-in-out infinite',
      }} />
      <div style={{
        position: 'absolute', bottom: '5%', left: '-8%',
        width: 700, height: 700,
        background: 'radial-gradient(ellipse 55% 65% at 45% 55%, rgba(37,99,235,0.22) 0%, rgba(37,99,235,0) 70%)',
        filter: 'blur(70px)',
        animation: 'cxFloat2 22s ease-in-out infinite',
      }} />
      <div style={{
        position: 'absolute', top: '40%', left: '30%',
        width: 600, height: 500,
        background: 'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(8,145,178,0.16) 0%, rgba(8,145,178,0) 70%)',
        filter: 'blur(80px)',
        animation: 'cxFloat3 15s ease-in-out infinite',
      }} />
    </div>
  )
}

/* ─── Scroll indicator ──────────────────────────────────────────────────────── */
function ScrollChevron({ onClick }: { onClick: () => void }) {
  return (
    <motion.button
      onClick={onClick}
      aria-label="Scroll to next section"
      style={{
        background: 'none', border: 'none', cursor: 'pointer', padding: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      }}
      animate={{ y: [0, 9, 0] }}
      transition={{ duration: 2.2, ease: 'easeInOut', repeat: Infinity }}
    >
      <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase' }}>Scroll</span>
      <svg width={20} height={20} viewBox="0 0 20 20" fill="none">
        <path d="M4 7l6 6 6-6" stroke="rgba(255,255,255,0.35)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </motion.button>
  )
}

/* ─── Mini Gauge SVG ────────────────────────────────────────────────────────── */
function MiniGauge({ value, color }: { value: number; color: string }) {
  const R = 36
  const cx = 44, cy = 46
  const arc = Math.PI * R
  const pct = Math.min(value / 10, 1)

  return (
    <svg width={88} height={54} viewBox="0 0 88 54" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id="mgGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor={color} />
        </linearGradient>
      </defs>
      <path
        d={`M 8,${cy} A ${R},${R} 0 0 1 ${2 * cx - 8},${cy}`}
        fill="none"
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={6}
        strokeLinecap="round"
      />
      <motion.path
        d={`M 8,${cy} A ${R},${R} 0 0 1 ${2 * cx - 8},${cy}`}
        fill="none"
        stroke="url(#mgGrad)"
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={`${arc}`}
        initial={{ strokeDashoffset: arc }}
        whileInView={{ strokeDashoffset: arc * (1 - pct) }}
        viewport={{ once: true }}
        transition={{ duration: 1.6, ease: EXPO, delay: 0.3 }}
      />
      <circle cx={cx} cy={cy} r={3.5} fill={color} />
    </svg>
  )
}

/* ─── Flag chip ─────────────────────────────────────────────────────────────── */
function FlagChip({ flag, label, delay }: { flag: string; label: string; delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8, y: 8 }}
      whileInView={{ opacity: 1, scale: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, ease: BOUNCE, delay }}
      style={{
        display: 'flex', alignItems: 'center', gap: 7,
        padding: '7px 14px',
        borderRadius: 99,
        background: 'rgba(255,255,255,0.08)',
        border: '1px solid rgba(255,255,255,0.14)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <span style={{ fontSize: 18, lineHeight: 1 }}>{flag}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.8)', letterSpacing: '0.02em' }}>{label}</span>
    </motion.div>
  )
}

/* ─── Device mockup — inner bento (reused from the product) ─────────────────── */
const PHOTO = 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1000&q=95&auto=format&fit=crop'

const INNER_SHELL: React.CSSProperties = {
  borderRadius: 18,
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.08)',
  padding: 3,
  boxShadow: '0 2px 0 rgba(255,255,255,0.07) inset, 0 12px 36px rgba(0,0,0,0.5)',
}
const INNER_CORE: React.CSSProperties = {
  borderRadius: 16,
  background: 'rgba(20,18,36,0.90)',
  padding: '14px 16px',
  height: '100%',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.07)',
  overflow: 'hidden',
  position: 'relative',
}

function DeviceBento() {
  const [tab, setTab] = useState(0)
  const [ivaOn, setIvaOn] = useState(true)
  const [rebuOn, setRebuOn] = useState(true)

  return (
    <div style={{
      width: '100%',
      borderRadius: 20,
      overflow: 'hidden',
      background: '#0e0e22',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
    }}>
      {/* Top bar */}
      <div style={{
        height: 46,
        display: 'flex', alignItems: 'center',
        padding: '0 12px', gap: 8,
        background: 'rgba(14,14,34,0.97)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 4 }}>
          <div style={{
            width: 26, height: 26, borderRadius: 8,
            background: 'rgba(99,102,241,0.20)',
            border: '1px solid rgba(99,102,241,0.40)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 14px rgba(99,102,241,0.28)',
          }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: 'linear-gradient(135deg,#a5b4fc,#6366f1)' }} />
          </div>
          <span style={{
            fontSize: 11, fontWeight: 800, letterSpacing: '0.14em',
            background: 'linear-gradient(120deg,#a5b4fc 0%,#c4b5fd 50%,#67e8f9 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
          }}>CARDEX</span>
        </div>
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: 999, padding: 2, border: '1px solid rgba(255,255,255,0.07)' }}>
          {['Dashboard', 'Coverage', 'Listings', 'Reports'].map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              style={{
                padding: '3px 11px', borderRadius: 999, fontSize: 10, fontWeight: 600,
                border: 'none', cursor: 'pointer', fontFamily: 'Inter, sans-serif',
                background: tab === i ? 'rgba(255,255,255,0.12)' : 'transparent',
                color: tab === i ? '#f1f5f9' : '#64748b',
                boxShadow: tab === i ? 'inset 0 1px 0 rgba(255,255,255,0.12)' : 'none',
                transition: 'all 180ms',
              }}
            >{t}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{
          width: 26, height: 26, borderRadius: '50%',
          background: 'linear-gradient(135deg,#6366f1,#7c3aed)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 9, fontWeight: 800, color: '#fff',
          boxShadow: '0 0 12px rgba(99,102,241,0.4)',
        }}>E</div>
      </div>

      {/* Body */}
      <div style={{ display: 'flex', height: 360, overflow: 'hidden' }}>
        {/* Sidebar */}
        <div style={{ width: 42, flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 12, gap: 3, background: 'rgba(10,10,26,0.88)', borderRight: '1px solid rgba(255,255,255,0.05)' }}>
          {[
            <path key="h" d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />,
            <><circle key="c" cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth={1.5} /><path d="M8 12h8M12 8v8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></>,
            <><rect key="r1" x="3" y="3" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5} /><rect x="14" y="3" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5} /><rect x="14" y="14" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5} /><rect x="3" y="14" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5} /></>,
            <path key="s" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" />,
          ].map((icon, i) => (
            <button
              key={i}
              style={{
                width: 30, height: 30, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer',
                background: i === 0 ? 'rgba(255,255,255,0.10)' : 'transparent',
                border: i === 0 ? '1px solid rgba(255,255,255,0.15)' : '1px solid transparent',
              }}
            >
              <svg width={14} height={14} viewBox="0 0 24 24" style={{ color: i === 0 ? '#e2e8f0' : '#334155' }}>{icon}</svg>
            </button>
          ))}
        </div>

        {/* Photo panel */}
        <div style={{ flex: '0 0 40%', position: 'relative', overflow: 'hidden' }}>
          <img src={PHOTO} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 55%' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 70% 40%, rgba(251,146,60,0.18) 0%, transparent 55%)' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to right, transparent 0%, rgba(14,14,34,0.65) 100%)' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(14,14,34,0.97) 0%, transparent 55%)' }} />
          <div style={{ position: 'absolute', top: 14, left: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em', textShadow: '0 2px 16px rgba(0,0,0,0.5)' }}>Hello, trader.</div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.42)', marginTop: 2 }}>Track your EU arbitrage in real time</div>
          </div>
          <div style={{ position: 'absolute', bottom: 12, left: 14 }}>
            <button style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '8px 16px', borderRadius: 999, fontSize: 11, fontWeight: 700, color: '#fff',
              background: 'linear-gradient(135deg,#6366f1,#7c3aed)',
              border: 'none', cursor: 'pointer',
              boxShadow: '0 0 20px rgba(99,102,241,0.45)',
              fontFamily: 'Inter, sans-serif',
            }}>
              Enter platform
              <svg width={8} height={8} viewBox="0 0 10 10" fill="none">
                <path d="M1 9L9 1M9 1H3M9 1V7" stroke="#fff" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>

        {/* Right bento */}
        <div style={{
          flex: 1, padding: '10px 10px 0 7px',
          display: 'grid', gridTemplateColumns: '1fr 1fr',
          gridTemplateRows: 'auto auto auto auto',
          gap: 6, background: 'rgba(8,8,22,0.5)', overflowY: 'auto',
        }}>
          {/* Card: New Listings */}
          <div style={INNER_SHELL}>
            <div style={INNER_CORE}>
              <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', letterSpacing: '0.04em', marginBottom: 8 }}>New Listings Today</div>
              <div style={{ fontSize: 26, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.05em', marginBottom: 10 }}>2,847</div>
              {[{ l: '🇩🇪', p: 0.72, c: '#6366f1' }, { l: '🇪🇸', p: 0.58, c: '#7c3aed' }, { l: '🇫🇷', p: 0.44, c: '#0891b2' }].map(({ l, p, c }) => (
                <div key={l} style={{ marginBottom: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                    <span style={{ fontSize: 9, color: '#475569' }}>{l} {Math.round(p * 100)}%</span>
                  </div>
                  <div style={{ height: 3.5, background: 'rgba(255,255,255,0.06)', borderRadius: 99 }}>
                    <div style={{ height: '100%', width: `${p * 100}%`, background: `linear-gradient(90deg,${c}55,${c})`, borderRadius: 99, transition: 'width 0.9s' }} />
                  </div>
                </div>
              ))}
              <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#06b6d4', boxShadow: '0 0 8px #06b6d4', animation: 'cxPulse 2s infinite' }} />
                <span style={{ fontSize: 8, color: '#334155' }}>Auto-indexing active</span>
              </div>
            </div>
          </div>

          {/* Card: Top Opportunity */}
          <div style={{ ...INNER_SHELL, background: 'rgba(99,102,241,0.10)', border: '1px solid rgba(99,102,241,0.22)' }}>
            <div style={{ ...INNER_CORE, background: 'rgba(18,16,40,0.90)', display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: '#818cf8', marginBottom: 5 }}>Top Opportunity</div>
              <div style={{ fontSize: 24, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.05em', lineHeight: 1.1, marginBottom: 2 }}>€58.900</div>
              <div style={{ fontSize: 9, color: '#6366f1', marginBottom: 8, fontWeight: 600 }}>BMW M3 · Munich</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, flex: 1, paddingBottom: 2 }}>
                {[42, 55, 48, 64, 58, 72, 66].map((v, i) => (
                  <div key={i} style={{ flex: 1, background: i === 6 ? '#6366f1' : 'rgba(99,102,241,0.18)', borderRadius: '2px 2px 0 0', height: `${v}%` }} />
                ))}
              </div>
            </div>
          </div>

          {/* Card: IVA — full width */}
          <div style={{ ...INNER_SHELL, gridColumn: '1 / -1' }}
            onClick={() => setIvaOn(v => !v)}>
            <div style={{ ...INNER_CORE, padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{ width: 28, height: 28, borderRadius: 9, background: 'rgba(6,182,212,0.14)', border: '1px solid rgba(6,182,212,0.28)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="#06b6d4" strokeWidth={1.8} strokeLinecap="round"><rect x="2" y="2" width="20" height="20" rx="5" /><path d="M16 12H8M12 8v8" /></svg>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#f1f5f9' }}>IVA Deductible</div>
                  <div style={{ fontSize: 8.5, color: '#475569', marginTop: 1 }}>Auto-classification · 62% of fleet</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: ivaOn ? '#06b6d4' : '#475569' }}>{ivaOn ? 'Active' : 'Paused'}</span>
                <div style={{ width: 40, height: 22, borderRadius: 99, background: ivaOn ? '#06b6d4' : 'rgba(255,255,255,0.10)', border: `1.5px solid ${ivaOn ? '#06b6d4' : 'rgba(255,255,255,0.14)'}`, position: 'relative', transition: 'background 0.25s, border 0.25s' }}>
                  <div style={{ position: 'absolute', top: 2.5, left: ivaOn ? 20 : 2.5, width: 14, height: 14, borderRadius: '50%', background: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.35)', transition: 'left 0.25s' }} />
                </div>
              </div>
            </div>
          </div>

          {/* Card: SDI */}
          <div style={INNER_SHELL}>
            <div style={INNER_CORE}>
              <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', marginBottom: 2 }}>Seller Desperation</div>
              <div style={{ fontSize: 10, color: '#f43f5e', fontWeight: 700, marginBottom: 4 }}>8.2 · High urgency</div>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <MiniGauge value={8.2} color="#f43f5e" />
              </div>
            </div>
          </div>

          {/* Card: REBU */}
          <div style={INNER_SHELL} onClick={() => setRebuOn(v => !v)}>
            <div style={{ ...INNER_CORE, display: 'flex', flexDirection: 'column', cursor: 'pointer' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: '#64748b' }}>REBU</span>
                <div style={{ width: 38, height: 20, borderRadius: 99, background: rebuOn ? '#f59e0b' : 'rgba(255,255,255,0.10)', position: 'relative', transition: 'background 0.25s' }}>
                  <div style={{ position: 'absolute', top: 2, left: rebuOn ? 18 : 2, width: 14, height: 14, borderRadius: '50%', background: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.35)', transition: 'left 0.25s' }} />
                </div>
              </div>
              <div style={{ fontSize: 26, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.04em' }}>38%</div>
              <div style={{ fontSize: 8.5, color: '#475569', marginTop: 2 }}>of fleet classified</div>
            </div>
          </div>

          {/* Card: NLC full width */}
          <div style={{ ...INNER_SHELL, gridColumn: '1 / -1', marginBottom: 10 }}>
            <div style={INNER_CORE}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', marginBottom: 3 }}>NLC Activity — this week</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <span style={{ fontSize: 20, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.04em' }}>4.8%</span>
                    <span style={{ fontSize: 9, color: '#06b6d4', fontWeight: 600 }}>avg margin EU6</span>
                  </div>
                </div>
                <div style={{ padding: '4px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.88)', backdropFilter: 'blur(8px)' }}>
                  <span style={{ fontSize: 9, fontWeight: 800, color: '#0a0a1a' }}>+4.8%</span>
                </div>
              </div>
              {/* Sparkline */}
              <svg width="100%" height={38} viewBox="0 0 100 38" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="nlcGr" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <path d="M0,38 L0,22 L14,18 L28,26 L43,12 L57,20 L71,8 L85,14 L100,4 L100,38 Z" fill="url(#nlcGr)" />
                <path d="M0,22 L14,18 L28,26 L43,12 L57,20 L71,8 L85,14 L100,4" fill="none" stroke="#06b6d4" strokeWidth={1.6} strokeLinecap="round" />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Feature card ──────────────────────────────────────────────────────────── */
interface FeatureCardProps {
  title: string
  description: string
  accent: string
  icon: React.ReactNode
  extra?: React.ReactNode
  large?: boolean
  delay?: number
}
function FeatureCard({ title, description, accent, icon, extra, large, delay = 0 }: FeatureCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.96 }}
      whileInView={{ opacity: 1, y: 0, scale: 1 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.55, ease: EXPO, delay }}
      whileHover={{ y: -5, transition: { duration: 0.22, ease: SPRING } }}
      style={{
        ...glassCard(`0 0 40px ${accent}18`),
        padding: large ? '32px 28px' : '24px 22px',
        gridColumn: large ? 'span 2' : undefined,
        cursor: 'default',
        minHeight: large ? 220 : 180,
      }}
    >
      {/* Top edge highlight */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 1, background: `linear-gradient(90deg, transparent 0%, ${accent}55 50%, transparent 100%)` }} />

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div style={{
            width: 44, height: 44, borderRadius: 14,
            background: `${accent}18`,
            border: `1px solid ${accent}35`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 0 20px ${accent}22`,
            flexShrink: 0,
          }}>
            {icon}
          </div>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}`, marginTop: 4 }} />
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.025em', marginBottom: 8, lineHeight: 1.2 }}>{title}</div>
          <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.52)', lineHeight: 1.6 }}>{description}</div>
        </div>

        {extra && <div>{extra}</div>}
      </div>
    </motion.div>
  )
}

/* ─── CTA Button with shimmer ───────────────────────────────────────────────── */
interface CtaButtonProps {
  label: string
  onClick: () => void
  large?: boolean
  secondary?: boolean
}
function CtaButton({ label, onClick, large, secondary }: CtaButtonProps) {
  const [hovered, setHovered] = useState(false)

  if (secondary) {
    return (
      <motion.button
        onClick={onClick}
        whileTap={{ scale: 0.97 }}
        onHoverStart={() => setHovered(true)}
        onHoverEnd={() => setHovered(false)}
        style={{
          padding: large ? '16px 36px' : '12px 26px',
          borderRadius: 99,
          fontSize: large ? 16 : 14,
          fontWeight: 600,
          color: 'rgba(255,255,255,0.65)',
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.20)',
          cursor: 'pointer',
          fontFamily: 'Inter, sans-serif',
          letterSpacing: '-0.01em',
          transition: 'color 200ms, border-color 200ms',
        }}
      >
        {label}
      </motion.button>
    )
  }

  return (
    <motion.button
      onClick={onClick}
      whileTap={{ scale: 0.97 }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      style={{
        position: 'relative',
        padding: large ? '18px 44px' : '13px 32px',
        borderRadius: 99,
        fontSize: large ? 17 : 15,
        fontWeight: 700,
        color: '#fff',
        background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 50%, #2563eb 100%)',
        border: 'none',
        cursor: 'pointer',
        fontFamily: 'Inter, sans-serif',
        letterSpacing: '-0.015em',
        overflow: 'hidden',
        boxShadow: hovered
          ? '0 0 60px rgba(124,58,237,0.55), 0 8px 32px rgba(124,58,237,0.35)'
          : '0 0 32px rgba(124,58,237,0.30), 0 4px 16px rgba(0,0,0,0.3)',
        transition: 'box-shadow 280ms',
      }}
    >
      {/* Shimmer sweep */}
      <motion.div
        style={{
          position: 'absolute', inset: 0,
          background: 'linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.22) 50%, transparent 70%)',
          backgroundSize: '200% 100%',
        }}
        animate={{ backgroundPosition: hovered ? '-100% 0' : '200% 0' }}
        transition={{ duration: 0.55, ease: EXPO }}
      />
      <span style={{ position: 'relative', zIndex: 1 }}>{label}</span>
    </motion.button>
  )
}

/* ─── SCENE 1: Hero ─────────────────────────────────────────────────────────── */
function SceneHero({ onScrollDown, isAuthenticated }: { onScrollDown: () => void; isAuthenticated: boolean }) {
  const nav = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ['start start', 'end start'] })
  const y = useTransform(scrollYProgress, [0, 1], [0, 180])
  const opacity = useTransform(scrollYProgress, [0, 0.6], [1, 0])

  const headline = 'The EU vehicle arbitrage intelligence platform.'.split(' ')

  return (
    <section
      ref={containerRef}
      style={{
        minHeight: '100vh', position: 'relative', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: 'clamp(80px, 8vw, 120px) clamp(20px, 5vw, 80px)',
        overflow: 'hidden',
      }}
    >
      <OrgMesh />

      {/* Parallax content wrapper */}
      <motion.div style={{ y, opacity, position: 'relative', zIndex: 1, width: '100%', maxWidth: 900, textAlign: 'center' }}>
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: -12, scale: 0.92 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.55, ease: EXPO, delay: 0.1 }}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginBottom: 40 }}
        >
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 18px',
            borderRadius: 99,
            background: 'rgba(255,255,255,0.07)',
            border: '1px solid rgba(255,255,255,0.14)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.14)',
          }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 10px #10b981', animation: 'cxPulse 2s infinite' }} />
            <span style={{ fontSize: 12, fontWeight: 700, color: 'rgba(255,255,255,0.85)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>CARDEX Intelligence</span>
          </div>
        </motion.div>

        {/* Headline — word stagger */}
        <motion.h1
          variants={staggerContainer}
          initial="hidden"
          animate="show"
          style={{
            fontSize: 'clamp(38px, 6.5vw, 88px)',
            fontWeight: 900,
            letterSpacing: '-0.04em',
            lineHeight: 1.0,
            color: '#f8fafc',
            marginBottom: 28,
            fontFamily: 'Inter, sans-serif',
          }}
        >
          {headline.map((word, i) => (
            <React.Fragment key={i}>
              <motion.span
                variants={wordReveal}
                style={{ display: 'inline-block', marginRight: '0.25em' }}
              >
                {word}
              </motion.span>
              {i === 4 && <br />}
            </React.Fragment>
          ))}
        </motion.h1>

        {/* Subline */}
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EXPO, delay: 0.75 }}
          style={{
            fontSize: 'clamp(15px, 1.8vw, 20px)',
            fontWeight: 400,
            color: 'rgba(255,255,255,0.50)',
            letterSpacing: '-0.01em',
            lineHeight: 1.6,
            maxWidth: 560,
            margin: '0 auto 48px',
          }}
        >
          1.55M vehicles. 6 countries.{' '}
          <span style={{ color: 'rgba(255,255,255,0.72)' }}>Real-time fiscal classification.</span>
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: EXPO, delay: 0.9 }}
          style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}
        >
          <CtaButton
            label={isAuthenticated ? 'Go to Dashboard →' : 'Enter Platform →'}
            onClick={() => nav(isAuthenticated ? '/dashboard' : '/login')}
          />
          <CtaButton
            label="Check a VIN"
            onClick={() => nav('/check')}
            secondary
          />
        </motion.div>
      </motion.div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4, duration: 0.8 }}
        style={{ position: 'absolute', bottom: 40, left: '50%', transform: 'translateX(-50%)', zIndex: 1 }}
      >
        <ScrollChevron onClick={onScrollDown} />
      </motion.div>

      {/* Gradient fade to next section */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 200, background: 'linear-gradient(to bottom, transparent, rgba(10,10,26,0.95))', pointerEvents: 'none', zIndex: 1 }} />
    </section>
  )
}

/* ─── SCENE 2: Stats ────────────────────────────────────────────────────────── */
function SceneStats() {
  const countries = [
    { flag: '🇩🇪', label: 'Germany' },
    { flag: '🇪🇸', label: 'Spain' },
    { flag: '🇫🇷', label: 'France' },
    { flag: '🇳🇱', label: 'Netherlands' },
    { flag: '🇧🇪', label: 'Belgium' },
    { flag: '🇨🇭', label: 'Switzerland' },
  ]

  return (
    <section style={{
      position: 'relative',
      padding: 'clamp(80px, 8vw, 120px) clamp(20px, 5vw, 80px)',
      overflow: 'hidden',
    }}>
      <OrgMesh />

      <div style={{ maxWidth: 1100, margin: '0 auto', position: 'relative', zIndex: 1 }}>
        {/* Section label */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: EXPO }}
          style={{ textAlign: 'center', marginBottom: 72 }}
        >
          <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(124,58,237,0.9)' }}>By the numbers</span>
        </motion.div>

        {/* Stat cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 56 }}>
          {/* Stat 1 */}
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            whileInView={{ opacity: 1, y: 0, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, ease: EXPO }}
            style={{
              ...glassCard('0 0 40px rgba(124,58,237,0.12)'),
              padding: '40px 32px',
              textAlign: 'center',
            }}
          >
            <div style={{ position: 'absolute', top: 0, left: '20%', right: '20%', height: 1, background: 'linear-gradient(90deg, transparent, rgba(124,58,237,0.6), transparent)' }} />
            <div style={{ fontSize: 'clamp(44px,5vw,72px)', fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1, color: '#f8fafc', marginBottom: 12 }}>
              <Counter target={1550000} duration={2.0} format={(n) => `${(n / 1000000).toFixed(1)}M+`} />
            </div>
            <div style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.48)', letterSpacing: '-0.01em' }}>Vehicles indexed across EU</div>
          </motion.div>

          {/* Stat 2 */}
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            whileInView={{ opacity: 1, y: 0, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, ease: EXPO, delay: 0.1 }}
            style={{
              ...glassCard('0 0 40px rgba(37,99,235,0.12)'),
              padding: '40px 32px',
              textAlign: 'center',
            }}
          >
            <div style={{ position: 'absolute', top: 0, left: '20%', right: '20%', height: 1, background: 'linear-gradient(90deg, transparent, rgba(37,99,235,0.6), transparent)' }} />
            <div style={{ fontSize: 'clamp(44px,5vw,72px)', fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1, color: '#f8fafc', marginBottom: 12 }}>
              <Counter target={6} duration={1.2} delay={0.2} />
            </div>
            <div style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.48)', letterSpacing: '-0.01em' }}>Countries covered</div>
          </motion.div>

          {/* Stat 3 */}
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            whileInView={{ opacity: 1, y: 0, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, ease: EXPO, delay: 0.2 }}
            style={{
              ...glassCard('0 0 40px rgba(8,145,178,0.12)'),
              padding: '40px 32px',
              textAlign: 'center',
            }}
          >
            <div style={{ position: 'absolute', top: 0, left: '20%', right: '20%', height: 1, background: 'linear-gradient(90deg, transparent, rgba(8,145,178,0.6), transparent)' }} />
            <div style={{ fontSize: 'clamp(44px,5vw,72px)', fontWeight: 900, letterSpacing: '-0.05em', lineHeight: 1, color: '#f8fafc', marginBottom: 12 }}>24/7</div>
            <div style={{ fontSize: 15, fontWeight: 500, color: 'rgba(255,255,255,0.48)', letterSpacing: '-0.01em' }}>Real-time fiscal monitoring</div>
          </motion.div>
        </div>

        {/* Country flags */}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          {countries.map((c, i) => (
            <FlagChip key={c.label} flag={c.flag} label={c.label} delay={i * 0.07} />
          ))}
        </div>
      </div>
    </section>
  )
}

/* ─── SCENE 3: Device Showcase ──────────────────────────────────────────────── */
function SceneDevice({ isAuthenticated }: { isAuthenticated: boolean }) {
  const nav = useNavigate()
  const sectionRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start end', 'end start'] })
  const deviceY = useTransform(scrollYProgress, [0, 1], [40, -40])
  const springY = useSpring(deviceY, { stiffness: 80, damping: 20 })

  const bullets = [
    { icon: '⚡', label: 'FiscalIQ', desc: 'IVA vs REBU in under 2 seconds' },
    { icon: '🧮', label: 'Net Landed Cost', desc: 'Full import cost to any EU country' },
    { icon: '📊', label: 'Seller Desperation Index', desc: 'Buy at the right price, every time' },
    { icon: '🌍', label: '100% territory coverage', desc: 'DE · ES · FR · NL · BE · CH' },
  ]

  return (
    <section
      ref={sectionRef}
      style={{
        position: 'relative',
        padding: 'clamp(80px, 8vw, 120px) clamp(20px, 5vw, 80px)',
        overflow: 'hidden',
      }}
    >
      <OrgMesh />

      <div style={{
        maxWidth: 1200, margin: '0 auto',
        display: 'grid', gridTemplateColumns: '1fr 1.2fr',
        gap: 'clamp(40px, 5vw, 80px)',
        alignItems: 'center',
        position: 'relative', zIndex: 1,
      }}>
        {/* Left copy */}
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-80px' }}
        >
          <motion.div variants={fadeUp} style={{ marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(124,58,237,0.9)' }}>The platform</span>
          </motion.div>

          <motion.h2
            variants={fadeUp}
            style={{
              fontSize: 'clamp(30px, 3.8vw, 54px)',
              fontWeight: 900,
              letterSpacing: '-0.04em',
              lineHeight: 1.08,
              color: '#f8fafc',
              marginBottom: 24,
              fontFamily: 'Inter, sans-serif',
            }}
          >
            Your arbitrage intelligence.{' '}
            <span style={{ background: 'linear-gradient(120deg, #a78bfa 0%, #60a5fa 60%, #67e8f9 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
              In one glass.
            </span>
          </motion.h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 40 }}>
            {bullets.map((b, i) => (
              <motion.div
                key={b.label}
                variants={fadeUpFast}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}
              >
                <div style={{
                  width: 38, height: 38, borderRadius: 11,
                  background: 'rgba(255,255,255,0.07)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, flexShrink: 0,
                  backdropFilter: 'blur(12px)',
                }}>{b.icon}</div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 3 }}>{b.label}</div>
                  <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', lineHeight: 1.5 }}>{b.desc}</div>
                </div>
              </motion.div>
            ))}
          </div>

          <motion.div variants={fadeUp}>
            <CtaButton
              label={isAuthenticated ? 'Open Dashboard →' : 'Start free →'}
              onClick={() => nav(isAuthenticated ? '/dashboard' : '/login')}
            />
          </motion.div>
        </motion.div>

        {/* Right device */}
        <motion.div style={{ y: springY }}>
          <motion.div
            initial={{ opacity: 0, x: 60, scale: 0.96 }}
            whileInView={{ opacity: 1, x: 0, scale: 1 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.85, ease: EXPO }}
            style={{
              borderRadius: 28,
              padding: 5,
              background: 'linear-gradient(160deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.05) 100%)',
              border: '1px solid rgba(255,255,255,0.18)',
              boxShadow: '0 48px 140px rgba(124,58,237,0.18), 0 12px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.25)',
            }}
          >
            <DeviceBento />
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}

/* ─── SCENE 4: Feature Bento ────────────────────────────────────────────────── */
function SceneFeatures() {
  return (
    <section style={{
      position: 'relative',
      padding: 'clamp(80px, 8vw, 120px) clamp(20px, 5vw, 80px)',
      overflow: 'hidden',
    }}>
      <OrgMesh />

      <div style={{ maxWidth: 1100, margin: '0 auto', position: 'relative', zIndex: 1 }}>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: EXPO }}
          style={{ textAlign: 'center', marginBottom: 64 }}
        >
          <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(124,58,237,0.9)', display: 'block', marginBottom: 16 }}>Core capabilities</span>
          <h2 style={{
            fontSize: 'clamp(28px, 3.5vw, 50px)',
            fontWeight: 900,
            letterSpacing: '-0.04em',
            lineHeight: 1.1,
            color: '#f8fafc',
            fontFamily: 'Inter, sans-serif',
          }}>
            Everything the professional trader needs.
          </h2>
        </motion.div>

        {/* Asymmetric bento grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          <FeatureCard
            title="FiscalIQ — IVA vs REBU"
            description="Our LLM classifier determines the fiscal regime of any EU used vehicle in under 2 seconds. IVA-deductible or REBU — with full traceability to the exact prompt and model used."
            accent="#7c3aed"
            delay={0}
            icon={
              <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth={1.8} strokeLinecap="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            }
            extra={
              <div style={{ display: 'flex', gap: 8 }}>
                {['IVA Deductible', 'REBU Regime', '<2s classification'].map((t) => (
                  <span key={t} style={{ fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 99, background: 'rgba(124,58,237,0.18)', border: '1px solid rgba(124,58,237,0.30)', color: '#a78bfa' }}>{t}</span>
                ))}
              </div>
            }
          />

          <FeatureCard
            title="Net Landed Cost"
            description="Calculate the complete import cost to any EU country instantly. Taxes, duties, transport — all computed with up-to-date fiscal rules for all 6 covered markets."
            accent="#2563eb"
            delay={0.1}
            icon={
              <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth={1.8} strokeLinecap="round">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M8 21h8M12 17v4" />
                <path d="M7 8h10M7 12h6" />
              </svg>
            }
            extra={
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 28, fontWeight: 900, letterSpacing: '-0.04em', color: '#f8fafc' }}>4.8%</span>
                <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>avg EU6 margin this week</span>
              </div>
            }
          />

          <FeatureCard
            title="Seller Desperation Index"
            description="A proprietary signal that quantifies seller urgency from listing age, price drops, and behavioral patterns. Know exactly when to negotiate."
            accent="#e11d48"
            delay={0.2}
            icon={
              <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth={1.8} strokeLinecap="round">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
            }
            extra={
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <MiniGauge value={8.2} color="#f43f5e" />
                <div>
                  <div style={{ fontSize: 20, fontWeight: 900, letterSpacing: '-0.03em', color: '#f43f5e' }}>8.2</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.42)' }}>High urgency</div>
                </div>
              </div>
            }
          />

          <FeatureCard
            title="100% EU Territory Coverage"
            description="Every live listing indexed across Germany, Spain, France, Netherlands, Belgium, and Switzerland. Exhaustive pagination — never a gap."
            accent="#0891b2"
            delay={0.3}
            icon={
              <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="#67e8f9" strokeWidth={1.8} strokeLinecap="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                <path d="M2 12h20" />
              </svg>
            }
            extra={
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {[{ flag: '🇩🇪', code: 'DE' }, { flag: '🇪🇸', code: 'ES' }, { flag: '🇫🇷', code: 'FR' }, { flag: '🇳🇱', code: 'NL' }, { flag: '🇧🇪', code: 'BE' }, { flag: '🇨🇭', code: 'CH' }].map(({ flag, code }) => (
                  <span key={code} style={{ fontSize: 12, padding: '4px 10px', borderRadius: 99, background: 'rgba(8,145,178,0.15)', border: '1px solid rgba(8,145,178,0.28)', color: '#67e8f9', fontWeight: 600 }}>
                    {flag} {code}
                  </span>
                ))}
              </div>
            }
          />
        </div>
      </div>
    </section>
  )
}

/* ─── SCENE 5: CTA Final ────────────────────────────────────────────────────── */
function SceneCta({ isAuthenticated }: { isAuthenticated: boolean }) {
  const nav = useNavigate()

  return (
    <section style={{
      position: 'relative',
      minHeight: '100vh',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: 'clamp(80px, 8vw, 120px) clamp(20px, 5vw, 80px)',
      overflow: 'hidden',
      textAlign: 'center',
    }}>
      {/* Dense violet/indigo nebula mesh */}
      <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', top: '10%', left: '15%',
          width: 1000, height: 1000,
          background: 'radial-gradient(ellipse 55% 65% at 50% 50%, rgba(124,58,237,0.38) 0%, rgba(124,58,237,0) 70%)',
          filter: 'blur(90px)',
          animation: 'cxFloat1 20s ease-in-out infinite',
        }} />
        <div style={{
          position: 'absolute', bottom: '5%', right: '10%',
          width: 800, height: 800,
          background: 'radial-gradient(ellipse 60% 70% at 50% 50%, rgba(79,70,229,0.30) 0%, rgba(79,70,229,0) 70%)',
          filter: 'blur(80px)',
          animation: 'cxFloat2 25s ease-in-out infinite',
        }} />
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
          width: 600, height: 600,
          background: 'radial-gradient(ellipse 70% 80% at 50% 50%, rgba(8,145,178,0.12) 0%, rgba(8,145,178,0) 70%)',
          filter: 'blur(100px)',
        }} />
      </div>

      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 800 }}>
        {/* Glass pill label */}
        <motion.div
          initial={{ opacity: 0, y: -14, scale: 0.92 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: EXPO }}
          style={{ display: 'inline-flex', marginBottom: 40 }}
        >
          <div style={{
            padding: '8px 20px', borderRadius: 99,
            background: 'rgba(124,58,237,0.15)',
            border: '1px solid rgba(124,58,237,0.35)',
            backdropFilter: 'blur(16px)',
            fontSize: 12, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: 'rgba(167,139,250,0.9)',
          }}>
            Ready to move first?
          </div>
        </motion.div>

        {/* Headline */}
        <motion.h2
          variants={staggerContainer}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true }}
          style={{
            fontSize: 'clamp(38px, 6vw, 82px)',
            fontWeight: 900,
            letterSpacing: '-0.045em',
            lineHeight: 1.0,
            color: '#f8fafc',
            marginBottom: 24,
            fontFamily: 'Inter, sans-serif',
          }}
        >
          {'Ready to arbitrate smarter?'.split(' ').map((word, i) => (
            <motion.span
              key={i}
              variants={wordReveal}
              style={{ display: 'inline-block', marginRight: '0.22em' }}
            >{word}</motion.span>
          ))}
        </motion.h2>

        {/* Subline */}
        <motion.p
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EXPO, delay: 0.4 }}
          style={{
            fontSize: 'clamp(15px, 1.8vw, 20px)',
            color: 'rgba(255,255,255,0.50)',
            fontWeight: 400,
            letterSpacing: '-0.01em',
            lineHeight: 1.6,
            marginBottom: 52,
          }}
        >
          Join the traders who move first.
        </motion.p>

        {/* CTA cluster */}
        <motion.div
          initial={{ opacity: 0, y: 18, scale: 0.96 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, ease: EXPO, delay: 0.5 }}
          style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap', marginBottom: 56 }}
        >
          <CtaButton
            label={isAuthenticated ? 'Open Dashboard' : 'Enter Platform'}
            onClick={() => nav(isAuthenticated ? '/dashboard' : '/login')}
            large
          />
          <CtaButton
            label="Check a vehicle VIN →"
            onClick={() => nav('/check')}
            secondary
            large
          />
        </motion.div>

        {/* Trust badge row */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease: EXPO, delay: 0.65 }}
          style={{ display: 'flex', gap: 28, justifyContent: 'center', flexWrap: 'wrap' }}
        >
          {['No credit card required', 'EU data · GDPR compliant', 'Live in minutes'].map((t) => (
            <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <svg width={14} height={14} viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="6" fill="rgba(16,185,129,0.20)" />
                <path d="M4.5 7l2 2 3-3" stroke="#10b981" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.45)', fontWeight: 500 }}>{t}</span>
            </div>
          ))}
        </motion.div>
      </div>

      {/* Footer */}
      <motion.footer
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.6, delay: 0.8 }}
        style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          padding: '24px clamp(20px,5vw,80px)',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 22, height: 22, borderRadius: 7, background: 'rgba(99,102,241,0.20)', border: '1px solid rgba(99,102,241,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ width: 8, height: 8, borderRadius: 2.5, background: 'linear-gradient(135deg,#a5b4fc,#6366f1)' }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.1em', color: 'rgba(255,255,255,0.55)' }}>CARDEX</span>
        </div>
        <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.25)' }}>© 2026 CARDEX Intelligence. All rights reserved.</span>
        <div style={{ display: 'flex', gap: 20 }}>
          {['Privacy Policy', 'Terms of Service', 'Contact'].map((l) => (
            <button
              key={l}
              style={{ fontSize: 12, color: 'rgba(255,255,255,0.30)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'Inter, sans-serif', padding: 0, transition: 'color 180ms' }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.7)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.30)')}
            >{l}</button>
          ))}
        </div>
      </motion.footer>
    </section>
  )
}

/* ─── ROOT ───────────────────────────────────────────────────────────────────── */
export default function Landing() {
  const { isAuthenticated } = useAuthContext()
  const statsRef = useRef<HTMLDivElement>(null)

  const scrollToStats = () => {
    statsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div style={{
      fontFamily: 'Inter, system-ui, sans-serif',
      background: 'var(--bg-base, #0a0a1a)',
      color: '#f8fafc',
      overflowX: 'hidden',
    }}>
      <SceneHero onScrollDown={scrollToStats} isAuthenticated={isAuthenticated} />
      <div ref={statsRef}>
        <SceneStats />
      </div>
      <SceneDevice isAuthenticated={isAuthenticated} />
      <SceneFeatures />
      <SceneCta isAuthenticated={isAuthenticated} />
    </div>
  )
}
