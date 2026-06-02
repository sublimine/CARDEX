/*
 * CARDEX Terminal — theme bridge (neutral / minimal)
 * Pure dark-or-white per platform theme. The terminal paints its OWN neutral backdrop (`bg`)
 * so the workspace's colourful mesh never tints it purple. Glass is subtle and monochrome;
 * a single restrained neon (cyan) accent marks only what is truly active. No grain noise,
 * no pointer-glow. Canvas charts can't read CSS vars, so we resolve concrete values and react
 * to theme via a MutationObserver on the <html> `.light` class.
 */
import { useEffect, useState } from 'react'

export interface TerminalPalette {
  dark: boolean
  bg: string            // terminal backdrop — covers the global mesh (neutral)
  // Surfaces
  panel: string
  panelHi: string
  rail: string
  inset: string
  glass: string
  glassHi: string
  // Borders, refraction & highlights
  border: string
  borderHi: string
  hairline: string
  topHighlight: string
  refractA: string
  refractB: string
  refractTint: string   // kept neutral/transparent — no colour cast
  sheen: string
  glow: string          // kept transparent in minimal mode
  noiseOpacity: number
  // Text hierarchy (neutral grays)
  t1: string
  t2: string
  t3: string
  t4: string
  // Market semantics
  up: string
  down: string
  upDim: string
  downDim: string
  upGlow: string
  downGlow: string
  // Single neon accent (cyan) — used sparingly
  accent: string
  accentSoft: string
  accentDim: string     // NEUTRAL active-surface tint (keeps UI monochrome)
  accentText: string
  // Secondary hues (used only where semantically needed)
  blue: string
  teal: string
  amber: string
  fuchsia: string
  // Chart canvas
  chartGrid: string
  chartBorder: string
  chartText: string
  crosshair: string
  volUp: string
  volDown: string
  // Shadows
  shadow: string
  shadowLg: string
  glowAccent: string
}

const DARK: TerminalPalette = {
  dark: true,
  bg: 'radial-gradient(120% 80% at 50% -10%, #14151a 0%, #0b0c0f 55%, #08090b 100%)',
  panel: 'rgba(22,23,28,0.62)',
  panelHi: 'rgba(30,32,38,0.78)',
  rail: 'rgba(16,17,21,0.66)',
  inset: 'rgba(0,0,0,0.30)',
  glass: 'rgba(255,255,255,0.045)',
  glassHi: 'rgba(255,255,255,0.09)',
  border: 'rgba(255,255,255,0.08)',
  borderHi: 'rgba(255,255,255,0.16)',
  hairline: 'rgba(255,255,255,0.055)',
  topHighlight: 'rgba(255,255,255,0.10)',
  refractA: 'rgba(255,255,255,0.18)',
  refractB: 'rgba(255,255,255,0.02)',
  refractTint: 'transparent',
  sheen: 'rgba(255,255,255,0.08)',
  glow: 'rgba(34,211,238,0.05)',   // faint cyan inner-edge depth (liquid-mirror, subtle neon) — chart panel opts out
  noiseOpacity: 0,
  t1: '#f3f4f6',
  t2: '#c3c6cd',
  t3: '#878b94',
  t4: '#565a63',
  up: '#26c281',
  down: '#f24b67',
  upDim: 'rgba(38,194,129,0.14)',
  downDim: 'rgba(242,75,103,0.14)',
  upGlow: 'rgba(38,194,129,0.5)',
  downGlow: 'rgba(242,75,103,0.5)',
  accent: '#22d3ee',
  accentSoft: '#67e8f9',
  accentDim: 'rgba(255,255,255,0.07)',
  accentText: '#5ed5e6',
  blue: '#60a5fa',
  teal: '#2dd4bf',
  amber: '#fbbf24',
  fuchsia: '#e879f9',
  chartGrid: 'rgba(255,255,255,0.038)',
  chartBorder: 'rgba(255,255,255,0.07)',
  chartText: '#6b7079',
  crosshair: 'rgba(255,255,255,0.34)',
  volUp: 'rgba(38,194,129,0.22)',
  volDown: 'rgba(242,75,103,0.18)',
  shadow: '0 10px 36px rgba(0,0,0,0.46), inset 0 1px 0 rgba(255,255,255,0.07)',
  shadowLg: '0 28px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.10)',
  glowAccent: '0 0 18px rgba(34,211,238,0.22)',
}

const LIGHT: TerminalPalette = {
  dark: false,
  bg: 'radial-gradient(120% 80% at 50% -10%, #ffffff 0%, #f6f7f9 60%, #eef0f3 100%)',
  panel: 'rgba(255,255,255,0.72)',
  panelHi: 'rgba(255,255,255,0.9)',
  rail: 'rgba(255,255,255,0.78)',
  inset: 'rgba(15,23,42,0.04)',
  glass: 'rgba(255,255,255,0.6)',
  glassHi: 'rgba(255,255,255,0.95)',
  border: 'rgba(15,23,42,0.09)',
  borderHi: 'rgba(15,23,42,0.16)',
  hairline: 'rgba(15,23,42,0.065)',
  topHighlight: 'rgba(255,255,255,0.9)',
  refractA: 'rgba(255,255,255,0.9)',
  refractB: 'rgba(255,255,255,0.1)',
  refractTint: 'transparent',
  sheen: 'rgba(15,23,42,0.05)',
  glow: 'rgba(8,145,178,0.045)',   // faint cyan inner-edge depth (liquid-mirror, subtle neon) — chart panel opts out
  noiseOpacity: 0,
  t1: '#0b0d12',
  t2: '#3a3f48',
  t3: '#6b7079',
  t4: '#9aa0aa',
  up: '#16a34a',
  down: '#e11d48',
  upDim: 'rgba(22,163,74,0.12)',
  downDim: 'rgba(225,29,72,0.10)',
  upGlow: 'rgba(22,163,74,0.32)',
  downGlow: 'rgba(225,29,72,0.30)',
  accent: '#0891b2',
  accentSoft: '#0e7490',
  accentDim: 'rgba(15,23,42,0.05)',
  accentText: '#0e7490',
  blue: '#2563eb',
  teal: '#0d9488',
  amber: '#d97706',
  fuchsia: '#c026d3',
  chartGrid: 'rgba(15,23,42,0.05)',
  chartBorder: 'rgba(15,23,42,0.09)',
  chartText: '#9aa0aa',
  crosshair: 'rgba(15,23,42,0.34)',
  volUp: 'rgba(22,163,74,0.2)',
  volDown: 'rgba(225,29,72,0.16)',
  shadow: '0 8px 28px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.9)',
  shadowLg: '0 22px 60px rgba(15,23,42,0.14), inset 0 1px 0 rgba(255,255,255,0.95)',
  glowAccent: '0 0 16px rgba(8,145,178,0.18)',
}

export function getPalette(dark: boolean): TerminalPalette {
  return dark ? DARK : LIGHT
}

export function useTheme(): TerminalPalette {
  const read = () => !document.documentElement.classList.contains('light')
  const [dark, setDark] = useState(read)
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(read()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return getPalette(dark)
}

// ── Backdrop filters — neutral, restrained saturation (no colour amplification) ──
export function getBlur(p: TerminalPalette): string {
  return p.dark ? 'blur(30px) saturate(125%)' : 'blur(30px) saturate(115%)'
}
export function getBlurLg(p: TerminalPalette): string {
  return p.dark ? 'blur(52px) saturate(135%)' : 'blur(52px) saturate(125%)'
}
export const CHIP_BLUR = 'blur(14px) saturate(120%)'

export const BLUR = 'blur(30px) saturate(125%)'
export const BLUR_LG = 'blur(52px) saturate(135%)'

export const MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace"
export const SANS = "'Inter', system-ui, -apple-system, sans-serif"
export const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)'
export const EASE_OUT_EXPO = 'cubic-bezier(0.16, 1, 0.3, 1)'
export const EASE_ARR = [0.22, 1, 0.36, 1] as const
