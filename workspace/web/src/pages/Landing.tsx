import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

const EXPO = [0.16, 1, 0.3, 1] as const
const HERO_IMG = 'https://i.pinimg.com/originals/8f/67/ad/8f67ad9d7fef82b5943608def344573b.jpg'
const AVATARS = ['E', 'M', 'A', 'J']
const AVATAR_COLORS = ['#6366f1', '#7c3aed', '#0891b2', '#059669']

const TIPOS = ['Todos', 'Ocasión', 'Km 0', 'Nuevo']
const PAISES = [
  { code: 'all', label: 'Todos los países' },
  { code: 'de',  label: '🇩🇪  Alemania' },
  { code: 'es',  label: '🇪🇸  España' },
  { code: 'fr',  label: '🇫🇷  Francia' },
  { code: 'nl',  label: '🇳🇱  Países Bajos' },
  { code: 'be',  label: '🇧🇪  Bélgica' },
  { code: 'ch',  label: '🇨🇭  Suiza' },
]
const MARCAS = [
  'Audi', 'BMW', 'Mercedes', 'Volkswagen', 'Toyota', 'Ford',
  'Renault', 'Peugeot', 'Seat', 'Skoda', 'Porsche', 'Volvo',
]
const PRECIOS = [
  { label: 'Sin límite',  value: '' },
  { label: 'Hasta 10.000 €', value: '10000' },
  { label: 'Hasta 20.000 €', value: '20000' },
  { label: 'Hasta 30.000 €', value: '30000' },
  { label: 'Hasta 50.000 €', value: '50000' },
  { label: 'Hasta 80.000 €', value: '80000' },
]

/* ── Glass select ──────────────────────────────────────────────────────────── */
function GlassSelect({
  label, options, value, onChange,
}: {
  label: string
  options: { label: string; value: string }[]
  value: string
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selected = options.find(o => o.value === value)

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [])

  return (
    <div ref={ref} style={{ position: 'relative', flex: 1 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 14px', height: 44, borderRadius: 10,
          background: 'rgba(255,255,255,0.06)',
          border: `1px solid ${open ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.10)'}`,
          cursor: 'pointer', fontFamily: 'inherit',
          transition: 'border-color 0.18s',
          gap: 8,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, overflow: 'hidden' }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.05em', textTransform: 'uppercase', lineHeight: 1 }}>
            {label}
          </span>
          <span style={{ fontSize: 13, fontWeight: 500, color: selected?.value ? '#fff' : 'rgba(255,255,255,0.55)', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
            {selected?.label ?? label}
          </span>
        </div>
        <svg width={12} height={12} viewBox="0 0 12 12" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.4)' }}>
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }}
            transition={{ duration: 0.16, ease: EXPO }}
            style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0, zIndex: 50,
              background: 'rgba(14,14,30,0.92)',
              backdropFilter: 'blur(24px) saturate(180%)',
              WebkitBackdropFilter: 'blur(24px) saturate(180%)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 12,
              boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
              overflow: 'hidden',
            }}
          >
            {options.map(opt => (
              <button
                key={opt.value}
                onClick={() => { onChange(opt.value); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '9px 14px', background: 'none', border: 'none',
                  cursor: 'pointer', fontFamily: 'inherit',
                  fontSize: 13, fontWeight: opt.value === value ? 600 : 400,
                  color: opt.value === value ? '#fff' : 'rgba(255,255,255,0.6)',
                  transition: 'background 0.12s, color 0.12s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.07)'; (e.currentTarget as HTMLElement).style.color = '#fff' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'none'; (e.currentTarget as HTMLElement).style.color = opt.value === value ? '#fff' : 'rgba(255,255,255,0.6)' }}
              >{opt.label}</button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Marca y modelo combined ───────────────────────────────────────────────── */
function MarcaModeloField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = MARCAS.filter(m => m.toLowerCase().startsWith(search.toLowerCase()))

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [])

  function openDropdown() {
    setOpen(true)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  return (
    <div ref={ref} style={{ position: 'relative', flex: 1.4 }}>
      <button
        onClick={openDropdown}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 14px', height: 44, borderRadius: 10,
          background: 'rgba(255,255,255,0.06)',
          border: `1px solid ${open ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.10)'}`,
          cursor: 'pointer', fontFamily: 'inherit',
          transition: 'border-color 0.18s', gap: 8,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1 }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.05em', textTransform: 'uppercase', lineHeight: 1 }}>
            Marca y modelo
          </span>
          <span style={{ fontSize: 13, fontWeight: value ? 500 : 400, color: value ? '#fff' : 'rgba(255,255,255,0.55)', lineHeight: 1.4 }}>
            {value || 'Cualquier marca'}
          </span>
        </div>
        <svg width={12} height={12} viewBox="0 0 12 12" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.4)' }}>
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.97 }}
            transition={{ duration: 0.16, ease: EXPO }}
            style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0, zIndex: 50,
              background: 'rgba(14,14,30,0.95)',
              backdropFilter: 'blur(24px) saturate(180%)',
              WebkitBackdropFilter: 'blur(24px) saturate(180%)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 12,
              boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
              overflow: 'hidden',
            }}
          >
            {/* Search inside dropdown */}
            <div style={{ padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
              <input
                ref={inputRef}
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Buscar marca..."
                style={{
                  width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 7, padding: '7px 10px', color: '#fff', fontSize: 13,
                  fontFamily: 'inherit', outline: 'none',
                }}
              />
            </div>
            {/* All option */}
            <button
              onClick={() => { onChange(''); setSearch(''); setOpen(false) }}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, color: !value ? '#fff' : 'rgba(255,255,255,0.55)', fontWeight: !value ? 600 : 400 }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.07)'; (e.currentTarget as HTMLElement).style.color = '#fff' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'none'; (e.currentTarget as HTMLElement).style.color = !value ? '#fff' : 'rgba(255,255,255,0.55)' }}
            >Cualquier marca</button>
            <div style={{ maxHeight: 180, overflowY: 'auto' }}>
              {filtered.map(m => (
                <button
                  key={m}
                  onClick={() => { onChange(m); setSearch(''); setOpen(false) }}
                  style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 14px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, color: m === value ? '#fff' : 'rgba(255,255,255,0.6)', fontWeight: m === value ? 600 : 400 }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.07)'; (e.currentTarget as HTMLElement).style.color = '#fff' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'none'; (e.currentTarget as HTMLElement).style.color = m === value ? '#fff' : 'rgba(255,255,255,0.6)' }}
                >{m}</button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ── Main ──────────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { isAuthenticated } = useAuthContext()
  const [navScrolled, setNavScrolled] = useState(false)
  const [query, setQuery] = useState('')
  const [tipo, setTipo] = useState('')
  const [marca, setMarca] = useState('')
  const [pais, setPais] = useState('')
  const [precio, setPrecio] = useState('')

  useEffect(() => {
    const fn = () => setNavScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  function handleEnter() { nav(isAuthenticated ? '/dashboard' : '/login') }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    nav('/dashboard')
  }

  /* Simulated result count based on active filters */
  const base = 1_550_000
  const filtered = Math.round(
    base
    * (tipo && tipo !== 'Todos' ? 0.35 : 1)
    * (marca ? 0.08 : 1)
    * (pais ? 0.22 : 1)
    * (precio ? 0.6 : 1)
  )
  const resultLabel = filtered.toLocaleString('es-ES')

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#07070f' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        height: 60, display: 'flex', alignItems: 'center',
        padding: '0 clamp(20px, 4vw, 48px)',
        transition: 'background 0.3s, border-color 0.3s',
        background: navScrolled ? 'rgba(7,7,15,0.75)' : 'transparent',
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
            <button key={l} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.55)', fontFamily: 'inherit', transition: 'color 0.18s' }}
              onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
              onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.55)')}
            >{l}</button>
          ))}
        </div>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12 }}>
          <button onClick={handleEnter} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.55)', fontFamily: 'inherit', transition: 'color 0.18s' }}
            onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
            onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.55)')}
          >Log In</button>
          <motion.button onClick={handleEnter} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.14, ease: EXPO }}
            style={{ padding: '7px 20px', borderRadius: 999, background: 'rgba(255,255,255,0.10)', border: '1px solid rgba(255,255,255,0.18)', backdropFilter: 'blur(12px)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >Sign In</motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>
        <img src={HERO_IMG} alt="" fetchPriority="high" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 40%' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(7,7,15,0.22) 0%, rgba(7,7,15,0.06) 28%, rgba(7,7,15,0.62) 68%, rgba(7,7,15,0.95) 100%)' }} />

        {/* Center content */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 clamp(16px,4vw,40px)', textAlign: 'center', paddingTop: 60 }}>

          {/* Social proof */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EXPO, delay: 0.1 }}
            style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 28 }}>
            <div style={{ display: 'flex' }}>
              {AVATARS.map((a, i) => (
                <div key={i} style={{ width: 30, height: 30, borderRadius: '50%', background: AVATAR_COLORS[i], border: '2px solid rgba(7,7,15,0.6)', marginLeft: i > 0 ? -8 : 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#fff', position: 'relative', zIndex: AVATARS.length - i }}>{a}</div>
              ))}
            </div>
            <span style={{ fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.75)' }}>
              1.550.000+ vehículos indexados en la UE
            </span>
          </motion.div>

          {/* ── SEARCH BAR ─────────────────────────────────────────────── */}
          <motion.form onSubmit={handleSearch} initial={{ opacity: 0, y: 14, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.55, ease: EXPO, delay: 0.22 }}
            style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: 560, borderRadius: 999, background: 'rgba(255,255,255,0.10)', backdropFilter: 'blur(24px) saturate(180%)', WebkitBackdropFilter: 'blur(24px) saturate(180%)', border: '1px solid rgba(255,255,255,0.18)', boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.14)', padding: '5px 5px 5px 20px', gap: 8 }}
          >
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth={2} strokeLinecap="round" style={{ flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="BMW Serie 3, Audi A4, Mercedes C..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 15, fontWeight: 400, color: '#fff', fontFamily: 'inherit' }} />
            <motion.button type="submit" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.12, ease: EXPO }}
              style={{ padding: '10px 22px', borderRadius: 999, flexShrink: 0, background: 'rgba(20,18,60,0.9)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', backdropFilter: 'blur(8px)' }}
            >Buscar →</motion.button>
          </motion.form>

          {/* ── FILTER BOX ─────────────────────────────────────────────── */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55, ease: EXPO, delay: 0.34 }}
            style={{ width: '100%', maxWidth: 560, marginTop: 8, borderRadius: 16, background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(32px) saturate(200%)', WebkitBackdropFilter: 'blur(32px) saturate(200%)', border: '1px solid rgba(255,255,255,0.12)', boxShadow: '0 16px 48px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.10)', padding: '14px 14px 12px' }}
          >
            {/* 4 filters in a row */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <GlassSelect
                label="Tipo"
                value={tipo}
                onChange={setTipo}
                options={TIPOS.map(t => ({ label: t, value: t === 'Todos' ? '' : t }))}
              />
              <MarcaModeloField value={marca} onChange={setMarca} />
              <GlassSelect
                label="País"
                value={pais}
                onChange={setPais}
                options={PAISES.map(p => ({ label: p.label, value: p.code === 'all' ? '' : p.code }))}
              />
              <GlassSelect
                label="Precio"
                value={precio}
                onChange={setPrecio}
                options={PRECIOS.map(p => ({ label: p.label, value: p.value }))}
              />
            </div>

            {/* Results CTA */}
            <motion.button
              onClick={handleSearch}
              whileHover={{ scale: 1.015, background: 'rgba(99,102,241,0.28)' }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.15, ease: EXPO }}
              style={{ width: '100%', padding: '11px 0', borderRadius: 10, background: 'rgba(99,102,241,0.18)', border: '1px solid rgba(99,102,241,0.3)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', letterSpacing: '-0.01em', transition: 'background 0.2s' }}
            >
              Mostrar {resultLabel} resultados
            </motion.button>
          </motion.div>

        </div>
      </div>

      <style>{`
        input::placeholder { color: rgba(255,255,255,0.38) !important; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 4px; }
      `}</style>
    </div>
  )
}
