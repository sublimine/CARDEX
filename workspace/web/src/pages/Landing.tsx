import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence, useScroll, useTransform, useReducedMotion } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'
import { BRANDS, type Brand, type Model } from '../data/catalog'
import LOGO_AR from '../data/logo-ar.json'
import LandingSections from './landing-sections'

const EXPO = [0.16, 1, 0.3, 1] as const
const HERO_IMG = '/hero-cardex.jpg'

/* ─── Source portals — one per country + AS24 global ──────────────────── */
interface Portal { name: string; favicon?: string; initial?: string; bg: string; border?: string; textColor?: string }
const PORTALS: Portal[] = [
  { name: 'AutoScout24', favicon: 'https://www.google.com/s2/favicons?domain=autoscout24.com&sz=128', bg: '#111', border: '#FFCD00' },
  { name: 'mobile.de',   favicon: 'https://www.google.com/s2/favicons?domain=mobile.de&sz=128',       bg: '#ff6600' },
  { name: 'coches.net',  favicon: 'https://www.google.com/s2/favicons?domain=coches.net&sz=128',      bg: '#e30613' },
  { name: 'La Centrale', favicon: 'https://www.google.com/s2/favicons?domain=lacentrale.fr&sz=128',   bg: '#c8102e' },
  { name: 'marktplaats', initial: 'M', bg: '#002b5c', textColor: '#4db8a4' },
  { name: '2dehands',    favicon: 'https://www.google.com/s2/favicons?domain=2dehands.be&sz=128',     bg: '#003a78' },
  { name: 'tutti.ch',    favicon: 'https://www.google.com/s2/favicons?domain=tutti.ch&sz=128',        bg: '#1a1a1a' },
]

/* ─── Countries with flag images ──────────────────────────────────────── */
const PAISES = [
  { code: '',   label: 'Todos los países', flag: '' },
  { code: 'de', label: 'Alemania',        flag: 'https://flagcdn.com/w40/de.png' },
  { code: 'es', label: 'España',          flag: 'https://flagcdn.com/w40/es.png' },
  { code: 'fr', label: 'Francia',         flag: 'https://flagcdn.com/w40/fr.png' },
  { code: 'nl', label: 'Países Bajos',    flag: 'https://flagcdn.com/w40/nl.png' },
  { code: 'be', label: 'Bélgica',         flag: 'https://flagcdn.com/w40/be.png' },
  { code: 'ch', label: 'Suiza',           flag: 'https://flagcdn.com/w40/ch.png' },
]

/* ─── Year + mileage domains ──────────────────────────────────────────── */
const CUR_YEAR = new Date().getFullYear()
const YEARS: number[] = Array.from({ length: CUR_YEAR - 1989 }, (_, i) => CUR_YEAR - i) // desc
const KM_MAX = 200_000          // top bucket is open-ended "200.000+"
const KM_STEP = 5_000
/* synthetic inventory density across 0..KM_MAX — drives the histogram cue (count is heuristic) */
const KM_DENSITY = [4, 8, 14, 22, 33, 46, 60, 73, 84, 93, 99, 100, 97, 90, 81, 71, 61, 52, 44, 36, 29, 23, 18, 13, 9, 6, 4, 3]

const fmt = (n: number) => n.toLocaleString('de-DE')

/* ─── Shared field styles (minimalist) ────────────────────────────────── */
function triggerStyle(open: boolean): React.CSSProperties {
  return {
    width: '100%', height: 46, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 14px', borderRadius: 10, gap: 8, cursor: 'pointer', fontFamily: 'inherit',
    background: open ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.05)',
    border: `1px solid ${open ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.09)'}`,
    transition: 'all 0.18s',
  }
}
const LABEL: React.CSSProperties = { fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.32)', letterSpacing: '0.08em', textTransform: 'uppercase', lineHeight: 1.1 }
const SECTION: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.5)', letterSpacing: '0.07em', textTransform: 'uppercase' }
function valueStyle(active: boolean): React.CSSProperties {
  return { fontSize: 13, fontWeight: active ? 600 : 400, color: active ? '#f8fafc' : 'rgba(255,255,255,0.42)', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }
}
function Chevron({ open }: { open: boolean }) {
  return (
    <svg width={11} height={11} viewBox="0 0 11 11" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.32)' }}>
      <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round" />
    </svg>
  )
}
function ClearDot({ onClick }: { onClick: (e: React.MouseEvent) => void }) {
  return (
    <div role="button" onClick={onClick}
      style={{ width: 18, height: 18, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: 'pointer' }}>
      <svg width={8} height={8} viewBox="0 0 8 8"><path d="M1 1l6 6M7 1L1 7" stroke="rgba(255,255,255,0.75)" strokeWidth={1.5} strokeLinecap="round" /></svg>
    </div>
  )
}

/* ─── Small car icon (logo fallback) ──────────────────────────────────── */
function CarIcon({ size = 16, color = 'rgba(255,255,255,0.5)' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 17H3a2 2 0 01-2-2v-4l2-5h14l2 5v4a2 2 0 01-2 2h-2" />
      <circle cx="7.5" cy="17.5" r="2.5" />
      <circle cx="16.5" cy="17.5" r="2.5" />
    </svg>
  )
}

/* ─── Brand logo — normalized to equal OPTICAL size across all marks ───── */
const AR_MAP = LOGO_AR as Record<string, number>
const LOGO_DENSE = new Set(['pagani.svg', 'wiesmann.svg', 'abarth.svg', 'lexus.svg', 'lancia.svg', 'alpine.svg', 'koenigsegg.svg'])
const LOGO_THIN = new Set(['lucid.svg', 'rivian.svg', 'jaguar.svg', 'hummer.svg'])

function logoImgStyle(logo: string, box: number): React.CSSProperties {
  const base: React.CSSProperties = { width: 'auto', height: 'auto', objectFit: 'contain', filter: 'brightness(0) invert(1)' }
  if (logo.includes('simpleicons')) {
    return { ...base, maxWidth: box * 0.64, maxHeight: box * 0.64 }
  }
  const file = logo.split('/').pop() || ''
  const ar = AR_MAP[file] ?? 1
  let maxW: number, maxH: number, scale = 1
  if (ar > 2.5) { maxW = box * 0.94; maxH = box * (ar > 7 ? 0.34 : 0.42) }      // wide wordmark
  else if (ar > 1.4) { maxW = box * 0.88; maxH = box * 0.56 }                   // landscape
  else if (ar < 0.7) { maxW = box * 0.5; maxH = box * 0.78 }                    // tall
  else { maxW = box * 0.68; maxH = box * 0.68 }                                 // square emblem
  if (LOGO_DENSE.has(file)) scale = 0.9
  if (LOGO_THIN.has(file)) scale = 1.1
  return { ...base, maxWidth: maxW, maxHeight: maxH, transform: scale !== 1 ? `scale(${scale})` : undefined }
}

function BrandLogo({ brand, size = 34 }: { brand: Brand; size?: number }) {
  const [failed, setFailed] = useState(false)
  if (!brand.logo || failed) {
    return (
      <div style={{ width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CarIcon size={Math.round(size * 0.46)} color="rgba(255,255,255,0.34)" />
      </div>
    )
  }
  return (
    <div style={{ width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
      <img src={brand.logo} alt={brand.name} onError={() => setFailed(true)} style={logoImgStyle(brand.logo, size)} />
    </div>
  )
}

/* ─── Minimalist glass overlay ─────────────────────────────────────────── */
const PANEL_GLASS: React.CSSProperties = {
  position: 'fixed',
  zIndex: 500,
  background: 'rgba(9,8,20,0.74)',
  backdropFilter: 'blur(40px) saturate(150%)',
  WebkitBackdropFilter: 'blur(40px) saturate(150%)',
  border: '1px solid rgba(255,255,255,0.07)',
  borderRadius: 14,
  boxShadow: '0 24px 70px rgba(0,0,0,0.5)',
  overflow: 'hidden',
}
const SEL_BG = 'rgba(255,255,255,0.09)'
const SEL_BORDER = 'rgba(255,255,255,0.14)'
const HOVER_BG = 'rgba(255,255,255,0.05)'
const DIVIDER = 'rgba(255,255,255,0.07)'

/* ─── Centered modal shell ─────────────────────────────────────────────── */
function CenterModal({ id, width, children }: { id: string; width: number; children: React.ReactNode }) {
  // Portal to <body> so the modal is centered on the viewport regardless of any
  // transformed ancestor (the right-side filter panel uses a transform).
  return createPortal(
    <div id={id} style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 500, width: `min(${width}px, 92vw)` }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 6 }}
        transition={{ duration: 0.2, ease: EXPO }}
        style={{ ...PANEL_GLASS, position: 'relative', width: '100%' }}
      >
        {children}
      </motion.div>
    </div>,
    document.body
  )
}
function ModalHeader({ title, onClose, onBack }: { title: React.ReactNode; onClose: () => void; onBack?: () => void }) {
  return (
    <div style={{ padding: '13px 14px 11px', borderBottom: `1px solid ${DIVIDER}`, display: 'flex', alignItems: 'center', gap: 10 }}>
      {onBack && (
        <button onClick={onBack} style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(255,255,255,0.05)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
          <svg width={11} height={11} viewBox="0 0 12 12"><path d="M8 2L4 6l4 4" stroke="rgba(255,255,255,0.6)" strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      )}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.85)', letterSpacing: '-0.01em' }}>{title}</div>
      <button onClick={onClose} style={{ width: 24, height: 24, borderRadius: 6, background: 'rgba(255,255,255,0.05)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}>
        <svg width={10} height={10} viewBox="0 0 10 10"><path d="M1 1l8 8M9 1L1 9" stroke="rgba(255,255,255,0.5)" strokeWidth={1.5} strokeLinecap="round" /></svg>
      </button>
    </div>
  )
}
function SearchBox({ value, onChange, placeholder, inputRef }: { value: string; onChange: (v: string) => void; placeholder: string; inputRef?: React.RefObject<HTMLInputElement> }) {
  return (
    <div style={{ padding: '10px 14px 6px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, padding: '7px 12px' }}>
        <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={2} strokeLinecap="round"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
        <input ref={inputRef} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
          style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#fff', fontFamily: 'inherit' }} />
        {value && <button onClick={() => onChange('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.35)', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>}
      </div>
    </div>
  )
}
function FooterActions({ onClear, onDone }: { onClear: () => void; onDone: () => void }) {
  return (
    <div style={{ padding: '12px 16px 16px', display: 'flex', gap: 8, borderTop: `1px solid ${DIVIDER}` }}>
      <button onClick={onClear} style={{ flex: '0 0 auto', padding: '10px 16px', borderRadius: 9, background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.6)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>Limpiar</button>
      <button onClick={onDone} style={{ flex: 1, padding: '10px 0', borderRadius: 9, background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.3)', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>Listo</button>
    </div>
  )
}
function useOutside(open: boolean, panelId: string, triggerRef: React.RefObject<HTMLElement>, close: () => void) {
  useEffect(() => {
    const fn = (e: MouseEvent) => {
      const panel = document.getElementById(panelId)
      if (!panel?.contains(e.target as Node) && !triggerRef.current?.contains(e.target as Node)) close()
    }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open, panelId, triggerRef, close])
}

/* ─── Marca y Modelo — 3-step picker (brand → model → submodel) ────────── */
interface MMState { brand: Brand | null; model: Model | null; submodel: string }

function MarcaModeloField({ value, onChange }: { value: MMState; onChange: (v: MMState) => void }) {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<'brand' | 'model' | 'submodel'>('brand')
  const [search, setSearch] = useState('')
  const triggerRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const close = useCallback(() => { setOpen(false); setSearch(''); setStep('brand') }, [])
  useOutside(open, 'mm-panel', triggerRef, close)
  useEffect(() => { if (open) setTimeout(() => searchRef.current?.focus(), 80) }, [open, step])

  const q = search.toLowerCase()
  const filteredBrands = BRANDS.filter(b => b.name.toLowerCase().includes(q))
  const filteredModels = value.brand ? value.brand.models.filter(m => m.name.toLowerCase().includes(q)) : []
  const filteredSubs = value.model ? value.model.submodels.filter(s => s.toLowerCase().includes(q)) : []

  const label = !value.brand ? 'Cualquier marca'
    : !value.model ? value.brand.name
    : !value.submodel ? `${value.brand.name} · ${value.model.name}`
    : `${value.brand.name} · ${value.model.name} · ${value.submodel}`

  function selectBrand(b: Brand) { onChange({ brand: b, model: null, submodel: '' }); setSearch(''); setStep('model') }
  function selectModel(m: Model) {
    onChange({ brand: value.brand, model: m, submodel: '' }); setSearch('')
    if (m.submodels.length > 0) setStep('submodel'); else close()
  }

  const title = step === 'brand' ? 'Selecciona una marca'
    : step === 'model' ? `${value.brand?.name} — modelo`
    : `${value.model?.name} — versión`

  return (
    <>
      <button ref={triggerRef}
        onClick={() => { setOpen(v => !v); setStep(value.submodel ? 'submodel' : value.brand ? 'model' : 'brand') }}
        style={triggerStyle(open)}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={LABEL}>Marca y modelo</span>
          <span style={valueStyle(!!value.brand)}>{label}</span>
        </div>
        {value.brand
          ? <ClearDot onClick={e => { e.stopPropagation(); onChange({ brand: null, model: null, submodel: '' }); close() }} />
          : <Chevron open={open} />}
      </button>

      <AnimatePresence>
        {open && (
          <CenterModal id="mm-panel" width={560}>
            <ModalHeader
              title={<>
                {step !== 'brand' && value.brand && <BrandLogo brand={value.brand} size={22} />}
                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
              </>}
              onClose={close}
              onBack={step === 'brand' ? undefined : () => {
                if (step === 'submodel') { setStep('model'); setSearch('') }
                else { setStep('brand'); setSearch(''); onChange({ brand: null, model: null, submodel: '' }) }
              }}
            />
            <SearchBox value={search} onChange={setSearch} inputRef={searchRef}
              placeholder={step === 'brand' ? 'Buscar marca…' : step === 'model' ? 'Buscar modelo…' : 'Buscar versión…'} />

            {step === 'brand' && (
              <div style={{ padding: '4px 14px 14px', maxHeight: '56vh', overflowY: 'auto' }}>
                <button onClick={() => { onChange({ brand: null, model: null, submodel: '' }); close() }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '8px 10px', borderRadius: 9, marginBottom: 8, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                  onMouseEnter={e => (e.currentTarget.style.background = HOVER_BG)} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <div style={{ width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><CarIcon size={15} color="rgba(255,255,255,0.5)" /></div>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.6)' }}>Cualquier marca</span>
                </button>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 6 }}>
                  {filteredBrands.map(b => {
                    const sel = value.brand?.name === b.name
                    return (
                      <motion.button key={b.name} onClick={() => selectBrand(b)} whileTap={{ scale: 0.97 }} transition={{ duration: 0.12 }}
                        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, padding: '11px 6px 8px', background: sel ? SEL_BG : 'transparent', border: `1px solid ${sel ? SEL_BORDER : 'transparent'}`, borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.14s, border-color 0.14s' }}
                        onMouseEnter={e => { if (!sel) e.currentTarget.style.background = HOVER_BG }}
                        onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent' }}>
                        <BrandLogo brand={b} size={30} />
                        <span style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.62)', textAlign: 'center', lineHeight: 1.2 }}>{b.name}</span>
                      </motion.button>
                    )
                  })}
                </div>
              </div>
            )}

            {step === 'model' && (
              <div style={{ maxHeight: '56vh', overflowY: 'auto', padding: '4px 14px 14px' }}>
                <button onClick={() => { onChange({ brand: value.brand, model: null, submodel: '' }); close() }}
                  style={{ display: 'flex', width: '100%', padding: '9px 12px', marginBottom: 3, background: 'transparent', border: 'none', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit' }}
                  onMouseEnter={e => (e.currentTarget.style.background = HOVER_BG)} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.6)' }}>Todos los modelos de {value.brand?.name}</span>
                </button>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                  {filteredModels.map(m => {
                    const sel = value.model?.name === m.name
                    return (
                      <button key={m.name} onClick={() => selectModel(m)}
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: sel ? SEL_BG : 'transparent', border: 'none', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left', gap: 6 }}
                        onMouseEnter={e => { if (!sel) e.currentTarget.style.background = HOVER_BG }} onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent' }}>
                        <span style={{ fontSize: 13, fontWeight: sel ? 600 : 400, color: sel ? '#fff' : 'rgba(255,255,255,0.66)' }}>{m.name}</span>
                        {m.submodels.length > 0 && <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.22)', flexShrink: 0 }}>{m.submodels.length}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {step === 'submodel' && (
              <div style={{ maxHeight: '56vh', overflowY: 'auto', padding: '4px 14px 14px' }}>
                <button onClick={() => { onChange({ brand: value.brand, model: value.model, submodel: '' }); close() }}
                  style={{ display: 'flex', width: '100%', padding: '9px 12px', marginBottom: 3, background: 'transparent', border: 'none', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit' }}
                  onMouseEnter={e => (e.currentTarget.style.background = HOVER_BG)} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.6)' }}>Todas las versiones de {value.model?.name}</span>
                </button>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                  {filteredSubs.map(s => {
                    const sel = value.submodel === s
                    return (
                      <button key={s} onClick={() => { onChange({ brand: value.brand, model: value.model, submodel: s }); close() }}
                        style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', background: sel ? SEL_BG : 'transparent', border: 'none', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}
                        onMouseEnter={e => { if (!sel) e.currentTarget.style.background = HOVER_BG }} onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent' }}>
                        <span style={{ fontSize: 13, fontWeight: sel ? 600 : 400, color: sel ? '#fff' : 'rgba(255,255,255,0.66)' }}>{s}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </CenterModal>
        )}
      </AnimatePresence>
    </>
  )
}

/* ─── Year column — type-or-pick ──────────────────────────────────────── */
function YearColumn({ heading, value, onChange, options }: { heading: string; value: number | null; onChange: (y: number | null) => void; options: number[] }) {
  const [text, setText] = useState('')
  const typed = text.replace(/\D/g, '')
  const list = options.filter(y => !typed || String(y).includes(typed))
  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <span style={{ ...LABEL, marginBottom: 6 }}>{heading}</span>
      <input
        value={text || (value ?? '')}
        onChange={e => { const v = e.target.value.replace(/\D/g, '').slice(0, 4); setText(v); onChange(v.length === 4 ? Number(v) : null) }}
        inputMode="numeric" placeholder="—"
        style={{ height: 40, borderRadius: 9, padding: '0 12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)', color: '#fff', fontSize: 14, fontWeight: 600, fontFamily: 'inherit', outline: 'none', width: '100%' }} />
      <div style={{ marginTop: 6, maxHeight: 152, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
        {list.map(y => {
          const sel = value === y
          return (
            <button key={y} onClick={() => { onChange(y); setText('') }}
              style={{ textAlign: 'left', padding: '7px 12px', borderRadius: 7, background: sel ? SEL_BG : 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: sel ? 600 : 400, color: sel ? '#fff' : 'rgba(255,255,255,0.6)' }}
              onMouseEnter={e => { if (!sel) e.currentTarget.style.background = HOVER_BG }} onMouseLeave={e => { if (!sel) e.currentTarget.style.background = 'transparent' }}>
              {y}
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ─── Año y kilómetros — one field, one widget with both ranges ────────── */
function AnoKmField({ minY, maxY, kmMin, kmMax, onYear, onKm }: {
  minY: number | null; maxY: number | null; kmMin: number; kmMax: number;
  onYear: (lo: number | null, hi: number | null) => void; onKm: (lo: number, hi: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [drag, setDrag] = useState<null | 'min' | 'max'>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const close = useCallback(() => setOpen(false), [])
  useOutside(open, 'anokm-panel', triggerRef, close)

  const minF = kmMin / KM_MAX, maxF = kmMax / KM_MAX
  const anoActive = minY != null || maxY != null
  const kmActive = kmMin > 0 || kmMax < KM_MAX
  const active = anoActive || kmActive
  const maxLabel = kmMax >= KM_MAX ? `${fmt(KM_MAX)}+` : fmt(kmMax)

  const anoTxt = !anoActive ? null : (minY != null && maxY != null ? `${minY}–${maxY}` : minY != null ? `desde ${minY}` : `hasta ${maxY}`)
  const kmTxt = !kmActive ? null : `${fmt(kmMin)}–${maxLabel} km`
  const label = [anoTxt, kmTxt].filter(Boolean).join('  ·  ') || 'Cualquiera'

  const setLo = (y: number | null) => onYear(y, maxY != null && y != null && y > maxY ? y : maxY)
  const setHi = (y: number | null) => onYear(minY != null && y != null && y < minY ? y : minY, y)

  useEffect(() => {
    if (!drag) return
    const move = (e: PointerEvent) => {
      const r = trackRef.current?.getBoundingClientRect(); if (!r) return
      const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
      const km = Math.round((f * KM_MAX) / KM_STEP) * KM_STEP
      if (drag === 'min') onKm(Math.min(km, kmMax - KM_STEP), kmMax)
      else onKm(kmMin, Math.max(km, kmMin + KM_STEP))
    }
    const up = () => setDrag(null)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [drag, kmMin, kmMax, onKm])

  const inv = Math.round(KM_DENSITY.reduce((acc, d, i) => {
    const c = (i + 0.5) / KM_DENSITY.length
    return acc + (c >= minF && c <= maxF ? d : 0)
  }, 0) / KM_DENSITY.reduce((a, b) => a + b, 0) * 1_550_000)

  const clearAll = () => { onYear(null, null); onKm(0, KM_MAX) }

  return (
    <>
      <button ref={triggerRef} onClick={() => setOpen(v => !v)} style={triggerStyle(open)}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={LABEL}>Año y kilómetros</span>
          <span style={valueStyle(active)}>{label}</span>
        </div>
        {active
          ? <ClearDot onClick={e => { e.stopPropagation(); clearAll(); close() }} />
          : <Chevron open={open} />}
      </button>

      <AnimatePresence>
        {open && (
          <CenterModal id="anokm-panel" width={500}>
            <ModalHeader title="Año y kilómetros" onClose={close} />
            <div style={{ maxHeight: '74vh', overflowY: 'auto' }}>
              {/* ── Año ── */}
              <div style={{ padding: '14px 18px 4px' }}>
                <div style={{ ...SECTION, marginBottom: 12 }}>Año de matriculación</div>
                <div style={{ display: 'flex', gap: 12 }}>
                  <YearColumn heading="Desde" value={minY} onChange={setLo} options={maxY != null ? YEARS.filter(y => y <= maxY) : YEARS} />
                  <div style={{ width: 1, background: DIVIDER }} />
                  <YearColumn heading="Hasta" value={maxY} onChange={setHi} options={minY != null ? YEARS.filter(y => y >= minY) : YEARS} />
                </div>
              </div>

              <div style={{ height: 1, background: DIVIDER, margin: '14px 0 0' }} />

              {/* ── Kilómetros ── */}
              <div style={{ padding: '16px 20px 6px' }}>
                <div style={{ ...SECTION, marginBottom: 14 }}>Kilómetros</div>
                <div ref={trackRef} style={{ position: 'relative', height: 72, touchAction: 'none' }}>
                  <div style={{ position: 'absolute', inset: '0 0 8px 0', display: 'flex', alignItems: 'flex-end', gap: 2 }}>
                    {KM_DENSITY.map((d, i) => {
                      const c = (i + 0.5) / KM_DENSITY.length
                      const on = c >= minF && c <= maxF
                      return <div key={i} style={{ flex: 1, height: `${d}%`, borderRadius: '2px 2px 0 0', background: on ? 'rgba(129,140,248,0.6)' : 'rgba(255,255,255,0.07)', transition: 'background 0.12s' }} />
                    })}
                  </div>
                  <div style={{ position: 'absolute', left: 0, right: 0, bottom: 5, height: 3, background: 'rgba(255,255,255,0.1)', borderRadius: 2 }} />
                  <div style={{ position: 'absolute', bottom: 5, height: 3, left: `${minF * 100}%`, width: `${(maxF - minF) * 100}%`, background: 'rgba(129,140,248,0.85)', borderRadius: 2 }} />
                  {(['min', 'max'] as const).map(h => {
                    const f = h === 'min' ? minF : maxF
                    return (
                      <div key={h} onPointerDown={e => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); setDrag(h) }}
                        style={{ position: 'absolute', bottom: -1, left: `${f * 100}%`, transform: 'translateX(-50%)', width: 16, height: 16, borderRadius: '50%', background: '#0b0a1e', border: `2px solid ${drag === h ? '#c7d2fe' : 'rgba(165,180,252,0.95)'}`, boxShadow: '0 2px 8px rgba(0,0,0,0.55)', cursor: drag === h ? 'grabbing' : 'grab', touchAction: 'none', zIndex: 2 }}>
                        <svg width={8} height={8} viewBox="0 0 8 8" style={{ position: 'absolute', inset: 2, opacity: 0.7 }}><path d="M3 1L1 4l2 3M5 1l2 3-2 3" stroke="#a5b4fc" strokeWidth={1} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      </div>
                    )
                  })}
                </div>
                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', textAlign: 'center', marginTop: 4 }}>≈ {fmt(inv)} coches en este rango</div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, paddingTop: 10 }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ ...LABEL, display: 'block', marginBottom: 6 }}>Desde</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 40, borderRadius: 9, padding: '0 12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
                      <input value={fmt(kmMin)} onChange={e => { const v = Number(e.target.value.replace(/\D/g, '')) || 0; onKm(Math.min(v, kmMax - KM_STEP), kmMax) }}
                        inputMode="numeric" style={{ flex: 1, minWidth: 0, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontWeight: 600, fontFamily: 'inherit' }} />
                      <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>km</span>
                    </div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ ...LABEL, display: 'block', marginBottom: 6 }}>Hasta</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, height: 40, borderRadius: 9, padding: '0 12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
                      <input value={maxLabel} onChange={e => { const raw = e.target.value.replace(/\D/g, ''); const v = raw ? Number(raw) : KM_MAX; onKm(kmMin, Math.max(Math.min(v, KM_MAX), kmMin + KM_STEP)) }}
                        inputMode="numeric" style={{ flex: 1, minWidth: 0, background: 'none', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontWeight: 600, fontFamily: 'inherit' }} />
                      <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>km</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <FooterActions onClear={clearAll} onDone={close} />
          </CenterModal>
        )}
      </AnimatePresence>
    </>
  )
}

/* ─── País — minimalist inline select ──────────────────────────────────── */
function PaisSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const sel = PAISES.find(p => p.code === value) ?? PAISES[0]
  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open])
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={() => setOpen(v => !v)} style={triggerStyle(open)}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={LABEL}>País</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            {sel.flag && <img src={sel.flag} alt="" style={{ width: 18, height: 13, borderRadius: 2, objectFit: 'cover', flexShrink: 0 }} />}
            <span style={valueStyle(value !== '')}>{sel.label}</span>
          </div>
        </div>
        <Chevron open={open} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 6, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 4, scale: 0.97 }} transition={{ duration: 0.16, ease: EXPO }}
            style={{ ...PANEL_GLASS, position: 'absolute', top: 'calc(100% + 8px)', left: 0, minWidth: '100%', zIndex: 300, padding: 4 }}>
            {PAISES.map(p => {
              const a = p.code === value
              return (
                <button key={p.code} onClick={() => { onChange(p.code); setOpen(false) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 8, background: a ? SEL_BG : 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: a ? 600 : 400, color: a ? '#fff' : 'rgba(255,255,255,0.62)', whiteSpace: 'nowrap' }}
                  onMouseEnter={e => { if (!a) e.currentTarget.style.background = HOVER_BG }} onMouseLeave={e => { if (!a) e.currentTarget.style.background = 'none' }}>
                  {p.flag ? <img src={p.flag} alt="" style={{ width: 20, height: 14, borderRadius: 2, objectFit: 'cover' }} /> : <span style={{ width: 20 }} />}
                  <span>{p.label}</span>
                </button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ─── Main ─────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { isAuthenticated } = useAuthContext()
  const [navScrolled, setNavScrolled] = useState(false)
  const [query, setQuery] = useState('')
  const [marca, setMarca] = useState<MMState>({ brand: null, model: null, submodel: '' })
  const [pais, setPais] = useState('')
  const [anoMin, setAnoMin] = useState<number | null>(null)
  const [anoMax, setAnoMax] = useState<number | null>(null)
  const [kmMin, setKmMin] = useState(0)
  const [kmMax, setKmMax] = useState(KM_MAX)

  useEffect(() => {
    const fn = () => setNavScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  const heroRef = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const { scrollYProgress: heroP } = useScroll({ target: heroRef, offset: ['start start', 'end start'] })
  const heroY = useTransform(heroP, [0, 1], ['0%', '15%'])
  const heroScale = useTransform(heroP, [0, 1], [1, 1.1])
  const heroFade = useTransform(heroP, [0, 0.8], [1, 0])

  function handleEnter() { nav(isAuthenticated ? '/dashboard' : '/login') }
  function handleSearch(e: React.FormEvent) { e.preventDefault(); nav('/dashboard') }

  const count = Math.round(
    1_550_000
    * (marca.brand ? 0.065 : 1)
    * (marca.model ? 0.18 : 1)
    * (marca.submodel ? 0.42 : 1)
    * (pais ? 0.22 : 1)
    * (anoMin != null || anoMax != null ? 0.5 : 1)
    * (kmMin > 0 || kmMax < KM_MAX ? 0.55 : 1)
  )

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#07070f' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 400, height: 60, display: 'flex', alignItems: 'center',
        padding: '0 clamp(20px,4vw,48px)', transition: 'background 0.3s, border-color 0.3s',
        background: navScrolled ? 'rgba(7,7,15,0.8)' : 'transparent',
        backdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
        WebkitBackdropFilter: navScrolled ? 'blur(20px) saturate(180%)' : 'none',
        borderBottom: navScrolled ? '1px solid rgba(255,255,255,0.07)' : '1px solid transparent',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg,#6366f1,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 14px rgba(99,102,241,0.4)' }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, background: 'rgba(255,255,255,0.92)' }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.13em', background: 'linear-gradient(120deg,#c4b5fd,#818cf8,#67e8f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>CARDEX</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 36 }}>
          {['Platform', 'Coverage', 'Pricing'].map(l => (
            <button key={l} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.5)', fontFamily: 'inherit', transition: 'color 0.18s' }}
              onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')} onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)')}>{l}</button>
          ))}
        </div>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12 }}>
          <button onClick={handleEnter} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.5)', fontFamily: 'inherit', transition: 'color 0.18s' }}
            onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')} onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)')}>Log In</button>
          <motion.button onClick={handleEnter} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.14, ease: EXPO }}
            style={{ padding: '7px 20px', borderRadius: 999, background: 'rgba(255,255,255,0.09)', border: '1px solid rgba(255,255,255,0.16)', backdropFilter: 'blur(12px)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>Sign In</motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div ref={heroRef} style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>
        {/* cinematic image — flipped horizontally, parallax wrapper */}
        <motion.div style={{ position: 'absolute', inset: '-7% 0 0 0', y: reduced ? 0 : heroY, scale: reduced ? 1 : heroScale, willChange: 'transform' }}>
          <img src={HERO_IMG} alt="" fetchPriority="high" style={{ width: '100%', height: '107%', objectFit: 'cover', objectPosition: 'center 60%', transform: 'scaleX(-1)' }} />
        </motion.div>
        {/* grades: bottom fade + left/right scrim for legibility */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(7,7,15,0.34) 0%, rgba(7,7,15,0.05) 28%, rgba(7,7,15,0.5) 72%, #07070f 100%)' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, rgba(7,7,15,0.72) 0%, rgba(7,7,15,0.2) 32%, transparent 50%, rgba(7,7,15,0.4) 100%)' }} />

        <motion.div style={{ position: 'absolute', inset: 0, opacity: reduced ? 1 : heroFade, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'clamp(24px,5vw,80px)', padding: '88px clamp(20px,5vw,72px) 64px', pointerEvents: 'none' }}>
          {/* LEFT — editorial title over the image */}
          <div style={{ pointerEvents: 'auto', maxWidth: 'min(640px, 56vw)', flexShrink: 1, minWidth: 0 }}>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EXPO, delay: 0.1 }}
              style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'rgba(196,181,253,0.9)' }}>
              Inteligencia · Mercado · 6 países UE
            </motion.div>
            <motion.h1 initial={{ opacity: 0, y: 26 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.85, ease: EXPO, delay: 0.2 }}
              style={{ margin: '18px 0 0', fontSize: 'clamp(2.7rem,1.3rem+4.9vw,5.4rem)', lineHeight: 0.97, fontWeight: 700, letterSpacing: '-0.045em', color: '#fff' }}>
              La biblia del<br />coche usado<br /><span style={{ background: 'linear-gradient(120deg,#c4b5fd,#818cf8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>en Europa.</span>
            </motion.h1>
            <motion.p initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EXPO, delay: 0.36 }}
              style={{ margin: '24px 0 0', maxWidth: '46ch', fontSize: 'clamp(1rem,0.94rem+0.32vw,1.2rem)', lineHeight: 1.6, color: 'rgba(255,255,255,0.72)' }}>
              Indexamos, verificamos y deduplicamos el inventario de seis mercados. Una sola plataforma para el profesional que mueve coches entre fronteras.
            </motion.p>
          </div>

          {/* RIGHT — narrow glass search panel (more image than panel) */}
          <motion.aside initial={{ opacity: 0, x: 28 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6, ease: EXPO, delay: 0.25 }}
            style={{
              pointerEvents: 'auto', position: 'relative', boxSizing: 'border-box', textAlign: 'left', flexShrink: 0,
              width: 'clamp(318px, 25vw, 356px)', maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 9,
              padding: '18px 18px 15px', borderRadius: 22,
              background: 'linear-gradient(160deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02) 64%)',
              backdropFilter: 'blur(40px) saturate(180%)', WebkitBackdropFilter: 'blur(40px) saturate(180%)',
              border: '1px solid rgba(255,255,255,0.14)',
              boxShadow: '0 30px 80px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.28)',
            }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.16em', color: 'rgba(196,181,253,0.9)', textTransform: 'uppercase', marginBottom: 1 }}>Busca en 6 países</div>
            <form onSubmit={handleSearch} style={{ display: 'flex', alignItems: 'center', gap: 9, height: 44, padding: '0 13px', borderRadius: 11, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth={2} strokeLinecap="round" style={{ flexShrink: 0 }}><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
              <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="BMW Serie 3, Audi A4…"
                style={{ flex: 1, minWidth: 0, background: 'none', border: 'none', outline: 'none', fontSize: 14, color: '#fff', fontFamily: 'inherit' }} />
            </form>
            <MarcaModeloField value={marca} onChange={setMarca} />
            <PaisSelect value={pais} onChange={setPais} />
            <AnoKmField
              minY={anoMin} maxY={anoMax} kmMin={kmMin} kmMax={kmMax}
              onYear={(lo, hi) => { setAnoMin(lo); setAnoMax(hi) }}
              onKm={(lo, hi) => { setKmMin(lo); setKmMax(hi) }}
            />
            <motion.button onClick={handleSearch} whileHover={{ scale: 1.012 }} whileTap={{ scale: 0.985 }} transition={{ duration: 0.14, ease: EXPO }}
              style={{ width: '100%', padding: '12px 0', borderRadius: 11, background: 'linear-gradient(120deg,#6366f1,#7c3aed)', border: 'none', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', letterSpacing: '-0.01em', marginTop: 2, boxShadow: '0 8px 28px rgba(99,102,241,0.32)' }}>
              Mostrar {count.toLocaleString('de-DE')} resultados
            </motion.button>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, paddingTop: 8, marginTop: 2, borderTop: `1px solid ${DIVIDER}` }}>
              <div style={{ display: 'flex' }}>
                {PORTALS.slice(0, 6).map((p, i) => (
                  <div key={p.name} title={p.name}
                    style={{ width: 22, height: 22, borderRadius: 6, background: p.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: i > 0 ? -5 : 0, boxShadow: '0 4px 12px rgba(0,0,0,0.55)', position: 'relative', zIndex: PORTALS.length - i, flexShrink: 0, border: `1.5px solid ${p.border ?? 'rgba(255,255,255,0.1)'}`, transform: 'rotate(8deg)', overflow: 'hidden' }}>
                    {p.favicon
                      ? <img src={p.favicon} alt={p.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                      : <span style={{ fontSize: 9, fontWeight: 800, color: p.textColor ?? '#fff', lineHeight: 1, fontFamily: 'Inter, sans-serif' }}>{p.initial}</span>}
                  </div>
                ))}
              </div>
              <span style={{ fontSize: 11, fontWeight: 500, color: 'rgba(255,255,255,0.45)', whiteSpace: 'nowrap' }}>28.000+ dealers</span>
            </div>
          </motion.aside>
        </motion.div>

        {/* scroll cue */}
        <motion.div aria-hidden style={{ position: 'absolute', bottom: 22, left: '50%', x: '-50%', opacity: reduced ? 1 : heroFade }}>
          <motion.div animate={{ y: [0, 7, 0] }} transition={{ duration: 1.8, ease: 'easeInOut', repeat: Infinity }}
            style={{ width: 22, height: 36, borderRadius: 12, border: '1.5px solid rgba(255,255,255,0.3)', display: 'flex', justifyContent: 'center', paddingTop: 7 }}>
            <div style={{ width: 3, height: 7, borderRadius: 2, background: 'rgba(255,255,255,0.6)' }} />
          </motion.div>
        </motion.div>
      </div>

      {/* ── SCROLL NARRATIVE ───────────────────────────────────────────── */}
      <LandingSections onEnter={handleEnter} />

      <style>{`
        input::placeholder { color: rgba(255,255,255,0.33) !important; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 4px; }
      `}</style>
    </div>
  )
}
