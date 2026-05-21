import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

const EXPO   = [0.16, 1, 0.3, 1] as const
const SPRING = { type: 'spring', stiffness: 380, damping: 30 } as const

const HERO_IMG = 'https://i.pinimg.com/originals/8f/67/ad/8f67ad9d7fef82b5943608def344573b.jpg'
const AVATARS  = ['E', 'M', 'A', 'J']
const AVATAR_COLORS = ['#6366f1', '#7c3aed', '#0891b2', '#059669']

/* ─── Brand / model data ────────────────────────────────────────────────── */
interface Brand {
  name: string
  logo: string          // simpleicons CDN URL or empty → initials fallback
  color: string         // brand accent for fallback badge
  models: string[]
}

const BRANDS: Brand[] = [
  {
    name: 'Volkswagen', color: '#1b4ca3',
    logo: 'https://cdn.simpleicons.org/volkswagen/ffffff',
    models: ['Golf', 'Polo', 'Passat', 'Tiguan', 'T-Roc', 'T-Cross', 'ID.3', 'ID.4', 'Touareg', 'Arteon', 'Sharan'],
  },
  {
    name: 'BMW', color: '#1c69d4',
    logo: 'https://cdn.simpleicons.org/bmw/ffffff',
    models: ['Serie 1', 'Serie 2', 'Serie 3', 'Serie 4', 'Serie 5', 'Serie 7', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'Z4', 'M3', 'M5', 'iX'],
  },
  {
    name: 'Audi', color: '#bb0a21',
    logo: 'https://cdn.simpleicons.org/audi/ffffff',
    models: ['A1', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'Q2', 'Q3', 'Q5', 'Q7', 'Q8', 'TT', 'R8', 'e-tron'],
  },
  {
    name: 'Mercedes', color: '#999999',
    logo: 'https://cdn.simpleicons.org/mercedesbenz/ffffff',
    models: ['Clase A', 'Clase B', 'Clase C', 'Clase E', 'Clase S', 'CLA', 'CLS', 'GLA', 'GLB', 'GLC', 'GLE', 'GLS', 'AMG GT', 'EQC', 'EQS'],
  },
  {
    name: 'Toyota', color: '#eb0a1e',
    logo: 'https://cdn.simpleicons.org/toyota/ffffff',
    models: ['Yaris', 'Corolla', 'Camry', 'Prius', 'C-HR', 'RAV4', 'Highlander', 'Land Cruiser', 'Supra', 'GR86'],
  },
  {
    name: 'Ford', color: '#003476',
    logo: 'https://cdn.simpleicons.org/ford/ffffff',
    models: ['Fiesta', 'Focus', 'Mondeo', 'Puma', 'Kuga', 'Explorer', 'Mustang', 'Mustang Mach-E', 'Ranger', 'F-150'],
  },
  {
    name: 'Renault', color: '#efdf00',
    logo: 'https://cdn.simpleicons.org/renault/ffffff',
    models: ['Clio', 'Megane', 'Captur', 'Kadjar', 'Koleos', 'Zoe', 'Arkana', 'Austral', 'Laguna', 'Scenic'],
  },
  {
    name: 'Peugeot', color: '#0099d6',
    logo: 'https://cdn.simpleicons.org/peugeot/ffffff',
    models: ['108', '208', '308', '408', '508', '2008', '3008', '4008', '5008', 'Partner', 'Rifter'],
  },
  {
    name: 'Opel', color: '#ffdd00',
    logo: 'https://cdn.simpleicons.org/opel/ffffff',
    models: ['Corsa', 'Astra', 'Insignia', 'Mokka', 'Crossland', 'Grandland', 'Combo', 'Zafira'],
  },
  {
    name: 'Hyundai', color: '#002c5f',
    logo: 'https://cdn.simpleicons.org/hyundai/ffffff',
    models: ['i10', 'i20', 'i30', 'Ioniq', 'Ioniq 5', 'Ioniq 6', 'Tucson', 'Santa Fe', 'Kona', 'NEXO'],
  },
  {
    name: 'Kia', color: '#05141f',
    logo: 'https://cdn.simpleicons.org/kia/ffffff',
    models: ['Picanto', 'Rio', 'Ceed', 'ProCeed', 'Stinger', 'EV6', 'EV9', 'Sportage', 'Sorento', 'Niro'],
  },
  {
    name: 'Skoda', color: '#4ba82e',
    logo: 'https://cdn.simpleicons.org/skoda/ffffff',
    models: ['Fabia', 'Scala', 'Octavia', 'Superb', 'Kamiq', 'Karoq', 'Kodiaq', 'Enyaq', 'Citigo'],
  },
  {
    name: 'SEAT', color: '#cc1729',
    logo: 'https://cdn.simpleicons.org/seat/ffffff',
    models: ['Ibiza', 'Arona', 'Leon', 'Ateca', 'Tarraco', 'Alhambra', 'Mii', 'Cupra Formentor'],
  },
  {
    name: 'Volvo', color: '#003057',
    logo: 'https://cdn.simpleicons.org/volvo/ffffff',
    models: ['V40', 'V60', 'V90', 'S60', 'S90', 'XC40', 'XC60', 'XC90', 'C40 Recharge', 'EX30'],
  },
  {
    name: 'Porsche', color: '#c9002b',
    logo: 'https://cdn.simpleicons.org/porsche/ffffff',
    models: ['911', '718 Boxster', '718 Cayman', 'Cayenne', 'Macan', 'Panamera', 'Taycan'],
  },
  {
    name: 'Fiat', color: '#8b1e3f',
    logo: 'https://cdn.simpleicons.org/fiat/ffffff',
    models: ['500', '500X', '500L', '500e', 'Panda', 'Tipo', 'Bravo', 'Stilo'],
  },
  {
    name: 'Citroën', color: '#ed1d24',
    logo: 'https://cdn.simpleicons.org/citroen/ffffff',
    models: ['C1', 'C3', 'C4', 'C5 X', 'C5 Aircross', 'Berlingo', 'C-Elysée', 'ë-C4'],
  },
  {
    name: 'Nissan', color: '#c71444',
    logo: 'https://cdn.simpleicons.org/nissan/ffffff',
    models: ['Micra', 'Juke', 'Qashqai', 'X-Trail', 'Leaf', 'Ariya', '370Z', 'GT-R'],
  },
  {
    name: 'Honda', color: '#cc0000',
    logo: 'https://cdn.simpleicons.org/honda/ffffff',
    models: ['Jazz', 'Civic', 'Accord', 'HR-V', 'CR-V', 'ZR-V', 'e:Ny1', 'NSX'],
  },
  {
    name: 'Land Rover', color: '#005a2b',
    logo: '',
    models: ['Defender', 'Discovery', 'Discovery Sport', 'Freelander', 'Range Rover', 'Range Rover Sport', 'Range Rover Evoque', 'Range Rover Velar'],
  },
]

/* ─── Price options ─────────────────────────────────────────────────────── */
const PRICE_FROM = [
  { label: 'Sin mínimo', value: 0 },
  { label: '2.000 €',    value: 2000 },
  { label: '5.000 €',    value: 5000 },
  { label: '8.000 €',    value: 8000 },
  { label: '10.000 €',   value: 10000 },
  { label: '15.000 €',   value: 15000 },
  { label: '20.000 €',   value: 20000 },
  { label: '30.000 €',   value: 30000 },
  { label: '40.000 €',   value: 40000 },
  { label: '50.000 €',   value: 50000 },
]
const PRICE_TO = [
  { label: 'Sin límite', value: 0 },
  { label: '5.000 €',    value: 5000 },
  { label: '10.000 €',   value: 10000 },
  { label: '15.000 €',   value: 15000 },
  { label: '20.000 €',   value: 20000 },
  { label: '30.000 €',   value: 30000 },
  { label: '40.000 €',   value: 40000 },
  { label: '50.000 €',   value: 50000 },
  { label: '80.000 €',   value: 80000 },
  { label: '100.000 €',  value: 100000 },
]

const PAISES = [
  { code: '', label: 'Todos los países' },
  { code: 'de', flag: '🇩🇪', label: 'Alemania' },
  { code: 'es', flag: '🇪🇸', label: 'España' },
  { code: 'fr', flag: '🇫🇷', label: 'Francia' },
  { code: 'nl', flag: '🇳🇱', label: 'Países Bajos' },
  { code: 'be', flag: '🇧🇪', label: 'Bélgica' },
  { code: 'ch', flag: '🇨🇭', label: 'Suiza' },
]

/* ─── Brand logo with fallback ──────────────────────────────────────────── */
function BrandLogo({ brand, size = 36 }: { brand: Brand; size?: number }) {
  const [failed, setFailed] = useState(false)
  const initials = brand.name.slice(0, 2).toUpperCase()

  if (!brand.logo || failed) {
    return (
      <div style={{
        width: size, height: size, borderRadius: 8,
        background: brand.color + '22',
        border: `1px solid ${brand.color}44`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: size * 0.3, fontWeight: 800, color: '#fff',
        letterSpacing: '-0.03em',
      }}>
        {initials}
      </div>
    )
  }

  return (
    <div style={{
      width: size, height: size, borderRadius: 8,
      background: 'rgba(255,255,255,0.06)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      overflow: 'hidden',
    }}>
      <img
        src={brand.logo}
        alt={brand.name}
        onError={() => setFailed(true)}
        style={{ width: size * 0.65, height: size * 0.65, objectFit: 'contain', filter: 'brightness(10)' }}
      />
    </div>
  )
}

/* ─── Marca y Modelo overlay ────────────────────────────────────────────── */
interface MarcaModeloState { brand: Brand | null; model: string }

function MarcaModeloField({
  value, onChange,
}: {
  value: MarcaModeloState
  onChange: (v: MarcaModeloState) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [step, setStep] = useState<'brand' | 'model'>('brand')
  const ref = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const close = useCallback(() => { setOpen(false); setSearch(''); setStep('brand') }, [])

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close() }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open, close])

  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 60)
  }, [open, step])

  const filtered = BRANDS.filter(b => b.name.toLowerCase().includes(search.toLowerCase()))
  const activeBrand = step === 'model' ? value.brand : null
  const filteredModels = activeBrand
    ? activeBrand.models.filter(m => m.toLowerCase().includes(search.toLowerCase()))
    : []

  const displayLabel = value.brand
    ? value.model ? `${value.brand.name} · ${value.model}` : value.brand.name
    : 'Cualquier marca'

  function selectBrand(b: Brand) {
    onChange({ brand: b, model: '' })
    setSearch('')
    setStep('model')
  }

  function selectModel(m: string) {
    onChange({ brand: value.brand, model: m })
    close()
  }

  function clearAndClose() {
    onChange({ brand: null, model: '' })
    close()
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {/* Trigger */}
      <button
        onClick={() => { setOpen(v => !v); setStep('brand') }}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 14px', height: 44, borderRadius: 10,
          background: open ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.06)',
          border: `1px solid ${open ? 'rgba(255,255,255,0.24)' : 'rgba(255,255,255,0.10)'}`,
          cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.18s', gap: 8,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.07em', textTransform: 'uppercase', lineHeight: 1 }}>
            Marca y modelo
          </span>
          <span style={{ fontSize: 13, fontWeight: value.brand ? 600 : 400, color: value.brand ? '#fff' : 'rgba(255,255,255,0.5)', lineHeight: 1.45, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
            {displayLabel}
          </span>
        </div>
        {value.brand ? (
          <div
            onClick={e => { e.stopPropagation(); clearAndClose() }}
            style={{ width: 16, height: 16, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: 'pointer' }}
          >
            <svg width={8} height={8} viewBox="0 0 8 8"><path d="M1 1l6 6M7 1L1 7" stroke="#fff" strokeWidth={1.4} strokeLinecap="round"/></svg>
          </div>
        ) : (
          <svg width={11} height={11} viewBox="0 0 11 11" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.38)' }}>
            <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round"/>
          </svg>
        )}
      </button>

      {/* Overlay panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: EXPO }}
            style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              left: '50%',
              transform: 'translateX(-50%)',
              width: 'clamp(320px, 80vw, 520px)',
              zIndex: 200,
              background: 'rgba(11,10,24,0.96)',
              backdropFilter: 'blur(40px) saturate(200%)',
              WebkitBackdropFilter: 'blur(40px) saturate(200%)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 16,
              boxShadow: '0 24px 80px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.08)',
              overflow: 'hidden',
            }}
          >
            {/* Panel header */}
            <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 10 }}>
              {step === 'model' && (
                <button
                  onClick={() => { setStep('brand'); setSearch(''); onChange({ brand: null, model: '' }) }}
                  style={{ width: 28, height: 28, borderRadius: 8, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}
                >
                  <svg width={12} height={12} viewBox="0 0 12 12"><path d="M8 2L4 6l4 4" stroke="rgba(255,255,255,0.7)" strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              )}
              {step === 'model' && value.brand && (
                <BrandLogo brand={value.brand} size={28} />
              )}
              <span style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.8)', flex: 1 }}>
                {step === 'brand' ? 'Selecciona una marca' : `${value.brand?.name} — elige el modelo`}
              </span>
            </div>

            {/* Search */}
            <div style={{ padding: '10px 12px 8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 9, padding: '7px 12px' }}>
                <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={2} strokeLinecap="round">
                  <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
                </svg>
                <input
                  ref={searchRef}
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder={step === 'brand' ? 'Buscar marca...' : `Buscar modelo de ${value.brand?.name}...`}
                  style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#fff', fontFamily: 'inherit' }}
                />
                {search && (
                  <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)', fontSize: 16, lineHeight: 1, padding: 0 }}>×</button>
                )}
              </div>
            </div>

            {/* Brand grid */}
            {step === 'brand' && (
              <div style={{ padding: '0 12px 12px', maxHeight: 280, overflowY: 'auto' }}>
                {/* Cualquier marca */}
                <button
                  onClick={clearAndClose}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                    padding: '8px 10px', borderRadius: 8, marginBottom: 8,
                    background: !value.brand ? 'rgba(99,102,241,0.15)' : 'transparent',
                    border: `1px solid ${!value.brand ? 'rgba(99,102,241,0.3)' : 'transparent'}`,
                    cursor: 'pointer', fontFamily: 'inherit',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (value.brand) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                  onMouseLeave={e => { if (value.brand) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>🚗</div>
                  <span style={{ fontSize: 13, fontWeight: 500, color: !value.brand ? '#fff' : 'rgba(255,255,255,0.65)' }}>Cualquier marca</span>
                </button>

                {/* Brand grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                  {filtered.map(b => (
                    <motion.button
                      key={b.name}
                      onClick={() => selectBrand(b)}
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      transition={{ duration: 0.12 }}
                      style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                        gap: 6, padding: '10px 6px 8px',
                        background: value.brand?.name === b.name ? 'rgba(99,102,241,0.18)' : 'rgba(255,255,255,0.04)',
                        border: `1px solid ${value.brand?.name === b.name ? 'rgba(99,102,241,0.35)' : 'rgba(255,255,255,0.07)'}`,
                        borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit',
                        transition: 'background 0.15s, border-color 0.15s',
                      }}
                    >
                      <BrandLogo brand={b} size={34} />
                      <span style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.65)', textAlign: 'center', lineHeight: 1.2, letterSpacing: '0.01em' }}>
                        {b.name}
                      </span>
                    </motion.button>
                  ))}
                </div>
              </div>
            )}

            {/* Model list */}
            {step === 'model' && (
              <div style={{ maxHeight: 280, overflowY: 'auto', padding: '0 12px 12px' }}>
                {/* All models */}
                <button
                  onClick={() => { onChange({ brand: value.brand, model: '' }); close() }}
                  style={{
                    display: 'flex', alignItems: 'center', width: '100%', padding: '9px 12px',
                    background: !value.model ? 'rgba(99,102,241,0.15)' : 'transparent',
                    border: `1px solid ${!value.model ? 'rgba(99,102,241,0.3)' : 'transparent'}`,
                    borderRadius: 8, marginBottom: 4, cursor: 'pointer', fontFamily: 'inherit',
                    transition: 'background 0.12s',
                  }}
                  onMouseEnter={e => { if (value.model) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                  onMouseLeave={e => { if (value.model) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <span style={{ fontSize: 13, fontWeight: !value.model ? 600 : 500, color: !value.model ? '#fff' : 'rgba(255,255,255,0.6)' }}>
                    Todos los modelos de {value.brand?.name}
                  </span>
                </button>
                {filteredModels.map(m => (
                  <button
                    key={m}
                    onClick={() => selectModel(m)}
                    style={{
                      display: 'flex', alignItems: 'center', width: '100%', padding: '9px 12px',
                      background: value.model === m ? 'rgba(99,102,241,0.15)' : 'transparent',
                      border: `1px solid ${value.model === m ? 'rgba(99,102,241,0.3)' : 'transparent'}`,
                      borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit',
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={e => { if (value.model !== m) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                    onMouseLeave={e => { if (value.model !== m) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                  >
                    <span style={{ fontSize: 13, fontWeight: value.model === m ? 600 : 400, color: value.model === m ? '#fff' : 'rgba(255,255,255,0.65)' }}>{m}</span>
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ─── Simple glass select ───────────────────────────────────────────────── */
function GlassSelect({
  label, options, value, onChange,
}: {
  label: string
  options: { label: string; value: string | number }[]
  value: string | number
  onChange: (v: string | number) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selected = options.find(o => o.value === value)

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 12px', height: 44, borderRadius: 10,
          background: open ? 'rgba(255,255,255,0.10)' : 'rgba(255,255,255,0.06)',
          border: `1px solid ${open ? 'rgba(255,255,255,0.24)' : 'rgba(255,255,255,0.10)'}`,
          cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.18s', gap: 6,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.07em', textTransform: 'uppercase', lineHeight: 1 }}>{label}</span>
          <span style={{ fontSize: 13, fontWeight: (value !== '' && value !== 0) ? 600 : 400, color: (value !== '' && value !== 0) ? '#fff' : 'rgba(255,255,255,0.5)', lineHeight: 1.45, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
            {selected?.label ?? label}
          </span>
        </div>
        <svg width={11} height={11} viewBox="0 0 11 11" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.38)' }}>
          <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round"/>
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
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, minWidth: '100%', zIndex: 200,
              background: 'rgba(11,10,24,0.96)',
              backdropFilter: 'blur(32px) saturate(180%)',
              WebkitBackdropFilter: 'blur(32px) saturate(180%)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 12,
              boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
              overflow: 'hidden',
            }}
          >
            {options.map(opt => {
              const isActive = opt.value === value
              return (
                <button
                  key={String(opt.value)}
                  onClick={() => { onChange(opt.value); setOpen(false) }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '9px 14px', background: isActive ? 'rgba(99,102,241,0.18)' : 'none',
                    border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 13, fontWeight: isActive ? 600 : 400,
                    color: isActive ? '#fff' : 'rgba(255,255,255,0.65)',
                    transition: 'background 0.1s',
                    whiteSpace: 'nowrap',
                  }}
                  onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                  onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'none' }}
                >{opt.label}</button>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ─── Main ──────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { isAuthenticated } = useAuthContext()
  const [navScrolled, setNavScrolled] = useState(false)
  const [query, setQuery]   = useState('')
  const [marca, setMarca]   = useState<MarcaModeloState>({ brand: null, model: '' })
  const [pais, setPais]     = useState('')
  const [desde, setDesde]   = useState<number>(0)
  const [hasta, setHasta]   = useState<number>(0)

  useEffect(() => {
    const fn = () => setNavScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  function handleEnter() { nav(isAuthenticated ? '/dashboard' : '/login') }
  function handleSearch(e: React.FormEvent) { e.preventDefault(); nav('/dashboard') }

  /* Dynamic result count */
  const base = 1_550_000
  const count = Math.round(
    base
    * (marca.brand  ? 0.065 : 1)
    * (marca.model  ? 0.18  : 1)
    * (pais         ? 0.22  : 1)
    * (desde > 0    ? 0.75  : 1)
    * (hasta > 0    ? 0.70  : 1)
  )
  const countLabel = count.toLocaleString('de-DE')

  /* Price validation */
  const validPrices = PRICE_TO.filter(p => p.value === 0 || hasta === 0 || p.value > desde)
  const validFromPrices = PRICE_FROM.filter(p => p.value === 0 || hasta === 0 || p.value < hasta)

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#07070f' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 300,
        height: 60, display: 'flex', alignItems: 'center',
        padding: '0 clamp(20px, 4vw, 48px)',
        transition: 'background 0.3s, border-color 0.3s',
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
            style={{ padding: '7px 20px', borderRadius: 999, background: 'rgba(255,255,255,0.09)', border: '1px solid rgba(255,255,255,0.18)', backdropFilter: 'blur(12px)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >Sign In</motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>
        <img src={HERO_IMG} alt="" fetchPriority="high" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 40%' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(7,7,15,0.22) 0%, rgba(7,7,15,0.05) 28%, rgba(7,7,15,0.65) 70%, rgba(7,7,15,0.96) 100%)' }} />

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

          {/* Search bar */}
          <motion.form onSubmit={handleSearch} initial={{ opacity: 0, y: 14, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease: EXPO, delay: 0.2 }}
            style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: 560, borderRadius: 999, background: 'rgba(255,255,255,0.10)', backdropFilter: 'blur(24px) saturate(180%)', WebkitBackdropFilter: 'blur(24px) saturate(180%)', border: '1px solid rgba(255,255,255,0.18)', boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.14)', padding: '5px 5px 5px 20px', gap: 8 }}>
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.38)" strokeWidth={2} strokeLinecap="round" style={{ flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
            </svg>
            <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="BMW Serie 3, Audi A4, Mercedes Clase C..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 15, color: '#fff', fontFamily: 'inherit' }} />
            <motion.button type="submit" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.12, ease: EXPO }}
              style={{ padding: '10px 22px', borderRadius: 999, flexShrink: 0, background: 'rgba(20,18,60,0.92)', border: '1px solid rgba(255,255,255,0.12)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
              Buscar →
            </motion.button>
          </motion.form>

          {/* Filter box */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EXPO, delay: 0.32 }}
            style={{ width: '100%', maxWidth: 560, marginTop: 8, borderRadius: 16, background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(32px) saturate(200%)', WebkitBackdropFilter: 'blur(32px) saturate(200%)', border: '1px solid rgba(255,255,255,0.12)', boxShadow: '0 16px 48px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.10)', padding: '12px 12px 10px' }}>

            {/* Filters — 2x2 grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 7, marginBottom: 10 }}>
              <MarcaModeloField value={marca} onChange={setMarca} />
              <GlassSelect
                label="País"
                value={pais}
                onChange={v => setPais(String(v))}
                options={PAISES.map(p => ({
                  label: p.code ? `${p.flag}  ${p.label}` : p.label,
                  value: p.code,
                }))}
              />
              <GlassSelect
                label="Desde"
                value={desde}
                onChange={v => { setDesde(Number(v)); if (hasta > 0 && Number(v) >= hasta) setHasta(0) }}
                options={validFromPrices.map(p => ({ label: p.label, value: p.value }))}
              />
              <GlassSelect
                label="Hasta"
                value={hasta}
                onChange={v => { setHasta(Number(v)); if (desde > 0 && Number(v) > 0 && Number(v) <= desde) setDesde(0) }}
                options={validPrices.map(p => ({ label: p.label, value: p.value }))}
              />
            </div>

            {/* Results */}
            <motion.button
              onClick={handleSearch}
              whileHover={{ scale: 1.012 }}
              whileTap={{ scale: 0.985 }}
              transition={{ duration: 0.14, ease: EXPO }}
              style={{ width: '100%', padding: '11px 0', borderRadius: 10, background: 'rgba(99,102,241,0.20)', border: '1px solid rgba(99,102,241,0.32)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', letterSpacing: '-0.01em' }}
            >
              Mostrar {countLabel} resultados
            </motion.button>
          </motion.div>
        </div>
      </div>

      <style>{`
        input::placeholder { color: rgba(255,255,255,0.36) !important; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 4px; }
      `}</style>
    </div>
  )
}
