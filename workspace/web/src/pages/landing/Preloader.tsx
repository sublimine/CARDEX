import { useEffect, useState } from 'react'
import { motion, animate, useReducedMotion } from 'framer-motion'

const EXPO = [0.16, 1, 0.3, 1] as const
const MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', monospace"

/**
 * Cinematic intro. Counts 00 → 100 while the CARDEX wordmark reveals, then exits
 * as a layered curtain (two panels sliding up, staggered) that uncovers the hero.
 * Parent renders it inside <AnimatePresence> and drops it via onComplete.
 */
export default function Preloader({ onComplete }: { onComplete: () => void }) {
  const reduced = useReducedMotion()
  const [n, setN] = useState(0)

  useEffect(() => {
    if (reduced) { setN(100); const t = setTimeout(onComplete, 300); return () => clearTimeout(t) }
    const c = animate(0, 100, { duration: 1.9, ease: [0.22, 1, 0.36, 1], onUpdate: v => setN(Math.round(v)) })
    const t = setTimeout(onComplete, 2350)
    return () => { c.stop(); clearTimeout(t) }
  }, [reduced, onComplete])

  const pad = (v: number) => String(v).padStart(3, '0')

  return (
    <motion.div
      style={{ position: 'fixed', inset: 0, zIndex: 9000, pointerEvents: 'none' }}
      initial={{ opacity: 1 }}
    >
      {/* two stacked curtain panels — staggered exit reveals the hero */}
      <motion.div
        style={{ position: 'absolute', inset: 0, background: '#0a0a18' }}
        initial={{ y: 0 }}
        exit={reduced ? { opacity: 0 } : { y: '-100%' }}
        transition={{ duration: 0.9, ease: EXPO, delay: 0.08 }}
      />
      <motion.div
        style={{ position: 'absolute', inset: 0, background: '#06060e', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: 'clamp(24px,4vw,56px)' }}
        initial={{ y: 0 }}
        exit={reduced ? { opacity: 0 } : { y: '-100%' }}
        transition={{ duration: 0.9, ease: EXPO }}
      >
        {/* top rail */}
        <motion.div
          style={{ display: 'flex', justifyContent: 'space-between', fontFamily: MONO, fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'rgba(203,213,225,0.92)' }}
          exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.4, ease: EXPO }}
        >
          <span>CARDEX // índice europeo</span>
          <span>DE · ES · FR · NL · BE · CH</span>
        </motion.div>

        {/* center wordmark + counter */}
        <motion.div
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}
          exit={{ opacity: 0, filter: 'blur(8px)', scale: 0.96 }} transition={{ duration: 0.5, ease: EXPO }}
        >
          <div style={{ overflow: 'hidden', paddingBottom: '0.1em' }}>
            <motion.div
              initial={reduced ? { y: 0 } : { y: '110%' }} animate={{ y: '0%' }} transition={{ duration: 1, ease: EXPO, delay: 0.1 }}
              style={{ fontSize: 'clamp(2.4rem,1rem+5vw,5rem)', fontWeight: 800, letterSpacing: '0.04em', background: 'linear-gradient(120deg,#c4b5fd,#818cf8,#67e8f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}
            >
              CARDEX
            </motion.div>
          </div>
          <div style={{ fontFamily: MONO, fontSize: 'clamp(0.8rem,0.7rem+0.4vw,1rem)', letterSpacing: '0.3em', color: 'rgba(165,180,252,0.8)', fontVariantNumeric: 'tabular-nums' }}>
            {pad(n)} <span style={{ color: 'rgba(148,163,184,0.45)' }}>/ 100</span>
          </div>
        </motion.div>

        {/* bottom: progress line + label */}
        <motion.div exit={{ opacity: 0, y: 10 }} transition={{ duration: 0.4, ease: EXPO }}>
          <div style={{ height: 1.5, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
            <motion.div style={{ height: '100%', width: `${n}%`, background: 'linear-gradient(90deg,#6366f1,#818cf8,#67e8f9)', boxShadow: '0 0 12px rgba(99,102,241,0.6)' }} />
          </div>
          <div style={{ marginTop: 12, fontFamily: MONO, fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'rgba(203,213,225,0.8)' }}>
            Cargando inventario · 1.550.000 vehículos
          </div>
        </motion.div>
      </motion.div>
    </motion.div>
  )
}
