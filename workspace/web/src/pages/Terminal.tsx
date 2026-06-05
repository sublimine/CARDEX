/*
 * CARDEX Terminal — institutional EU used-vehicle market intelligence terminal.
 * TradingView-grade charting (lightweight-charts), theme-reactive, with neutral chrome
 * (the brand mesh is suppressed on this route — pure dark/white per theme, no violet),
 * the full 95-tool drawing engine (drawings.tsx + tools.ts), 53 working indicators
 * (indicators.ts), cross-border NLC arbitrage, supply depth and the SDI decision desk.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown, Maximize2, Minimize2, BarChart2, GitCompareArrows, Search, X,
  MousePointer2, TrendingUp, GitBranch, Activity, Square, Type, ArrowUpRight, Ruler,
  ZoomIn, ZoomOut, Magnet, Lock, Eye, EyeOff, Trash2, Star, Triangle,
  CandlestickChart, LineChart, AreaChart,
} from 'lucide-react'
import type { CandlestickData } from 'lightweight-charts'

import { useTheme, MONO, SANS, getBlurLg, EASE, EASE_ARR } from './terminal/theme'
import { GlassFilterDefs } from './terminal/glass'
import { INSTRUMENTS, MARKETS, MARKET_BY_CODE, priceSeries, quote, fmtPrice, type Instrument } from './terminal/market'
import { INDICATOR_CATALOG, type IndicatorDef } from './terminal/indicators'
import { TOOL_GROUPS, TOOL_BY_ID, ALL_TOOLS, requiredClicks, isDrawable, type DrawTool } from './terminal/tools'
import { MarketChart, type ChartType, type RangeLabel, type ActiveIndicator } from './terminal/MarketChart'
import type { Drawing } from './terminal/drawings'
import { GlassPanel, PanelTitle, Eyebrow, Title, IconButton, Segmented, Pill } from './terminal/ui'
import { Watchlist } from './terminal/Watchlist'
import { DepthLadder } from './terminal/Depth'
import { ArbitrageScanner, ArbitrageScreener } from './terminal/Arbitrage'
import { IntelRail } from './terminal/Intel'

type View = 'chart' | 'depth' | 'arbitrage' | 'screener'

// Neutral-led drawing palette. Default is the terminal's cyan accent (subtle neon);
// no violet/fuchsia — the terminal stays pure dark/white per theme.
const DRAW_COLORS = ['#22d3ee', '#e5e7eb', '#26c281', '#fb6f78', '#fbbf24', '#60a5fa', '#94a3b8']
const RANGES: RangeLabel[] = ['1M', '3M', '6M', '1Y', 'ALL']

// Tool groups shown as flyouts in the rail (toggles/zoom rendered as dedicated actions)
const RAIL_GROUPS = TOOL_GROUPS.filter(g => g.id !== 'toggles' && g.id !== 'zoom')
const DEFAULT_GROUP_TOOL: Record<string, string> = {
  cursors: 'cross', trend_lines: 'trend_line', gann_fibonacci: 'fib_retracement', patterns: 'xabcd_pattern',
  projection: 'long_position', brushes: 'brush', arrows: 'arrow', shapes: 'rectangle',
  text_notes: 'text', patterns_emojis_icons: 'icon', measure: 'measure',
}
function groupIcon(id: string): React.ReactNode {
  const s = { width: 15, height: 15 }
  switch (id) {
    case 'cursors': return <MousePointer2 style={s} />
    case 'trend_lines': return <TrendingUp style={s} />
    case 'gann_fibonacci': return <span style={{ fontFamily: MONO, fontWeight: 800, fontSize: 13 }}>φ</span>
    case 'patterns': return <Activity style={s} />
    case 'projection': return <ArrowUpRight style={s} />
    case 'brushes': return <span style={{ fontSize: 13 }}>✎</span>
    case 'arrows': return <ArrowUpRight style={s} />
    case 'shapes': return <Square style={s} />
    case 'text_notes': return <Type style={s} />
    case 'patterns_emojis_icons': return <Star style={s} />
    case 'measure': return <Ruler style={s} />
    default: return <Triangle style={s} />
  }
}

// ── Click-outside popover ─────────────────────────────────────────────────────
function Popover({ open, onClose, children, anchor }: { open: boolean; onClose: () => void; children: React.ReactNode; anchor: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open, onClose])
  return <div ref={ref} style={{ position: 'relative' }}>{anchor}{children}</div>
}

export default function Terminal() {
  const p = useTheme()

  // Neutralise the global brand mesh while on the terminal so the translucent
  // workspace chrome (sidebar/topbar) reads as pure dark/white — no violet bleed.
  // Scoped to this route: the class is removed on unmount, other pages keep the mesh.
  useEffect(() => {
    document.body.classList.add('on-terminal')
    return () => document.body.classList.remove('on-terminal')
  }, [])

  const menuBg: React.CSSProperties = {
    background: p.panelHi, backdropFilter: getBlurLg(p), WebkitBackdropFilter: getBlurLg(p),
    border: `1px solid ${p.borderHi}`, boxShadow: p.shadowLg,
  }

  const [inst, setInst] = useState<Instrument>(INSTRUMENTS[0])
  const [market, setMarket] = useState('DE')
  const [view, setView] = useState<View>('chart')
  const [range, setRange] = useState<RangeLabel>('3M')
  const [chartType, setChartType] = useState<ChartType>('candle')
  const [indicators, setIndicators] = useState<ActiveIndicator[]>(
    () => { const d = INDICATOR_CATALOG.find(i => i.id === 'ema'); return d ? [{ uid: 'ema_1', def: d, params: Object.fromEntries(d.inputs.map(x => [x.name, x.default])) }] : [] },
  )
  const [compare, setCompare] = useState<string[]>([])
  const [tool, setTool] = useState<DrawTool>('cross')
  const [groupTool, setGroupTool] = useState<Record<string, string>>(DEFAULT_GROUP_TOOL)
  const [color, setColor] = useState(DRAW_COLORS[0])
  const [drawings, setDrawings] = useState<Drawing[]>([])
  const [hideDrawings, setHideDrawings] = useState(false)
  const [lockDrawings, setLockDrawings] = useState(false)
  const [magnet, setMagnet] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [cross, setCross] = useState<CandlestickData | null>(null)
  const [flyout, setFlyout] = useState<string | null>(null)
  const [indMenu, setIndMenu] = useState(false)
  const [indQuery, setIndQuery] = useState('')
  const [cmpMenu, setCmpMenu] = useState(false)
  const [instMenu, setInstMenu] = useState(false)
  const [showColors, setShowColors] = useState(false)
  const [deskOpen, setDeskOpen] = useState(true)   // Decision Desk dock (below chart) expanded/collapsed
  // Rail flyout/color render in a portal (document.body) with fixed coords captured from the
  // clicked control — escapes the rail's overflow clip and the glass backdrop-filter containing-block.
  const [flyoutPos, setFlyoutPos] = useState<{ x: number; y: number } | null>(null)
  const [colorPos, setColorPos] = useState<{ x: number; y: number } | null>(null)

  // ── DEV-only test bridge ──────────────────────────────────────────────────
  // Exposes tool selection + committed drawings so the automated per-tool draw
  // audit (Playwright) can drive every tool through its real click path and
  // assert non-degenerate geometry. Tree-shaken out of production builds.
  const drawingsRef = useRef(drawings); drawingsRef.current = drawings
  useEffect(() => {
    if (!(import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV) return
    ;(window as unknown as { __term?: unknown }).__term = {
      setTool,
      clear: () => setDrawings([]),
      get: () => drawingsRef.current,
      tools: ALL_TOOLS.map(t => ({ id: t.id, geometry: t.geometry, clicks: requiredClicks(t), drawable: isDrawable(t.geometry) || t.clicks > 0 })),
    }
  }, [])

  const data = useMemo(() => priceSeries(inst, market, 60), [inst, market])
  const last = data.at(-1)!, prev = data.at(-2)!
  const pct = prev?.close ? ((last.close - prev.close) / prev.close) * 100 : 0
  const disp = (cross ?? { open: last.open, high: last.high, low: last.low, close: last.close }) as { open: number; high: number; low: number; close: number }
  const dispUp = disp.close >= disp.open
  const mkt = MARKET_BY_CODE[market]

  // Cross-border price strip: the selected instrument quoted in every market (arbitrage core).
  const marketRows = useMemo(() => MARKETS.map(m => ({ m, q: quote(inst, m.code) })), [inst])
  const bestBuyCode = useMemo(
    () => marketRows.reduce((a, b) => (b.q.last < a.q.last ? b : a), marketRows[0]).m.code,
    [marketRows],
  )

  // Keyboard shortcuts
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      const map: Record<string, DrawTool> = { v: 'cross', c: 'cross_line', t: 'trend_line', h: 'horizontal_line', r: 'rectangle', f: 'fib_retracement', m: 'measure', b: 'long_position' }
      const t = map[e.key.toLowerCase()]; if (t) setTool(t)
      if (e.key === 'Escape') { setTool('cross'); setFullscreen(false); setFlyout(null) }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [])

  // Close rail flyout / color popover on any click outside the portal or the trigger
  useEffect(() => {
    if (!flyout && !showColors) return
    const h = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (t.closest && (t.closest('[data-rail-pop]') || t.closest('[data-rail-arrow]'))) return
      setFlyout(null); setShowColors(false)
    }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [flyout, showColors])

  const studiesGrouped = useMemo(() => {
    const q = indQuery.toLowerCase()
    const cats = new Map<string, IndicatorDef[]>()
    for (const d of INDICATOR_CATALOG) {
      if (q && !d.name.toLowerCase().includes(q) && !d.id.includes(q)) continue
      if (!cats.has(d.category)) cats.set(d.category, [])
      cats.get(d.category)!.push(d)
    }
    return [...cats.entries()]
  }, [indQuery])

  const toggleIndicator = useCallback((def: IndicatorDef) => {
    setIndicators(prev => {
      if (prev.some(i => i.def.id === def.id)) return prev.filter(i => i.def.id !== def.id)
      const uid = `${def.id}_${prev.length + 1}_${def.inputs.map(x => x.default).join('')}`
      return [...prev, { uid, def, params: Object.fromEntries(def.inputs.map(x => [x.name, x.default])) }]
    })
  }, [])
  const removeIndicator = useCallback((uid: string) => setIndicators(prev => prev.filter(i => i.uid !== uid)), [])
  const toggleCompare = useCallback((code: string) => setCompare(prev => prev.includes(code) ? prev.filter(c => c !== code) : prev.length >= 3 ? prev : [...prev, code]), [])
  const addDrawing = useCallback((d: Drawing) => setDrawings(prev => [...prev, d]), [])
  const updateDrawing = useCallback((id: string, pts: Drawing['pts']) => setDrawings(prev => prev.map(d => d.id === id ? { ...d, pts } : d)), [])
  const deleteDrawing = useCallback((id: string) => setDrawings(prev => prev.filter(d => d.id !== id)), [])
  const pickTool = useCallback((groupId: string, toolId: string) => { setGroupTool(g => ({ ...g, [groupId]: toolId })); setTool(toolId); setFlyout(null) }, [])

  return (
    <div style={{
      minHeight: 'calc(100vh - 60px)', height: fullscreen ? '100vh' : undefined,
      overflow: fullscreen ? 'hidden' : 'visible', display: 'flex', flexDirection: 'column',
      background: p.bg, fontFamily: SANS, padding: 10, gap: 10,
      position: fullscreen ? 'fixed' : 'relative', inset: fullscreen ? 0 : 'auto', zIndex: fullscreen ? 9999 : 'auto',
    }}>
      <GlassFilterDefs />

      {/* ════ HEADER ════ */}
      {/* zIndex lifts the header's stacking context (backdrop-filter creates one) above the
          body panels so its popovers/flyouts paint over them instead of behind. */}
      <GlassPanel p={p} radius={14} style={{ flexShrink: 0, overflow: 'visible', zIndex: 60 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 12px', height: 52 }}>
          {/* Instrument selector */}
          <Popover open={instMenu} onClose={() => setInstMenu(false)}
            anchor={
              <button onClick={() => setInstMenu(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '6px 10px', borderRadius: 10, cursor: 'pointer', background: p.glass, border: `1px solid ${p.border}` }}>
                <LogoImg inst={inst} p={p} size={20} />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 12.5, fontWeight: 800, color: p.t1, letterSpacing: '-0.01em', lineHeight: 1.1 }}>{inst.make} {inst.model}</div>
                  <div style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{inst.variant}</div>
                </div>
                <ChevronDown style={{ width: 12, height: 12, color: p.t4 }} />
              </button>
            }>
            <AnimatePresence>
              {instMenu && (
                <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.14 }}
                  style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, width: 300, maxHeight: 400, overflowY: 'auto', zIndex: 600, borderRadius: 14, padding: 6, ...menuBg }}>
                  {INSTRUMENTS.map(it => {
                    const on = it.id === inst.id
                    return (
                      <button key={it.id} onClick={() => { setInst(it); setInstMenu(false) }}
                        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, padding: '8px 9px', borderRadius: 9, cursor: 'pointer', border: 'none', background: on ? p.accentDim : 'transparent', textAlign: 'left' }}
                        onMouseEnter={e => { if (!on) e.currentTarget.style.background = p.glass }} onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                        <LogoImg inst={it} p={p} size={18} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 11.5, fontWeight: on ? 700 : 600, color: on ? p.accentText : p.t1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.make} {it.model}</div>
                          <div style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{it.variant}</div>
                        </div>
                      </button>
                    )
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </Popover>

          {/* Market readout removed from header — it's redundant with the Markets cross-border
              panel and the footer status bar (less chrome, calmer header). */}
          <div style={{ width: 1, height: 24, background: p.border, flexShrink: 0 }} />
          {/* Hero price + a single calm delta cluster (no pill chrome) */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
            <span style={{ fontFamily: MONO, fontSize: 21, fontWeight: 700, color: p.t1, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', lineHeight: 1 }}>{fmtPrice(last.close)}</span>
            <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, fontFamily: MONO, fontVariantNumeric: 'tabular-nums', color: pct >= 0 ? p.up : p.down }}>
              <span style={{ fontSize: 12, fontWeight: 700 }}>{pct >= 0 ? '▲' : '▼'} {pct >= 0 ? '+' : '−'}{Math.abs(pct).toFixed(2)}%</span>
              <span style={{ fontSize: 10.5, fontWeight: 600, opacity: 0.65 }}>{pct >= 0 ? '+' : '−'}€{fmtPrice(Math.abs(last.close - prev.close)).slice(1)}</span>
            </span>
          </div>
          <div style={{ flex: 1 }} />

          <Segmented<View> p={p} value={view} onChange={setView} options={[
            { id: 'chart', label: 'Chart' }, { id: 'depth', label: 'Depth' }, { id: 'arbitrage', label: 'Arbitrage' }, { id: 'screener', label: 'Screener' },
          ]} />

          {view === 'chart' && (
            <>
              <Segmented<ChartType> p={p} value={chartType} onChange={setChartType} size="xs" options={[
                { id: 'candle', label: <CandlestickChart style={{ width: 13, height: 13, display: 'block' }} />, title: 'Candles' },
                { id: 'line', label: <LineChart style={{ width: 13, height: 13, display: 'block' }} />, title: 'Line' },
                { id: 'area', label: <AreaChart style={{ width: 13, height: 13, display: 'block' }} />, title: 'Area' },
              ]} />
              <Segmented<RangeLabel> p={p} value={range} onChange={setRange} size="xs" options={RANGES.map(r => ({ id: r, label: r }))} />

              {/* Studies */}
              <Popover open={indMenu} onClose={() => setIndMenu(false)}
                anchor={
                  <button onClick={() => setIndMenu(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 10px', borderRadius: 9, cursor: 'pointer', background: p.glass, border: `1px solid ${p.border}`, color: p.t2, fontSize: 11, fontWeight: 600, fontFamily: SANS }}>
                    <BarChart2 style={{ width: 12, height: 12 }} /> Studies
                    {indicators.length > 0 && <span style={{ background: p.accent, color: '#fff', fontSize: 9, fontWeight: 700, padding: '0 5px', borderRadius: 99, minWidth: 14, textAlign: 'center' }}>{indicators.length}</span>}
                  </button>
                }>
                <AnimatePresence>
                  {indMenu && (
                    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.14 }}
                      style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, width: 270, maxHeight: 460, display: 'flex', flexDirection: 'column', zIndex: 600, borderRadius: 14, ...menuBg }}>
                      <div style={{ padding: 8, borderBottom: `1px solid ${p.hairline}` }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '6px 9px', background: p.inset, border: `1px solid ${p.border}`, borderRadius: 8 }}>
                          <Search style={{ width: 12, height: 12, color: p.t4 }} />
                          <input value={indQuery} onChange={e => setIndQuery(e.target.value)} placeholder="Search 53 studies…" autoFocus
                            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 11.5, color: p.t1, fontFamily: SANS }} />
                        </div>
                      </div>
                      <div style={{ flex: 1, overflowY: 'auto', padding: 6 }}>
                        {studiesGrouped.map(([cat, defs]) => (
                          <div key={cat} style={{ marginBottom: 4 }}>
                            <Eyebrow p={p} style={{ display: 'block', padding: '6px 8px 3px' }}>{cat}</Eyebrow>
                            {defs.map(def => {
                              const on = indicators.some(i => i.def.id === def.id)
                              return (
                                <button key={def.id} onClick={() => toggleIndicator(def)}
                                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, padding: '6px 9px', borderRadius: 8, cursor: 'pointer', border: 'none', background: on ? p.accentDim : 'transparent', textAlign: 'left' }}
                                  onMouseEnter={e => { if (!on) e.currentTarget.style.background = p.glass }} onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: on ? p.accent : p.t4 }} />
                                  <span style={{ flex: 1, fontSize: 11.5, fontWeight: on ? 700 : 500, color: on ? p.accentText : p.t2 }}>{def.name}</span>
                                  <span style={{ fontSize: 8.5, color: p.t4, fontFamily: MONO }}>{def.pane === 'overlay' ? 'OVL' : 'OSC'}</span>
                                </button>
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </Popover>

              {/* Compare */}
              <Popover open={cmpMenu} onClose={() => setCmpMenu(false)}
                anchor={
                  <button onClick={() => setCmpMenu(o => !o)} title="Cross-border overlay" style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '6px 10px', borderRadius: 9, cursor: 'pointer', background: compare.length ? p.accentDim : p.glass, border: `1px solid ${compare.length ? p.accent + '55' : p.border}`, color: compare.length ? p.accentText : p.t2, fontSize: 11, fontWeight: 600, fontFamily: SANS }}>
                    <GitCompareArrows style={{ width: 12, height: 12 }} /> Compare{compare.length > 0 && <span style={{ background: p.accent, color: '#fff', fontSize: 9, fontWeight: 700, padding: '0 5px', borderRadius: 99 }}>{compare.length}</span>}
                  </button>
                }>
                <AnimatePresence>
                  {cmpMenu && (
                    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.14 }}
                      style={{ position: 'absolute', top: 'calc(100% + 6px)', right: 0, width: 200, zIndex: 600, borderRadius: 14, padding: 6, ...menuBg }}>
                      <Eyebrow p={p} style={{ display: 'block', padding: '6px 8px' }}>Overlay markets · max 3</Eyebrow>
                      {MARKETS.filter(m => m.code !== market).map(m => {
                        const on = compare.includes(m.code)
                        return (
                          <button key={m.code} onClick={() => toggleCompare(m.code)}
                            style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, padding: '8px 9px', borderRadius: 9, cursor: 'pointer', border: 'none', background: on ? p.accentDim : 'transparent', textAlign: 'left' }}
                            onMouseEnter={e => { if (!on) e.currentTarget.style.background = p.glass }} onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                            <span style={{ flex: 1, fontSize: 11.5, fontWeight: on ? 700 : 500, color: on ? p.accentText : p.t2 }}>{m.flag} {m.name}</span>
                            {on && <span style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>ON</span>}
                          </button>
                        )
                      })}
                    </motion.div>
                  )}
                </AnimatePresence>
              </Popover>
            </>
          )}

          <IconButton p={p} active={fullscreen} onClick={() => setFullscreen(f => !f)} title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            {fullscreen ? <Minimize2 style={{ width: 13, height: 13 }} /> : <Maximize2 style={{ width: 13, height: 13 }} />}
          </IconButton>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginLeft: 2 }}>
            <motion.span style={{ width: 5, height: 5, borderRadius: '50%', background: p.up }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.5, repeat: Infinity }} />
            <span style={{ fontSize: 9.5, fontWeight: 700, color: p.t4, fontFamily: MONO, letterSpacing: '0.04em' }}>LIVE</span>
          </div>
        </div>

        {/* Active studies chips */}
        {view === 'chart' && indicators.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderTop: `1px solid ${p.hairline}`, flexWrap: 'wrap' }}>
            {indicators.map(ind => (
              <span key={ind.uid} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: p.glass, border: `1px solid ${p.border}`, borderRadius: 99 }}>
                <span style={{ fontSize: 10, fontWeight: 600, color: p.t2 }}>{ind.def.name}</span>
                <button onClick={() => removeIndicator(ind.uid)} style={{ width: 13, height: 13, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: p.glassHi, border: 'none', cursor: 'pointer', color: p.t4 }}><X style={{ width: 8, height: 8 }} /></button>
              </span>
            ))}
            {compare.map(c => (
              <span key={c} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', background: p.accentDim, border: `1px solid ${p.accent}44`, borderRadius: 99 }}>
                <GitCompareArrows style={{ width: 10, height: 10, color: p.accentText }} />
                <span style={{ fontSize: 10, fontWeight: 700, color: p.accentText }}>{MARKET_BY_CODE[c]?.flag} {c}</span>
                <button onClick={() => toggleCompare(c)} style={{ width: 13, height: 13, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: p.glassHi, border: 'none', cursor: 'pointer', color: p.t4 }}><X style={{ width: 8, height: 8 }} /></button>
              </span>
            ))}
          </div>
        )}
      </GlassPanel>

      {/* ════ BODY ════ */}
      {/* flex 1 0 auto: fills the viewport when content is short, but grows (never shrinks below
          content) so the page scrolls to reveal the full decision-desk dock when it doesn't fit. */}
      <div style={{ flex: '1 0 auto', display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* Markets — cross-border strip, TOP, full width */}
        <GlassPanel p={p} radius={12} style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'stretch', gap: 4, padding: '6px 8px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', paddingRight: 10, marginRight: 4, borderRight: `1px solid ${p.hairline}`, flexShrink: 0 }}>
              <Eyebrow p={p}>Markets</Eyebrow>
              <span style={{ fontSize: 8.5, color: p.t4, fontFamily: MONO }}>cross-border</span>
            </div>
            {marketRows.map(({ m, q }) => {
              const on = m.code === market; const u = q.changePct >= 0; const isBest = m.code === bestBuyCode
              return (
                <button key={m.code} onClick={() => setMarket(m.code)} title={`${m.name} · ${m.dealers.toLocaleString('de-DE')} dealers · VAT ${m.vat}%`}
                  style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1, padding: '5px 10px', borderRadius: 9, cursor: 'pointer', textAlign: 'left',
                    background: on ? p.accentDim : 'transparent', border: `1px solid ${on ? p.accent + '55' : 'transparent'}`, transition: `background 120ms ${EASE}` }}
                  onMouseEnter={e => { if (!on) e.currentTarget.style.background = p.glass }}
                  onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 12 }}>{m.flag}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: on ? p.accentText : p.t2, fontFamily: SANS }}>{m.code}</span>
                    {isBest && <span style={{ fontSize: 7, fontWeight: 800, color: p.up, letterSpacing: '0.05em', padding: '1px 4px', borderRadius: 99, background: p.upDim }}>BEST</span>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: p.t1, fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(q.last)}</span>
                    <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 700, color: u ? p.up : p.down, fontVariantNumeric: 'tabular-nums' }}>{u ? '+' : ''}{q.changePct.toFixed(2)}%</span>
                  </div>
                </button>
              )
            })}
          </div>
        </GlassPanel>

        {/* Middle row: view content + watchlist — grows on tall screens, ≥380 on short (chart stays large) */}
        <div style={{ flex: '1 1 auto', minHeight: 380, display: 'flex', gap: 10 }}>
          {/* Center: view-switched */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 10 }}>
          {view === 'chart' && (
            <>
              {/* Drawing rail — full TradingView tool taxonomy.
                  zIndex raises its stacking context above the chart panel so tool flyouts paint over it. */}
              <GlassPanel p={p} radius={14} style={{ width: 46, flexShrink: 0, overflow: 'visible', zIndex: 50 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, padding: '7px 0', overflowY: 'auto', overflowX: 'visible', maxHeight: '100%' }}>
                  {RAIL_GROUPS.map(grp => {
                    const sel = groupTool[grp.id] ?? grp.tools[0]?.id
                    const active = grp.tools.some(t => t.id === tool)
                    return (
                      <div key={grp.id} style={{ display: 'flex', alignItems: 'center' }}>
                        <button onClick={() => setTool(sel)} title={TOOL_BY_ID[sel]?.label ?? grp.label}
                          style={{ width: 30, height: 30, borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', background: active ? p.accentDim : 'transparent', border: `1px solid ${active ? p.accent + '55' : 'transparent'}`, color: active ? p.accentText : p.t3, transition: 'all 120ms' }}>
                          {groupIcon(grp.id)}
                        </button>
                        <button data-rail-arrow="1" title={`${grp.label} — choose tool`}
                          onClick={e => { const r = e.currentTarget.getBoundingClientRect(); setShowColors(false); setFlyout(f => f === grp.id ? null : grp.id); setFlyoutPos({ x: r.right + 6, y: r.top }) }}
                          style={{ width: 10, height: 30, cursor: 'pointer', background: 'transparent', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: flyout === grp.id ? p.accentText : p.t4, padding: 0 }}>
                          <svg width={5} height={5} viewBox="0 0 6 6" fill="currentColor"><polygon points="0,0 6,3 0,6" /></svg>
                        </button>
                      </div>
                    )
                  })}

                  <div style={{ width: 22, height: 1, background: p.border, margin: '3px 0' }} />
                  <button data-rail-arrow="1" title="Drawing color"
                    onClick={e => { const r = e.currentTarget.getBoundingClientRect(); setFlyout(null); setShowColors(s => !s); setColorPos({ x: r.right + 6, y: r.top }) }}
                    style={{ width: 30, height: 30, borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', background: p.glass, border: `1px solid ${p.border}` }}>
                    <span style={{ width: 14, height: 14, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}aa` }} />
                  </button>
                  <IconButton p={p} active={magnet} onClick={() => setMagnet(m => !m)} title="Magnet (snap)"><Magnet style={{ width: 13, height: 13 }} /></IconButton>
                  <IconButton p={p} active={lockDrawings} onClick={() => setLockDrawings(l => !l)} title="Lock drawings"><Lock style={{ width: 13, height: 13 }} /></IconButton>
                  <IconButton p={p} active={hideDrawings} onClick={() => setHideDrawings(h => !h)} title="Hide drawings">{hideDrawings ? <EyeOff style={{ width: 13, height: 13 }} /> : <Eye style={{ width: 13, height: 13 }} />}</IconButton>
                  {drawings.length > 0 && (
                    <button onClick={() => setDrawings([])} title="Remove all drawings" style={{ width: 30, height: 30, borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', background: p.downDim, border: `1px solid ${p.down}44`, color: p.down }}><Trash2 style={{ width: 13, height: 13 }} /></button>
                  )}
                </div>
              </GlassPanel>

              {/* Rail flyout — portal to body so it escapes the rail's overflow clip + glass containing-block */}
              {flyout && flyoutPos && (() => {
                const grp = RAIL_GROUPS.find(g => g.id === flyout); if (!grp) return null
                const top = Math.max(8, Math.min(flyoutPos.y, window.innerHeight - 372))
                return createPortal(
                  <div data-rail-pop="1" style={{ position: 'fixed', left: flyoutPos.x, top, minWidth: 212, maxHeight: 360, overflowY: 'auto', zIndex: 4000, borderRadius: 12, padding: 6, ...menuBg }}>
                    <Eyebrow p={p} style={{ display: 'block', padding: '4px 8px 6px' }}>{grp.label}</Eyebrow>
                    {grp.tools.map(t => {
                      const on = t.id === tool
                      return (
                        <button key={t.id} onClick={() => pickTool(grp.id, t.id)} title={t.note}
                          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '7px 9px', borderRadius: 7, cursor: 'pointer', border: 'none', background: on ? p.accentDim : 'transparent', textAlign: 'left' }}
                          onMouseEnter={e => { if (!on) e.currentTarget.style.background = p.glass }} onMouseLeave={e => { if (!on) e.currentTarget.style.background = 'transparent' }}>
                          <span style={{ fontSize: 11.5, fontWeight: on ? 700 : 500, color: on ? p.accentText : p.t2 }}>{t.label}</span>
                          <span style={{ fontSize: 8.5, color: p.t4, fontFamily: MONO }}>{t.clicks > 0 ? `${t.clicks}pt` : t.geometry === 'brush' ? '✎' : ''}</span>
                        </button>
                      )
                    })}
                  </div>, document.body)
              })()}

              {/* Color picker — portal */}
              {showColors && colorPos && createPortal(
                <div data-rail-pop="1" style={{ position: 'fixed', left: colorPos.x, top: Math.max(8, colorPos.y), display: 'flex', flexDirection: 'column', gap: 5, padding: 8, zIndex: 4000, borderRadius: 10, ...menuBg }}>
                  {DRAW_COLORS.map(c => (
                    <button key={c} onClick={() => { setColor(c); setShowColors(false) }} style={{ width: 18, height: 18, borderRadius: '50%', background: c, border: c === color ? '2px solid #fff' : `1px solid ${p.border}`, cursor: 'pointer', boxShadow: c === color ? `0 0 8px ${c}` : 'none' }} />
                  ))}
                </div>, document.body)}

              {/* Chart — glow off: the chart surface must never glow (only material elevation) */}
              <GlassPanel p={p} radius={14} glow={false} style={{ flex: 1, minWidth: 0 }}>
                {/* Corner legend (TradingView-style) — keeps OHLC off the header */}
                <div style={{ position: 'absolute', top: 11, left: 14, zIndex: 4, pointerEvents: 'none', display: 'flex', alignItems: 'baseline', gap: 9, fontFamily: MONO }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: p.t1, fontFamily: SANS }}>{inst.make} {inst.model}</span>
                  <span style={{ fontSize: 9.5, color: p.t4 }}>{inst.variant}</span>
                  {([['O', disp.open], ['H', disp.high], ['L', disp.low], ['C', disp.close]] as [string, number][]).map(([k, v]) => (
                    <span key={k} style={{ fontSize: 9.5 }}><span style={{ color: p.t4 }}>{k} </span><span style={{ color: k === 'C' ? (dispUp ? p.up : p.down) : p.t3, fontWeight: k === 'C' ? 700 : 500 }}>{Math.round(v).toLocaleString('de-DE')}</span></span>
                  ))}
                </div>
                <MarketChart p={p} inst={inst} market={market} range={range} chartType={chartType} indicators={indicators} compare={compare} tool={tool} color={color} drawings={drawings} onAddDrawing={addDrawing} onUpdateDrawing={updateDrawing} onDeleteDrawing={deleteDrawing} hideDrawings={hideDrawings} lockDrawings={lockDrawings} magnet={magnet} onCross={setCross} />
              </GlassPanel>
            </>
          )}

          {view === 'depth' && (
            <>
              <GlassPanel p={p} radius={14} glow={false} style={{ flex: 1, minWidth: 0 }}>
                <PanelTitle p={p} label="Price-Index" sub={`${inst.make} ${inst.model} · ${market}`} />
                <MarketChart p={p} inst={inst} market={market} range={range} chartType="area" indicators={[]} compare={[]} tool="cross" color={color} drawings={[]} onAddDrawing={addDrawing} onUpdateDrawing={updateDrawing} onDeleteDrawing={deleteDrawing} hideDrawings lockDrawings magnet={false} onCross={setCross} />
              </GlassPanel>
              <GlassPanel p={p} radius={14} style={{ width: 320, flexShrink: 0 }}>
                <PanelTitle p={p} label="Supply Depth" sub="listings by price" />
                <DepthLadder p={p} inst={inst} market={market} />
              </GlassPanel>
            </>
          )}

          {view === 'arbitrage' && (
            <GlassPanel p={p} radius={14} style={{ flex: 1, minWidth: 0 }}>
              <ArbitrageScanner p={p} inst={inst} />
            </GlassPanel>
          )}

          {view === 'screener' && (
            <GlassPanel p={p} radius={14} style={{ flex: 1, minWidth: 0 }}>
              <PanelTitle p={p} label="Arbitrage Screener" sub="best net-landed margin · universe" right={<Eyebrow p={p}>net of NLC + fiscal</Eyebrow>} />
              <ArbitrageScreener p={p} onSelect={(it) => { setInst(it); setView('arbitrage') }} />
            </GlassPanel>
          )}
        </div>

          {/* Watchlist — right column (tall: 10+ rows) */}
          <GlassPanel p={p} radius={14} style={{ width: 300, flexShrink: 0 }}>
            <PanelTitle p={p} label="Watchlist" sub={`${INSTRUMENTS.length} indices · search to add`} />
            <Watchlist p={p} market={market} selectedId={inst.id} onSelect={setInst} />
          </GlassPanel>
        </div>

        {/* Decision Desk dock — BELOW the chart, full width, collapsible (Revolut / Plus500 style) */}
        <GlassPanel p={p} radius={14} style={{ flexShrink: 0, height: deskOpen ? 352 : 40, overflow: 'hidden', transition: 'height 260ms cubic-bezier(0.22,1,0.36,1)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', height: 38, borderBottom: deskOpen ? `1px solid ${p.hairline}` : 'none' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: '-0.01em', color: p.t1, fontFamily: SANS }}>Decision Desk</span>
              <span style={{ fontSize: 10, color: p.t4, fontFamily: MONO }}>{inst.make} {inst.model} · {inst.variant}</span>
              <motion.span style={{ width: 5, height: 5, borderRadius: '50%', background: p.accent }} animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 1.6, repeat: Infinity }} />
            </div>
            <button onClick={() => setDeskOpen(o => !o)} title={deskOpen ? 'Collapse — bigger chart' : 'Expand decision desk'}
              style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 9px', borderRadius: 8, cursor: 'pointer', background: p.glass, border: `1px solid ${p.border}`, color: p.t3, fontSize: 10, fontWeight: 700, fontFamily: SANS }}>
              {deskOpen ? 'Collapse' : 'Expand'}
              <motion.span animate={{ rotate: deskOpen ? 0 : 180 }} transition={{ duration: 0.2 }} style={{ display: 'flex' }}><ChevronDown style={{ width: 12, height: 12 }} /></motion.span>
            </button>
          </div>
          {deskOpen && (
            <div style={{ height: 314 }}>
              <AnimatePresence mode="wait">
                <motion.div key={inst.id + market} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25, ease: EASE_ARR }} style={{ height: '100%' }}>
                  <IntelRail p={p} inst={inst} market={market} orientation="dock" />
                </motion.div>
              </AnimatePresence>
            </div>
          )}
        </GlassPanel>
      </div>

      {/* ════ FOOTER ════ */}
      <GlassPanel p={p} radius={12} style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '0 14px', height: 26, fontFamily: MONO, fontSize: 9.5, color: p.t4 }}>
          <span style={{ fontWeight: 700, letterSpacing: '0.06em', color: p.t3 }}>{inst.make.toUpperCase()} {inst.model.toUpperCase()} · {mkt?.name.toUpperCase()}</span>
          <span>VAT {mkt?.vat}% · {mkt?.regTax}</span>
          <div style={{ flex: 1 }} />
          <span>{tool === 'cross' ? 'cursor' : `tool · ${TOOL_BY_ID[tool]?.label ?? tool}`}</span>
          {magnet && <span style={{ color: p.accentText, fontWeight: 700 }}>MAGNET</span>}
          {lockDrawings && <span style={{ color: p.amber, fontWeight: 700 }}>LOCKED</span>}
          <span style={{ color: p.t3, fontWeight: 700, letterSpacing: '0.08em' }}>CARDEX</span>
        </div>
      </GlassPanel>
    </div>
  )
}

// Header logo with graceful fallback (mirrors ui BrandLogo, kept inline for the chrome)
function LogoImg({ inst, p, size }: { inst: Instrument; p: ReturnType<typeof useTheme>; size: number }) {
  const [failed, setFailed] = useState(false)
  if (failed || !inst.logo) {
    return <div style={{ width: size, height: size, borderRadius: size * 0.28, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `${inst.color}22`, border: `1px solid ${inst.color}55`, color: inst.color, fontSize: size * 0.4, fontWeight: 800, fontFamily: SANS }}>{inst.make.slice(0, 2).toUpperCase()}</div>
  }
  return <img src={inst.logo} alt="" width={size} height={size} style={{ objectFit: 'contain', filter: p.dark ? 'none' : 'invert(1) brightness(0.3)' }} onError={() => setFailed(true)} />
}
