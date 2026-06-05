/*
 * CARDEX Terminal — intelligent watchlist
 * Folder-organised (by marque) and flat views, dense compact rows so 10+ indices read at once,
 * live search across the universe, sparkline, session delta and an SDI heat dot that pulses on
 * seller-pressure opportunities. Client-customisable: pin instruments to a "Pinned" folder and
 * collapse folders — both persist across reloads (localStorage). Pure neutral, no segment-label
 * noise. Selecting a row drives the whole terminal.
 */
import React, { useCallback, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, ChevronRight, Folder, List, Star } from 'lucide-react'
import type { TerminalPalette } from './theme'
import { MONO, SANS, EASE, EASE_ARR } from './theme'
import { INSTRUMENTS, quote, computeSdi, fmtPrice, type Instrument } from './market'
import { Eyebrow, Spark, BrandLogo } from './ui'

const heat = (band: string, p: TerminalPalette) =>
  band === 'Distressed' || band === 'Hot' ? p.up : band === 'Cold' ? p.down : p.t4

// localStorage-backed state so the client's organisation (pins, collapsed folders) survives reloads.
function usePersistent<T>(key: string, initial: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [val, setVal] = useState<T>(() => {
    try { const s = localStorage.getItem(key); return s ? (JSON.parse(s) as T) : initial } catch { return initial }
  })
  const set = useCallback((v: T | ((prev: T) => T)) => {
    setVal(prev => {
      const next = typeof v === 'function' ? (v as (prev: T) => T)(prev) : v
      try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* quota / private mode — non-fatal */ }
      return next
    })
  }, [key])
  return [val, set]
}

interface Row { inst: Instrument; price: number; chg: number; spark: number[]; sdiBand: string }

function Line({ p, r, active, pinned, onSelect, onTogglePin, indent }: {
  p: TerminalPalette; r: Row; active: boolean; pinned: boolean; onSelect: () => void; onTogglePin: () => void; indent?: boolean
}) {
  const hot = r.sdiBand === 'Distressed' || r.sdiBand === 'Hot'
  const c = heat(r.sdiBand, p)
  return (
    <div role="button" tabIndex={0} onClick={onSelect}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 7, height: 30, padding: `0 12px 0 ${indent ? 8 : 6}px`,
        cursor: 'pointer', background: active ? p.accentDim : 'transparent',
        borderLeft: `2px solid ${active ? p.accent : 'transparent'}`, transition: `background 120ms ${EASE}`,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = p.glass }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
      {/* Pin star — client favourites float to the Pinned folder */}
      <button onClick={e => { e.stopPropagation(); onTogglePin() }} title={pinned ? 'Unpin' : 'Pin'}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16, padding: 0, border: 'none', background: 'transparent', cursor: 'pointer', flexShrink: 0 }}>
        <Star style={{ width: 11.5, height: 11.5, color: pinned ? p.accent : p.t4, fill: pinned ? p.accent : 'none', opacity: pinned ? 1 : 0.3 }} />
      </button>
      <BrandLogo inst={r.inst} size={18} p={p} />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontSize: 11.5, fontWeight: active ? 700 : 600, color: active ? p.t1 : p.t2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: SANS }}>{r.inst.model}</span>
        <span style={{ fontSize: 9, color: p.t4, fontFamily: MONO, whiteSpace: 'nowrap' }}>{r.inst.variant}</span>
      </div>
      {/* SDI opportunity dot pulses on seller pressure (actionable); static otherwise — calm by default */}
      {hot
        ? <motion.span title={`SDI · ${r.sdiBand}`} style={{ width: 6, height: 6, borderRadius: '50%', background: c, flexShrink: 0 }}
            animate={{ scale: [1, 1.4, 1], boxShadow: [`0 0 0px ${c}00`, `0 0 6px ${c}`, `0 0 0px ${c}00`] }}
            transition={{ duration: 1.7, repeat: Infinity, ease: 'easeInOut' }} />
        : <span title={`SDI · ${r.sdiBand}`} style={{ width: 5, height: 5, borderRadius: '50%', background: c, flexShrink: 0 }} />}
      <div style={{ width: 46, height: 18, flexShrink: 0, opacity: 0.9 }}><Spark values={r.spark} p={p} w={46} h={18} /></div>
      <span style={{ width: 56, textAlign: 'right', fontSize: 11, fontWeight: 600, color: p.t1, fontFamily: MONO, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{fmtPrice(r.price)}</span>
      <span style={{ width: 48, textAlign: 'right', flexShrink: 0, fontSize: 10, fontWeight: 700, color: r.chg >= 0 ? p.up : p.down, fontFamily: MONO, fontVariantNumeric: 'tabular-nums' }}>{r.chg >= 0 ? '+' : ''}{r.chg.toFixed(2)}%</span>
    </div>
  )
}

function FolderHead({ p, open, onToggle, logo, label, count, avg }: {
  p: TerminalPalette; open: boolean; onToggle: () => void; logo: React.ReactNode; label: string; count: number; avg: number
}) {
  return (
    <button onClick={onToggle}
      style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, height: 28, padding: '0 12px', cursor: 'pointer', background: 'transparent', border: 'none', borderBottom: `1px solid ${p.hairline}` }}>
      <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.16, ease: EASE_ARR }} style={{ display: 'flex', color: p.t4 }}>
        <ChevronRight style={{ width: 12, height: 12 }} />
      </motion.span>
      {logo}
      <span style={{ flex: 1, fontSize: 10.5, fontWeight: 700, letterSpacing: '0.03em', color: p.t2, fontFamily: SANS, textAlign: 'left' }}>{label}</span>
      <span style={{ fontSize: 9, color: p.t4, fontFamily: MONO }}>{count}</span>
      <span style={{ width: 48, textAlign: 'right', fontSize: 9.5, fontWeight: 700, color: avg >= 0 ? p.up : p.down, fontFamily: MONO }}>{avg >= 0 ? '+' : ''}{avg.toFixed(2)}%</span>
    </button>
  )
}

export function Watchlist({ p, market, selectedId, onSelect }: {
  p: TerminalPalette; market: string; selectedId: string; onSelect: (inst: Instrument) => void
}) {
  const [query, setQuery] = useState('')
  const [grouped, setGrouped] = useState(true)
  const [collapsed, setCollapsed] = usePersistent<Record<string, boolean>>('cx.wl.collapsed', {})
  const [pinnedArr, setPinnedArr] = usePersistent<string[]>('cx.wl.pinned', [])

  const pinned = useMemo(() => new Set(pinnedArr), [pinnedArr])
  const togglePin = useCallback((id: string) =>
    setPinnedArr(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])), [setPinnedArr])
  const toggleFolder = useCallback((k: string) =>
    setCollapsed(prev => ({ ...prev, [k]: !prev[k] })), [setCollapsed])

  const rows: Row[] = useMemo(() => INSTRUMENTS.map(inst => {
    const q = quote(inst, market); const sdi = computeSdi(inst, market)
    return { inst, price: q.last, chg: q.changePct, spark: q.spark, sdiBand: sdi.band }
  }), [market])

  const filtered = rows.filter(r => `${r.inst.make} ${r.inst.model} ${r.inst.variant}`.toLowerCase().includes(query.toLowerCase()))
  const pinnedRows = useMemo(() => filtered.filter(r => pinned.has(r.inst.id)), [filtered, pinned])

  // Brand folders exclude pinned rows — a pinned instrument lives in the Pinned folder only.
  const folders = useMemo(() => {
    const map = new Map<string, Row[]>()
    for (const r of filtered) { if (pinned.has(r.inst.id)) continue; if (!map.has(r.inst.make)) map.set(r.inst.make, []); map.get(r.inst.make)!.push(r) }
    return [...map.entries()]
  }, [filtered, pinned])

  const renderRow = (r: Row, indent?: boolean) => (
    <Line key={r.inst.id} p={p} r={r} active={r.inst.id === selectedId} pinned={pinned.has(r.inst.id)}
      onSelect={() => onSelect(r.inst)} onTogglePin={() => togglePin(r.inst.id)} indent={indent} />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Search + view toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', flexShrink: 0 }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 7, padding: '6px 10px', background: p.inset, border: `1px solid ${p.border}`, borderRadius: 8 }}>
          <Search style={{ width: 12, height: 12, color: p.t4 }} />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search…"
            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 11.5, color: p.t1, fontFamily: SANS }} />
        </div>
        <button onClick={() => setGrouped(g => !g)} title={grouped ? 'Flat list' : 'Group by marque'}
          style={{ width: 28, height: 28, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', background: p.glass, border: `1px solid ${p.border}`, color: p.t3 }}>
          {grouped ? <Folder style={{ width: 13, height: 13 }} /> : <List style={{ width: 13, height: 13 }} />}
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {/* Pinned folder — client favourites, always on top */}
        {pinnedRows.length > 0 && (() => {
          const open = !collapsed['__pinned__']
          const avg = pinnedRows.reduce((s, r) => s + r.chg, 0) / pinnedRows.length
          return (
            <div>
              <FolderHead p={p} open={open} onToggle={() => toggleFolder('__pinned__')} count={pinnedRows.length} avg={avg} label="Pinned"
                logo={<Star style={{ width: 13, height: 13, color: p.accent, fill: p.accent }} />} />
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease: EASE_ARR }} style={{ overflow: 'hidden' }}>
                    {pinnedRows.map(r => renderRow(r, true))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )
        })()}

        {!grouped && filtered.filter(r => !pinned.has(r.inst.id)).map(r => renderRow(r))}

        {grouped && folders.map(([make, items], fi) => {
          const open = !collapsed[make]
          const avg = items.reduce((s, r) => s + r.chg, 0) / items.length
          return (
            <motion.div key={make} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(fi * 0.04, 0.3), type: 'spring', stiffness: 130, damping: 18 }}>
              <FolderHead p={p} open={open} onToggle={() => toggleFolder(make)} count={items.length} avg={avg} label={make}
                logo={<BrandLogo inst={items[0].inst} size={16} p={p} />} />
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease: EASE_ARR }} style={{ overflow: 'hidden' }}>
                    {items.map(r => renderRow(r, true))}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )
        })}

        {filtered.length === 0 && (
          <div style={{ padding: '24px 12px', textAlign: 'center' }}><Eyebrow p={p}>No matches</Eyebrow></div>
        )}
      </div>
    </div>
  )
}
