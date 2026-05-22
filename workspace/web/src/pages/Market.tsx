import React, { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Bell, Star, Check, Plus, Maximize2, Minimize2, ChevronDown,
  MousePointer2, TrendingUp, Minus, MoveVertical, ArrowUpRight,
  Square, Triangle, Type, Trash2, Pipette,
} from 'lucide-react'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries,
  ColorType, CrosshairMode,
  type IChartApi, type ISeriesApi, type CandlestickData,
} from 'lightweight-charts'

// ── Design tokens ─────────────────────────────────────────────────────────────
const GLASS     = 'rgba(14,14,30,0.48)'
const GLASS_LT  = 'rgba(255,255,255,0.05)'
const CHIP_DARK = 'rgba(0,0,0,0.58)'
const BRD       = 'rgba(255,255,255,0.11)'
const BRD_DARK  = 'rgba(255,255,255,0.08)'
const DIV       = 'rgba(255,255,255,0.07)'
const BLUR      = 'blur(52px) saturate(200%)'
const BLUR_MD   = 'blur(24px) saturate(180%)'
const SHADOW    = '0 8px 40px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.10)'
const SHADOW_SM = '0 4px 20px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.08)'
const T1 = '#f1f5f9', T2 = '#cbd5e1', T3 = '#94a3b8', T4 = '#475569'
const UP = '#a78bfa', DN = '#f87171'

// ── Brand logos ───────────────────────────────────────────────────────────────
const BRAND_DOMAINS: Record<string, string> = {
  BMW: 'bmw.com', VW: 'vw.com', Volkswagen: 'vw.com',
  Mercedes: 'mercedes-benz.com', Audi: 'audi.com',
  Toyota: 'toyota.com', Skoda: 'skoda-auto.com',
  Renault: 'renault.com', Peugeot: 'peugeot.com', Ford: 'ford.com',
}

function BrandLogo({ brand, size = 30 }: { brand: string; size?: number }) {
  const domain = BRAND_DOMAINS[brand] ?? `${brand.toLowerCase()}.com`
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: '#f5f5f5',
      border: '1.5px solid rgba(255,255,255,0.18)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden',
      boxShadow: '0 2px 8px rgba(0,0,0,0.30)',
    }}>
      <img
        src={`https://www.google.com/s2/favicons?domain=${domain}&sz=128`}
        alt={brand}
        width={size - 5}
        height={size - 5}
        style={{ objectFit: 'contain', display: 'block' }}
        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
      />
    </div>
  )
}

// ── Vehicle data ──────────────────────────────────────────────────────────────
interface VehicleSpec { basePrice: number; vol: number }
const VEHICLE_DATA: Record<string, Record<string, Record<string, VehicleSpec>>> = {
  BMW: {
    '3 Series': { '318d': { basePrice: 24200, vol: 1.0 }, '320d': { basePrice: 28450, vol: 1.1 }, '330i': { basePrice: 31800, vol: 1.3 }, 'M340i': { basePrice: 45200, vol: 1.8 } },
    '5 Series': { '520d': { basePrice: 38900, vol: 0.9 }, '530e': { basePrice: 52000, vol: 1.2 }, '540i': { basePrice: 58000, vol: 1.4 } },
    'X3':       { 'xDrive20d': { basePrice: 44500, vol: 1.1 }, 'xDrive30i': { basePrice: 50000, vol: 1.3 }, 'M40i': { basePrice: 62000, vol: 2.0 } },
    'X5':       { 'xDrive30d': { basePrice: 61000, vol: 1.0 }, 'xDrive45e': { basePrice: 75000, vol: 1.4 } },
  },
  VW: {
    Golf:    { '1.0 eTSI': { basePrice: 14500, vol: 0.7 }, '1.5 TSI': { basePrice: 16200, vol: 0.8 }, '2.0 TDI': { basePrice: 18900, vol: 0.8 }, 'GTI': { basePrice: 28500, vol: 1.5 }, 'R': { basePrice: 39000, vol: 2.0 } },
    Passat:  { '1.5 TSI': { basePrice: 19500, vol: 0.7 }, '2.0 TDI': { basePrice: 22000, vol: 0.7 } },
    Tiguan:  { '1.5 TSI': { basePrice: 28000, vol: 0.9 }, '2.0 TDI': { basePrice: 31000, vol: 1.0 }, 'R-Line': { basePrice: 36000, vol: 1.2 } },
    'ID.4':  { 'Pure': { basePrice: 32000, vol: 1.5 }, 'Pro': { basePrice: 38000, vol: 1.6 }, 'GTX': { basePrice: 48000, vol: 1.8 } },
  },
  Mercedes: {
    'C-Class': { 'C 180': { basePrice: 28000, vol: 1.0 }, 'C 200': { basePrice: 32100, vol: 1.1 }, 'C 220d': { basePrice: 34500, vol: 1.0 }, 'C 63 AMG': { basePrice: 68000, vol: 2.5 } },
    'E-Class': { 'E 200': { basePrice: 38000, vol: 0.9 }, 'E 220d': { basePrice: 42000, vol: 0.9 }, 'E 450': { basePrice: 58000, vol: 1.4 } },
    GLC:       { 'GLC 200': { basePrice: 44000, vol: 1.0 }, 'GLC 220d': { basePrice: 48000, vol: 1.0 }, 'GLC 63 AMG': { basePrice: 86000, vol: 2.2 } },
  },
  Audi: {
    A4:  { '35 TDI': { basePrice: 24000, vol: 0.9 }, '40 TFSI': { basePrice: 29500, vol: 1.0 }, 'S4': { basePrice: 48000, vol: 1.7 } },
    A6:  { '40 TDI': { basePrice: 36000, vol: 0.8 }, '50 TDI': { basePrice: 52000, vol: 1.0 }, 'S6': { basePrice: 68000, vol: 1.8 } },
    Q5:  { '35 TDI': { basePrice: 38000, vol: 0.9 }, '40 TDI quattro': { basePrice: 42000, vol: 1.1 }, 'SQ5': { basePrice: 60000, vol: 1.6 } },
    Q7:  { '45 TDI': { basePrice: 62000, vol: 0.9 }, '55 TFSI e': { basePrice: 72000, vol: 1.2 } },
  },
}
const ALL_MAKES = Object.keys(VEHICLE_DATA)

// ── Chart data generator ──────────────────────────────────────────────────────
interface ChartBar { time: string; open: number; high: number; low: number; close: number; volume: number }

function seedRng(seed: number) {
  let s = seed
  return () => { s = (s * 1664525 + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
}

function generateData(make: string, model: string, sub: string, days = 400): ChartBar[] {
  const spec = VEHICLE_DATA[make]?.[model]?.[sub] ?? { basePrice: 20000, vol: 1.0 }
  const rng  = seedRng(make.charCodeAt(0) * 31 + model.charCodeAt(0) * 17 + sub.charCodeAt(0))
  const bars: ChartBar[] = []
  let price = spec.basePrice * (0.93 + rng() * 0.05)
  const today = new Date('2026-05-22')
  for (let i = days; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    if (d.getDay() === 0 || d.getDay() === 6) continue
    const time  = d.toISOString().split('T')[0]
    const open  = price
    const drift = (rng() - 0.47) * spec.vol * (spec.basePrice / 80)
    const close = Math.max(spec.basePrice * 0.60, Math.min(spec.basePrice * 1.45, open + drift))
    const wick  = rng() * spec.vol * (spec.basePrice / 280)
    bars.push({ time, open, high: Math.max(open, close) + wick, low: Math.min(open, close) - wick, close, volume: 40 + rng() * 110 })
    price = close
  }
  return bars
}

// ── Static data ───────────────────────────────────────────────────────────────
const TICKER_CHIPS = [
  { code: 'DE', flag: '🇩🇪', price: 22_100, delta: +1.8 },
  { code: 'FR', flag: '🇫🇷', price: 17_800, delta: +0.6 },
  { code: 'ES', flag: '🇪🇸', price: 15_200, delta: -0.4 },
  { code: 'NL', flag: '🇳🇱', price: 19_500, delta: +2.1 },
  { code: 'CH', flag: '🇨🇭', price: 28_400, delta: +3.2 },
]
const ASSETS = [
  { id: 'a1', brand: 'BMW',      ticker: '3 Series', price: 28_450, delta: +1.2, color: '#1c69d4', bars: [3,5,4,7,6,8,9,7,10,8,11] },
  { id: 'a2', brand: 'VW',       ticker: 'Golf',     price: 16_800, delta: -0.4, color: '#001e50', bars: [8,7,9,8,6,5,7,6,5,6,5]  },
  { id: 'a3', brand: 'Mercedes', ticker: 'C-Class',  price: 32_100, delta: +2.1, color: '#808080', bars: [4,5,6,7,8,9,10,11,12,13,14] },
]
const MARKETS = [
  { flag: '🇩🇪', name: 'Germany',     code: 'DE', delta: -14.88, date: '15 Jan, 2026', price: 22_100, listings: '1.32M' },
  { flag: '🇫🇷', name: 'France',      code: 'FR', delta:  -9.58, date: '15 Jan, 2026', price: 17_800, listings:  '980K' },
  { flag: '🇪🇸', name: 'Spain',       code: 'ES', delta:  +2.14, date: '15 Jan, 2026', price: 15_200, listings:  '760K' },
  { flag: '🇳🇱', name: 'Netherlands', code: 'NL', delta:  +1.87, date: '15 Jan, 2026', price: 19_500, listings:  '541K' },
]
const PORTFOLIO = [
  { id: 'p1', brand: 'BMW',     name: 'BMW 3 Series',     price: 28_450, delta: -2.49, listings: '42,300' },
  { id: 'p2', brand: 'VW',      name: 'VW Golf',          price: 16_800, delta: -0.40, listings: '98,700' },
  { id: 'p3', brand: 'Mercedes',name: 'Mercedes C-Class', price: 32_100, delta: +2.10, listings: '31,450' },
  { id: 'p4', brand: 'Audi',    name: 'Audi A4',          price: 26_900, delta: -0.80, listings: '38,200' },
  { id: 'p5', brand: 'Toyota',  name: 'Toyota Corolla',   price: 22_300, delta: +3.40, listings: '28,100' },
  { id: 'p6', brand: 'Skoda',   name: 'Skoda Octavia',    price: 18_200, delta: +1.60, listings: '36,700' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────
function LiveClock() {
  const [t, setT] = useState(new Date())
  useEffect(() => { const id = setInterval(() => setT(new Date()), 1000); return () => clearInterval(id) }, [])
  return <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: T4 }}>{t.toLocaleTimeString('en-GB')}</span>
}

function MiniBar({ vals, color }: { vals: number[]; color: string }) {
  const max = Math.max(...vals)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 32 }}>
      {vals.map((v, i) => <div key={i} style={{ width: 3, borderRadius: 2, height: `${(v / max) * 100}%`, background: color, opacity: 0.45 + (i / vals.length) * 0.55 }} />)}
    </div>
  )
}

// ── Dropdown ──────────────────────────────────────────────────────────────────
function Dropdown({ value, options, onChange, label }: { value: string; options: string[]; onChange: (v: string) => void; label: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={() => setOpen(o => !o)} style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 8,
        background: GLASS_LT, border: `1px solid ${BRD}`, backdropFilter: BLUR_MD, WebkitBackdropFilter: BLUR_MD,
        color: T2, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui',
        minWidth: 90, transition: 'all 140ms',
      }}>
        <span style={{ fontSize: 8.5, color: T4, fontWeight: 700, letterSpacing: '0.09em', textTransform: 'uppercase', marginRight: 2 }}>{label}</span>
        <span style={{ flex: 1, textAlign: 'left' }}>{value}</span>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.15 }}>
          <ChevronDown style={{ width: 11, height: 11, color: T4 }} />
        </motion.span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.13 }}
            style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, minWidth: '100%', zIndex: 200, background: 'rgba(10,10,22,0.97)', backdropFilter: 'blur(32px)', border: `1px solid ${BRD}`, borderRadius: 10, boxShadow: '0 14px 40px rgba(0,0,0,0.60)', overflow: 'hidden', maxHeight: 220, overflowY: 'auto' }}>
            {options.map(opt => (
              <div key={opt} onClick={() => { onChange(opt); setOpen(false) }}
                style={{ padding: '8px 12px', fontSize: 11.5, color: opt === value ? UP : T2, fontFamily: 'Inter, system-ui', cursor: 'pointer', background: opt === value ? 'rgba(124,58,237,0.14)' : 'transparent', transition: 'background 110ms', fontWeight: opt === value ? 600 : 400 }}
                onMouseEnter={e => { if (opt !== value) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.06)' }}
                onMouseLeave={e => { if (opt !== value) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}>
                {opt}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Drawing tools ─────────────────────────────────────────────────────────────
type DrawingTool = 'cursor' | 'trendline' | 'horizontal' | 'vertical' | 'arrow' | 'rectangle' | 'fibonacci' | 'ray'
type ChartType   = 'candle' | 'line' | 'area'

interface DrawingPoint { time: string; price: number }
interface Drawing { id: string; type: DrawingTool; points: DrawingPoint[]; color: string; width: number; dash: string }

const TOOL_COLORS = ['#a78bfa', '#f87171', '#22c55e', '#f59e0b', '#60a5fa', '#f472b6', '#ffffff']

const DRAW_TOOLS: { type: DrawingTool; icon: React.ReactNode; label: string }[] = [
  { type: 'cursor',     icon: <MousePointer2 style={{ width: 13, height: 13 }} />, label: 'Cursor'       },
  { type: 'trendline',  icon: <TrendingUp    style={{ width: 13, height: 13 }} />, label: 'Trend Line'   },
  { type: 'ray',        icon: <ArrowUpRight  style={{ width: 13, height: 13 }} />, label: 'Ray'          },
  { type: 'horizontal', icon: <Minus         style={{ width: 13, height: 13 }} />, label: 'H-Line'       },
  { type: 'vertical',   icon: <MoveVertical  style={{ width: 13, height: 13 }} />, label: 'V-Line'       },
  { type: 'arrow',      icon: <ArrowUpRight  style={{ width: 13, height: 13 }} />, label: 'Arrow'        },
  { type: 'rectangle',  icon: <Square        style={{ width: 13, height: 13 }} />, label: 'Rectangle'    },
  { type: 'fibonacci',  icon: <Triangle      style={{ width: 13, height: 13 }} />, label: 'Fibonacci'    },
]

// ── Drawing toolbar ───────────────────────────────────────────────────────────
function DrawingToolbar({
  activeTool, setActiveTool,
  activeColor, setActiveColor,
  drawings, onClear,
}: {
  activeTool: DrawingTool; setActiveTool: (t: DrawingTool) => void
  activeColor: string; setActiveColor: (c: string) => void
  drawings: Drawing[]; onClear: () => void
}) {
  const [showColors, setShowColors] = useState(false)
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 3,
      padding: '8px 6px',
      background: 'rgba(8,8,18,0.88)',
      backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
      borderRight: `1px solid ${DIV}`,
      minWidth: 36, alignItems: 'center',
    }}>
      {DRAW_TOOLS.map(tool => (
        <button key={tool.type} onClick={() => setActiveTool(tool.type)} title={tool.label}
          style={{
            width: 28, height: 28, borderRadius: 7, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: activeTool === tool.type ? 'rgba(124,58,237,0.28)' : 'rgba(255,255,255,0.04)',
            border: activeTool === tool.type ? '1px solid rgba(124,58,237,0.50)' : '1px solid transparent',
            color: activeTool === tool.type ? UP : T3, transition: 'all 130ms',
          }}>
          {tool.icon}
        </button>
      ))}

      {/* Divider */}
      <div style={{ width: 20, height: 1, background: DIV, margin: '4px 0' }} />

      {/* Color picker */}
      <div style={{ position: 'relative' }}>
        <button onClick={() => setShowColors(s => !s)} title="Color"
          style={{ width: 28, height: 28, borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.04)', border: `1px solid ${DIV}` }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: activeColor, boxShadow: `0 0 5px ${activeColor}` }} />
        </button>
        <AnimatePresence>
          {showColors && (
            <motion.div initial={{ opacity: 0, x: 6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}
              style={{ position: 'absolute', left: 34, top: 0, display: 'flex', flexDirection: 'column', gap: 4, padding: '6px', background: 'rgba(10,10,22,0.97)', backdropFilter: 'blur(20px)', border: `1px solid ${BRD}`, borderRadius: 10, boxShadow: '0 8px 28px rgba(0,0,0,0.55)', zIndex: 300 }}>
              {TOOL_COLORS.map(c => (
                <button key={c} onClick={() => { setActiveColor(c); setShowColors(false) }}
                  style={{ width: 18, height: 18, borderRadius: '50%', background: c, border: c === activeColor ? '2px solid white' : '1px solid rgba(255,255,255,0.20)', cursor: 'pointer', boxShadow: c === activeColor ? `0 0 8px ${c}` : 'none' }}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Clear all */}
      {drawings.length > 0 && (
        <button onClick={onClear} title="Clear all drawings"
          style={{ width: 28, height: 28, borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(248,113,113,0.12)', border: '1px solid rgba(248,113,113,0.28)', color: '#f87171', transition: 'all 130ms', marginTop: 2 }}>
          <Trash2 style={{ width: 12, height: 12 }} />
        </button>
      )}
    </div>
  )
}

// ── Drawing overlay (SVG on top of chart) ─────────────────────────────────────
function DrawingOverlay({
  chartApi, drawings, onAdd, activeTool, activeColor, version, height,
}: {
  chartApi: IChartApi | null
  drawings: Drawing[]
  onAdd: (d: Drawing) => void
  activeTool: DrawingTool
  activeColor: string
  version: number
  height: number
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [w, setW] = useState(0)
  const [pendingPt, setPendingPt] = useState<{ x: number; y: number } | null>(null)
  const [hoverPt, setHoverPt]     = useState<{ x: number; y: number } | null>(null)
  const [, tick] = useState(0)

  useEffect(() => { tick(n => n + 1) }, [version])

  useEffect(() => {
    if (!svgRef.current) return
    const obs = new ResizeObserver(e => setW(e[0].contentRect.width))
    obs.observe(svgRef.current)
    return () => obs.disconnect()
  }, [])

  if (!chartApi) return null

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ps = chartApi.priceScale('right') as any

  function pxToChart(x: number, y: number): DrawingPoint | null {
    const time  = chartApi!.timeScale().coordinateToTime(x)
    const price = ps.coordinateToPrice?.(y) ?? null
    if (time === null || price === null) return null
    return { time: String(time), price }
  }

  function chartToPx(pt: DrawingPoint): { x: number; y: number } {
    const x = chartApi!.timeScale().timeToCoordinate(pt.time as any) ?? -9999
    const y = ps.priceToCoordinate?.(pt.price) ?? -9999
    return { x, y }
  }

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (activeTool === 'cursor') return
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left
    const py = e.clientY - rect.top

    if (activeTool === 'horizontal') {
      const pt = pxToChart(px, py); if (!pt) return
      const tRange = chartApi!.timeScale().getVisibleRange()
      if (!tRange) return
      onAdd({ id: Date.now().toString(), type: 'horizontal', points: [{ time: String(tRange.from), price: pt.price }, { time: String(tRange.to), price: pt.price }], color: activeColor, width: 1, dash: '' })
      return
    }

    if (activeTool === 'vertical') {
      const pt = pxToChart(px, py); if (!pt) return
      const prMin = ps.coordinateToPrice?.(0) ?? 0
      const prMax = ps.coordinateToPrice?.(height) ?? 9999999
      onAdd({ id: Date.now().toString(), type: 'vertical', points: [{ time: pt.time, price: Math.min(prMin, prMax) }, { time: pt.time, price: Math.max(prMin, prMax) }], color: activeColor, width: 1, dash: '5,3' })
      return
    }

    // Two-click tools: trendline, ray, arrow, rectangle, fibonacci
    if (!pendingPt) {
      setPendingPt({ x: px, y: py })
    } else {
      const pt1 = pxToChart(pendingPt.x, pendingPt.y)
      const pt2 = pxToChart(px, py)
      if (!pt1 || !pt2) { setPendingPt(null); return }
      onAdd({ id: Date.now().toString(), type: activeTool, points: [pt1, pt2], color: activeColor, width: 1.5, dash: '' })
      setPendingPt(null)
    }
  }

  function renderDrawing(d: Drawing): React.ReactNode {
    if (d.points.length < 2) return null
    const p1 = chartToPx(d.points[0])
    const p2 = chartToPx(d.points[1])
    const da = d.dash || undefined

    if (d.type === 'horizontal') {
      const y = ps.priceToCoordinate?.(d.points[0].price) ?? -9999
      return (
        <g key={d.id}>
          <line x1={0} y1={y} x2={w} y2={y} stroke={d.color} strokeWidth={d.width} strokeDasharray={da} opacity={0.85} />
          <text x={w - 4} y={y - 4} fontSize={9} fill={d.color} textAnchor="end" fontFamily="JetBrains Mono, monospace" opacity={0.85}>
            {d.points[0].price.toFixed(0)}
          </text>
        </g>
      )
    }

    if (d.type === 'vertical') {
      const x = chartApi!.timeScale().timeToCoordinate(d.points[0].time as any) ?? -9999
      return <line key={d.id} x1={x} y1={0} x2={x} y2={height} stroke={d.color} strokeWidth={d.width} strokeDasharray={da ?? '5,3'} opacity={0.75} />
    }

    if (d.type === 'trendline') {
      // Extend line to screen edges
      if (p1.x === p2.x) return <line key={d.id} x1={p1.x} y1={0} x2={p2.x} y2={height} stroke={d.color} strokeWidth={d.width} opacity={0.85} />
      const slope = (p2.y - p1.y) / (p2.x - p1.x)
      const yLeft  = p1.y - slope * p1.x
      const yRight = p1.y + slope * (w - p1.x)
      return <line key={d.id} x1={0} y1={yLeft} x2={w} y2={yRight} stroke={d.color} strokeWidth={d.width} strokeDasharray={da} opacity={0.85} />
    }

    if (d.type === 'ray') {
      const dx = p2.x - p1.x, dy = p2.y - p1.y
      const len = Math.sqrt(dx * dx + dy * dy) || 1
      const extend = 5000
      const ex = p1.x + dx / len * extend, ey = p1.y + dy / len * extend
      return <line key={d.id} x1={p1.x} y1={p1.y} x2={ex} y2={ey} stroke={d.color} strokeWidth={d.width} strokeDasharray={da} opacity={0.85} />
    }

    if (d.type === 'arrow') {
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x)
      const aLen = 13, aAngle = 0.38
      return (
        <g key={d.id} opacity={0.88}>
          <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={d.color} strokeWidth={d.width} markerEnd={`url(#arrowhead-${d.id})`} />
          <line x1={p2.x} y1={p2.y} x2={p2.x - aLen * Math.cos(angle - aAngle)} y2={p2.y - aLen * Math.sin(angle - aAngle)} stroke={d.color} strokeWidth={d.width} />
          <line x1={p2.x} y1={p2.y} x2={p2.x - aLen * Math.cos(angle + aAngle)} y2={p2.y - aLen * Math.sin(angle + aAngle)} stroke={d.color} strokeWidth={d.width} />
        </g>
      )
    }

    if (d.type === 'rectangle') {
      const rx = Math.min(p1.x, p2.x), ry = Math.min(p1.y, p2.y)
      const rw = Math.abs(p2.x - p1.x), rh = Math.abs(p2.y - p1.y)
      return (
        <g key={d.id} opacity={0.82}>
          <rect x={rx} y={ry} width={rw} height={rh} stroke={d.color} strokeWidth={d.width} fill={`${d.color}18`} rx={2} />
        </g>
      )
    }

    if (d.type === 'fibonacci') {
      const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
      const priceHigh = Math.max(d.points[0].price, d.points[1].price)
      const priceLow  = Math.min(d.points[0].price, d.points[1].price)
      const priceRange = priceHigh - priceLow
      const xLeft  = Math.min(p1.x, p2.x)
      const xRight = Math.max(p1.x, p2.x)
      return (
        <g key={d.id}>
          {levels.map(lv => {
            const price = priceLow + priceRange * (1 - lv)
            const y = ps.priceToCoordinate?.(price) ?? -9999
            const lvColor = lv === 0 || lv === 1 ? d.color : `${d.color}cc`
            return (
              <g key={lv}>
                <line x1={xLeft} y1={y} x2={xRight} y2={y} stroke={lvColor} strokeWidth={0.9} strokeDasharray="3,3" opacity={0.80} />
                <text x={xRight + 5} y={y + 3.5} fontSize={8.5} fill={lvColor} fontFamily="JetBrains Mono, monospace" opacity={0.85}>
                  {(lv * 100).toFixed(1)}%  {price.toFixed(0)}
                </text>
              </g>
            )
          })}
          <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={d.color} strokeWidth={0.7} strokeDasharray="2,4" opacity={0.4} />
        </g>
      )
    }

    return null
  }

  const isDrawing = activeTool !== 'cursor'

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'absolute', inset: 0, width: '100%', height: '100%',
        cursor: isDrawing ? 'crosshair' : 'default',
        pointerEvents: isDrawing ? 'all' : 'none',
        zIndex: 10,
      }}
      onClick={handleClick}
      onMouseMove={e => {
        const rect = e.currentTarget.getBoundingClientRect()
        setHoverPt({ x: e.clientX - rect.left, y: e.clientY - rect.top })
      }}
      onMouseLeave={() => setHoverPt(null)}
    >
      {drawings.map(renderDrawing)}

      {/* Preview line while waiting for second point */}
      {pendingPt && hoverPt && (
        <line x1={pendingPt.x} y1={pendingPt.y} x2={hoverPt.x} y2={hoverPt.y}
          stroke={activeColor} strokeWidth={1.5} strokeDasharray="5,3" opacity={0.55} />
      )}
      {pendingPt && <circle cx={pendingPt.x} cy={pendingPt.y} r={3.5} fill={activeColor} opacity={0.80} />}

      {/* Crosshair while drawing */}
      {isDrawing && hoverPt && !pendingPt && (
        <>
          <line x1={hoverPt.x} y1={0} x2={hoverPt.x} y2={height} stroke={activeColor} strokeWidth={0.6} opacity={0.35} />
          <line x1={0} y1={hoverPt.y} x2={w} y2={hoverPt.y} stroke={activeColor} strokeWidth={0.6} opacity={0.35} />
        </>
      )}
    </svg>
  )
}

// ── TradingChart ──────────────────────────────────────────────────────────────
const RANGE_BTNS = [
  { label: '1D', days: 5   },
  { label: '1W', days: 7   },
  { label: '1M', days: 21  },
  { label: '3M', days: 63  },
  { label: '6M', days: 126 },
  { label: '1Y', days: 252 },
  { label: 'ALL', days: 0  },
] as const
type RangeLabel = typeof RANGE_BTNS[number]['label']

function TradingChart() {
  const containerRef = useRef<HTMLDivElement>(null)
  const wrapRef      = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceRef     = useRef<ISeriesApi<any> | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volRef       = useRef<ISeriesApi<any> | null>(null)

  const [legend,     setLegend]    = useState<CandlestickData | null>(null)
  const [range,      setRange]     = useState<RangeLabel>('1M')
  const [chartType,  setChartType] = useState<ChartType>('candle')
  const [fs,         setFs]        = useState(false)
  const [drawVersion,setDrawVersion] = useState(0)

  // Vehicle
  const [make,     setMake]     = useState('BMW')
  const [model,    setModel]    = useState('3 Series')
  const [submodel, setSubmodel] = useState('320d')
  const [chartData,setChartData] = useState<ChartBar[]>(() => generateData('BMW', '3 Series', '320d'))

  // Drawing state
  const [activeTool,  setActiveTool]  = useState<DrawingTool>('cursor')
  const [activeColor, setActiveColor] = useState<string>(UP)
  const [drawings,    setDrawings]    = useState<Drawing[]>([])

  const [chartH, setChartH] = useState(280)

  const models    = Object.keys(VEHICLE_DATA[make] ?? {})
  const submodels = Object.keys(VEHICLE_DATA[make]?.[model] ?? {})

  const handleMake = useCallback((m: string) => {
    const mods = Object.keys(VEHICLE_DATA[m] ?? {}); const mod = mods[0] ?? ''
    const subs = Object.keys(VEHICLE_DATA[m]?.[mod] ?? {}); const sub = subs[0] ?? ''
    setMake(m); setModel(mod); setSubmodel(sub); setChartData(generateData(m, mod, sub)); setDrawings([])
  }, [])
  const handleModel = useCallback((mod: string) => {
    const subs = Object.keys(VEHICLE_DATA[make]?.[mod] ?? {}); const sub = subs[0] ?? ''
    setModel(mod); setSubmodel(sub); setChartData(generateData(make, mod, sub)); setDrawings([])
  }, [make])
  const handleSub = useCallback((sub: string) => {
    setSubmodel(sub); setChartData(generateData(make, model, sub)); setDrawings([])
  }, [make, model])

  // ESC
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') { setFs(false); setActiveTool('cursor') } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  // Build chart
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.offsetWidth, height: chartH,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#475569', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: 'rgba(167,139,250,0.38)', labelBackgroundColor: '#7c3aed' },
        horzLine: { color: 'rgba(167,139,250,0.38)', labelBackgroundColor: '#7c3aed' },
      },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.07)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.07)', timeVisible: true, secondsVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
      handleScale:  { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    })
    chartRef.current = chart
    setTimeout(() => { containerRef.current?.querySelectorAll('a').forEach(a => { a.style.display = 'none' }) }, 150)

    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false, priceLineVisible: false })
    volRef.current = vol
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } })

    const obs = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current)
        chartRef.current.applyOptions({ width: containerRef.current.offsetWidth })
    })
    obs.observe(containerRef.current)

    // Trigger drawing re-render on viewport change
    const onRangeChange = () => setDrawVersion(n => n + 1)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ts = chart.timeScale() as any
    ts.subscribeVisibleLogicalRangeChange?.(onRangeChange)
    ts.subscribeVisibleTimeRangeChange?.(onRangeChange)

    chart.timeScale().fitContent()
    return () => {
      obs.disconnect()
      ts.unsubscribeVisibleLogicalRangeChange?.(onRangeChange)
      ts.unsubscribeVisibleTimeRangeChange?.(onRangeChange)
      chart.remove()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update series on type or data change
  useEffect(() => {
    if (!chartRef.current) return
    if (priceRef.current) {
      try { chartRef.current.removeSeries(priceRef.current) } catch { /**/ }
      priceRef.current = null
    }
    const chart = chartRef.current

    if (chartType === 'candle') {
      const s = chart.addSeries(CandlestickSeries, { upColor: '#a78bfa', downColor: '#f87171', borderUpColor: '#a78bfa', borderDownColor: '#f87171', wickUpColor: 'rgba(167,139,250,0.65)', wickDownColor: 'rgba(248,113,113,0.65)' })
      s.setData(chartData.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })))
      priceRef.current = s
      chart.subscribeCrosshairMove(param => {
        if (param.seriesData && param.seriesData.has(s)) setLegend(param.seriesData.get(s) as CandlestickData)
        else setLegend(null)
      })
    } else if (chartType === 'line') {
      const s = chart.addSeries(LineSeries, { color: '#a78bfa', lineWidth: 2 })
      s.setData(chartData.map(d => ({ time: d.time, value: d.close })))
      priceRef.current = s
    } else {
      const s = chart.addSeries(AreaSeries, { lineColor: '#a78bfa', topColor: 'rgba(124,58,237,0.28)', bottomColor: 'rgba(124,58,237,0)', lineWidth: 2 })
      s.setData(chartData.map(d => ({ time: d.time, value: d.close })))
      priceRef.current = s
    }

    if (volRef.current) {
      volRef.current.setData(chartData.map(d => ({ time: d.time, value: d.volume, color: d.close >= d.open ? 'rgba(167,139,250,0.28)' : 'rgba(248,113,113,0.22)' })))
    }

    chartRef.current.timeScale().fitContent()
  }, [chartType, chartData])

  // Range
  useEffect(() => {
    if (!chartRef.current) return
    if (range === 'ALL') { chartRef.current.timeScale().fitContent(); return }
    const btn = RANGE_BTNS.find(b => b.label === range)!
    const from = new Date('2026-05-22')
    from.setDate(from.getDate() - btn.days)
    chartRef.current.timeScale().setVisibleRange({ from: from.toISOString().split('T')[0] as any, to: '2026-05-22' as any })
  }, [range])

  // Fullscreen
  useEffect(() => {
    if (!chartRef.current || !containerRef.current) return
    const newH = fs ? window.innerHeight - 190 : 280
    setChartH(newH)
    const newW = fs ? window.innerWidth - 76 : containerRef.current.offsetWidth
    chartRef.current.applyOptions({ width: newW, height: newH })
    chartRef.current.timeScale().fitContent()
    setDrawVersion(n => n + 1)
  }, [fs])

  const spec   = VEHICLE_DATA[make]?.[model]?.[submodel] ?? { basePrice: 20000, vol: 1 }
  const last   = chartData.at(-1)!
  const prev   = chartData.at(-2)!
  const disp   = legend ?? { open: last.open, high: last.high, low: last.low, close: last.close }
  const dispUp = disp.close >= disp.open
  const pct    = ((last.close - prev.close) / prev.close * 100)

  return (
    <div style={{
      position: fs ? 'fixed' : 'relative',
      inset:    fs ? 0 : 'auto',
      zIndex:   fs ? 9999 : 'auto',
      background: fs ? 'rgba(8,8,18,0.97)' : 'transparent',
      backdropFilter: fs ? 'blur(52px)' : 'none',
      WebkitBackdropFilter: fs ? 'blur(52px)' : 'none',
      padding: fs ? '16px 20px' : '12px 18px 0',
      display: 'flex', flexDirection: 'column',
    }}>

      {/* Vehicle selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 9, fontWeight: 700, color: T4, letterSpacing: '0.10em', textTransform: 'uppercase' }}>Vehicle</span>
        <Dropdown value={make}     options={ALL_MAKES} onChange={handleMake}  label="Make"    />
        <Dropdown value={model}    options={models}    onChange={handleModel} label="Model"   />
        <Dropdown value={submodel} options={submodels} onChange={handleSub}   label="Variant" />
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 14, fontWeight: 700, color: T1 }}>€{spec.basePrice.toLocaleString('de-DE')}</div>
          <div style={{ fontSize: 9.5, color: pct >= 0 ? UP : DN, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</div>
        </div>
      </div>

      {/* Chart toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: T2, fontFamily: 'JetBrains Mono, monospace' }}>{make} {model} {submodel}</span>
          <div style={{ display: 'flex', gap: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 9.5 }}>
            {([['O', disp.open], ['H', disp.high], ['L', disp.low], ['C', disp.close]] as [string, number][]).map(([k, v]) => (
              <span key={k}>
                <span style={{ color: T4 }}>{k} </span>
                <span style={{ color: k === 'C' ? (dispUp ? UP : DN) : T2, fontWeight: k === 'C' ? 700 : 400 }}>{v.toFixed(0)}</span>
              </span>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Chart type */}
          <div style={{ display: 'flex', gap: 2, padding: 2, background: 'rgba(255,255,255,0.04)', borderRadius: 8, border: `1px solid ${BRD}` }}>
            {(['candle', 'line', 'area'] as ChartType[]).map(type => (
              <button key={type} onClick={() => setChartType(type)} style={{ padding: '3px 8px', borderRadius: 6, fontSize: 9.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'Inter, system-ui', border: 'none', background: chartType === type ? 'rgba(124,58,237,0.22)' : 'transparent', color: chartType === type ? UP : T4, transition: 'all 140ms' }}>
                {type === 'candle' ? '🕯' : type === 'line' ? '📈' : '▨'}
              </button>
            ))}
          </div>

          {/* Range */}
          <div style={{ display: 'flex', gap: 2 }}>
            {RANGE_BTNS.map(btn => (
              <button key={btn.label} onClick={() => setRange(btn.label)} style={{ padding: '3px 7px', borderRadius: 6, fontSize: 9.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'Inter, system-ui', background: range === btn.label ? 'rgba(124,58,237,0.18)' : 'transparent', border: range === btn.label ? '1px solid rgba(124,58,237,0.32)' : '1px solid transparent', color: range === btn.label ? UP : T4, transition: 'all 140ms' }}>{btn.label}</button>
            ))}
          </div>

          {/* Fullscreen */}
          <button onClick={() => setFs(f => !f)} title={fs ? 'Exit (Esc)' : 'Fullscreen'} style={{ width: 26, height: 26, borderRadius: 7, cursor: 'pointer', background: fs ? 'rgba(124,58,237,0.18)' : GLASS_LT, border: fs ? '1px solid rgba(124,58,237,0.32)' : `1px solid ${BRD}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: fs ? UP : T4, transition: 'all 140ms' }}>
            {fs ? <Minimize2 style={{ width: 11, height: 11 }} /> : <Maximize2 style={{ width: 11, height: 11 }} />}
          </button>
        </div>
      </div>

      {/* Chart + drawing tools row */}
      <div style={{ display: 'flex', flex: fs ? 1 : 'none', minHeight: 0, position: 'relative' }}>
        {/* Drawing toolbar */}
        <DrawingToolbar
          activeTool={activeTool} setActiveTool={setActiveTool}
          activeColor={activeColor} setActiveColor={setActiveColor}
          drawings={drawings} onClear={() => setDrawings([])}
        />

        {/* Chart canvas + SVG overlay */}
        <div ref={wrapRef} style={{ flex: 1, position: 'relative' }}>
          <div ref={containerRef} style={{ width: '100%' }} />
          <DrawingOverlay
            chartApi={chartRef.current}
            drawings={drawings}
            onAdd={d => setDrawings(ds => [...ds, d])}
            activeTool={activeTool}
            activeColor={activeColor}
            version={drawVersion}
            height={chartH}
          />
        </div>
      </div>

      {/* Drawing mode hint */}
      {activeTool !== 'cursor' && (
        <div style={{ textAlign: 'center', marginTop: 4, fontSize: 9, color: activeColor, fontWeight: 600 }}>
          {activeTool === 'horizontal' || activeTool === 'vertical'
            ? 'Click on the chart to place'
            : 'Click first point, then second point'}
          <span style={{ color: T4, marginLeft: 8 }}>· Press Esc to exit</span>
        </div>
      )}

      {fs && activeTool === 'cursor' && (
        <div style={{ textAlign: 'center', marginTop: 4, fontSize: 9, color: T4 }}>
          <kbd style={{ padding: '1px 5px', borderRadius: 4, background: GLASS_LT, border: `1px solid ${BRD}`, color: T3 }}>Esc</kbd> to exit fullscreen
        </div>
      )}
    </div>
  )
}

// ── Right panel ───────────────────────────────────────────────────────────────
function RightPanel() {
  const [tab,   setTab]   = useState<'track' | 'alert'>('track')
  const [brand, setBrand] = useState('BMW')
  const [added, setAdded] = useState(false)
  function handleAdd() { setAdded(true); setTimeout(() => setAdded(false), 2000) }
  const asset = ASSETS.find(a => a.brand === brand) ?? ASSETS[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '18px 16px 0', flexShrink: 0 }}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 14, padding: 3, background: 'rgba(255,255,255,0.04)', borderRadius: 10, border: `1px solid ${BRD}` }}>
          {(['track', 'alert'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{ flex: 1, padding: '6px 0', borderRadius: 8, fontSize: 11.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'Inter, system-ui', transition: 'all 170ms', border: 'none', background: tab === t ? 'linear-gradient(135deg, rgba(124,58,237,0.80), rgba(37,99,235,0.80))' : 'transparent', color: tab === t ? '#fff' : T3, boxShadow: tab === t ? '0 2px 12px rgba(124,58,237,0.25)' : 'none' }}>
              {t === 'track' ? 'Track' : 'Alert'}
            </button>
          ))}
        </div>

        {/* Brand selector */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 9, color: T4, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 7 }}>Brand</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {ASSETS.map(a => (
              <button key={a.id} onClick={() => setBrand(a.brand)} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 9px', borderRadius: 99, fontSize: 10.5, fontWeight: 600, cursor: 'pointer', fontFamily: 'Inter, system-ui', transition: 'all 130ms', background: brand === a.brand ? 'rgba(124,58,237,0.12)' : 'rgba(255,255,255,0.04)', border: brand === a.brand ? '1px solid rgba(124,58,237,0.30)' : `1px solid ${BRD}`, color: brand === a.brand ? UP : T4 }}>
                <img src={`https://www.google.com/s2/favicons?domain=${BRAND_DOMAINS[a.brand] ?? a.brand.toLowerCase() + '.com'}&sz=32`} alt={a.brand} width={13} height={13} style={{ objectFit: 'contain' }} />
                {a.brand}
              </button>
            ))}
          </div>
        </div>

        {/* Price */}
        <div style={{ padding: '12px 14px', marginBottom: 10, background: GLASS_LT, backdropFilter: BLUR_MD, WebkitBackdropFilter: BLUR_MD, border: `1px solid ${BRD}`, borderRadius: 12, boxShadow: SHADOW_SM }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 9.5, color: T4, fontWeight: 600 }}>Market Price</span>
            <span style={{ fontSize: 9.5, color: T3, fontFamily: 'JetBrains Mono, monospace' }}>1,500 listings</span>
          </div>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 22, fontWeight: 700, color: T1 }}>€{asset.price.toLocaleString('de-DE')}</span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, color: UP, marginLeft: 8 }}>avg</span>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12 }}>
          {[['24h High', '€29,100'], ['24h Low', '€27,800'], ['Listings', '42,300'], ['Vol 24h', '1,240']].map(([k, v]) => (
            <div key={k} style={{ padding: '8px 10px', background: GLASS_LT, backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', border: `1px solid ${DIV}`, borderRadius: 10 }}>
              <div style={{ fontSize: 8.5, color: T4, marginBottom: 3, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{k}</div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 700, color: T2 }}>{v}</div>
            </div>
          ))}
        </div>

        {/* CTA */}
        <motion.button onClick={handleAdd} whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.01 }} style={{ width: '100%', padding: '11px 0', borderRadius: 11, background: added ? 'rgba(34,197,94,0.16)' : 'linear-gradient(135deg, rgba(124,58,237,0.88), rgba(37,99,235,0.88))', border: added ? '1px solid rgba(34,197,94,0.35)' : '1px solid rgba(124,58,237,0.40)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)', color: added ? '#22c55e' : '#fff', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', fontFamily: 'Inter, system-ui', boxShadow: added ? 'none' : '0 4px 20px rgba(124,58,237,0.28)', transition: 'all 220ms', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7 }}>
          {added ? <><Check style={{ width: 13, height: 13 }} /> Added</> : tab === 'track' ? <><Star style={{ width: 13, height: 13 }} /> Add to Watchlist</> : <><Bell style={{ width: 13, height: 13 }} /> Set Alert</>}
        </motion.button>
      </div>

      <div style={{ height: 1, background: DIV, margin: '16px 16px 0' }} />

      {/* Portfolio with real logos */}
      <div style={{ padding: '14px 16px 18px', flex: 1, minHeight: 0, overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: T2 }}>My Portfolios</span>
          <button style={{ width: 20, height: 20, borderRadius: 6, background: GLASS_LT, border: `1px solid ${BRD}`, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Plus style={{ width: 9, height: 9, color: T3 }} />
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {PORTFOLIO.map((p, i) => {
            const up = p.delta >= 0
            return (
              <motion.div key={p.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 + i * 0.055 }}
                style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '7px 7px', borderRadius: 9, cursor: 'default', transition: 'background 120ms' }}
                whileHover={{ backgroundColor: 'rgba(255,255,255,0.04)' }}>
                <BrandLogo brand={p.brand} size={30} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: T2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</div>
                  <div style={{ fontSize: 9.5, color: T4, fontFamily: 'JetBrains Mono, monospace', marginTop: 1 }}>€{p.price.toLocaleString('de-DE')}</div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: up ? UP : DN, fontFamily: 'JetBrains Mono, monospace' }}>{up ? '+' : ''}{p.delta.toFixed(2)}%</div>
                  <div style={{ fontSize: 9.5, color: T4, fontFamily: 'JetBrains Mono, monospace', marginTop: 1 }}>{p.listings}</div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function Market() {
  const baseData = generateData('BMW', '3 Series', '320d')
  const last = baseData.at(-1)!
  const prev = baseData.at(-2)!
  const pct  = (last.close - prev.close) / prev.close * 100

  return (
    <div style={{ padding: '14px 18px 28px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 258px', gap: 12 }}>

        {/* Left panel */}
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.38, ease: [0.32, 0.72, 0, 1] }}
          style={{ background: GLASS, backdropFilter: BLUR, WebkitBackdropFilter: BLUR, border: `1px solid ${BRD}`, borderRadius: 18, boxShadow: SHADOW, overflow: 'hidden' }}>

          {/* Header */}
          <div style={{ padding: '18px 22px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <h2 style={{ fontSize: 17, fontWeight: 800, color: T1, letterSpacing: '-0.01em' }}>Overview</h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <motion.span style={{ width: 5, height: 5, borderRadius: '50%', background: '#22c55e', display: 'block' }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.4, repeat: Infinity }} />
                  <span style={{ fontSize: 9.5, fontWeight: 700, color: '#22c55e', letterSpacing: '0.05em' }}>LIVE</span>
                </div>
                <LiveClock />
                <div style={{ padding: '3px 10px', borderRadius: 99, background: 'rgba(124,58,237,0.12)', border: '1px solid rgba(124,58,237,0.25)', fontSize: 9.5, fontWeight: 700, color: UP, letterSpacing: '0.05em' }}>EU INDEX</div>
              </div>
            </div>
            {/* Dark glass ticker */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {TICKER_CHIPS.map(c => {
                const up = c.delta > 0
                return (
                  <div key={c.code} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 9px', background: CHIP_DARK, backdropFilter: 'blur(20px) saturate(140%)', WebkitBackdropFilter: 'blur(20px) saturate(140%)', border: `1px solid ${BRD_DARK}`, borderRadius: 99, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.07)' }}>
                    <span style={{ fontSize: 12 }}>{c.flag}</span>
                    <span style={{ fontSize: 9.5, fontWeight: 700, color: T4 }}>{c.code}</span>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 9.5, fontWeight: 700, color: up ? UP : DN }}>{up ? '+' : ''}{c.delta.toFixed(1)}%</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Asset cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, padding: '14px 18px 0' }}>
            {ASSETS.map((a, i) => {
              const up = a.delta > 0
              return (
                <motion.div key={a.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 + i * 0.07 }}
                  style={{ padding: '13px', background: GLASS_LT, backdropFilter: BLUR_MD, WebkitBackdropFilter: BLUR_MD, border: `1px solid ${BRD}`, borderRadius: 13, boxShadow: SHADOW_SM, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 9 }}>
                      <BrandLogo brand={a.brand} size={22} />
                      <span style={{ fontSize: 11, fontWeight: 700, color: T2 }}>{a.brand}</span>
                    </div>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 16, fontWeight: 700, color: T1, marginBottom: 5 }}>€{a.price.toLocaleString('de-DE')}</div>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 7px', borderRadius: 99, background: up ? 'rgba(124,58,237,0.12)' : 'rgba(248,113,113,0.12)', border: `1px solid ${up ? 'rgba(124,58,237,0.26)' : 'rgba(248,113,113,0.26)'}`, fontSize: 9.5, fontWeight: 700, color: up ? UP : DN, fontFamily: 'JetBrains Mono, monospace' }}>
                      {up ? '▲' : '▼'} {Math.abs(a.delta).toFixed(2)}%
                    </div>
                  </div>
                  <MiniBar vals={a.bars} color={a.color} />
                </motion.div>
              )
            })}
          </div>

          {/* Hero balance */}
          <div style={{ padding: '14px 22px 0' }}>
            <div style={{ fontSize: 9, color: T4, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 6 }}>Estimated Balance</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 3 }}>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 34, fontWeight: 800, color: T1, letterSpacing: '-0.03em', lineHeight: 1 }}>4,234,891</span>
              <span style={{ fontSize: 12, color: T3, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>EU</span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 700, color: pct >= 0 ? UP : DN }}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</span>
            </div>
            <div style={{ fontSize: 10, color: T4, fontFamily: 'JetBrains Mono, monospace' }}>Index {last.close.toFixed(2)} · May 2026</div>
          </div>

          {/* Chart */}
          <TradingChart />

          {/* Markets */}
          <div style={{ padding: '8px 22px 22px' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T1, marginBottom: 10 }}>Markets</div>
            <div style={{ display: 'flex', padding: '5px 0', borderBottom: `1px solid ${DIV}`, marginBottom: 3 }}>
              {['Name', 'Date', 'Last Price', 'Status', 'Amount'].map((h, i) => <div key={h} style={{ fontSize: 8.5, fontWeight: 700, color: T4, letterSpacing: '0.10em', textTransform: 'uppercase', flex: [2, 1.5, 1.2, 1.2, 1][i], textAlign: i >= 2 ? 'right' : 'left' }}>{h}</div>)}
            </div>
            {MARKETS.map((m, i) => {
              const up = m.delta > 0
              return (
                <motion.div key={m.code} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 + i * 0.07 }}
                  style={{ display: 'flex', alignItems: 'center', padding: '9px 0', borderBottom: i < MARKETS.length - 1 ? `1px solid ${DIV}` : 'none', cursor: 'default' }}
                  whileHover={{ backgroundColor: 'rgba(255,255,255,0.025)', borderRadius: 8 }}>
                  <div style={{ flex: 2, display: 'flex', alignItems: 'center', gap: 9 }}>
                    <div style={{ width: 30, height: 30, borderRadius: '50%', flexShrink: 0, background: GLASS_LT, border: `1px solid ${BRD}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15 }}>{m.flag}</div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: T1 }}>{m.name}</div>
                      <div style={{ fontSize: 9.5, color: up ? UP : DN, fontFamily: 'JetBrains Mono, monospace', marginTop: 1 }}>{up ? '+' : ''}{m.delta.toFixed(2)}%</div>
                    </div>
                  </div>
                  <div style={{ flex: 1.5, fontSize: 10.5, color: T4 }}>{m.date}</div>
                  <div style={{ flex: 1.2, textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 700, color: T2 }}>€{m.price.toLocaleString('de-DE')}</div>
                  <div style={{ flex: 1.2, display: 'flex', justifyContent: 'flex-end' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 99, background: 'rgba(34,197,94,0.10)', border: '1px solid rgba(34,197,94,0.20)' }}>
                      <div style={{ width: 4, height: 4, borderRadius: '50%', background: '#22c55e' }} />
                      <span style={{ fontSize: 9.5, fontWeight: 600, color: '#22c55e' }}>Active</span>
                    </div>
                  </div>
                  <div style={{ flex: 1, textAlign: 'right', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, fontWeight: 700, color: T1 }}>{m.listings}</div>
                </motion.div>
              )
            })}
          </div>
        </motion.div>

        {/* Right panel */}
        <motion.div initial={{ opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.10, duration: 0.38, ease: [0.32, 0.72, 0, 1] }}
          style={{ background: GLASS, backdropFilter: BLUR, WebkitBackdropFilter: BLUR, border: `1px solid ${BRD}`, borderRadius: 18, boxShadow: SHADOW, overflow: 'hidden' }}>
          <RightPanel />
        </motion.div>
      </div>
    </div>
  )
}
