/*
 * CARDEX Terminal — drawing engine (TradingView-parity)
 * One SVG overlay that renders every drawing geometry: trend lines & rays, channels,
 * the full Fibonacci/Gann family, pitchforks, harmonic & Elliott patterns, projection /
 * position tools, shapes, arrows, text/notes, brush, and measure. Anchors live in
 * chart space ({time,price}) so drawings stay glued to the data through pan/zoom.
 * Click-count is driven by tools.ts (requiredClicks); pointN/brush terminate on dblclick / mouseup.
 */
import React, { useEffect, useRef, useState } from 'react'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import type { TerminalPalette } from './theme'
import { MONO } from './theme'
import { TOOL_BY_ID, requiredClicks, type Geometry } from './tools'
import type { Bar } from './market'

export interface DrawPoint { time: string; price: number }
export interface Drawing { id: string; tool: string; geometry: Geometry; pts: DrawPoint[]; color: string; text?: string }

const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
const FIB_EXT = [0, 0.618, 1, 1.272, 1.618, 2, 2.618]
const PATTERN_LABELS: Record<string, string[]> = {
  xabcd_pattern: ['X', 'A', 'B', 'C', 'D'],
  cypher_pattern: ['X', 'A', 'B', 'C', 'D'],
  abcd_pattern: ['A', 'B', 'C', 'D'],
  head_and_shoulders: ['', 'LS', '', 'H', '', 'RS', ''],
  triangle_pattern: ['A', 'B', 'C', 'D'],
  three_drives: ['', '1', '', '2', '', '3', ''],
  elliott_impulse: ['0', '1', '2', '3', '4', '5'],
  elliott_triangle: ['0', 'A', 'B', 'C', 'D', 'E'],
  elliott_triple_combo: ['0', 'W', 'X', 'Y', 'X', 'Z'],
  elliott_double_combo: ['0', 'W', 'X', 'Y'],
  elliott_correction: ['0', 'A', 'B', 'C'],
}

export function DrawingLayer({ chart, series, p, drawings, onAdd, onUpdate, onDelete, tool, color, version, height, lock, hide, magnet, bars }: {
  chart: IChartApi | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  series: React.MutableRefObject<ISeriesApi<any> | null>
  p: TerminalPalette
  drawings: Drawing[]
  onAdd: (d: Drawing) => void
  onUpdate: (id: string, pts: DrawPoint[]) => void
  onDelete: (id: string) => void
  tool: string
  color: string
  version: number
  height: number
  lock: boolean
  hide: boolean
  magnet: boolean
  bars: Bar[]
}) {
  const ref = useRef<SVGSVGElement>(null)
  const [w, setW] = useState(0)
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null)
  // Accumulators as refs so multi-click tools & brush are immune to React render timing —
  // closure-stale state was dropping points on fast clicks and on brush mouseup.
  const pendingRef = useRef<{ x: number; y: number }[]>([])
  const strokeRef = useRef<DrawPoint[]>([])
  const brushingRef = useRef(false)
  const idRef = useRef(0)
  const [, force] = useState(0)
  const rerender = () => force(n => n + 1)
  useEffect(() => { rerender() }, [version])
  useEffect(() => { pendingRef.current = []; strokeRef.current = []; brushingRef.current = false; rerender() }, [tool])
  // Selection + anchor-drag editing
  const selRef = useRef<string | null>(null)
  const dragRef = useRef<{ id: string; idx: number } | null>(null)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if ((e.key === 'Delete' || e.key === 'Backspace') && selRef.current) { onDelete(selRef.current); selRef.current = null; rerender() }
      else if (e.key === 'Escape') { selRef.current = null; rerender() }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onDelete])
  useEffect(() => {
    if (!ref.current) return
    const obs = new ResizeObserver(e => setW(e[0].contentRect.width))
    obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])

  if (!chart) return null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ts = chart.timeScale() as any
  // Price↔coordinate conversion lives on the SERIES (ISeriesApi), not the price scale.
  const ser = series.current
  const def = TOOL_BY_ID[tool]
  const geom: Geometry | undefined = def?.geometry
  const need = def ? requiredClicks(def) : 0
  const isBrush = geom === 'brush'
  const isPointN = geom === 'pointN'
  const drawingMode = !!def && (def.geometry !== 'placed' || def.clicks > 0)
  const interactive = drawingMode && !lock

  const prY = (price: number): number => (ser ? (ser.priceToCoordinate(price) as number | null) : null) ?? -9999
  const toPx = (pt: DrawPoint) => ({ x: ts.timeToCoordinate(pt.time as any) ?? -9999, y: prY(pt.price) })
  const fromPx = (x: number, y: number): DrawPoint | null => {
    const time = ts.coordinateToTime(x)
    let price = (ser ? (ser.coordinateToPrice(y) as number | null) : null)
    if (time == null || price == null) return null
    if (magnet) {
      // True magnet: snap to the nearest OHLC of the bar under the cursor (TradingView behaviour)
      const bar = bars.find(b => b.time === String(time))
      if (bar) {
        let best = bar.open
        for (const c of [bar.open, bar.high, bar.low, bar.close]) if (Math.abs(c - price) < Math.abs(best - price)) best = c
        price = best
      }
    }
    return { time: String(time), price }
  }

  // ── interaction ──────────────────────────────────────────────────────────
  function commit(ptsPx: { x: number; y: number }[], extra?: Partial<Drawing>) {
    const pts = ptsPx.map(pp => fromPx(pp.x, pp.y)).filter(Boolean) as DrawPoint[]
    if (pts.length < 1) return
    onAdd({ id: `d${idRef.current++}`, tool, geometry: geom!, pts, color, ...extra })
  }
  function relPos(e: React.MouseEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  function handleDown(e: React.MouseEvent<SVGSVGElement>) {
    if (!interactive || !isBrush) return
    const pt = fromPx(relPos(e).x, relPos(e).y); if (!pt) return
    brushingRef.current = true; strokeRef.current = [pt]; rerender(); e.preventDefault()
  }
  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    const pos = relPos(e); setHover(pos)
    if (brushingRef.current && isBrush) { const pt = fromPx(pos.x, pos.y); if (pt) { strokeRef.current = [...strokeRef.current, pt]; rerender() } }
  }
  function handleUp() {
    if (!brushingRef.current) return
    brushingRef.current = false
    const st = strokeRef.current
    if (st.length > 1) onAdd({ id: `d${idRef.current++}`, tool, geometry: 'brush', pts: st, color })
    strokeRef.current = []; rerender()
  }
  // Distance from point (px,py) to segment (ax,ay)-(bx,by) — for eraser hit-testing line bodies.
  function distToSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
    const dx = bx - ax, dy = by - ay
    const len2 = dx * dx + dy * dy
    const tt = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2))
    const cx = ax + tt * dx, cy = ay + tt * dy
    return Math.hypot(px - cx, py - cy)
  }
  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    if (!interactive || isBrush) return
    const pos = relPos(e)
    // ── action tools: erase / zoom (perform the action, never commit a drawing) ──
    if (tool === 'eraser') {
      let bestId: string | null = null, best = 12 // px hit radius
      for (const d of drawings) {
        const a = d.pts.map(toPx)
        for (const pt of a) { const dd = Math.hypot(pt.x - pos.x, pt.y - pos.y); if (dd < best) { best = dd; bestId = d.id } }
        for (let i = 1; i < a.length; i++) { const dd = distToSeg(pos.x, pos.y, a[i - 1].x, a[i - 1].y, a[i].x, a[i].y); if (dd < best) { best = dd; bestId = d.id } }
      }
      if (bestId) onDelete(bestId)
      return
    }
    if (tool === 'zoom_out') {
      const r = ts.getVisibleLogicalRange?.()
      if (r) { const span = r.to - r.from, mid = (r.to + r.from) / 2; ts.setVisibleLogicalRange({ from: mid - span * 0.75, to: mid + span * 0.75 }) }
      return
    }
    if (tool === 'zoom_in') {
      const next = [...pendingRef.current, pos]
      if (next.length >= 2) {
        const l0 = ts.coordinateToLogical?.(next[0].x), l1 = ts.coordinateToLogical?.(next[1].x)
        if (l0 != null && l1 != null && l0 !== l1) ts.setVisibleLogicalRange({ from: Math.min(l0, l1), to: Math.max(l0, l1) })
        pendingRef.current = []; rerender()
      } else { pendingRef.current = next; rerender() }
      return
    }
    if (isPointN) { pendingRef.current = [...pendingRef.current, pos]; rerender(); return }
    const next = [...pendingRef.current, pos]
    if (need <= 0 || next.length >= need) { commit(next); pendingRef.current = []; rerender() }
    else { pendingRef.current = next; rerender() }
  }
  function handleDouble() {
    if (isPointN && pendingRef.current.length >= 2) { commit(pendingRef.current); pendingRef.current = []; rerender() }
  }
  // Grab an anchor of an existing drawing and reshape it (works for every tool/geometry)
  function startHandleDrag(e: React.MouseEvent, id: string, idx: number) {
    e.stopPropagation(); e.preventDefault()
    selRef.current = id; dragRef.current = { id, idx }; rerender()
    const svgEl = ref.current; if (!svgEl) return
    const onMove = (ev: MouseEvent) => {
      const dr = dragRef.current; if (!dr) return
      const r = svgEl.getBoundingClientRect()
      const pt = fromPx(ev.clientX - r.left, ev.clientY - r.top); if (!pt) return
      const d = drawings.find(x => x.id === dr.id); if (!d) return
      onUpdate(dr.id, d.pts.map((q, i) => i === dr.idx ? pt : q))
    }
    const onUp = () => { dragRef.current = null; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); rerender() }
    document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp)
  }
  // Move the whole drawing — translate every anchor by the pixel delta (handles time + price)
  function startBodyDrag(e: React.MouseEvent, id: string) {
    e.stopPropagation(); e.preventDefault()
    selRef.current = id; rerender()
    const svgEl = ref.current; if (!svgEl) return
    const r0 = svgEl.getBoundingClientRect()
    const d0 = drawings.find(x => x.id === id); if (!d0) return
    const startPx = d0.pts.map(toPx)
    const m0 = { x: e.clientX - r0.left, y: e.clientY - r0.top }
    const onMove = (ev: MouseEvent) => {
      const r = svgEl.getBoundingClientRect()
      const dx = (ev.clientX - r.left) - m0.x, dy = (ev.clientY - r.top) - m0.y
      const next = startPx.map(px => fromPx(px.x + dx, px.y + dy)).filter(Boolean) as DrawPoint[]
      if (next.length === startPx.length) onUpdate(id, next)
    }
    const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); rerender() }
    document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp)
  }

  // ── primitives ─────────────────────────────────────────────────────────────
  const txt = (x: number, y: number, s: string, c = color, anchor: 'start' | 'middle' | 'end' = 'start', size = 9) =>
    <text x={x} y={y} fontSize={size} fill={c} textAnchor={anchor} fontFamily={MONO} style={{ pointerEvents: 'none' }}>{s}</text>
  const line = (x1: number, y1: number, x2: number, y2: number, c = color, sw = 1.4, dash?: string) =>
    <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={c} strokeWidth={sw} strokeDasharray={dash} />

  function render(d: Drawing): React.ReactNode {
    if (hide) return null
    const a = d.pts.map(toPx)
    const c = d.color
    const g = d.geometry
    const id = d.tool

    // brush / highlighter
    if (g === 'brush') {
      if (d.pts.length < 2) return null
      const path = `M ${a.map(pt => `${pt.x},${pt.y}`).join(' L ')}`
      const hl = id === 'highlighter'
      return <path key={d.id} d={path} stroke={c} strokeWidth={hl ? 14 : 2} fill="none" strokeLinecap="round" strokeLinejoin="round" opacity={hl ? 0.3 : 0.9} />
    }
    // pointN: polyline / path
    if (g === 'pointN') {
      if (a.length < 2) return null
      const path = `M ${a.map(pt => `${pt.x},${pt.y}`).join(id === 'path' ? ' L ' : ' L ')}`
      return <path key={d.id} d={path} stroke={c} strokeWidth={1.5} fill={id === 'path' ? `${c}14` : 'none'} strokeLinejoin="round" opacity={0.9} />
    }
    // single-anchor tools
    if (a.length === 1) {
      const pt = a[0]
      if (id === 'horizontal_line' || id === 'horizontal_ray' || id === 'price_label') {
        const x1 = id === 'horizontal_ray' ? pt.x : 0
        return <g key={d.id} opacity={0.9}>{line(x1, pt.y, w, pt.y, c, 1.3)}
          <rect x={w - 58} y={pt.y - 9} width={54} height={16} rx={3} fill={`${c}22`} stroke={c} strokeWidth={0.6} />
          {txt(w - 6, pt.y + 2.5, Math.round(d.pts[0].price).toLocaleString('de-DE'), c, 'end')}</g>
      }
      if (id === 'vertical_line' || id === 'cross_line' || id === 'signpost') {
        return <g key={d.id} opacity={0.85}>{line(pt.x, 0, pt.x, height, c, 1.2, id === 'signpost' ? undefined : '5,3')}
          {id === 'cross_line' && line(0, pt.y, w, pt.y, c, 1.2, '5,3')}
          {id === 'signpost' && <circle cx={pt.x} cy={14} r={4} fill={c} />}</g>
      }
      if (id.startsWith('arrow_mark')) {
        const dir = id.endsWith('up') ? -1 : id.endsWith('down') ? 1 : 0
        const hor = id.endsWith('left') ? -1 : id.endsWith('right') ? 1 : 0
        return <g key={d.id} opacity={0.92}><polygon points={
          hor !== 0
            ? `${pt.x + hor * 14},${pt.y} ${pt.x + hor * 26},${pt.y - 7} ${pt.x + hor * 26},${pt.y + 7}`
            : `${pt.x},${pt.y + dir * 13} ${pt.x - 7},${pt.y + dir * 24} ${pt.x + 7},${pt.y + dir * 24}`
        } fill={c} /></g>
      }
      if (g === 'text') {
        const note = id === 'note' || id === 'anchored_note' || id === 'comment'
        return <g key={d.id} opacity={0.95}>
          {note && <rect x={pt.x - 4} y={pt.y - 13} width={(d.text?.length ?? 4) * 7 + 12} height={18} rx={4} fill={`${p.dark ? 'rgba(10,10,22,0.7)' : 'rgba(255,255,255,0.8)'}`} stroke={c} strokeWidth={0.7} />}
          {txt(pt.x, pt.y, d.text || id.replace(/_/g, ' '), c, 'start', 11.5)}</g>
      }
      // flag_mark / icon / emoji / sticker / image / table → glyph marker
      return <g key={d.id} opacity={0.9}><circle cx={pt.x} cy={pt.y} r={6} fill={`${c}33`} stroke={c} strokeWidth={1} />{txt(pt.x, pt.y + 3, '◆', c, 'middle', 9)}</g>
    }

    if (a.length < 2) return null
    const [p0, p1] = a
    const slope = p1.x === p0.x ? 0 : (p1.y - p0.y) / (p1.x - p0.x)

    // ── lines family (point2) ──
    if (id === 'trend_line' || id === 'info_line' || id === 'trend_angle' || id === 'arrow' || id === 'arrow_marker') {
      const head = id === 'arrow' || id === 'arrow_marker'
      const ang = Math.atan2(p1.y - p0.y, p1.x - p0.x)
      const dp = ((d.pts[1].price - d.pts[0].price) / (d.pts[0].price || 1)) * 100
      const deg = (-Math.atan2(p1.y - p0.y, p1.x - p0.x) * 180 / Math.PI).toFixed(1)
      return <g key={d.id} opacity={0.9}>{line(p0.x, p0.y, p1.x, p1.y, c, 1.6)}
        {head && <polygon points={`${p1.x},${p1.y} ${p1.x - 11 * Math.cos(ang - 0.4)},${p1.y - 11 * Math.sin(ang - 0.4)} ${p1.x - 11 * Math.cos(ang + 0.4)},${p1.y - 11 * Math.sin(ang + 0.4)}`} fill={c} />}
        {id === 'info_line' && txt((p0.x + p1.x) / 2, (p0.y + p1.y) / 2 - 6, `${dp >= 0 ? '+' : ''}${dp.toFixed(2)}%`, c, 'middle')}
        {id === 'trend_angle' && txt(p1.x + 6, p1.y, `${deg}°`, c, 'start')}</g>
    }
    if (id === 'ray') {
      const dx = p1.x - p0.x, dy = p1.y - p0.y, l = Math.hypot(dx, dy) || 1
      return <g key={d.id} opacity={0.9}>{line(p0.x, p0.y, p0.x + dx / l * 6000, p0.y + dy / l * 6000, c, 1.5)}</g>
    }
    if (id === 'extended_line') {
      return <g key={d.id} opacity={0.9}>{line(-2000, p0.y - slope * (p0.x + 2000), w + 2000, p0.y + slope * (w - p0.x + 2000), c, 1.5)}</g>
    }
    if (id === 'regression_trend') {
      const off = 26
      return <g key={d.id} opacity={0.88}>
        {line(p0.x, p0.y, p1.x, p1.y, c, 1.6)}
        {line(p0.x, p0.y - off, p1.x, p1.y - off, c, 0.9, '4,3')}
        {line(p0.x, p0.y + off, p1.x, p1.y + off, c, 0.9, '4,3')}
        <rect x={Math.min(p0.x, p1.x)} y={Math.min(p0.y, p1.y) - off} width={Math.abs(p1.x - p0.x)} height={Math.abs(p1.y - p0.y) + off * 2} fill={`${c}0c`} /></g>
    }
    if (id === 'callout') {
      return <g key={d.id} opacity={0.92}>{line(p0.x, p0.y, p1.x, p1.y, c, 1.2)}
        <rect x={p1.x} y={p1.y - 12} width={Math.max(54, (d.text?.length ?? 5) * 7)} height={22} rx={6} fill={`${c}1f`} stroke={c} strokeWidth={1} />
        {txt(p1.x + 7, p1.y + 3, d.text || 'Callout', c, 'start', 10)}</g>
    }
    if (id === 'price_range' || id === 'date_range' || id === 'measure' || id === 'date_and_price_range') {
      const dp = ((d.pts[1].price - d.pts[0].price) / (d.pts[0].price || 1)) * 100
      const up = dp >= 0
      const col = up ? p.up : p.down
      const x = Math.min(p0.x, p1.x), y = Math.min(p0.y, p1.y), bw = Math.abs(p1.x - p0.x), bh = Math.abs(p1.y - p0.y)
      return <g key={d.id} opacity={0.92}>
        <rect x={x} y={y} width={bw} height={bh} fill={up ? p.upDim : p.downDim} stroke={col} strokeWidth={1} strokeDasharray="4,3" />
        {txt(x + bw / 2, y - 6, `${up ? '+' : ''}${dp.toFixed(2)}%  ${up ? '+' : '−'}€${Math.abs(Math.round(d.pts[1].price - d.pts[0].price)).toLocaleString('de-DE')}`, col, 'middle', 10)}</g>
    }

    // ── channels ──
    if (g === 'channel' && a.length >= 2) {
      const p2 = a[2] ?? { x: p1.x, y: p1.y - 40 }
      const off = id === 'flat_top_bottom' ? 0 : (p2.y - (p0.y + slope * (p2.x - p0.x)))
      const flat = id === 'flat_top_bottom'
      return <g key={d.id} opacity={0.88}>
        {line(p0.x, p0.y, p1.x, p1.y, c, 1.5)}
        {flat ? line(p0.x, Math.min(p0.y, p2.y), p1.x, Math.min(p0.y, p2.y), c, 1.5) : line(p0.x, p0.y + off, p1.x, p1.y + off, c, 1.5)}
        <path d={`M ${p0.x},${p0.y} L ${p1.x},${p1.y} L ${p1.x},${flat ? Math.min(p0.y, p2.y) : p1.y + off} L ${p0.x},${flat ? Math.min(p0.y, p2.y) : p0.y + off} Z`} fill={`${c}10`} /></g>
    }

    // ── fibonacci family ──
    if (g === 'fib') {
      if (id === 'fib_retracement' || id === 'trend_based_fib_extension' || id === 'fib_channel') {
        const levels = id === 'trend_based_fib_extension' ? FIB_EXT : FIB_LEVELS
        const hi = Math.max(d.pts[0].price, d.pts[1].price), lo = Math.min(d.pts[0].price, d.pts[1].price)
        const rng = hi - lo
        const xL = Math.min(p0.x, p1.x), xR = Math.max(p0.x, p1.x)
        return <g key={d.id} opacity={0.92}>
          {line(p0.x, p0.y, p1.x, p1.y, c, 0.7, '2,4')}
          {levels.map((lv, i) => {
            const price = lo + rng * (1 - lv)
            const y = prY(price)
            const yNext = i < levels.length - 1 ? prY(lo + rng * (1 - levels[i + 1])) : y
            return <g key={i}>
              {i < levels.length - 1 && <rect x={xL} y={Math.min(y, yNext)} width={xR - xL} height={Math.abs(yNext - y)} fill={`${c}0e`} />}
              {line(xL, y, xR, y, c, 0.9, '3,3')}
              {txt(xR + 5, y + 3, `${(lv * 100).toFixed(1)}%  ${Math.round(price).toLocaleString('de-DE')}`, c, 'start', 8.5)}
            </g>
          })}</g>
      }
      if (id === 'fib_time_zone' || id === 'trend_based_fib_time') {
        const fibs = [0, 1, 2, 3, 5, 8, 13, 21]
        const unit = p1.x - p0.x
        return <g key={d.id} opacity={0.8}>{fibs.map((f, i) => {
          const x = p0.x + unit * f
          return <g key={i}>{line(x, 0, x, height, c, 0.8, '3,4')}{txt(x + 3, 13, String(f), c)}</g>
        })}</g>
      }
      if (id === 'fib_speed_resistance_fan' || id === 'fib_wedge') {
        const lvs = [0.236, 0.382, 0.5, 0.618, 0.786, 1]
        return <g key={d.id} opacity={0.82}>{lvs.map((lv, i) => {
          const tx = p0.x + (p1.x - p0.x) * lv
          return line(p0.x, p0.y, tx, p1.y, c, 0.9, '4,3') && <g key={i}>{line(p0.x, p0.y, tx, p1.y, c, 0.9, '4,3')}</g>
        })}{line(p0.x, p0.y, p1.x, p1.y, c, 1.2)}</g>
      }
      if (id === 'fib_circles' || id === 'fib_speed_resistance_arcs' || id === 'fib_spiral') {
        const cx = p0.x, cy = p0.y, R = Math.hypot(p1.x - p0.x, p1.y - p0.y)
        const lvs = [0.236, 0.382, 0.618, 1]
        return <g key={d.id} opacity={0.8}>{lvs.map((lv, i) =>
          <circle key={i} cx={cx} cy={cy} r={R * lv} fill="none" stroke={c} strokeWidth={0.9} strokeDasharray="3,3" />)}
          <circle cx={cx} cy={cy} r={2.5} fill={c} /></g>
      }
    }

    // ── gann ──
    if (g === 'gann') {
      const x = Math.min(p0.x, p1.x), y = Math.min(p0.y, p1.y), bw = Math.abs(p1.x - p0.x), bh = Math.abs(p1.y - p0.y)
      if (id === 'gann_fan') {
        const angles = [1 / 8, 1 / 4, 1 / 3, 1 / 2, 1, 2, 3, 4, 8]
        return <g key={d.id} opacity={0.82}>{angles.map((m, i) =>
          line(p0.x, p0.y, p1.x, p0.y + (p1.y - p0.y) * m, c, m === 1 ? 1.4 : 0.8, m === 1 ? undefined : '4,3'))
          .map((el, i) => <g key={i}>{el}</g>)}</g>
      }
      return <g key={d.id} opacity={0.82}>
        <rect x={x} y={y} width={bw} height={bh} fill={`${c}0c`} stroke={c} strokeWidth={1} />
        {[0.25, 0.5, 0.75].map((f, i) => <g key={i}>{line(x + bw * f, y, x + bw * f, y + bh, c, 0.6, '2,3')}{line(x, y + bh * f, x + bw, y + bh * f, c, 0.6, '2,3')}</g>)}
        {line(x, y + bh, x + bw, y, c, 1, '4,3')}{line(x, y, x + bw, y + bh, c, 1, '4,3')}</g>
    }

    // ── pitchforks (point3) ──
    if (id.includes('pitchfork')) {
      const p2 = a[2] ?? p1
      let origin = p0
      if (id === 'schiff_pitchfork') origin = { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2 }
      if (id === 'modified_schiff_pitchfork') origin = { x: (p0.x + p1.x) / 2, y: p0.y }
      const midX = (p1.x + p2.x) / 2, midY = (p1.y + p2.y) / 2
      const dx = midX - origin.x, dy = midY - origin.y, l = Math.hypot(dx, dy) || 1
      const ux = dx / l, uy = dy / l, ext = 6000
      return <g key={d.id} opacity={0.85}>
        {line(origin.x, origin.y, origin.x + ux * ext, origin.y + uy * ext, c, 1.3)}
        {line(p1.x, p1.y, p1.x + ux * ext, p1.y + uy * ext, c, 0.9, '5,3')}
        {line(p2.x, p2.y, p2.x + ux * ext, p2.y + uy * ext, c, 0.9, '5,3')}
        {line(p1.x, p1.y, p2.x, p2.y, c, 0.7, '3,4')}
        <circle cx={p0.x} cy={p0.y} r={3} fill={c} /><circle cx={p1.x} cy={p1.y} r={2.5} fill={c} /><circle cx={p2.x} cy={p2.y} r={2.5} fill={c} /></g>
    }

    // ── shapes (point2 / point3) ──
    if (id === 'rectangle') return <rect key={d.id} x={Math.min(p0.x, p1.x)} y={Math.min(p0.y, p1.y)} width={Math.abs(p1.x - p0.x)} height={Math.abs(p1.y - p0.y)} fill={`${c}1c`} stroke={c} strokeWidth={1.2} rx={2} opacity={0.9} />
    if (id === 'ellipse') {
      const cx = (p0.x + p1.x) / 2, cy = (p0.y + p1.y) / 2
      return <ellipse key={d.id} cx={cx} cy={cy} rx={Math.abs(p1.x - p0.x) / 2} ry={Math.abs(p1.y - p0.y) / 2} fill={`${c}16`} stroke={c} strokeWidth={1.2} opacity={0.9} />
    }
    if (id === 'triangle' || id === 'rotated_rectangle' || id === 'arc' || id === 'curve' || id === 'double_curve') {
      const p2 = a[2] ?? { x: p1.x + (p1.x - p0.x), y: p0.y }
      if (id === 'arc' || id === 'curve' || id === 'double_curve')
        return <path key={d.id} d={`M ${p0.x},${p0.y} Q ${p2.x},${p2.y} ${p1.x},${p1.y}`} fill="none" stroke={c} strokeWidth={1.4} opacity={0.9} />
      return <polygon key={d.id} points={`${p0.x},${p0.y} ${p1.x},${p1.y} ${p2.x},${p2.y}`} fill={`${c}16`} stroke={c} strokeWidth={1.2} opacity={0.9} />
    }

    // ── positions / projection (range) ──
    if (id === 'long_position' || id === 'short_position') {
      const isLong = id === 'long_position'
      const entry = d.pts[0].price, target = d.pts[1].price
      // 3rd anchor (if placed) is the protective stop; else mirror the target for a 1:1 default
      const stop = d.pts.length >= 3 ? d.pts[2].price : entry - (target - entry)
      const yE = toPx({ time: d.pts[0].time, price: entry }).y
      const yT = toPx({ time: d.pts[0].time, price: target }).y
      const yS = toPx({ time: d.pts[0].time, price: stop }).y
      const xL = Math.min(p0.x, p1.x), xR = Math.max(p0.x, p1.x) + 58
      const rr = Math.abs(target - entry) / (Math.abs(entry - stop) || 1)
      return <g key={d.id} opacity={0.92}>
        <rect x={xL} y={Math.min(yE, yT)} width={xR - xL} height={Math.abs(yT - yE)} fill={p.upDim} stroke={`${p.up}66`} strokeWidth={0.8} />
        <rect x={xL} y={Math.min(yE, yS)} width={xR - xL} height={Math.abs(yS - yE)} fill={p.downDim} stroke={`${p.down}66`} strokeWidth={0.8} />
        {line(xL, yE, xR, yE, isLong ? p.up : p.down, 1.6)}
        {txt(xR + 5, yT + 3, `T ${Math.round(target).toLocaleString('de-DE')}`, p.up)}
        {txt(xR + 5, yE + 3, `E ${Math.round(entry).toLocaleString('de-DE')}`, p.t2)}
        {txt(xR + 5, yS + 3, `S ${Math.round(stop).toLocaleString('de-DE')}`, p.down)}
        {txt((xL + xR) / 2, Math.min(yE, yT) - 5, `R:R ${rr.toFixed(2)}`, isLong ? p.up : p.down, 'middle', 9.5)}</g>
    }
    if (g === 'range') {
      const x = Math.min(p0.x, p1.x), y = Math.min(p0.y, p1.y), bw = Math.abs(p1.x - p0.x), bh = Math.abs(p1.y - p0.y)
      return <g key={d.id} opacity={0.85}>
        <rect x={x} y={y} width={bw} height={bh} fill={`${c}12`} stroke={c} strokeWidth={1} strokeDasharray={id === 'forecast' || id === 'projection' ? '5,3' : undefined} />
        {txt(x + 5, y + 13, def?.label ?? id, c, 'start', 9)}</g>
    }

    // ── patterns (labeled polyline) ──
    if (g === 'pattern') {
      const labels = PATTERN_LABELS[id] ?? []
      const path = `M ${a.map(pt => `${pt.x},${pt.y}`).join(' L ')}`
      return <g key={d.id} opacity={0.9}>
        <path d={path} fill={`${c}0c`} stroke={c} strokeWidth={1.4} strokeLinejoin="round" />
        {a.map((pt, i) => <g key={i}><circle cx={pt.x} cy={pt.y} r={2.6} fill={c} />{labels[i] ? txt(pt.x + 4, pt.y - 5, labels[i], c, 'start', 10) : null}</g>)}</g>
    }

    // fallback: simple segment
    return <g key={d.id} opacity={0.85}>{line(p0.x, p0.y, p1.x, p1.y, c, 1.4)}</g>
  }

  return (
    <svg ref={ref}
      onClick={handleClick} onDoubleClick={handleDouble}
      onMouseDown={handleDown} onMouseMove={handleMove} onMouseUp={handleUp}
      onMouseLeave={() => { setHover(null); if (brushingRef.current) handleUp() }}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 10, cursor: interactive ? 'crosshair' : 'default', pointerEvents: interactive ? 'all' : 'none', userSelect: 'none' }}>
      {drawings.map(render)}
      {/* live brush */}
      {brushingRef.current && strokeRef.current.length > 1 && (() => {
        const a = strokeRef.current.map(toPx); const hl = tool === 'highlighter'
        return <path d={`M ${a.map(pt => `${pt.x},${pt.y}`).join(' L ')}`} stroke={color} strokeWidth={hl ? 14 : 2} fill="none" strokeLinecap="round" opacity={hl ? 0.3 : 0.9} />
      })()}
      {/* pending anchors + rubber-band */}
      {pendingRef.current.map((pt, i) => <g key={i}><circle cx={pt.x} cy={pt.y} r={3.5} fill={color} opacity={0.85} />{i > 0 && line(pendingRef.current[i - 1].x, pendingRef.current[i - 1].y, pt.x, pt.y, color, 1, '4,3')}</g>)}
      {pendingRef.current.length > 0 && hover && line(pendingRef.current[pendingRef.current.length - 1].x, pendingRef.current[pendingRef.current.length - 1].y, hover.x, hover.y, color, 1, '5,3')}
      {interactive && !isBrush && hover && pendingRef.current.length === 0 && <>
        {line(hover.x, 0, hover.x, height, color, 0.6, undefined)}
        {line(0, hover.y, w, hover.y, color, 0.6, undefined)}
      </>}
      {/* Body grab — transparent thick path through the anchors lets you move the whole drawing.
          Rendered BEFORE the anchor handles so grabbing near an anchor reshapes instead of moves. */}
      {(tool === 'cross' || tool === 'crosshair') && !lock && !hide && drawings.filter(d => d.pts.length >= 2).map(d => {
        const a = d.pts.map(toPx)
        if (a.some(px => px.x < -2000 || px.y < -2000)) return null
        return <path key={`${d.id}_body`} d={`M ${a.map(px => `${px.x},${px.y}`).join(' L ')}`} fill="none" stroke="transparent" strokeWidth={12}
          style={{ pointerEvents: 'stroke', cursor: 'move' }} onMouseDown={e => startBodyDrag(e, d.id)} />
      })}
      {/* Edit handles — invisible hit-targets on every anchor in cursor mode (empty space still
          pans the chart since the svg itself is pointer-events:none); selected shows solid dots. */}
      {(tool === 'cross' || tool === 'crosshair') && !lock && !hide && drawings.flatMap(d => d.pts.map((pt, i) => {
        const px = toPx(pt); if (px.x < -2000 || px.y < -2000) return null
        const isSel = selRef.current === d.id
        return <circle key={`${d.id}_h${i}`} cx={px.x} cy={px.y} r={isSel ? 5 : 8}
          fill={isSel ? p.accent : 'transparent'} stroke={isSel ? (p.dark ? '#0b0c0f' : '#ffffff') : 'transparent'} strokeWidth={1.5}
          style={{ pointerEvents: 'auto', cursor: 'grab' }} onMouseDown={e => startHandleDrag(e, d.id, i)} />
      }))}
    </svg>
  )
}
