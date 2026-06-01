import React, { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MousePointer2, TrendingUp, TrendingDown, Minus, MoveVertical,
  ArrowUpRight, Square, Triangle, Type, Trash2, Maximize2, Minimize2,
  Bell, Star, Check, Plus, X, ChevronDown, Settings, Camera, Search,
  Lock, Eye, EyeOff, BarChart2, Activity, ZoomIn, ZoomOut,
  Circle, AlignLeft, GitBranch, ChevronRight,
} from 'lucide-react'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries, AreaSeries,
  ColorType, CrosshairMode,
  type IChartApi, type ISeriesApi, type CandlestickData,
} from 'lightweight-charts'

// ── Design tokens ─────────────────────────────────────────────────────────────
const BG    = 'rgba(8,8,20,0.94)'
const PANEL = 'rgba(12,12,26,0.90)'
const GLASS = 'rgba(255,255,255,0.05)'
const BRD   = 'rgba(255,255,255,0.10)'
const BRD_HI= 'rgba(255,255,255,0.18)'
const BLUR  = 'blur(40px) saturate(180%)'
const T1 = '#f1f5f9', T2 = '#cbd5e1', T3 = '#94a3b8', T4 = '#475569'
const UP = '#a78bfa', DN = '#f87171', UP_DIM = 'rgba(167,139,250,0.22)', DN_DIM = 'rgba(248,113,113,0.18)'
const ACCENT = '#7c3aed'

// ── Inline SVG icons (not in lucide 0.424) ────────────────────────────────────
function CxIcon({ s = 13, c = 'currentColor' }: { s?: number; c?: string }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
      <circle cx="12" cy="12" r="3"/><line x1="12" y1="3" x2="12" y2="8"/><line x1="12" y1="16" x2="12" y2="21"/>
      <line x1="3" y1="12" x2="8" y2="12"/><line x1="16" y1="12" x2="21" y2="12"/>
    </svg>
  )
}
function FibIcon({ s = 13, c = 'currentColor' }: { s?: number; c?: string }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5}>
      <line x1="3" y1="21" x2="21" y2="3"/><line x1="3" y1="21" x2="21" y2="9"/><line x1="3" y1="21" x2="21" y2="14"/>
      <line x1="3" y1="21" x2="21" y2="17.5"/><line x1="3" y1="21" x2="21" y2="19.5" opacity={0.5}/>
    </svg>
  )
}
function MagnetIcon({ s = 13, c = 'currentColor' }: { s?: number; c?: string }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
      <path d="M6 15A6 6 0 1 0 18 15"/><line x1="6" y1="15" x2="6" y2="20"/><line x1="18" y1="15" x2="18" y2="20"/>
      <line x1="6" y1="20" x2="9" y2="20"/><line x1="15" y1="20" x2="18" y2="20"/>
    </svg>
  )
}
function LongIcon({ s = 13 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" strokeWidth={1.6} strokeLinecap="round">
      <line x1="3" y1="12" x2="21" y2="12" stroke="rgba(167,139,250,0.7)"/>
      <rect x="3" y="8" width="18" height="4" fill="rgba(167,139,250,0.15)" stroke="rgba(167,139,250,0.5)"/>
      <rect x="3" y="12" width="18" height="4" fill="rgba(248,113,113,0.15)" stroke="rgba(248,113,113,0.5)"/>
      <line x1="12" y1="4" x2="12" y2="8" stroke="#a78bfa"/><polyline points="9,6 12,4 15,6" stroke="#a78bfa"/>
    </svg>
  )
}
function ShortIcon({ s = 13 }: { s?: number }) {
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" strokeWidth={1.6} strokeLinecap="round">
      <line x1="3" y1="12" x2="21" y2="12" stroke="rgba(248,113,113,0.7)"/>
      <rect x="3" y="8" width="18" height="4" fill="rgba(167,139,250,0.15)" stroke="rgba(167,139,250,0.5)"/>
      <rect x="3" y="12" width="18" height="4" fill="rgba(248,113,113,0.15)" stroke="rgba(248,113,113,0.5)"/>
      <line x1="12" y1="16" x2="12" y2="20" stroke="#f87171"/><polyline points="9,18 12,20 15,18" stroke="#f87171"/>
    </svg>
  )
}

// ── Types ─────────────────────────────────────────────────────────────────────
type DrawingTool = 'cursor'|'crosshair'|'trendline'|'ray'|'extended'|'hline'|'hray'|'vline'|'crossline'
  |'rectangle'|'triangle_shape'|'ellipse_shape'
  |'fibonacci'|'fib_fan'|'fib_ext'|'fib_time'
  |'text'|'arrow_up'|'arrow_down'|'note'
  |'long_pos'|'short_pos'|'date_range'|'price_range'
  |'brush'|'highlighter'|'pitchfork'
type ChartType = 'candle'|'bar'|'line'|'area'|'hollow'
interface DrawingPoint { time: string; price: number }
interface Drawing {
  id: string; type: DrawingTool; points: DrawingPoint[]
  color: string; width: number; dash: string; text?: string
}
interface VehicleSpec { basePrice: number; vol: number }
interface IndicatorDef { id: string; name: string; kind: string; type: 'overlay'|'oscillator'; color: string; params: Record<string, number> }
interface ChartBar { time: string; open: number; high: number; low: number; close: number; volume: number }
type RangeLabel = '1D'|'1W'|'1M'|'3M'|'6M'|'1Y'|'ALL'

// ── Vehicle data ──────────────────────────────────────────────────────────────
const VEHICLE_DATA: Record<string, Record<string, Record<string, VehicleSpec>>> = {
  BMW:      { '3 Series': { '318d':{basePrice:22800,vol:0.9},'320d':{basePrice:28450,vol:1.1},'330i':{basePrice:31800,vol:1.3},'M340i':{basePrice:45200,vol:1.8} }, 'X3':{ 'xDrive20d':{basePrice:44500,vol:1.1},'M40i':{basePrice:62000,vol:2.0} }, 'X5':{ 'xDrive30d':{basePrice:61000,vol:1.0},'xDrive45e':{basePrice:75000,vol:1.4} }, 'M3':{ 'Competition':{basePrice:82000,vol:2.2},'CS':{basePrice:115000,vol:2.8} } },
  VW:       { Golf:{ '1.5 TSI':{basePrice:16200,vol:0.8},'2.0 TDI':{basePrice:18900,vol:0.8},'GTI':{basePrice:28500,vol:1.5},'R':{basePrice:39000,vol:2.0} }, Tiguan:{ '1.5 TSI':{basePrice:28000,vol:0.9},'R-Line':{basePrice:36000,vol:1.2} }, 'ID.4':{ 'Pure':{basePrice:32000,vol:1.5},'GTX':{basePrice:48000,vol:1.8} } },
  Mercedes: { 'C-Class':{ 'C200':{basePrice:32100,vol:1.1},'C220d':{basePrice:34500,vol:1.0},'C63 AMG':{basePrice:68000,vol:2.5} }, 'GLC':{ 'GLC200':{basePrice:44000,vol:1.0},'GLC63 AMG':{basePrice:86000,vol:2.2} }, 'E-Class':{ 'E220d':{basePrice:42000,vol:0.9},'E450':{basePrice:58000,vol:1.4} } },
  Audi:     { A4:{ '35 TDI':{basePrice:24000,vol:0.9},'40 TFSI':{basePrice:29500,vol:1.0},'S4':{basePrice:48000,vol:1.7} }, Q5:{ '35 TDI':{basePrice:38000,vol:0.9},'SQ5':{basePrice:60000,vol:1.6} }, 'RS6':{ 'Avant':{basePrice:98000,vol:2.4},'Performance':{basePrice:130000,vol:2.9} } },
  Porsche:  { '911':{ 'Carrera':{basePrice:115000,vol:2.0},'Turbo S':{basePrice:215000,vol:3.0} }, Cayenne:{ 'S':{basePrice:92000,vol:1.5},'Turbo':{basePrice:158000,vol:2.5} }, Macan:{ '2.0':{basePrice:58000,vol:1.2},'GTS':{basePrice:82000,vol:1.8} } },
  Toyota:   { Corolla:{ '1.8 HV':{basePrice:22300,vol:0.9},'GR Sport':{basePrice:28000,vol:1.4} }, 'RAV4':{ 'Hybrid':{basePrice:38000,vol:1.3},'PHEV':{basePrice:45000,vol:1.6} } },
  Renault:  { Clio:{ '1.0 TCe':{basePrice:13500,vol:0.6},'1.6 E-Tech':{basePrice:18900,vol:0.9} }, Megane:{ 'E-Tech':{basePrice:35000,vol:1.2} } },
  Skoda:    { Octavia:{ '1.5 TSI':{basePrice:16800,vol:0.8},'RS':{basePrice:31000,vol:1.5} }, Kodiaq:{ '2.0 TDI':{basePrice:38000,vol:1.0} } },
}
const ALL_MAKES = Object.keys(VEHICLE_DATA)
const COUNTRIES = [
  { code:'ALL', flag:'🌍', name:'All EU' },
  { code:'DE',  flag:'🇩🇪', name:'Germany'     },
  { code:'FR',  flag:'🇫🇷', name:'France'       },
  { code:'ES',  flag:'🇪🇸', name:'Spain'        },
  { code:'NL',  flag:'🇳🇱', name:'Netherlands'  },
  { code:'BE',  flag:'🇧🇪', name:'Belgium'      },
  { code:'CH',  flag:'🇨🇭', name:'Switzerland'  },
]
const BRAND_DOMAINS: Record<string, string> = {
  BMW:'bmw.com',VW:'vw.com',Mercedes:'mercedes-benz.com',Audi:'audi.com',
  Porsche:'porsche.com',Toyota:'toyota.com',Renault:'renault.com',Skoda:'skoda-auto.com',
}
const WATCHLIST_DEFAULT = [
  { brand:'BMW',    model:'3 Series', sub:'320d',        country:'DE', listings:42_300 },
  { brand:'VW',     model:'Golf',     sub:'GTI',         country:'DE', listings:98_700 },
  { brand:'Mercedes',model:'C-Class', sub:'C220d',       country:'FR', listings:31_450 },
  { brand:'Audi',   model:'A4',       sub:'40 TFSI',     country:'DE', listings:38_200 },
  { brand:'Porsche',model:'911',      sub:'Carrera',     country:'DE', listings:6_800  },
  { brand:'Toyota', model:'Corolla',  sub:'1.8 HV',      country:'ES', listings:28_100 },
  { brand:'Skoda',  model:'Octavia',  sub:'1.5 TSI',     country:'DE', listings:36_700 },
  { brand:'Renault',model:'Clio',     sub:'1.6 E-Tech',  country:'FR', listings:54_200 },
]

// ── Chart data generator ──────────────────────────────────────────────────────
function seedRng(seed: number) {
  let s = seed
  return () => { s = (s * 1664525 + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
}
function generateData(make: string, model: string, sub: string, days = 400): ChartBar[] {
  const spec = VEHICLE_DATA[make]?.[model]?.[sub] ?? { basePrice: 20000, vol: 1.0 }
  const rng  = seedRng(make.charCodeAt(0) * 31 + model.charCodeAt(0) * 17 + (sub.charCodeAt(0) || 7))
  const bars: ChartBar[] = []
  let price = spec.basePrice * (0.93 + rng() * 0.05)
  const today = new Date('2026-05-22')
  for (let i = days; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i)
    if (d.getDay() === 0 || d.getDay() === 6) continue
    const time  = d.toISOString().split('T')[0]
    const drift = (rng() - 0.47) * spec.vol * (spec.basePrice / 80)
    const close = Math.max(spec.basePrice * 0.60, Math.min(spec.basePrice * 1.45, price + drift))
    const wick  = rng() * spec.vol * (spec.basePrice / 260)
    bars.push({ time, open: price, high: Math.max(price, close) + wick, low: Math.min(price, close) - wick, close, volume: 40 + rng() * 110 })
    price = close
  }
  return bars
}

// ── Indicator calculations ────────────────────────────────────────────────────
type PD = { time: string; value: number }
function calcSMA(data: ChartBar[], period: number): PD[] {
  return data.map((d, i) => {
    if (i < period - 1) return null
    const sum = data.slice(i - period + 1, i + 1).reduce((s, b) => s + b.close, 0)
    return { time: d.time, value: sum / period }
  }).filter(Boolean) as PD[]
}
function calcEMA(data: ChartBar[], period: number): PD[] {
  const k = 2 / (period + 1)
  let ema = data[0]?.close ?? 0
  return data.map((d, i) => {
    ema = i === 0 ? d.close : d.close * k + ema * (1 - k)
    return { time: d.time, value: ema }
  })
}
function calcBB(data: ChartBar[], period = 20, mult = 2) {
  const mid = calcSMA(data, period)
  const upper: PD[] = [], lower: PD[] = []
  for (let i = period - 1; i < data.length; i++) {
    const slice = data.slice(i - period + 1, i + 1)
    const m = mid[i - (period - 1)].value
    const sd = Math.sqrt(slice.reduce((s, b) => s + (b.close - m) ** 2, 0) / period)
    upper.push({ time: data[i].time, value: m + mult * sd })
    lower.push({ time: data[i].time, value: m - mult * sd })
  }
  return { mid, upper, lower }
}
function calcRSI(data: ChartBar[], period = 14): PD[] {
  if (data.length < period + 1) return []
  let ag = 0, al = 0
  for (let i = 1; i <= period; i++) {
    const c = data[i].close - data[i - 1].close
    if (c > 0) ag += c; else al += Math.abs(c)
  }
  ag /= period; al /= period
  const result: PD[] = []
  for (let i = period; i < data.length; i++) {
    if (i > period) {
      const c = data[i].close - data[i - 1].close
      ag = (ag * (period - 1) + (c > 0 ? c : 0)) / period
      al = (al * (period - 1) + (c < 0 ? Math.abs(c) : 0)) / period
    }
    result.push({ time: data[i].time, value: 100 - 100 / (1 + (al === 0 ? 1e9 : ag / al)) })
  }
  return result
}
function calcMACD(data: ChartBar[], fast = 12, slow = 26, signal = 9) {
  const kf = 2/(fast+1), ks = 2/(slow+1), kg = 2/(signal+1)
  let ef = data[0].close, es = data[0].close
  const ml: PD[] = []
  for (let i = 0; i < data.length; i++) {
    ef = i===0 ? data[0].close : data[i].close*kf + ef*(1-kf)
    es = i===0 ? data[0].close : data[i].close*ks + es*(1-ks)
    if (i >= slow - 1) ml.push({ time: data[i].time, value: ef - es })
  }
  let sig = ml[0]?.value ?? 0
  const sl: PD[] = [], hist: { time: string; value: number; color: string }[] = []
  for (let i = 0; i < ml.length; i++) {
    sig = i===0 ? ml[0].value : ml[i].value*kg + sig*(1-kg)
    if (i >= signal - 1) {
      sl.push({ time: ml[i].time, value: sig })
      hist.push({ time: ml[i].time, value: ml[i].value - sig, color: ml[i].value - sig >= 0 ? 'rgba(167,139,250,0.5)' : 'rgba(248,113,113,0.5)' })
    }
  }
  return { macd: ml, signal: sl, hist }
}

// ── Drawing toolbar ───────────────────────────────────────────────────────────
type DrawingGroup = {
  id: string; icon: React.ReactNode; label: string
  tools: { id: DrawingTool; label: string; icon: React.ReactNode; disabled?: boolean; shortcut?: string }[]
}
const DRAWING_GROUPS: DrawingGroup[] = [
  { id:'g_cursor', icon:<MousePointer2 style={{width:13,height:13}}/>, label:'Cursor', tools:[
    { id:'cursor',    label:'Cursor',      icon:<MousePointer2 style={{width:12,height:12}}/>, shortcut:'V' },
    { id:'crosshair', label:'Crosshair',   icon:<CxIcon s={12}/>, shortcut:'C' },
  ]},
  { id:'g_lines', icon:<TrendingUp style={{width:13,height:13}}/>, label:'Lines', tools:[
    { id:'trendline', label:'Trend Line',   icon:<TrendingUp style={{width:12,height:12}}/>,    shortcut:'T' },
    { id:'ray',       label:'Ray',          icon:<ArrowUpRight style={{width:12,height:12}}/>,  shortcut:'R' },
    { id:'extended',  label:'Extended Line',icon:<AlignLeft style={{width:12,height:12}}/>,     shortcut:'E' },
    { id:'hline',     label:'H-Line',       icon:<Minus style={{width:12,height:12}}/>,         shortcut:'H' },
    { id:'hray',      label:'H-Ray',        icon:<ArrowUpRight style={{width:12,height:12}}/>,  },
    { id:'vline',     label:'V-Line',       icon:<MoveVertical style={{width:12,height:12}}/>,  shortcut:'L' },
    { id:'crossline', label:'Cross',        icon:<CxIcon s={12}/>, },
  ]},
  { id:'g_fib', icon:<FibIcon s={13}/>, label:'Fibonacci', tools:[
    { id:'fibonacci',  label:'Fib Retracement', icon:<FibIcon s={12}/>, shortcut:'F' },
    { id:'fib_fan',    label:'Fib Fan',          icon:<FibIcon s={12}/>, },
    { id:'fib_ext',    label:'Fib Extension',    icon:<FibIcon s={12}/>, disabled:true },
    { id:'fib_time',   label:'Fib Time Zones',   icon:<FibIcon s={12}/>, disabled:true },
  ]},
  { id:'g_shapes', icon:<Square style={{width:13,height:13}}/>, label:'Shapes', tools:[
    { id:'rectangle',      label:'Rectangle', icon:<Square style={{width:12,height:12}}/>,   shortcut:'G' },
    { id:'triangle_shape', label:'Triangle',  icon:<Triangle style={{width:12,height:12}}/>, disabled:true },
    { id:'ellipse_shape',  label:'Ellipse',   icon:<Circle style={{width:12,height:12}}/>,   disabled:true },
  ]},
  { id:'g_pos', icon:<LongIcon s={13}/>, label:'Position', tools:[
    { id:'long_pos',    label:'Long Position',  icon:<LongIcon s={12}/>,  shortcut:'B' },
    { id:'short_pos',   label:'Short Position', icon:<ShortIcon s={12}/>, shortcut:'N' },
    { id:'date_range',  label:'Date Range',     icon:<GitBranch style={{width:12,height:12}}/>, disabled:true },
    { id:'price_range', label:'Price Range',    icon:<MoveVertical style={{width:12,height:12}}/>, disabled:true },
  ]},
  { id:'g_text', icon:<Type style={{width:13,height:13}}/>, label:'Annotations', tools:[
    { id:'text',      label:'Text',       icon:<Type style={{width:12,height:12}}/>, shortcut:'X' },
    { id:'arrow_up',  label:'Arrow Up',   icon:<ArrowUpRight style={{width:12,height:12}}/>, },
    { id:'arrow_down',label:'Arrow Down', icon:<ArrowUpRight style={{width:12,height:12,transform:'rotate(90deg)'}}/>, },
    { id:'note',      label:'Note',       icon:<AlignLeft style={{width:12,height:12}}/>, disabled:true },
  ]},
  { id:'g_brush', icon:<Activity style={{width:13,height:13}}/>, label:'Brush', tools:[
    { id:'brush',      label:'Brush',       icon:<Activity style={{width:12,height:12}}/>, disabled:true },
    { id:'highlighter',label:'Highlighter', icon:<Activity style={{width:12,height:12}}/>, disabled:true },
  ]},
  { id:'g_pitchfork', icon:<GitBranch style={{width:13,height:13}}/>, label:'Pitchfork', tools:[
    { id:'pitchfork', label:"Andrews' Pitchfork", icon:<GitBranch style={{width:12,height:12}}/>, disabled:true },
  ]},
]
const TOOL_COLORS = ['#a78bfa','#60a5fa','#34d399','#fb923c','#f87171','#e879f9','#ffffff','#facc15']

function DrawingToolbar({
  activeTool, onToolSelect,
  activeColor, onColorChange,
  drawings, onClear,
  magnetMode, onMagnetToggle,
  lockMode, onLockToggle,
  hideMode, onHideToggle,
}: {
  activeTool: DrawingTool; onToolSelect: (t: DrawingTool) => void
  activeColor: string; onColorChange: (c: string) => void
  drawings: Drawing[]; onClear: () => void
  magnetMode: boolean; onMagnetToggle: () => void
  lockMode: boolean; onLockToggle: () => void
  hideMode: boolean; onHideToggle: () => void
}) {
  const [flyout, setFlyout] = useState<string | null>(null)
  const [showColors, setShowColors] = useState(false)
  const [activeGroups, setActiveGroups] = useState<Record<string, DrawingTool>>(() => ({
    g_cursor:'cursor', g_lines:'trendline', g_fib:'fibonacci', g_shapes:'rectangle',
    g_pos:'long_pos', g_text:'text', g_brush:'brush', g_pitchfork:'pitchfork',
  }))

  const toolForGroup = (gid: string) => {
    const grp = DRAWING_GROUPS.find(g => g.id === gid)
    if (!grp) return null
    const tid = activeGroups[gid]
    return grp.tools.find(t => t.id === tid) ?? grp.tools[0]
  }

  function selectTool(gid: string, tid: DrawingTool) {
    setActiveGroups(prev => ({ ...prev, [gid]: tid }))
    onToolSelect(tid)
    setFlyout(null)
  }

  const isActive = (gid: string) => {
    const grp = DRAWING_GROUPS.find(g => g.id === gid)
    return grp?.tools.some(t => t.id === activeTool) ?? false
  }

  return (
    <div style={{ position:'relative', display:'flex', flexDirection:'column', gap:2, padding:'8px 4px', background:PANEL, backdropFilter:BLUR, WebkitBackdropFilter:BLUR, borderRight:`1px solid ${BRD}`, width:44, alignItems:'center', flexShrink:0, zIndex:20 }}>
      {DRAWING_GROUPS.map(grp => {
        const tool = toolForGroup(grp.id)
        const active = isActive(grp.id)
        return (
          <div key={grp.id} style={{ position:'relative' }}>
            <div style={{ display:'flex', alignItems:'center', height:30, gap:0 }}>
              {/* Main tool button */}
              <button
                onClick={() => { const t = activeGroups[grp.id] as DrawingTool; onToolSelect(t); setFlyout(null) }}
                title={tool?.label ?? grp.label}
                style={{ width:30, height:30, borderRadius:6, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center', background:active ? 'rgba(124,58,237,0.28)' : 'rgba(255,255,255,0.04)', border:active ? '1px solid rgba(124,58,237,0.50)' : '1px solid transparent', color:active ? UP : T3, transition:'all 120ms' }}
              >
                {tool?.icon ?? grp.icon}
              </button>
              {/* Flyout arrow */}
              <button
                onClick={() => setFlyout(f => f === grp.id ? null : grp.id)}
                style={{ width:8, height:30, cursor:'pointer', background:'transparent', border:'none', display:'flex', alignItems:'center', justifyContent:'center', color:T4, padding:0 }}
              >
                <svg width={5} height={5} viewBox="0 0 6 6" fill={T4}><polygon points="0,0 6,3 0,6"/></svg>
              </button>
            </div>

            {/* Flyout panel */}
            <AnimatePresence>
              {flyout === grp.id && (
                <motion.div initial={{opacity:0,x:-6}} animate={{opacity:1,x:0}} exit={{opacity:0,x:-6}} transition={{duration:0.13}}
                  style={{ position:'absolute', left:44, top:0, background:'rgba(10,10,22,0.97)', backdropFilter:'blur(24px)', border:`1px solid ${BRD}`, borderRadius:10, boxShadow:'0 14px 40px rgba(0,0,0,0.6)', minWidth:160, zIndex:300, overflow:'hidden' }}>
                  <div style={{ padding:'6px 6px' }}>
                    {grp.tools.map(t => (
                      <div key={t.id} onClick={() => !t.disabled && selectTool(grp.id, t.id)}
                        style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:8, padding:'7px 10px', borderRadius:7, cursor:t.disabled?'not-allowed':'pointer', opacity:t.disabled?0.4:1, background:activeTool===t.id?UP_DIM:'transparent', transition:'background 110ms' }}
                        onMouseEnter={e => !t.disabled && ((e.currentTarget as HTMLDivElement).style.background = activeTool===t.id?UP_DIM:'rgba(255,255,255,0.06)')}
                        onMouseLeave={e => !t.disabled && ((e.currentTarget as HTMLDivElement).style.background = activeTool===t.id?UP_DIM:'transparent')}
                      >
                        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                          <span style={{ color:activeTool===t.id?UP:T3 }}>{t.icon}</span>
                          <span style={{ fontSize:11.5, fontWeight:activeTool===t.id?600:400, color:activeTool===t.id?UP:T2, fontFamily:'Inter, system-ui' }}>{t.label}</span>
                          {t.disabled && <span style={{ fontSize:9, color:T4, background:'rgba(255,255,255,0.06)', padding:'1px 5px', borderRadius:4 }}>Soon</span>}
                        </div>
                        {t.shortcut && <span style={{ fontSize:9.5, color:T4, fontFamily:'JetBrains Mono, monospace' }}>{t.shortcut}</span>}
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )
      })}

      {/* Divider */}
      <div style={{ width:24, height:1, background:BRD, margin:'3px 0' }} />

      {/* Color picker */}
      <div style={{ position:'relative' }}>
        <button onClick={() => { setShowColors(s => !s); setFlyout(null) }} title="Drawing color"
          style={{ width:28, height:28, borderRadius:7, cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center', background:GLASS, border:`1px solid ${BRD}` }}>
          <div style={{ width:13, height:13, borderRadius:'50%', background:activeColor, boxShadow:`0 0 6px ${activeColor}88` }} />
        </button>
        <AnimatePresence>
          {showColors && (
            <motion.div initial={{opacity:0,x:-6}} animate={{opacity:1,x:0}} exit={{opacity:0}} transition={{duration:0.12}}
              style={{ position:'absolute', left:36, top:0, display:'flex', flexDirection:'column', gap:5, padding:8, background:'rgba(10,10,22,0.97)', backdropFilter:'blur(20px)', border:`1px solid ${BRD}`, borderRadius:10, boxShadow:'0 8px 28px rgba(0,0,0,0.55)', zIndex:300 }}>
              {TOOL_COLORS.map(c => (
                <button key={c} onClick={() => { onColorChange(c); setShowColors(false) }}
                  style={{ width:18, height:18, borderRadius:'50%', background:c, border:c===activeColor?'2px solid white':'1px solid rgba(255,255,255,0.20)', cursor:'pointer', boxShadow:c===activeColor?`0 0 8px ${c}`:'none' }} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Divider */}
      <div style={{ width:24, height:1, background:BRD, margin:'3px 0' }} />

      {/* Magnet */}
      <button onClick={onMagnetToggle} title="Magnet mode (snap to price)"
        style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center', background:magnetMode?UP_DIM:GLASS, border:magnetMode?'1px solid rgba(124,58,237,0.40)':`1px solid ${BRD}`, color:magnetMode?UP:T3, transition:'all 120ms' }}>
        <MagnetIcon s={12} c={magnetMode?UP:T3} />
      </button>
      {/* Lock */}
      <button onClick={onLockToggle} title="Lock all drawings"
        style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center', background:lockMode?'rgba(245,158,11,0.15)':GLASS, border:lockMode?'1px solid rgba(245,158,11,0.35)':`1px solid ${BRD}`, color:lockMode?'#f59e0b':T3, transition:'all 120ms' }}>
        <Lock style={{ width:12, height:12 }} />
      </button>
      {/* Hide */}
      <button onClick={onHideToggle} title="Toggle drawings visibility"
        style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center', background:hideMode?'rgba(248,113,113,0.12)':GLASS, border:hideMode?'1px solid rgba(248,113,113,0.28)':`1px solid ${BRD}`, color:hideMode?'#f87171':T3, transition:'all 120ms' }}>
        {hideMode ? <EyeOff style={{width:12,height:12}}/> : <Eye style={{width:12,height:12}}/>}
      </button>
      {/* Clear */}
      {drawings.length > 0 && (
        <button onClick={onClear} title="Clear all drawings"
          style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center', background:'rgba(248,113,113,0.10)', border:'1px solid rgba(248,113,113,0.26)', color:'#f87171', transition:'all 120ms', marginTop:2 }}>
          <Trash2 style={{width:12,height:12}}/>
        </button>
      )}

      {/* Zoom */}
      <div style={{ width:24, height:1, background:BRD, margin:'3px 0' }} />
      <button title="Zoom in" style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',background:GLASS,border:`1px solid ${BRD}`,color:T3 }}>
        <ZoomIn style={{width:12,height:12}}/>
      </button>
      <button title="Zoom out" style={{ width:28,height:28,borderRadius:7,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',background:GLASS,border:`1px solid ${BRD}`,color:T3 }}>
        <ZoomOut style={{width:12,height:12}}/>
      </button>
    </div>
  )
}

// ── Drawing overlay ───────────────────────────────────────────────────────────
function DrawingOverlay({ chartApi, drawings, onAdd, activeTool, activeColor, version, height, lockMode, hideMode, textInput, onTextCommit }:{
  chartApi:IChartApi|null; drawings:Drawing[]; onAdd:(d:Drawing)=>void
  activeTool:DrawingTool; activeColor:string; version:number; height:number
  lockMode:boolean; hideMode:boolean
  textInput:{x:number;y:number}|null
  onTextCommit:(x:number,y:number,text:string)=>void
}) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const [w, setW] = useState(0)
  const [pending, setPending] = useState<{x:number;y:number}|null>(null)
  const [hover, setHover]     = useState<{x:number;y:number}|null>(null)
  const [, tick] = useState(0)

  useEffect(() => { tick(n => n+1) }, [version])
  useEffect(() => {
    if (!svgRef.current) return
    const obs = new ResizeObserver(e => setW(e[0].contentRect.width))
    obs.observe(svgRef.current)
    return () => obs.disconnect()
  }, [])

  if (!chartApi) return null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ps = chartApi.priceScale('right') as any

  function pxToChart(x:number,y:number):DrawingPoint|null {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const time  = (chartApi!.timeScale() as any).coordinateToTime(x)
    const price = (ps.coordinateToPrice?.(y) as number|null) ?? null
    if (time===null||time===undefined||price===null) return null
    return { time:String(time), price }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function toPx(pt:DrawingPoint):{x:number;y:number} {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const x = (chartApi!.timeScale() as any).timeToCoordinate(pt.time as any) ?? -9999
    const y = (ps.priceToCoordinate?.(pt.price) as number|null) ?? -9999
    return { x, y }
  }

  function handleClick(e:React.MouseEvent<SVGSVGElement>) {
    if (activeTool==='cursor'||activeTool==='crosshair'||lockMode) return
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left, py = e.clientY - rect.top

    if (activeTool==='hline'||activeTool==='hray') {
      const pt = pxToChart(px,py); if(!pt) return
      const tr = chartApi!.timeScale().getVisibleRange(); if(!tr) return
      onAdd({ id:Date.now().toString(), type:activeTool, points:[{time:String(tr.from),price:pt.price},{time:String(tr.to),price:pt.price}], color:activeColor, width:1, dash:'' })
      return
    }
    if (activeTool==='vline'||activeTool==='crossline') {
      const pt = pxToChart(px,py); if(!pt) return
      const prMin = ps.coordinateToPrice?.(0)??0, prMax = ps.coordinateToPrice?.(height)??999999
      onAdd({ id:Date.now().toString(), type:activeTool, points:[{time:pt.time,price:Math.min(prMin,prMax)},{time:pt.time,price:Math.max(prMin,prMax)}], color:activeColor, width:1, dash:'5,3' })
      return
    }
    if (activeTool==='arrow_up'||activeTool==='arrow_down') {
      const pt = pxToChart(px,py); if(!pt) return
      onAdd({ id:Date.now().toString(), type:activeTool, points:[pt], color:activeColor, width:1, dash:'' })
      return
    }
    if (!pending) { setPending({x:px,y:py}) }
    else {
      const pt1 = pxToChart(pending.x,pending.y), pt2 = pxToChart(px,py)
      if(!pt1||!pt2) { setPending(null); return }
      onAdd({ id:Date.now().toString(), type:activeTool, points:[pt1,pt2], color:activeColor, width:1.5, dash:'' })
      setPending(null)
    }
  }

  function renderDrawing(d:Drawing):React.ReactNode {
    const da = d.dash||undefined
    if (d.type==='hline'||d.type==='hray') {
      const y = ps.priceToCoordinate?.(d.points[0].price)??-9999
      const x2 = d.type==='hray' ? w : w
      return <g key={d.id} opacity={hideMode?0:0.85}>
        <line x1={0} y1={y} x2={x2} y2={y} stroke={d.color} strokeWidth={d.width}/>
        <text x={w-6} y={y-4} fontSize={9} fill={d.color} textAnchor="end" fontFamily="JetBrains Mono,monospace">{d.points[0].price.toFixed(0)}</text>
      </g>
    }
    if (d.type==='vline'||d.type==='crossline') {
      const x = (chartApi!.timeScale() as any).timeToCoordinate(d.points[0].time)??-9999
      return <g key={d.id} opacity={hideMode?0:0.8}>
        <line x1={x} y1={0} x2={x} y2={height} stroke={d.color} strokeWidth={d.width} strokeDasharray={da}/>
        {d.type==='crossline' && <line x1={0} y1={ps.priceToCoordinate?.(d.points[0].price)??-9999} x2={w} y2={ps.priceToCoordinate?.(d.points[0].price)??-9999} stroke={d.color} strokeWidth={d.width} strokeDasharray={da}/>}
      </g>
    }
    if (d.points.length < 2) {
      if (d.type==='arrow_up'||d.type==='arrow_down') {
        const p = toPx(d.points[0])
        const dir = d.type==='arrow_up' ? -1 : 1
        return <g key={d.id} opacity={hideMode?0:0.9}>
          <polygon points={`${p.x},${p.y + dir*14} ${p.x-6},${p.y + dir*22} ${p.x+6},${p.y + dir*22}`} fill={d.color}/>
        </g>
      }
      if (d.type==='text') {
        const p = toPx(d.points[0])
        return <g key={d.id} opacity={hideMode?0:0.9}>
          <text x={p.x} y={p.y} fontSize={12} fill={d.color} fontFamily="Inter, system-ui" fontWeight={500}>{d.text??''}</text>
        </g>
      }
      return null
    }
    const p1 = toPx(d.points[0]), p2 = toPx(d.points[1])

    if (d.type==='trendline') {
      if (p1.x===p2.x) return <line key={d.id} x1={p1.x} y1={0} x2={p2.x} y2={height} stroke={d.color} strokeWidth={d.width} opacity={hideMode?0:0.85}/>
      const slope = (p2.y-p1.y)/(p2.x-p1.x)
      return <g key={d.id} opacity={hideMode?0:0.85}>
        <line x1={0} y1={p1.y-slope*p1.x} x2={w} y2={p1.y+slope*(w-p1.x)} stroke={d.color} strokeWidth={d.width}/>
      </g>
    }
    if (d.type==='ray') {
      const dx=p2.x-p1.x, dy=p2.y-p1.y, l=Math.sqrt(dx*dx+dy*dy)||1
      return <line key={d.id} x1={p1.x} y1={p1.y} x2={p1.x+dx/l*5000} y2={p1.y+dy/l*5000} stroke={d.color} strokeWidth={d.width} opacity={hideMode?0:0.85}/>
    }
    if (d.type==='extended') {
      if (p1.x===p2.x) return <line key={d.id} x1={p1.x} y1={0} x2={p2.x} y2={height} stroke={d.color} strokeWidth={d.width} opacity={hideMode?0:0.85}/>
      const slope=(p2.y-p1.y)/(p2.x-p1.x)
      return <line key={d.id} x1={-1000} y1={p1.y-slope*(p1.x+1000)} x2={w+1000} y2={p1.y+slope*(w-p1.x+1000)} stroke={d.color} strokeWidth={d.width} opacity={hideMode?0:0.85}/>
    }
    if (d.type==='rectangle') {
      const rx=Math.min(p1.x,p2.x), ry=Math.min(p1.y,p2.y)
      return <g key={d.id} opacity={hideMode?0:0.85}>
        <rect x={rx} y={ry} width={Math.abs(p2.x-p1.x)} height={Math.abs(p2.y-p1.y)} stroke={d.color} strokeWidth={d.width} fill={`${d.color}18`} rx={2}/>
      </g>
    }
    if (d.type==='fibonacci') {
      const lvs = [0,0.236,0.382,0.5,0.618,0.786,1]
      const pHi = Math.max(d.points[0].price,d.points[1].price)
      const pLo = Math.min(d.points[0].price,d.points[1].price)
      const rng = pHi-pLo
      const xL=Math.min(p1.x,p2.x), xR=Math.max(p1.x,p2.x)
      return <g key={d.id} opacity={hideMode?0:1}>
        {lvs.map(lv => {
          const price = pLo + rng*(1-lv)
          const y = ps.priceToCoordinate?.(price)??-9999
          const c = lv===0||lv===1 ? d.color : `${d.color}bb`
          return <g key={lv}>
            <line x1={xL} y1={y} x2={xR} y2={y} stroke={c} strokeWidth={0.9} strokeDasharray="3,3" opacity={0.82}/>
            <text x={xR+5} y={y+3.5} fontSize={8.5} fill={c} fontFamily="JetBrains Mono,monospace" opacity={0.85}>{(lv*100).toFixed(1)}%  {price.toFixed(0)}</text>
          </g>
        })}
        <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={d.color} strokeWidth={0.7} strokeDasharray="2,4" opacity={0.4}/>
      </g>
    }
    if (d.type==='fib_fan') {
      const lvs=[0.236,0.382,0.5,0.618,0.786]
      const pHi=Math.max(d.points[0].price,d.points[1].price), pLo=Math.min(d.points[0].price,d.points[1].price)
      const rng=pHi-pLo
      return <g key={d.id} opacity={hideMode?0:0.82}>
        {lvs.map(lv => {
          const targetPrice = d.points[0].price + (d.points[1].price > d.points[0].price ? 1 : -1) * rng * lv
          const tp = {time:d.points[1].time, price:targetPrice}
          const pp = toPx(tp)
          const dx=pp.x-p1.x, dy=pp.y-p1.y, l=Math.sqrt(dx*dx+dy*dy)||1
          return <line key={lv} x1={p1.x} y1={p1.y} x2={p1.x+dx/l*5000} y2={p1.y+dy/l*5000} stroke={d.color} strokeWidth={0.9} strokeDasharray="4,3"/>
        })}
      </g>
    }
    if (d.type==='long_pos'||d.type==='short_pos') {
      const isLong = d.type==='long_pos'
      const entry = d.points[0].price, target = d.points[1].price
      const stop  = entry - (target - entry)
      const yEntry  = ps.priceToCoordinate?.(entry)??-9999
      const yTarget = ps.priceToCoordinate?.(target)??-9999
      const yStop   = ps.priceToCoordinate?.(stop)??-9999
      const xL=Math.min(p1.x,p2.x), xR=Math.max(p1.x,p2.x)+60
      return <g key={d.id} opacity={hideMode?0:0.88}>
        <rect x={xL} y={Math.min(yEntry,yTarget)} width={xR-xL} height={Math.abs(yTarget-yEntry)} fill={isLong?'rgba(167,139,250,0.10)':'rgba(248,113,113,0.10)'} stroke={isLong?'rgba(167,139,250,0.5)':'rgba(248,113,113,0.5)'} strokeWidth={0.8}/>
        <rect x={xL} y={Math.min(yEntry,yStop)} width={xR-xL} height={Math.abs(yStop-yEntry)} fill="rgba(248,113,113,0.06)" stroke="rgba(248,113,113,0.4)" strokeWidth={0.8}/>
        <line x1={xL} y1={yEntry} x2={xR} y2={yEntry} stroke={isLong?UP:'#f87171'} strokeWidth={1.5}/>
        <text x={xR+4} y={yTarget+3.5} fontSize={9} fill={isLong?UP:'#f87171'} fontFamily="JetBrains Mono,monospace">T: {target.toFixed(0)}</text>
        <text x={xR+4} y={yEntry+3.5} fontSize={9} fill={T3} fontFamily="JetBrains Mono,monospace">E: {entry.toFixed(0)}</text>
        <text x={xR+4} y={yStop+3.5} fontSize={9} fill="#f87171" fontFamily="JetBrains Mono,monospace">S: {stop.toFixed(0)}</text>
      </g>
    }
    return null
  }

  const isDrawing = !['cursor','crosshair'].includes(activeTool) && !lockMode

  return (
    <svg ref={svgRef} style={{ position:'absolute',inset:0,width:'100%',height:'100%', cursor:isDrawing?'crosshair':'default', pointerEvents:isDrawing?'all':'none', zIndex:10 }}
      onClick={handleClick}
      onMouseMove={e => { const r=e.currentTarget.getBoundingClientRect(); setHover({x:e.clientX-r.left,y:e.clientY-r.top}) }}
      onMouseLeave={() => setHover(null)}
    >
      {drawings.map(renderDrawing)}
      {pending&&hover&&<line x1={pending.x} y1={pending.y} x2={hover.x} y2={hover.y} stroke={activeColor} strokeWidth={1.5} strokeDasharray="5,3" opacity={0.55}/>}
      {pending&&<circle cx={pending.x} cy={pending.y} r={3.5} fill={activeColor} opacity={0.82}/>}
      {isDrawing&&hover&&!pending&&<>
        <line x1={hover.x} y1={0} x2={hover.x} y2={height} stroke={activeColor} strokeWidth={0.6} opacity={0.3}/>
        <line x1={0} y1={hover.y} x2={w} y2={hover.y} stroke={activeColor} strokeWidth={0.6} opacity={0.3}/>
      </>}
    </svg>
  )
}

// ── Indicator modal ───────────────────────────────────────────────────────────
const INDICATOR_CATALOG = [
  { id:'sma',   name:'SMA',               desc:'Simple Moving Average',           kind:'SMA',   type:'overlay'    as const, color:'#f59e0b',  params:{period:20} },
  { id:'ema',   name:'EMA',               desc:'Exponential Moving Average',       kind:'EMA',   type:'overlay'    as const, color:'#60a5fa',  params:{period:20} },
  { id:'wma',   name:'WMA',               desc:'Weighted Moving Average',          kind:'WMA',   type:'overlay'    as const, color:'#34d399',  params:{period:20} },
  { id:'bb',    name:'Bollinger Bands',   desc:'Bollinger Bands (20, 2)',          kind:'BB',    type:'overlay'    as const, color:'#a78bfa',  params:{period:20,mult:2} },
  { id:'rsi',   name:'RSI',               desc:'Relative Strength Index (14)',     kind:'RSI',   type:'oscillator' as const, color:'#a78bfa',  params:{period:14} },
  { id:'macd',  name:'MACD',              desc:'MACD (12, 26, 9)',                 kind:'MACD',  type:'oscillator' as const, color:'#a78bfa',  params:{fast:12,slow:26,signal:9} },
  { id:'stoch', name:'Stochastic',        desc:'Stochastic Oscillator (14, 3)',    kind:'Stoch', type:'oscillator' as const, color:'#fb923c',  params:{k:14,d:3}, disabled:true },
  { id:'atr',   name:'ATR',               desc:'Average True Range (14)',          kind:'ATR',   type:'oscillator' as const, color:'#94a3b8',  params:{period:14}, disabled:true },
  { id:'obv',   name:'OBV',               desc:'On-Balance Volume',                kind:'OBV',   type:'oscillator' as const, color:'#6ee7b7',  params:{}, disabled:true },
  { id:'vwap',  name:'VWAP',              desc:'Volume Weighted Average Price',    kind:'VWAP',  type:'overlay'    as const, color:'#f472b6',  params:{}, disabled:true },
]
const INDICATOR_CATS = ['All','Moving Averages','Oscillators','Volatility','Volume']

function IndicatorModal({ onAdd, onClose }: { onAdd:(def:typeof INDICATOR_CATALOG[number])=>void; onClose:()=>void }) {
  const [query, setQuery] = useState('')
  const [cat, setCat]     = useState('All')
  const filtered = INDICATOR_CATALOG.filter(i =>
    i.name.toLowerCase().includes(query.toLowerCase()) ||
    i.desc.toLowerCase().includes(query.toLowerCase())
  )
  return (
    <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:0.18}}
      style={{ position:'fixed',inset:0,zIndex:9999,background:'rgba(0,0,0,0.7)',backdropFilter:'blur(16px)',display:'flex',alignItems:'center',justifyContent:'center' }}
      onClick={e => e.target===e.currentTarget&&onClose()}>
      <motion.div initial={{scale:0.94,y:16}} animate={{scale:1,y:0}} exit={{scale:0.94,y:16}} transition={{duration:0.2,ease:[0.22,1,0.36,1]}}
        style={{ width:560,maxHeight:'70vh',display:'flex',flexDirection:'column',background:'rgba(12,12,26,0.97)',backdropFilter:BLUR,border:`1px solid ${BRD_HI}`,borderRadius:18,boxShadow:'0 32px 80px rgba(0,0,0,0.7)',overflow:'hidden' }}>
        {/* Header */}
        <div style={{ padding:'18px 20px 14px',borderBottom:`1px solid ${BRD}`,flexShrink:0 }}>
          <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:12 }}>
            <span style={{ fontSize:15,fontWeight:700,color:T1,letterSpacing:'-0.01em' }}>Add Indicator</span>
            <button onClick={onClose} style={{ width:28,height:28,borderRadius:8,display:'flex',alignItems:'center',justifyContent:'center',background:GLASS,border:`1px solid ${BRD}`,color:T3,cursor:'pointer' }}>
              <X style={{width:13,height:13}}/>
            </button>
          </div>
          {/* Search */}
          <div style={{ display:'flex',alignItems:'center',gap:8,padding:'7px 12px',background:GLASS,border:`1px solid ${BRD}`,borderRadius:10 }}>
            <Search style={{width:13,height:13,color:T4,flexShrink:0}}/>
            <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search indicators..." autoFocus
              style={{ flex:1,background:'transparent',border:'none',outline:'none',fontSize:12.5,color:T1,fontFamily:'Inter, system-ui' }} />
          </div>
          {/* Categories */}
          <div style={{ display:'flex',gap:6,marginTop:10,flexWrap:'wrap' }}>
            {INDICATOR_CATS.map(c => (
              <button key={c} onClick={()=>setCat(c)} style={{ padding:'3px 10px',borderRadius:99,fontSize:10.5,fontWeight:600,cursor:'pointer',fontFamily:'Inter, system-ui',transition:'all 120ms', background:cat===c?UP_DIM:GLASS, border:cat===c?'1px solid rgba(124,58,237,0.40)':`1px solid ${BRD}`, color:cat===c?UP:T3 }}>
                {c}
              </button>
            ))}
          </div>
        </div>
        {/* List */}
        <div style={{ flex:1,overflowY:'auto',padding:'8px 10px' }}>
          {filtered.map((ind,i) => (
            <motion.div key={ind.id} initial={{opacity:0,y:4}} animate={{opacity:1,y:0}} transition={{delay:i*0.03}}
              onClick={() => !ind.disabled && (onAdd(ind), onClose())}
              style={{ display:'flex',alignItems:'center',gap:12,padding:'10px 12px',borderRadius:10,cursor:ind.disabled?'not-allowed':'pointer',opacity:ind.disabled?0.4:1,transition:'background 110ms',marginBottom:2 }}
              onMouseEnter={e => !ind.disabled&&((e.currentTarget as HTMLDivElement).style.background='rgba(255,255,255,0.05)')}
              onMouseLeave={e => !ind.disabled&&((e.currentTarget as HTMLDivElement).style.background='transparent')}
            >
              <div style={{ width:8,height:8,borderRadius:'50%',background:ind.color,flexShrink:0,boxShadow:`0 0 5px ${ind.color}88` }}/>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:12.5,fontWeight:600,color:T1,marginBottom:2 }}>{ind.name}</div>
                <div style={{ fontSize:10.5,color:T4 }}>{ind.desc}</div>
              </div>
              <div style={{ fontSize:9.5,fontWeight:600,color:ind.type==='overlay'?'#34d399':'#f59e0b',background:ind.type==='overlay'?'rgba(52,211,153,0.10)':'rgba(245,158,11,0.10)',padding:'2px 7px',borderRadius:5 }}>
                {ind.type}
              </div>
              {ind.disabled && <span style={{ fontSize:9,color:T4,background:'rgba(255,255,255,0.06)',padding:'1px 5px',borderRadius:4 }}>Soon</span>}
            </motion.div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  )
}

// ── Range buttons ─────────────────────────────────────────────────────────────
const RANGES: { label:RangeLabel; days:number }[] = [
  {label:'1D',days:5},{label:'1W',days:7},{label:'1M',days:21},
  {label:'3M',days:63},{label:'6M',days:126},{label:'1Y',days:252},{label:'ALL',days:0},
]

// ── Pane layout calculator ────────────────────────────────────────────────────
interface PaneMargins { top:number; bottom:number }
interface PaneLayout { main:PaneMargins; vol:PaneMargins; rsi?:PaneMargins; macd?:PaneMargins }

function computePaneLayout(activeOsc: string[]): PaneLayout {
  const VOL=0.10, OSC=0.17, GAP=0.015
  let alloc = 0
  const layout: Record<string, PaneMargins> = {}
  for (const id of [...activeOsc].reverse()) {
    layout[id] = { top: 1-(alloc+OSC), bottom: alloc }
    alloc += OSC + GAP
  }
  layout['vol'] = { top: 1-(alloc+VOL), bottom: alloc }
  alloc += VOL + GAP
  layout['main'] = { top: 0, bottom: alloc }
  return layout as unknown as PaneLayout
}

// ── Main chart ────────────────────────────────────────────────────────────────
function TradingChart({
  make, model, submodel, country, range, chartType, activeIndicators,
  activeTool, activeColor, onCrossMove, fullscreen, setFullscreen, onDrawingOverlay,
  drawingProps,
}: {
  make:string; model:string; submodel:string; country:string
  range:RangeLabel; chartType:ChartType; activeIndicators:IndicatorDef[]
  activeTool:DrawingTool; activeColor:string
  onCrossMove:(d:CandlestickData|null)=>void
  fullscreen:boolean; setFullscreen:(v:boolean)=>void
  onDrawingOverlay:(h:number)=>void
  drawingProps:{ drawings:Drawing[]; onAdd:(d:Drawing)=>void; version:number; lockMode:boolean; hideMode:boolean; textInput:{x:number;y:number}|null; onTextCommit:(x:number,y:number,t:string)=>void }
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef   = useRef<IChartApi|null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef  = useRef<ISeriesApi<any>|null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volRef     = useRef<ISeriesApi<any>|null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const indRefs    = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const [chartH, setChartH] = useState(0)
  const [drawVersion, setDrawVersion] = useState(0)

  const chartData = React.useMemo(() => generateData(make, model, submodel), [make, model, submodel])
  const paneLayout = React.useMemo(() => computePaneLayout(activeIndicators.filter(i=>i.type==='oscillator').map(i=>i.kind)), [activeIndicators])

  // Build/destroy chart once
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.offsetWidth,
      height: containerRef.current.offsetHeight || 400,
      layout: { background:{type:ColorType.Solid,color:'transparent'}, textColor:'#475569', fontSize:10, fontFamily:'JetBrains Mono, monospace' },
      grid: { vertLines:{color:'rgba(255,255,255,0.04)'}, horzLines:{color:'rgba(255,255,255,0.04)'} },
      crosshair: { mode:CrosshairMode.Normal, vertLine:{color:'rgba(167,139,250,0.35)',labelBackgroundColor:ACCENT}, horzLine:{color:'rgba(167,139,250,0.35)',labelBackgroundColor:ACCENT} },
      rightPriceScale: { borderColor:'rgba(255,255,255,0.07)' },
      timeScale: { borderColor:'rgba(255,255,255,0.07)', timeVisible:true, secondsVisible:false },
      handleScroll:{ mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true },
      handleScale:{ mouseWheel:true, pinch:true, axisPressedMouseMove:true },
    })
    chartRef.current = chart
    setTimeout(() => containerRef.current?.querySelectorAll('a').forEach(a=>{a.style.display='none'}), 200)
    const vol = chart.addSeries(HistogramSeries,{ priceFormat:{type:'volume'}, priceScaleId:'vol', lastValueVisible:false, priceLineVisible:false })
    volRef.current = vol

    const obs = new ResizeObserver(entries => {
      const entry = entries[0]
      if (!entry||!chartRef.current) return
      const h = entry.contentRect.height
      chartRef.current.applyOptions({ width:entry.contentRect.width, height:h })
      setChartH(h)
      onDrawingOverlay(h)
    })
    obs.observe(containerRef.current)

    const ts = chart.timeScale() as any
    const onRange = () => setDrawVersion(n=>n+1)
    ts.subscribeVisibleLogicalRangeChange?.(onRange)
    ts.subscribeVisibleTimeRangeChange?.(onRange)

    return () => {
      obs.disconnect()
      ts.unsubscribeVisibleLogicalRangeChange?.(onRange)
      ts.unsubscribeVisibleTimeRangeChange?.(onRange)
      chart.remove()
      chartRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Update price series on type/data change
  useEffect(() => {
    if (!chartRef.current) return
    if (seriesRef.current) {
      try { chartRef.current.removeSeries(seriesRef.current) } catch { /* ok */ }
      seriesRef.current = null
    }
    const chart = chartRef.current
    let s
    if (chartType==='candle'||chartType==='hollow') {
      s = chart.addSeries(CandlestickSeries,{ upColor:UP, downColor:DN, borderUpColor:UP, borderDownColor:DN, wickUpColor:'rgba(167,139,250,0.6)', wickDownColor:'rgba(248,113,113,0.6)' })
      s.setData(chartData.map(d=>({time:d.time,open:d.open,high:d.high,low:d.low,close:d.close})))
    } else if (chartType==='line') {
      s = chart.addSeries(LineSeries,{ color:UP, lineWidth:2 })
      s.setData(chartData.map(d=>({time:d.time,value:d.close})))
    } else {
      s = chart.addSeries(AreaSeries,{ lineColor:UP, topColor:'rgba(124,58,237,0.28)', bottomColor:'rgba(124,58,237,0)', lineWidth:2 })
      s.setData(chartData.map(d=>({time:d.time,value:d.close})))
    }
    seriesRef.current = s
    chart.subscribeCrosshairMove(param => {
      if (param.seriesData?.has(s)) onCrossMove(param.seriesData.get(s) as CandlestickData)
      else onCrossMove(null)
    })
    if (volRef.current) {
      volRef.current.setData(chartData.map(d=>({time:d.time,value:d.volume,color:d.close>=d.open?'rgba(167,139,250,0.28)':'rgba(248,113,113,0.22)'})))
    }
    chart.timeScale().fitContent()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartType, chartData])

  // Update pane margins
  useEffect(() => {
    if (!chartRef.current) return
    const chart = chartRef.current
    chart.priceScale('vol').applyOptions({ scaleMargins: paneLayout.vol })
    if (seriesRef.current) {
      try { seriesRef.current.priceScale().applyOptions({ scaleMargins: paneLayout.main }) } catch { /**/ }
    }
    if (volRef.current) {
      try { volRef.current.priceScale().applyOptions({ scaleMargins: paneLayout.vol }) } catch { /**/ }
    }
    setDrawVersion(n=>n+1)
  }, [paneLayout])

  // Manage indicator series
  useEffect(() => {
    if (!chartRef.current) return
    const chart = chartRef.current
    // Remove series not in activeIndicators
    const activeIds = new Set(activeIndicators.map(i=>i.id))
    for (const [id, series] of indRefs.current.entries()) {
      if (!activeIds.has(id)) {
        series.forEach(s => { try { chart.removeSeries(s) } catch { /**/ } })
        indRefs.current.delete(id)
      }
    }
    // Add new indicators
    for (const ind of activeIndicators) {
      if (indRefs.current.has(ind.id)) continue
      const series: ISeriesApi<any>[] = []
      try {
        if (ind.kind==='SMA') {
          const data = calcSMA(chartData, ind.params.period??20)
          const s = chart.addSeries(LineSeries,{ color:ind.color, lineWidth:2, priceLineVisible:false, lastValueVisible:false })
          s.setData(data); series.push(s)
        } else if (ind.kind==='EMA') {
          const data = calcEMA(chartData, ind.params.period??20)
          const s = chart.addSeries(LineSeries,{ color:ind.color, lineWidth:2, priceLineVisible:false, lastValueVisible:false })
          s.setData(data); series.push(s)
        } else if (ind.kind==='WMA') {
          const data = calcSMA(chartData, ind.params.period??20)
          const s = chart.addSeries(LineSeries,{ color:ind.color, lineWidth:2, priceLineVisible:false, lastValueVisible:false })
          s.setData(data); series.push(s)
        } else if (ind.kind==='BB') {
          const {mid,upper,lower} = calcBB(chartData, ind.params.period??20, ind.params.mult??2)
          const sm = chart.addSeries(LineSeries,{color:ind.color,lineWidth:2,priceLineVisible:false,lastValueVisible:false})
          const su = chart.addSeries(LineSeries,{color:`${ind.color}80`,lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false})
          const sl = chart.addSeries(LineSeries,{color:`${ind.color}80`,lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false})
          sm.setData(mid); su.setData(upper); sl.setData(lower)
          series.push(sm,su,sl)
        } else if (ind.kind==='RSI') {
          const ml = paneLayout as any
          const data = calcRSI(chartData, ind.params.period??14)
          const s = chart.addSeries(LineSeries,{ color:ind.color, lineWidth:2, priceLineVisible:false, lastValueVisible:false, priceScaleId:'rsi' })
          s.setData(data)
          chart.priceScale('rsi').applyOptions({ scaleMargins: ml.rsi ?? ml.RSI ?? {top:0.72,bottom:0.14} })
          series.push(s)
          // RSI levels
          const rsiHi = chart.addSeries(LineSeries,{color:'rgba(248,113,113,0.35)',lineWidth:1,lineStyle:2,priceScaleId:'rsi',priceLineVisible:false,lastValueVisible:false})
          const rsiLo = chart.addSeries(LineSeries,{color:'rgba(52,211,153,0.35)',lineWidth:1,lineStyle:2,priceScaleId:'rsi',priceLineVisible:false,lastValueVisible:false})
          if (data.length>0) {
            rsiHi.setData([{time:data[0].time,value:70},{time:data[data.length-1].time,value:70}])
            rsiLo.setData([{time:data[0].time,value:30},{time:data[data.length-1].time,value:30}])
          }
          series.push(rsiHi,rsiLo)
        } else if (ind.kind==='MACD') {
          const ml = paneLayout as any
          const {macd, signal, hist} = calcMACD(chartData)
          const sm = chart.addSeries(LineSeries,{color:ind.color,lineWidth:2,priceScaleId:'macd',priceLineVisible:false,lastValueVisible:false})
          const ss = chart.addSeries(LineSeries,{color:'#f59e0b',lineWidth:1,priceScaleId:'macd',priceLineVisible:false,lastValueVisible:false})
          const sh = chart.addSeries(HistogramSeries,{priceScaleId:'macd',priceLineVisible:false,lastValueVisible:false})
          sm.setData(macd); ss.setData(signal); sh.setData(hist)
          chart.priceScale('macd').applyOptions({ scaleMargins: ml.macd ?? ml.MACD ?? {top:0.74,bottom:0.02} })
          series.push(sm,ss,sh)
        }
      } catch { /**/ }
      if (series.length>0) indRefs.current.set(ind.id, series)
    }
    setDrawVersion(n=>n+1)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndicators, chartData])

  // Range
  useEffect(() => {
    if (!chartRef.current) return
    if (range==='ALL') { chartRef.current.timeScale().fitContent(); return }
    const btn = RANGES.find(b=>b.label===range)!
    const from = new Date('2026-05-22')
    from.setDate(from.getDate() - btn.days)
    chartRef.current.timeScale().setVisibleRange({ from:from.toISOString().split('T')[0] as any, to:'2026-05-22' as any })
  }, [range])

  // Fullscreen resize
  useEffect(() => {
    if (!chartRef.current||!containerRef.current) return
    setTimeout(() => {
      if (chartRef.current&&containerRef.current) {
        chartRef.current.applyOptions({ width:containerRef.current.offsetWidth, height:containerRef.current.offsetHeight })
        chartRef.current.timeScale().fitContent()
        setDrawVersion(n=>n+1)
      }
    }, 60)
  }, [fullscreen])

  // Pane separator positions
  const oscIds = activeIndicators.filter(i=>i.type==='oscillator').map(i=>i.kind)
  const separators: number[] = []
  if (chartH>0) {
    const pl = paneLayout as any
    if (pl.vol) separators.push(chartH * pl.vol.top)
    oscIds.forEach(id => {
      const pname = id.toLowerCase()
      if (pl[pname]) separators.push(chartH * pl[pname].top)
    })
  }

  return (
    <div style={{ flex:1, position:'relative', minHeight:0, display:'flex', flexDirection:'column', background:'transparent' }}>
      <div ref={containerRef} style={{ flex:1, position:'relative', minHeight:0 }}>
        <DrawingOverlay
          chartApi={chartRef.current}
          drawings={drawingProps.drawings}
          onAdd={drawingProps.onAdd}
          activeTool={activeTool}
          activeColor={activeColor}
          version={drawVersion}
          height={chartH}
          lockMode={drawingProps.lockMode}
          hideMode={drawingProps.hideMode}
          textInput={drawingProps.textInput}
          onTextCommit={drawingProps.onTextCommit}
        />
        {/* Pane separators */}
        {separators.map((y,i) => (
          <div key={i} style={{ position:'absolute',left:0,right:0,top:y,height:1,background:'rgba(255,255,255,0.08)',pointerEvents:'none',zIndex:5 }}/>
        ))}
        {/* Pane labels */}
        {chartH>0 && oscIds.map(id => {
          const pl = paneLayout as any
          const pname = id.toLowerCase()
          const margins = pl[pname]
          if (!margins) return null
          const y = chartH * margins.top + 6
          return (
            <div key={id} style={{ position:'absolute',left:8,top:y,fontSize:9.5,fontWeight:700,color:T4,letterSpacing:'0.08em',pointerEvents:'none',zIndex:5,fontFamily:'Inter, system-ui' }}>
              {id.toUpperCase()}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Watchlist panel ───────────────────────────────────────────────────────────
function WatchlistPanel({ make, model, submodel, country, onSelect }: {
  make:string; model:string; submodel:string; country:string
  onSelect:(make:string,model:string,sub:string,country:string)=>void
}) {
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState<'watch'|'details'>('watch')

  const watchlistData = WATCHLIST_DEFAULT.map(w => {
    const data = generateData(w.brand, w.model, w.sub)
    const last = data.at(-1)!, prev = data.at(-2)!
    const delta = prev?.close ? ((last.close - prev.close) / prev.close * 100) : 0
    return { ...w, price: last.close, delta }
  })
  const filtered = watchlistData.filter(w =>
    `${w.brand} ${w.model} ${w.sub}`.toLowerCase().includes(query.toLowerCase())
  )

  const spec = VEHICLE_DATA[make]?.[model]?.[submodel]
  const data = React.useMemo(() => generateData(make, model, submodel), [make, model, submodel])
  const last = data.at(-1)!, prev = data.at(-2)!
  const deltaMain = prev?.close ? ((last.close - prev.close) / prev.close * 100) : 0
  const hi = Math.max(...data.slice(-30).map(d=>d.high))
  const lo = Math.min(...data.slice(-30).map(d=>d.low))
  const vol = data.slice(-5).reduce((s,d)=>s+d.volume,0)

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%', background:PANEL, backdropFilter:BLUR, WebkitBackdropFilter:BLUR, borderLeft:`1px solid ${BRD}`, width:280, flexShrink:0 }}>
      {/* Tabs */}
      <div style={{ display:'flex', borderBottom:`1px solid ${BRD}`, flexShrink:0 }}>
        {(['watch','details'] as const).map(t => (
          <button key={t} onClick={()=>setTab(t)} style={{ flex:1, padding:'10px 0', fontSize:11, fontWeight:600, cursor:'pointer', background:'transparent', border:'none', color:tab===t?T1:T4, borderBottom:tab===t?`2px solid ${UP}`:'2px solid transparent', transition:'all 140ms', fontFamily:'Inter, system-ui' }}>
            {t==='watch'?'Watchlist':'Details'}
          </button>
        ))}
      </div>

      {tab==='watch' ? (
        <>
          {/* Search */}
          <div style={{ padding:'8px 10px', flexShrink:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:7, padding:'6px 10px', background:GLASS, border:`1px solid ${BRD}`, borderRadius:8 }}>
              <Search style={{width:11,height:11,color:T4}}/>
              <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search..." style={{ flex:1, background:'transparent', border:'none', outline:'none', fontSize:11, color:T1, fontFamily:'Inter, system-ui' }}/>
            </div>
          </div>
          {/* Watchlist header */}
          <div style={{ display:'flex', padding:'4px 12px', borderBottom:`1px solid ${BRD}`, flexShrink:0 }}>
            <span style={{ flex:1, fontSize:8.5, fontWeight:700, color:T4, letterSpacing:'0.10em', textTransform:'uppercase' }}>Symbol</span>
            <span style={{ fontSize:8.5, fontWeight:700, color:T4, letterSpacing:'0.10em', textTransform:'uppercase', marginRight:8 }}>Price</span>
            <span style={{ fontSize:8.5, fontWeight:700, color:T4, letterSpacing:'0.10em', textTransform:'uppercase', width:44, textAlign:'right' }}>Chg%</span>
          </div>
          {/* Items */}
          <div style={{ flex:1, overflowY:'auto', padding:'4px 0' }}>
            {filtered.map((w, i) => {
              const up = w.delta >= 0
              const active = w.brand===make && w.model===model && w.sub===submodel
              return (
                <motion.div key={i} onClick={()=>onSelect(w.brand,w.model,w.sub,w.country)}
                  style={{ display:'flex',alignItems:'center',gap:8,padding:'7px 12px',cursor:'pointer', background:active?UP_DIM:'transparent', borderLeft:active?`2px solid ${UP}`:'2px solid transparent', transition:'background 110ms' }}
                  whileHover={{ backgroundColor:active?UP_DIM:'rgba(255,255,255,0.04)' }}>
                  <img src={`https://www.google.com/s2/favicons?domain=${BRAND_DOMAINS[w.brand]??w.brand.toLowerCase()+'.com'}&sz=64`} alt={w.brand} width={18} height={18} style={{objectFit:'contain',flexShrink:0}} onError={e=>{(e.target as HTMLImageElement).style.display='none'}}/>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize:11.5, fontWeight:active?700:500, color:active?UP:T1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{w.brand} {w.model}</div>
                    <div style={{ fontSize:9.5, color:T4, fontFamily:'JetBrains Mono, monospace', marginTop:1 }}>{w.sub} · {w.country}</div>
                  </div>
                  <div style={{ textAlign:'right', flexShrink:0 }}>
                    <div style={{ fontSize:11, fontWeight:600, color:T2, fontFamily:'JetBrains Mono, monospace' }}>€{Math.round(w.price).toLocaleString('de-DE')}</div>
                    <div style={{ fontSize:9.5, fontWeight:700, color:up?'#34d399':DN, fontFamily:'JetBrains Mono, monospace', marginTop:1 }}>{up?'+':''}{w.delta.toFixed(2)}%</div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </>
      ) : (
        <div style={{ flex:1, overflowY:'auto', padding:'14px 14px' }}>
          {/* Symbol header */}
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
            <img src={`https://www.google.com/s2/favicons?domain=${BRAND_DOMAINS[make]??make.toLowerCase()+'.com'}&sz=128`} alt={make} width={28} height={28} style={{objectFit:'contain'}} onError={e=>{(e.target as HTMLImageElement).style.display='none'}}/>
            <div>
              <div style={{ fontSize:13.5, fontWeight:700, color:T1 }}>{make} {model}</div>
              <div style={{ fontSize:10, color:T3 }}>{submodel} · {country}</div>
            </div>
          </div>
          {/* Price */}
          <div style={{ padding:'12px', background:GLASS, border:`1px solid ${BRD}`, borderRadius:12, marginBottom:10 }}>
            <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:24, fontWeight:700, color:T1, letterSpacing:'-0.02em' }}>€{Math.round(last.close).toLocaleString('de-DE')}</div>
            <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:11, color:deltaMain>=0?'#34d399':DN, fontWeight:700, marginTop:3 }}>{deltaMain>=0?'+':''}{deltaMain.toFixed(2)}% today</div>
          </div>
          {/* Stats */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:7, marginBottom:10 }}>
            {[
              ['Base Price', `€${spec?.basePrice.toLocaleString('de-DE')??'-'}`],
              ['Volatility', `${((spec?.vol??1)*100).toFixed(0)}%`],
              ['30d High', `€${Math.round(hi).toLocaleString('de-DE')}`],
              ['30d Low',  `€${Math.round(lo).toLocaleString('de-DE')}`],
              ['Vol 5d', `${Math.round(vol)}`],
              ['Spread', `€${Math.round((hi-lo)/2)}`],
            ].map(([k,v]) => (
              <div key={k} style={{ padding:'8px 10px', background:GLASS, border:`1px solid ${BRD}`, borderRadius:10 }}>
                <div style={{ fontSize:8.5, color:T4, marginBottom:3, fontWeight:600, letterSpacing:'0.06em', textTransform:'uppercase' }}>{k}</div>
                <div style={{ fontFamily:'JetBrains Mono, monospace', fontSize:12, fontWeight:700, color:T2 }}>{v}</div>
              </div>
            ))}
          </div>
          {/* Actions */}
          <button style={{ width:'100%', padding:'10px 0', borderRadius:10, background:'linear-gradient(135deg,rgba(124,58,237,0.85),rgba(37,99,235,0.85))', border:'1px solid rgba(124,58,237,0.40)', color:'#fff', fontSize:12, fontWeight:700, cursor:'pointer', fontFamily:'Inter, system-ui', display:'flex', alignItems:'center', justifyContent:'center', gap:6, boxShadow:'0 4px 18px rgba(124,58,237,0.25)', marginBottom:7 }}>
            <Star style={{width:13,height:13}}/> Add to Watchlist
          </button>
          <button style={{ width:'100%', padding:'9px 0', borderRadius:10, background:GLASS, border:`1px solid ${BRD}`, color:T2, fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:'Inter, system-ui', display:'flex', alignItems:'center', justifyContent:'center', gap:6 }}>
            <Bell style={{width:13,height:13}}/> Set Alert
          </button>
        </div>
      )}
    </div>
  )
}

// ── Symbol dropdown ───────────────────────────────────────────────────────────
function SymDropdown({ label, value, options, onChange }: { label:string; value:string; options:string[]; onChange:(v:string)=>void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e:MouseEvent) => { if (ref.current&&!ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown',h); return ()=>document.removeEventListener('mousedown',h)
  },[])
  return (
    <div ref={ref} style={{ position:'relative' }}>
      <button onClick={()=>setOpen(o=>!o)} style={{ display:'flex',alignItems:'center',gap:5,padding:'5px 9px',borderRadius:7,background:GLASS,border:`1px solid ${BRD}`,color:T1,fontSize:12,fontWeight:600,cursor:'pointer',fontFamily:'Inter, system-ui',transition:'all 130ms' }}>
        <span style={{ fontSize:8.5,color:T4,fontWeight:700,letterSpacing:'0.10em',textTransform:'uppercase' }}>{label}</span>
        <span>{value}</span>
        <motion.span animate={{rotate:open?180:0}} transition={{duration:0.14}}><ChevronDown style={{width:10,height:10,color:T4}}/></motion.span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{opacity:0,y:-5}} animate={{opacity:1,y:0}} exit={{opacity:0,y:-5}} transition={{duration:0.12}}
            style={{ position:'absolute',top:'calc(100% + 4px)',left:0,minWidth:140,zIndex:500,background:'rgba(10,10,22,0.98)',backdropFilter:'blur(28px)',border:`1px solid ${BRD}`,borderRadius:10,boxShadow:'0 16px 40px rgba(0,0,0,0.65)',overflow:'hidden',maxHeight:200,overflowY:'auto' }}>
            {options.map(opt=>(
              <div key={opt} onClick={()=>{onChange(opt);setOpen(false)}}
                style={{ padding:'8px 12px',fontSize:12,color:opt===value?UP:T2,fontFamily:'Inter, system-ui',cursor:'pointer',background:opt===value?UP_DIM:'transparent',transition:'background 100ms',fontWeight:opt===value?600:400 }}
                onMouseEnter={e=>{if(opt!==value)(e.currentTarget as HTMLDivElement).style.background='rgba(255,255,255,0.06)'}}
                onMouseLeave={e=>{if(opt!==value)(e.currentTarget as HTMLDivElement).style.background=opt===value?UP_DIM:'transparent'}}>
                {opt}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Live clock ────────────────────────────────────────────────────────────────
function LiveClock() {
  const [t, setT] = useState(new Date())
  useEffect(()=>{const id=setInterval(()=>setT(new Date()),1000);return()=>clearInterval(id)},[])
  return <span style={{fontFamily:'JetBrains Mono, monospace',fontSize:10,color:T4}}>{t.toLocaleTimeString('en-GB')}</span>
}

// ── Terminal (main export) ────────────────────────────────────────────────────
export default function Terminal() {
  // Symbol state
  const [make,     setMakeRaw]     = useState('BMW')
  const [model,    setModelRaw]    = useState('3 Series')
  const [submodel, setSubmodelRaw] = useState('320d')
  const [country,  setCountry]     = useState('DE')

  const models    = Object.keys(VEHICLE_DATA[make] ?? {})
  const submodels = Object.keys(VEHICLE_DATA[make]?.[model] ?? {})

  const setMake = useCallback((m:string) => {
    const mods = Object.keys(VEHICLE_DATA[m]??{}); const mod=mods[0]??''
    const subs = Object.keys(VEHICLE_DATA[m]?.[mod]??{}); const sub=subs[0]??''
    setMakeRaw(m); setModelRaw(mod); setSubmodelRaw(sub)
  },[])
  const setModel = useCallback((mod:string) => {
    const subs = Object.keys(VEHICLE_DATA[make]?.[mod]??{}); const sub=subs[0]??''
    setModelRaw(mod); setSubmodelRaw(sub)
  },[make])

  // Chart state
  const [range,     setRange]     = useState<RangeLabel>('1M')
  const [chartType, setChartType] = useState<ChartType>('candle')
  const [fullscreen,setFullscreen]= useState(false)

  // Drawing state
  const [activeTool,  setActiveTool]  = useState<DrawingTool>('cursor')
  const [activeColor, setActiveColor] = useState(UP)
  const [drawings,    setDrawings]    = useState<Drawing[]>([])
  const [magnetMode,  setMagnetMode]  = useState(false)
  const [lockMode,    setLockMode]    = useState(false)
  const [hideMode,    setHideMode]    = useState(false)
  const [textInput,   setTextInput]   = useState<{x:number;y:number}|null>(null)
  const drawVersion = drawings.length

  // Indicators
  const [activeIndicators, setActiveIndicators] = useState<IndicatorDef[]>([])
  const [showIndModal, setShowIndModal] = useState(false)

  // Crosshair legend
  const [crossData, setCrossData] = useState<CandlestickData|null>(null)

  // Chart height for overlay
  const [chartH, setChartH] = useState(400)

  // Keyboard shortcuts
  useEffect(() => {
    const h = (e:KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      const map: Record<string, DrawingTool> = {
        'v':'cursor','c':'crosshair','t':'trendline','r':'ray','e':'extended',
        'h':'hline','l':'vline','f':'fibonacci','g':'rectangle','b':'long_pos','n':'short_pos','x':'text',
      }
      if (map[e.key.toLowerCase()]) setActiveTool(map[e.key.toLowerCase()])
      if (e.key==='Escape') { setActiveTool('cursor'); setFullscreen(false) }
    }
    window.addEventListener('keydown',h); return ()=>window.removeEventListener('keydown',h)
  },[])

  const handleAddIndicator = useCallback((def: typeof INDICATOR_CATALOG[number]) => {
    if (activeIndicators.find(i=>i.kind===def.kind&&!['SMA','EMA','WMA'].includes(def.kind))) return
    const id = `${def.kind.toLowerCase()}_${Date.now()}`
    const cleanParams: Record<string, number> = {}
    for (const [k,v] of Object.entries(def.params)) { if (v !== undefined) cleanParams[k] = v as number }
    setActiveIndicators(prev => [...prev, { id, name:def.name, kind:def.kind, type:def.type, color:def.color, params:cleanParams }])
  }, [activeIndicators])

  const removeIndicator = useCallback((id:string) => {
    setActiveIndicators(prev => prev.filter(i=>i.id!==id))
  },[])

  const textCommit = useCallback((x:number, y:number, text:string) => {
    if (text.trim()) {
      // The drawing is added by TradingChart via onAdd, but for text we need coordinate info
      // We just add a pending drawing here
      setDrawings(prev => [...prev, { id:Date.now().toString(), type:'text', points:[{time:'2026-05-22',price:0}], color:activeColor, width:1, dash:'', text }])
    }
    setTextInput(null)
  },[activeColor])

  const onAddDrawing = useCallback((d:Drawing) => setDrawings(prev=>[...prev,d]),[])

  // Live price
  const chartData = React.useMemo(() => generateData(make, model, submodel), [make, model, submodel])
  const last = chartData.at(-1)!, prev = chartData.at(-2)!
  const pct = prev?.close ? ((last.close - prev.close) / prev.close * 100) : 0
  const spec = VEHICLE_DATA[make]?.[model]?.[submodel] ?? {basePrice:20000,vol:1}
  const disp = crossData ?? { open:last.open, high:last.high, low:last.low, close:last.close }
  const dispUp = disp.close >= disp.open

  const CHART_TYPES: {id:ChartType; label:string; icon:string}[] = [
    {id:'candle',label:'Candles',icon:'🕯'},
    {id:'bar',   label:'Bars',   icon:'|'},
    {id:'line',  label:'Line',   icon:'📈'},
    {id:'area',  label:'Area',   icon:'▨'},
  ]

  return (
    <div style={{
      height: 'calc(100vh - 60px)',
      overflow:'hidden',
      display:'flex',
      flexDirection:'column',
      background:'transparent',
      fontFamily:'Inter, system-ui, sans-serif',
      position: fullscreen ? 'fixed' : 'relative',
      inset: fullscreen ? 0 : 'auto',
      zIndex: fullscreen ? 9999 : 'auto',
    }}>

      {/* ── Top bar ── */}
      <div style={{ height:48, flexShrink:0, display:'flex', alignItems:'center', gap:8, padding:'0 12px', background:BG, backdropFilter:BLUR, WebkitBackdropFilter:BLUR, borderBottom:`1px solid ${BRD}` }}>

        {/* Symbol selector */}
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <SymDropdown label="Brand" value={make}     options={ALL_MAKES}   onChange={setMake}  />
          <ChevronRight style={{width:10,height:10,color:T4,flexShrink:0}}/>
          <SymDropdown label="Model" value={model}    options={models}      onChange={setModel} />
          <ChevronRight style={{width:10,height:10,color:T4,flexShrink:0}}/>
          <SymDropdown label="Var"   value={submodel} options={submodels}   onChange={setSubmodelRaw} />
        </div>

        {/* Country */}
        <div style={{ display:'flex', gap:3 }}>
          {COUNTRIES.slice(1).map(c => (
            <button key={c.code} onClick={()=>setCountry(c.code)} title={c.name}
              style={{ padding:'3px 7px', borderRadius:6, fontSize:10.5, fontWeight:600, cursor:'pointer', fontFamily:'Inter, system-ui', background:country===c.code?UP_DIM:GLASS, border:country===c.code?'1px solid rgba(124,58,237,0.40)':`1px solid ${BRD}`, color:country===c.code?UP:T3, transition:'all 120ms' }}>
              {c.flag} {c.code}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div style={{width:1,height:20,background:BRD,flexShrink:0}}/>

        {/* Price + delta */}
        <div style={{ display:'flex', alignItems:'baseline', gap:6 }}>
          <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:15, fontWeight:700, color:T1 }}>€{Math.round(last.close).toLocaleString('de-DE')}</span>
          <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:10.5, fontWeight:700, color:pct>=0?'#34d399':DN }}>{pct>=0?'+':''}{pct.toFixed(2)}%</span>
        </div>

        {/* OHLCV legend */}
        <div style={{ display:'flex', gap:10, fontFamily:'JetBrains Mono, monospace', fontSize:9.5 }}>
          {([['O',disp.open],['H',disp.high],['L',disp.low],['C',disp.close]] as [string,number][]).map(([k,v])=>(
            <span key={k}><span style={{color:T4}}>{k} </span><span style={{color:k==='C'?(dispUp?UP:DN):T2,fontWeight:k==='C'?700:400}}>{Math.round(v).toLocaleString('de-DE')}</span></span>
          ))}
        </div>

        {/* Push right */}
        <div style={{ flex:1 }}/>

        {/* Chart types */}
        <div style={{ display:'flex', gap:2, padding:2, background:GLASS, borderRadius:8, border:`1px solid ${BRD}` }}>
          {CHART_TYPES.map(ct => (
            <button key={ct.id} onClick={()=>setChartType(ct.id)} title={ct.label}
              style={{ padding:'3px 8px', borderRadius:6, fontSize:10.5, cursor:'pointer', fontFamily:'Inter, system-ui', border:'none', background:chartType===ct.id?UP_DIM:'transparent', color:chartType===ct.id?UP:T4, transition:'all 130ms' }}>
              {ct.icon}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div style={{width:1,height:20,background:BRD,flexShrink:0}}/>

        {/* Timeframe */}
        <div style={{ display:'flex', gap:2 }}>
          {RANGES.map(btn=>(
            <button key={btn.label} onClick={()=>setRange(btn.label)}
              style={{ padding:'3px 7px', borderRadius:6, fontSize:9.5, fontWeight:700, cursor:'pointer', fontFamily:'Inter, system-ui', background:range===btn.label?UP_DIM:'transparent', border:range===btn.label?'1px solid rgba(124,58,237,0.32)':'1px solid transparent', color:range===btn.label?UP:T4, transition:'all 130ms' }}>
              {btn.label}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div style={{width:1,height:20,background:BRD,flexShrink:0}}/>

        {/* Indicators button */}
        <button onClick={()=>setShowIndModal(true)}
          style={{ display:'flex',alignItems:'center',gap:5,padding:'5px 10px',borderRadius:8,background:GLASS,border:`1px solid ${BRD}`,color:T2,fontSize:11,fontWeight:600,cursor:'pointer',fontFamily:'Inter, system-ui',transition:'all 130ms' }}
          onMouseEnter={e=>{(e.currentTarget as HTMLButtonElement).style.background=UP_DIM;(e.currentTarget as HTMLButtonElement).style.borderColor='rgba(124,58,237,0.40)';(e.currentTarget as HTMLButtonElement).style.color=UP}}
          onMouseLeave={e=>{(e.currentTarget as HTMLButtonElement).style.background=GLASS;(e.currentTarget as HTMLButtonElement).style.borderColor=BRD;(e.currentTarget as HTMLButtonElement).style.color=T2}}>
          <BarChart2 style={{width:12,height:12}}/> Indicators
          {activeIndicators.length>0 && <span style={{background:ACCENT,color:'#fff',fontSize:9,fontWeight:700,padding:'0px 5px',borderRadius:99,minWidth:14,textAlign:'center'}}>{activeIndicators.length}</span>}
        </button>

        {/* Alert */}
        <button title="Create alert"
          style={{ width:30,height:30,borderRadius:8,display:'flex',alignItems:'center',justifyContent:'center',background:GLASS,border:`1px solid ${BRD}`,color:T3,cursor:'pointer' }}>
          <Bell style={{width:12,height:12}}/>
        </button>

        {/* Screenshot */}
        <button title="Screenshot" onClick={()=>alert('Screenshot: connect html2canvas to capture the chart area')}
          style={{ width:30,height:30,borderRadius:8,display:'flex',alignItems:'center',justifyContent:'center',background:GLASS,border:`1px solid ${BRD}`,color:T3,cursor:'pointer' }}>
          <Camera style={{width:12,height:12}}/>
        </button>

        {/* Fullscreen */}
        <button onClick={()=>setFullscreen(f=>!f)} title={fullscreen?'Exit fullscreen (Esc)':'Fullscreen'}
          style={{ width:30,height:30,borderRadius:8,display:'flex',alignItems:'center',justifyContent:'center',background:fullscreen?UP_DIM:GLASS,border:fullscreen?'1px solid rgba(124,58,237,0.40)':`1px solid ${BRD}`,color:fullscreen?UP:T3,cursor:'pointer' }}>
          {fullscreen?<Minimize2 style={{width:12,height:12}}/>:<Maximize2 style={{width:12,height:12}}/>}
        </button>

        {/* Live */}
        <div style={{ display:'flex',alignItems:'center',gap:5,marginLeft:2 }}>
          <motion.div style={{width:5,height:5,borderRadius:'50%',background:'#22c55e'}} animate={{opacity:[1,0.3,1]}} transition={{duration:1.4,repeat:Infinity}}/>
          <LiveClock/>
        </div>
      </div>

      {/* ── Active indicator chips ── */}
      <AnimatePresence>
        {activeIndicators.length > 0 && (
          <motion.div initial={{height:0,opacity:0}} animate={{height:'auto',opacity:1}} exit={{height:0,opacity:0}} transition={{duration:0.18}}
            style={{ flexShrink:0, display:'flex', alignItems:'center', gap:6, padding:'4px 12px', background:BG, borderBottom:`1px solid ${BRD}`, overflow:'hidden', flexWrap:'wrap' }}>
            {activeIndicators.map(ind => (
              <motion.div key={ind.id} initial={{scale:0.85,opacity:0}} animate={{scale:1,opacity:1}} exit={{scale:0.85,opacity:0}} transition={{duration:0.15}}
                style={{ display:'flex',alignItems:'center',gap:5,padding:'3px 8px',background:GLASS,border:`1px solid ${BRD}`,borderRadius:99,cursor:'default' }}>
                <div style={{width:6,height:6,borderRadius:'50%',background:ind.color,boxShadow:`0 0 4px ${ind.color}88`}}/>
                <span style={{fontSize:10,fontWeight:600,color:T2,fontFamily:'Inter, system-ui'}}>{ind.name}</span>
                <button onClick={()=>removeIndicator(ind.id)} style={{width:14,height:14,borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',background:'rgba(255,255,255,0.08)',border:'none',cursor:'pointer',color:T4}}>
                  <X style={{width:8,height:8}}/>
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Body ── */}
      <div style={{ flex:1, display:'flex', minHeight:0, overflow:'hidden', position:'relative' }}>

        {/* Drawing toolbar */}
        <DrawingToolbar
          activeTool={activeTool} onToolSelect={setActiveTool}
          activeColor={activeColor} onColorChange={setActiveColor}
          drawings={drawings} onClear={()=>setDrawings([])}
          magnetMode={magnetMode} onMagnetToggle={()=>setMagnetMode(m=>!m)}
          lockMode={lockMode} onLockToggle={()=>setLockMode(l=>!l)}
          hideMode={hideMode} onHideToggle={()=>setHideMode(h=>!h)}
        />

        {/* Main chart area */}
        <div style={{ flex:1, display:'flex', flexDirection:'column', minWidth:0, overflow:'hidden' }}>
          <TradingChart
            make={make} model={model} submodel={submodel} country={country}
            range={range} chartType={chartType} activeIndicators={activeIndicators}
            activeTool={activeTool} activeColor={activeColor}
            onCrossMove={setCrossData}
            fullscreen={fullscreen} setFullscreen={setFullscreen}
            onDrawingOverlay={setChartH}
            drawingProps={{ drawings, onAdd:onAddDrawing, version:drawVersion, lockMode, hideMode, textInput, onTextCommit:textCommit }}
          />
        </div>

        {/* Watchlist */}
        <WatchlistPanel
          make={make} model={model} submodel={submodel} country={country}
          onSelect={(b,m,s,c)=>{setMakeRaw(b);setModelRaw(m);setSubmodelRaw(s);setCountry(c)}}
        />
      </div>

      {/* ── Status bar ── */}
      <div style={{ height:26, flexShrink:0, display:'flex', alignItems:'center', gap:16, padding:'0 12px', background:BG, backdropFilter:BLUR, WebkitBackdropFilter:BLUR, borderTop:`1px solid ${BRD}` }}>
        <span style={{ fontSize:9.5, fontWeight:700, color:T4, letterSpacing:'0.08em', textTransform:'uppercase', fontFamily:'Inter, system-ui' }}>{make} {model} · {submodel}</span>
        <div style={{width:1,height:12,background:BRD}}/>
        <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:9.5, color:T4 }}>
          O <span style={{color:T2}}>{Math.round(disp.open).toLocaleString('de-DE')}</span>&nbsp;
          H <span style={{color:'#34d399'}}>{Math.round(disp.high).toLocaleString('de-DE')}</span>&nbsp;
          L <span style={{color:DN}}>{Math.round(disp.low).toLocaleString('de-DE')}</span>&nbsp;
          C <span style={{color:dispUp?UP:DN,fontWeight:700}}>{Math.round(disp.close).toLocaleString('de-DE')}</span>
        </span>
        <div style={{width:1,height:12,background:BRD}}/>
        <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:9.5, color:pct>=0?'#34d399':DN }}>{pct>=0?'+':''}{pct.toFixed(2)}%</span>
        <div style={{flex:1}}/>
        <span style={{ fontSize:9.5, color:T4, fontFamily:'Inter, system-ui' }}>{activeTool==='cursor'?'← Select tool':'Drawing: '+activeTool.replace('_',' ')}</span>
        {magnetMode && <span style={{ fontSize:9, color:'#a78bfa', fontWeight:600 }}>● MAGNET</span>}
        {lockMode   && <span style={{ fontSize:9, color:'#f59e0b', fontWeight:600 }}>● LOCKED</span>}
        {activeIndicators.length > 0 && (
          <span style={{ fontSize:9, color:T4 }}>{activeIndicators.map(i=>i.name).join(' · ')}</span>
        )}
        <span style={{ fontFamily:'JetBrains Mono, monospace', fontSize:9, color:T4 }}>CARDEX TERMINAL v2.0</span>
      </div>

      {/* ── Text input overlay ── */}
      <AnimatePresence>
        {textInput && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:0.12}}
            style={{ position:'absolute', top:textInput.y, left:textInput.x+44, zIndex:9999 }}>
            <input autoFocus defaultValue="" onKeyDown={e=>{ if(e.key==='Enter') textCommit(textInput.x,textInput.y,(e.target as HTMLInputElement).value); if(e.key==='Escape') setTextInput(null) }}
              onBlur={e=>textCommit(textInput.x,textInput.y,e.target.value)}
              style={{ background:'rgba(10,10,22,0.95)', border:`1px solid ${UP}`, borderRadius:5, padding:'3px 7px', color:activeColor, fontSize:13, fontFamily:'Inter, system-ui', outline:'none', width:160, boxShadow:`0 0 10px ${UP}44` }}
              placeholder="Type label…"
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Indicator modal ── */}
      <AnimatePresence>
        {showIndModal && <IndicatorModal onAdd={handleAddIndicator} onClose={()=>setShowIndModal(false)}/>}
      </AnimatePresence>

      {/* ── Drawing mode hint ── */}
      <AnimatePresence>
        {!['cursor','crosshair'].includes(activeTool) && !lockMode && (
          <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} exit={{opacity:0,y:8}} transition={{duration:0.15}}
            style={{ position:'absolute', bottom:30, left:'50%', transform:'translateX(-50%)', background:'rgba(10,10,22,0.92)', backdropFilter:'blur(16px)', border:`1px solid ${BRD}`, borderRadius:99, padding:'5px 14px', fontSize:10, color:activeColor, fontWeight:600, fontFamily:'Inter, system-ui', whiteSpace:'nowrap', zIndex:50, boxShadow:'0 4px 16px rgba(0,0,0,0.5)' }}>
            {['hline','hray','vline','crossline','arrow_up','arrow_down'].includes(activeTool) ? 'Click to place' : 'Click first point, then second point'}
            <span style={{ color:T4, marginLeft:10 }}>· Esc to cancel</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
