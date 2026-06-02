import { useEffect } from 'react'
import Lenis from 'lenis'

/**
 * Momentum smooth-scroll for the landing. Lenis drives window scroll on its own
 * rAF loop, so framer-motion's useScroll (window-based) stays perfectly synced —
 * no scroll-jank between the page motion and the scrubbed scene animations.
 * Disabled under prefers-reduced-motion. `paused` freezes it during the preloader.
 */
export function useLenis(paused: boolean) {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const lenis = new Lenis({
      duration: 1.1,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 1,
      touchMultiplier: 1.6,
      anchors: true,
    })

    let raf = 0
    const loop = (time: number) => { lenis.raf(time); raf = requestAnimationFrame(loop) }
    raf = requestAnimationFrame(loop)

    return () => { cancelAnimationFrame(raf); lenis.destroy() }
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('lenis-stopped', paused)
    if (paused) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
    return () => { document.body.style.overflow = '' }
  }, [paused])
}
