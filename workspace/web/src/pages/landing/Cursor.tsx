import { useEffect, useRef, useState } from 'react'
import { motion, useMotionValue, useSpring } from 'framer-motion'

/**
 * Custom cursor — a lagging ring + precise dot. The ring grows and inverts over
 * interactive elements (anything with [data-cursor] or native button/a/input).
 * Uses mix-blend-mode: difference so it reads on any surface. Renders nothing on
 * coarse-pointer (touch) devices.
 */
export default function Cursor() {
  const [enabled, setEnabled] = useState(false)
  const [active, setActive] = useState(false)
  const [down, setDown] = useState(false)

  const x = useMotionValue(-100)
  const y = useMotionValue(-100)
  const rx = useSpring(x, { stiffness: 320, damping: 28, mass: 0.6 })
  const ry = useSpring(y, { stiffness: 320, damping: 28, mass: 0.6 })
  const activeRef = useRef(false)

  useEffect(() => {
    if (window.matchMedia('(pointer: coarse)').matches) return
    setEnabled(true)

    // Pointermove only writes MotionValues (no React render); setState fires
    // strictly on interactive-state transitions, not on every move.
    const move = (e: PointerEvent) => {
      x.set(e.clientX); y.set(e.clientY)
      const t = e.target as HTMLElement | null
      const interactive = !!t?.closest('a,button,input,[role="button"],[data-cursor]')
      if (interactive !== activeRef.current) { activeRef.current = interactive; setActive(interactive) }
    }
    const dn = () => setDown(true)
    const up = () => setDown(false)
    window.addEventListener('pointermove', move, { passive: true })
    window.addEventListener('pointerdown', dn)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerdown', dn)
      window.removeEventListener('pointerup', up)
    }
  }, [x, y])

  if (!enabled) return null
  const ring = active ? 46 : 30
  const scale = down ? 0.82 : 1

  return (
    <>
      <motion.div
        aria-hidden
        style={{
          position: 'fixed', left: 0, top: 0, x: rx, y: ry, zIndex: 9999, pointerEvents: 'none',
          translateX: '-50%', translateY: '-50%', mixBlendMode: 'difference',
        }}
      >
        <motion.div
          animate={{ width: ring, height: ring, scale, opacity: active ? 1 : 0.7 }}
          transition={{ type: 'spring', stiffness: 360, damping: 26 }}
          style={{ borderRadius: 999, border: '1.5px solid #fff' }}
        />
      </motion.div>
      <motion.div
        aria-hidden
        style={{
          position: 'fixed', left: 0, top: 0, x, y, zIndex: 9999, pointerEvents: 'none',
          width: 5, height: 5, borderRadius: 999, background: '#fff',
          translateX: '-50%', translateY: '-50%', mixBlendMode: 'difference',
        }}
      />
    </>
  )
}
