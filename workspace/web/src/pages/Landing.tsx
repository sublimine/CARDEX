import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuthContext } from '../auth/AuthContext'

const EXPO = [0.16, 1, 0.3, 1] as const
const HERO_IMG = 'https://i.pinimg.com/originals/8f/67/ad/8f67ad9d7fef82b5943608def344573b.jpg'
/* ─── Source portals — one per country + AS24 global ──────────────────── */
interface Portal { name: string; favicon?: string; initial?: string; bg: string; border?: string; textColor?: string }
const PORTALS: Portal[] = [
  { name: 'AutoScout24', favicon: 'https://www.google.com/s2/favicons?domain=autoscout24.com&sz=64', bg: '#0d1117', border: '#FFCD00' },
  { name: 'mobile.de',   favicon: 'https://www.google.com/s2/favicons?domain=mobile.de&sz=64',       bg: '#003a78' },
  { name: 'coches.net',  favicon: 'https://www.google.com/s2/favicons?domain=coches.net&sz=64',      bg: '#cc0000' },
  { name: 'La Centrale', favicon: 'https://www.google.com/s2/favicons?domain=lacentrale.fr&sz=64',   bg: '#c8102e' },
  { name: 'marktplaats', initial: 'M', bg: '#002b5c', textColor: '#4db8a4' },
  { name: '2dehands',    favicon: 'https://www.google.com/s2/favicons?domain=2dehands.be&sz=64',     bg: '#003a78' },
  { name: 'tutti.ch',    favicon: 'https://www.google.com/s2/favicons?domain=tutti.ch&sz=64',        bg: '#1a1a1a' },
]

/* Diamond layout: 1 + 2 + 3 + 1 */
const DIAMOND_ROWS = [
  PORTALS.slice(0, 1),
  PORTALS.slice(1, 3),
  PORTALS.slice(3, 6),
  PORTALS.slice(6, 7),
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

/* ─── Year filter ──────────────────────────────────────────────────────── */
const ANOS = [
  { label: 'Cualquier año', value: '' },
  { label: '2024 o más nuevo', value: '2024' },
  { label: '2022 o más nuevo', value: '2022' },
  { label: '2020 o más nuevo', value: '2020' },
  { label: '2018 o más nuevo', value: '2018' },
  { label: '2015 o más nuevo', value: '2015' },
  { label: '2012 o más nuevo', value: '2012' },
  { label: '2010 o más nuevo', value: '2010' },
  { label: '2005 o más nuevo', value: '2005' },
  { label: 'Anterior a 2005',  value: '0' },
]

/* ─── Price filter ─────────────────────────────────────────────────────── */
const PRECIOS = [
  { label: 'Sin límite de precio', value: '' },
  { label: 'Hasta 5.000 €',        value: '5000' },
  { label: 'Hasta 10.000 €',       value: '10000' },
  { label: 'Hasta 15.000 €',       value: '15000' },
  { label: 'Hasta 20.000 €',       value: '20000' },
  { label: 'Hasta 25.000 €',       value: '25000' },
  { label: 'Hasta 30.000 €',       value: '30000' },
  { label: 'Hasta 40.000 €',       value: '40000' },
  { label: 'Hasta 50.000 €',       value: '50000' },
  { label: 'Hasta 70.000 €',       value: '70000' },
  { label: 'Hasta 100.000 €',      value: '100000' },
]

/* ─── Brand / Model data — complete EU catalogue ───────────────────────── */
interface Brand { name: string; logo: string; color: string; models: string[] }

const BRANDS: Brand[] = [
  {
    name: 'Volkswagen', color: '#1b4ca3',
    logo: 'https://cdn.simpleicons.org/volkswagen/ffffff',
    models: ['Arteon','Arteon Shooting Brake','Beetle','Caddy','California','Golf','Golf GTI','Golf GTE','Golf R','Golf Variant','ID.3','ID.4','ID.5','ID.7','ID. Buzz','Jetta','Passat','Passat Variant','Phaeton','Polo','Scirocco','Sharan','T-Cross','T-Roc','Tiguan','Tiguan Allspace','Touareg','Touran','Up','Amarok'],
  },
  {
    name: 'BMW', color: '#1c69d4',
    logo: 'https://cdn.simpleicons.org/bmw/ffffff',
    models: ['Serie 1','Serie 2','Serie 2 Active Tourer','Serie 2 Gran Coupé','Serie 2 Gran Tourer','Serie 3','Serie 3 Touring','Serie 4','Serie 4 Cabrio','Serie 4 Gran Coupé','Serie 5','Serie 5 Touring','Serie 6','Serie 6 Gran Turismo','Serie 7','Serie 8','Serie 8 Gran Coupé','X1','X2','X3','X3 M','X4','X4 M','X5','X5 M','X6','X6 M','X7','Z3','Z4','M2','M2 CS','M3','M3 Touring','M4','M4 Cabrio','M5','M6','M8','iX','iX1','iX3','i3','i3s','i4','i5','i7','i8'],
  },
  {
    name: 'Audi', color: '#bb0a21',
    logo: 'https://cdn.simpleicons.org/audi/ffffff',
    models: ['A1','A1 Sportback','A2','A3','A3 Cabriolet','A3 Sedan','A3 Sportback','A4','A4 Allroad','A4 Avant','A5','A5 Cabriolet','A5 Coupé','A5 Sportback','A6','A6 Allroad','A6 Avant','A7','A7 Sportback','A8','A8 L','Q2','Q3','Q3 Sportback','Q4 e-tron','Q4 Sportback e-tron','Q5','Q5 Sportback','Q7','Q8','Q8 e-tron','Q8 Sportback e-tron','R8','R8 Spyder','RS3','RS4','RS4 Avant','RS5','RS5 Sportback','RS6','RS6 Avant','RS7','S3','S4','S4 Avant','S5','S6','S7','S8','TT','TT Roadster','TT RS','e-tron GT','RS e-tron GT'],
  },
  {
    name: 'Mercedes', color: '#8a8a8a',
    logo: 'https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Mercedes-Logo.svg/100px-Mercedes-Logo.svg.png',
    models: ['AMG GT','AMG One','Clase A','Clase A Sedan','Clase B','Clase C','Clase C Cabriolet','Clase C Coupé','Clase C Estate','Clase CLA','Clase CLA Shooting Brake','Clase CLS','Clase E','Clase E Cabriolet','Clase E Coupé','Clase E Estate','Clase EQA','Clase EQB','Clase EQC','Clase EQE','Clase EQS','Clase EQV','Clase G','Clase GLA','Clase GLB','Clase GLC','Clase GLC Coupé','Clase GLE','Clase GLE Coupé','Clase GLS','Clase GT 4 puertas','Clase S','Clase S Coupé','Clase SL','Clase SLC','Clase V','Maybach GLS','Maybach S','Sprinter','Vito'],
  },
  {
    name: 'Toyota', color: '#eb0a1e',
    logo: 'https://cdn.simpleicons.org/toyota/ffffff',
    models: ['Auris','Avensis','Aygo','Aygo X','C-HR','Camry','Corolla','Corolla Cross','Corolla Touring Sports','GR86','GR Supra','GR Yaris','Highlander','Land Cruiser','Prius','Prius+','Proace','Proace City','RAV4','Supra','Verso','Yaris','Yaris Cross'],
  },
  {
    name: 'Ford', color: '#003476',
    logo: 'https://cdn.simpleicons.org/ford/ffffff',
    models: ['B-Max','C-Max','EcoSport','Edge','Explorer','Fiesta','Focus','Focus Active','Fusion','Galaxy','Grand C-Max','Ka+','Kuga','Maverick','Mondeo','Mustang','Mustang Mach-E','Puma','Ranger','S-Max','Transit','Transit Connect','Transit Custom'],
  },
  {
    name: 'Renault', color: '#efdf00',
    logo: 'https://cdn.simpleicons.org/renault/ffffff',
    models: ['Arkana','Austral','Captur','Clio','Clio E-Tech','Espace','Fluence','Kadjar','Kangoo','Koleos','Laguna','Latitude','Megane','Megane E-Tech','Megane Estate','Modus','Scenic','Talisman','Twingo','Wind','Zoe'],
  },
  {
    name: 'Peugeot', color: '#0099d6',
    logo: 'https://cdn.simpleicons.org/peugeot/ffffff',
    models: ['107','108','2008','208','3008','301','308','308 SW','408','4008','5008','508','508 SW','607','807','Bipper','Boxer','e-208','e-2008','Expert','Partner','RCZ','Rifter','Traveller'],
  },
  {
    name: 'Opel', color: '#f0be00',
    logo: 'https://cdn.simpleicons.org/opel/ffffff',
    models: ['Adam','Agila','Ampera','Ampera-e','Astra','Astra Sports Tourer','Cascada','Combo','Combo Life','Corsa','Corsa-e','Crossland','Frontera','Grandland','Insignia','Insignia Grand Sport','Insignia Sports Tourer','Meriva','Mokka','Mokka-e','Movano','Signum','Tigra','Vectra','Vivaro','Zafira','Zafira Life','Zafira Tourer'],
  },
  {
    name: 'Hyundai', color: '#002c5f',
    logo: 'https://cdn.simpleicons.org/hyundai/ffffff',
    models: ['Accent','Bayon','Elantra','Genesis','Grand Santa Fe','i10','i20','i20 N','i30','i30 N','i30 Wagon','i40','i40 CW','i40 Wagon','Ioniq','Ioniq 5','Ioniq 5 N','Ioniq 6','Kona','Kona Electric','NEXO','Santa Cruz','Santa Fe','Staria','Tucson','Veloster'],
  },
  {
    name: 'Kia', color: '#05141f',
    logo: 'https://cdn.simpleicons.org/kia/ffffff',
    models: ['Carens','Carnival','Ceed','Ceed GT','Ceed SW','EV3','EV6','EV6 GT','EV9','K5','Niro','Niro EV','Niro Plug-in','Picanto','ProCeed','Rio','Soul','Soul EV','Sportage','Stinger','Stonic','Sorento','Telluride','Venga','XCeed'],
  },
  {
    name: 'Skoda', color: '#4ba82e',
    logo: 'https://cdn.simpleicons.org/skoda/ffffff',
    models: ['Citigo','Enyaq','Enyaq Coupé','Fabia','Fabia Combi','Kamiq','Karoq','Kodiaq','Kodiaq RS','Octavia','Octavia Combi','Octavia RS','Rapid','Roomster','Scala','Superb','Superb Combi','Yeti'],
  },
  {
    name: 'SEAT', color: '#cc1729',
    logo: 'https://cdn.simpleicons.org/seat/ffffff',
    models: ['Alhambra','Altea','Altea XL','Arona','Ateca','Exeo','Ibiza','Ibiza SC','Ibiza ST','Leon','Leon SC','Leon ST','Mii','Tarraco','Toledo'],
  },
  {
    name: 'Volvo', color: '#003057',
    logo: 'https://cdn.simpleicons.org/volvo/ffffff',
    models: ['C30','C40 Recharge','C70','EX30','EX90','S40','S60','S60 Cross Country','S80','S90','V40','V40 Cross Country','V50','V60','V60 Cross Country','V70','V90','V90 Cross Country','XC40','XC40 Recharge','XC60','XC70','XC90'],
  },
  {
    name: 'Porsche', color: '#c9002b',
    logo: 'https://cdn.simpleicons.org/porsche/ffffff',
    models: ['718 Boxster','718 Boxster GTS','718 Cayman','718 Cayman GT4','718 Spyder','911','911 Carrera','911 Carrera S','911 GT3','911 GT3 RS','911 R','911 Targa','911 Turbo','911 Turbo S','Cayenne','Cayenne Coupé','Cayenne E-Hybrid','Macan','Macan S','Macan GTS','Panamera','Panamera Sport Turismo','Taycan','Taycan Cross Turismo','Taycan Sport Turismo'],
  },
  {
    name: 'Fiat', color: '#8b1e3f',
    logo: 'https://cdn.simpleicons.org/fiat/ffffff',
    models: ['124 Spider','500','500 Abarth','500C','500L','500L Cross','500L Wagon','500X','500e','Bravo','Coupé','Doblo','Ducato','Freemont','Grande Punto','Idea','Linea','Multipla','Panda','Punto','Qubo','Stilo','Tipo','Tipo Station Wagon','Ulysse'],
  },
  {
    name: 'Citroën', color: '#ed1d24',
    logo: 'https://cdn.simpleicons.org/citroen/ffffff',
    models: ['Berlingo','Berlingo Multispace','C-Crosser','C-Elysée','C-Zero','C1','C2','C3','C3 Aircross','C3 Picasso','C4','C4 Cactus','C4 Picasso','C4 Spacetourer','C4 X','C5','C5 Aircross','C5 X','C6','C8','DS3','DS3 Crossback','DS4','DS4 Crossback','DS5','DS7 Crossback','ë-C4','Jumpy','Nemo','Spacetourer','Xsara','Xsara Picasso'],
  },
  {
    name: 'Nissan', color: '#c71444',
    logo: 'https://cdn.simpleicons.org/nissan/ffffff',
    models: ['350Z','370Z','Ariya','Cube','GT-R','Juke','Juke Nismo','Leaf','Maxima','Micra','Murano','Navara','Note','Pathfinder','Patrol','Pixo','Primera','Pulsar','Qashqai','Qashqai+2','Sentra','Terrano','Tiida','Townstar','Townstar EV','X-Trail'],
  },
  {
    name: 'Honda', color: '#cc0000',
    logo: 'https://cdn.simpleicons.org/honda/ffffff',
    models: ['Accord','Civic','Civic Coupé','Civic Sport','Civic Type R','CR-V','CR-Z','e','e:Ny1','FR-V','HR-V','Insight','Jazz','Jazz Crosstar','Jazz e:HEV','Legend','NSX','Odyssey','Pilot','Stream','ZR-V'],
  },
  {
    name: 'Land Rover', color: '#005a2b',
    logo: '',
    models: ['Defender','Defender 90','Defender 110','Defender 130','Discovery','Discovery 3','Discovery 4','Discovery 5','Discovery Sport','Freelander','Freelander 2','Range Rover','Range Rover Evoque','Range Rover Sport','Range Rover Velar','Range Rover Vogue'],
  },
]

/* ─── Small car icon (no emoji) ─────────────────────────────────────────── */
function CarIcon({ size = 16, color = 'rgba(255,255,255,0.5)' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 17H3a2 2 0 01-2-2v-4l2-5h14l2 5v4a2 2 0 01-2 2h-2"/>
      <circle cx="7.5" cy="17.5" r="2.5"/>
      <circle cx="16.5" cy="17.5" r="2.5"/>
    </svg>
  )
}

/* ─── Brand logo ────────────────────────────────────────────────────────── */
function BrandLogo({ brand, size = 34 }: { brand: Brand; size?: number }) {
  const [failed, setFailed] = useState(false)

  if (!brand.logo || failed) {
    return (
      <div style={{
        width: size, height: size, borderRadius: 7,
        background: `${brand.color}18`,
        border: `1px solid ${brand.color}35`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: Math.round(size * 0.28), fontWeight: 800, color: '#fff',
        letterSpacing: '-0.04em', fontFamily: 'Inter, sans-serif',
      }}>
        {brand.name.slice(0, 2).toUpperCase()}
      </div>
    )
  }

  return (
    <div style={{
      width: size, height: size, borderRadius: 7,
      background: 'rgba(255,255,255,0.05)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <img
        src={brand.logo}
        alt={brand.name}
        onError={() => setFailed(true)}
        style={{ width: size * 0.64, height: size * 0.64, objectFit: 'contain', filter: 'brightness(0) invert(1)' }}
        crossOrigin="anonymous"
      />
    </div>
  )
}

/* ─── Glassmorphism panel overlay ───────────────────────────────────────── */
const PANEL_GLASS: React.CSSProperties = {
  position: 'fixed',
  zIndex: 500,
  background: 'rgba(12,9,30,0.62)',
  backdropFilter: 'blur(56px) saturate(220%) brightness(1.1)',
  WebkitBackdropFilter: 'blur(56px) saturate(220%) brightness(1.1)',
  border: '1px solid rgba(255,255,255,0.13)',
  borderRadius: 18,
  boxShadow: '0 32px 96px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.10)',
  overflow: 'hidden',
}

/* ─── Marca y Modelo field + panel ─────────────────────────────────────── */
interface MMState { brand: Brand | null; model: string }

function MarcaModeloField({ value, onChange }: { value: MMState; onChange: (v: MMState) => void }) {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<'brand' | 'model'>('brand')
  const [search, setSearch] = useState('')
  const triggerRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const close = useCallback(() => { setOpen(false); setSearch(''); setStep('brand') }, [])

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      const panel = document.getElementById('mm-panel')
      if (!panel?.contains(e.target as Node) && !triggerRef.current?.contains(e.target as Node)) close()
    }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open, close])

  useEffect(() => {
    if (open) setTimeout(() => searchRef.current?.focus(), 80)
  }, [open, step])

  const filtered = BRANDS.filter(b => b.name.toLowerCase().includes(search.toLowerCase()))
  const filteredModels = value.brand
    ? value.brand.models.filter(m => m.toLowerCase().includes(search.toLowerCase()))
    : []

  const label = value.brand
    ? (value.model ? `${value.brand.name} · ${value.model}` : value.brand.name)
    : 'Cualquier marca'

  function selectBrand(b: Brand) {
    onChange({ brand: b, model: '' })
    setSearch('')
    setStep('model')
  }

  return (
    <>
      <button
        ref={triggerRef}
        onClick={() => { setOpen(v => !v); setStep('brand') }}
        style={{
          width: '100%', height: 46, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 14px', borderRadius: 10, gap: 8, cursor: 'pointer', fontFamily: 'inherit',
          background: open ? 'rgba(255,255,255,0.11)' : 'rgba(255,255,255,0.07)',
          border: `1px solid ${open ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.11)'}`,
          transition: 'all 0.18s',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em', textTransform: 'uppercase', lineHeight: 1.1 }}>Marca y modelo</span>
          <span style={{ fontSize: 13, fontWeight: value.brand ? 600 : 400, color: value.brand ? '#f8fafc' : 'rgba(255,255,255,0.45)', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }}>
            {label}
          </span>
        </div>
        {value.brand ? (
          <div
            role="button"
            onClick={e => { e.stopPropagation(); onChange({ brand: null, model: '' }); close() }}
            style={{ width: 18, height: 18, borderRadius: '50%', background: 'rgba(255,255,255,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: 'pointer' }}
          >
            <svg width={8} height={8} viewBox="0 0 8 8"><path d="M1 1l6 6M7 1L1 7" stroke="rgba(255,255,255,0.8)" strokeWidth={1.5} strokeLinecap="round"/></svg>
          </div>
        ) : (
          <svg width={11} height={11} viewBox="0 0 11 11" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.35)' }}>
            <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth={1.5} fill="none" strokeLinecap="round"/>
          </svg>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <div
            id="mm-panel"
            style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', zIndex: 500, width: 'min(560px, 92vw)' }}
          >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 6 }}
            transition={{ duration: 0.2, ease: EXPO }}
            style={{ ...PANEL_GLASS, position: 'relative', width: '100%' }}
          >
            {/* Header */}
            <div style={{ padding: '14px 16px 10px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'center', gap: 10 }}>
              {step === 'model' && (
                <button
                  onClick={() => { setStep('brand'); setSearch(''); onChange({ brand: null, model: '' }) }}
                  style={{ width: 30, height: 30, borderRadius: 8, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0 }}
                >
                  <svg width={12} height={12} viewBox="0 0 12 12"><path d="M8 2L4 6l4 4" stroke="rgba(255,255,255,0.7)" strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              )}
              {step === 'model' && value.brand && <BrandLogo brand={value.brand} size={26} />}
              <span style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.85)', flex: 1, letterSpacing: '-0.01em' }}>
                {step === 'brand' ? 'Selecciona una marca' : `${value.brand?.name} — selecciona el modelo`}
              </span>
              <button onClick={close} style={{ width: 24, height: 24, borderRadius: 6, background: 'rgba(255,255,255,0.07)', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                <svg width={10} height={10} viewBox="0 0 10 10"><path d="M1 1l8 8M9 1L1 9" stroke="rgba(255,255,255,0.5)" strokeWidth={1.5} strokeLinecap="round"/></svg>
              </button>
            </div>

            {/* Search */}
            <div style={{ padding: '10px 14px 6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 9, padding: '7px 12px' }}>
                <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth={2} strokeLinecap="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
                <input
                  ref={searchRef}
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder={step === 'brand' ? 'Buscar marca...' : `Buscar modelo...`}
                  style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 13, color: '#fff', fontFamily: 'inherit' }}
                />
                {search && <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.35)', fontSize: 14, lineHeight: 1, padding: 0 }}>×</button>}
              </div>
            </div>

            {/* Brand grid */}
            {step === 'brand' && (
              <div style={{ padding: '4px 14px 14px', maxHeight: '56vh', overflowY: 'auto' }}>
                {/* All brands option */}
                <button
                  onClick={() => { onChange({ brand: null, model: '' }); close() }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '8px 10px', borderRadius: 9, marginBottom: 10, background: !value.brand ? 'rgba(99,102,241,0.15)' : 'transparent', border: `1px solid ${!value.brand ? 'rgba(99,102,241,0.28)' : 'transparent'}`, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.14s' }}
                  onMouseEnter={e => { if (value.brand) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.05)' }}
                  onMouseLeave={e => { if (value.brand) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <div style={{ width: 34, height: 34, borderRadius: 7, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CarIcon size={16} color="rgba(255,255,255,0.55)" />
                  </div>
                  <span style={{ fontSize: 13, fontWeight: !value.brand ? 600 : 500, color: !value.brand ? '#fff' : 'rgba(255,255,255,0.6)' }}>Cualquier marca</span>
                </button>

                {/* Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 7 }}>
                  {filtered.map(b => (
                    <motion.button
                      key={b.name}
                      onClick={() => selectBrand(b)}
                      whileHover={{ scale: 1.03 }}
                      whileTap={{ scale: 0.97 }}
                      transition={{ duration: 0.12 }}
                      style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7, padding: '10px 6px 8px',
                        background: value.brand?.name === b.name ? 'rgba(99,102,241,0.18)' : 'rgba(255,255,255,0.04)',
                        border: `1px solid ${value.brand?.name === b.name ? 'rgba(99,102,241,0.32)' : 'rgba(255,255,255,0.07)'}`,
                        borderRadius: 10, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.14s, border-color 0.14s',
                      }}
                      onMouseEnter={e => { if (value.brand?.name !== b.name) { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.07)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.12)' } }}
                      onMouseLeave={e => { if (value.brand?.name !== b.name) { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'; (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.07)' } }}
                    >
                      <BrandLogo brand={b} size={32} />
                      <span style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.6)', textAlign: 'center', lineHeight: 1.2, letterSpacing: '0.01em' }}>{b.name}</span>
                    </motion.button>
                  ))}
                </div>
              </div>
            )}

            {/* Model list */}
            {step === 'model' && (
              <div style={{ maxHeight: '56vh', overflowY: 'auto', padding: '4px 14px 14px' }}>
                <button
                  onClick={() => { onChange({ brand: value.brand, model: '' }); close() }}
                  style={{ display: 'flex', alignItems: 'center', width: '100%', padding: '9px 12px', marginBottom: 3, background: !value.model ? 'rgba(99,102,241,0.15)' : 'transparent', border: `1px solid ${!value.model ? 'rgba(99,102,241,0.28)' : 'transparent'}`, borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.12s' }}
                  onMouseEnter={e => { if (value.model) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                  onMouseLeave={e => { if (value.model) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                >
                  <span style={{ fontSize: 13, fontWeight: !value.model ? 600 : 500, color: !value.model ? '#fff' : 'rgba(255,255,255,0.6)' }}>Todos los modelos de {value.brand?.name}</span>
                </button>
                {/* 2-column model grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3 }}>
                  {filteredModels.map(m => (
                    <button
                      key={m}
                      onClick={() => { onChange({ brand: value.brand, model: m }); close() }}
                      style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', background: value.model === m ? 'rgba(99,102,241,0.15)' : 'transparent', border: `1px solid ${value.model === m ? 'rgba(99,102,241,0.28)' : 'transparent'}`, borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', transition: 'background 0.1s', textAlign: 'left' }}
                      onMouseEnter={e => { if (value.model !== m) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.06)' }}
                      onMouseLeave={e => { if (value.model !== m) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
                    >
                      <span style={{ fontSize: 13, fontWeight: value.model === m ? 600 : 400, color: value.model === m ? '#fff' : 'rgba(255,255,255,0.65)' }}>{m}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}

/* ─── Generic glass select ──────────────────────────────────────────────── */
function GlassSelect<T extends string | number>({
  label, options, value, onChange, renderOption,
}: {
  label: string
  options: { label: string; value: T; prefix?: React.ReactNode }[]
  value: T
  onChange: (v: T) => void
  renderOption?: (opt: { label: string; value: T; prefix?: React.ReactNode }) => React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const sel = options.find(o => o.value === value)

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    if (open) document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', height: 46, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', borderRadius: 10, gap: 8, cursor: 'pointer', fontFamily: 'inherit', background: open ? 'rgba(255,255,255,0.11)' : 'rgba(255,255,255,0.07)', border: `1px solid ${open ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.11)'}`, transition: 'all 0.18s' }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: 'rgba(255,255,255,0.35)', letterSpacing: '0.08em', textTransform: 'uppercase', lineHeight: 1.1 }}>{label}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            {sel?.prefix}
            <span style={{ fontSize: 13, fontWeight: (value !== '' && value !== 0) ? 600 : 400, color: (value !== '' && value !== 0) ? '#f8fafc' : 'rgba(255,255,255,0.45)', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {sel?.label ?? label}
            </span>
          </div>
        </div>
        <svg width={11} height={11} viewBox="0 0 11 11" style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', color: 'rgba(255,255,255,0.35)' }}>
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
            style={{ ...PANEL_GLASS, position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, minWidth: '100%', zIndex: 300 }}
          >
            {options.map(opt => {
              const active = opt.value === value
              return (
                <button
                  key={String(opt.value)}
                  onClick={() => { onChange(opt.value); setOpen(false) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left', padding: '9px 14px', background: active ? 'rgba(99,102,241,0.18)' : 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: active ? 600 : 400, color: active ? '#fff' : 'rgba(255,255,255,0.65)', transition: 'background 0.1s', whiteSpace: 'nowrap' }}
                  onMouseEnter={e => { if (!active) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.07)' }}
                  onMouseLeave={e => { if (!active) (e.currentTarget as HTMLElement).style.background = 'none' }}
                >
                  {renderOption ? renderOption(opt) : (
                    <>{opt.prefix}<span>{opt.label}</span></>
                  )}
                </button>
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
  const [query,  setQuery]  = useState('')
  const [marca,  setMarca]  = useState<MMState>({ brand: null, model: '' })
  const [pais,   setPais]   = useState('')
  const [precio, setPrecio] = useState('')
  const [ano,    setAno]    = useState('')

  useEffect(() => {
    const fn = () => setNavScrolled(window.scrollY > 30)
    window.addEventListener('scroll', fn, { passive: true })
    return () => window.removeEventListener('scroll', fn)
  }, [])

  function handleEnter() { nav(isAuthenticated ? '/dashboard' : '/login') }
  function handleSearch(e: React.FormEvent) { e.preventDefault(); nav('/dashboard') }

  const count = Math.round(
    1_550_000
    * (marca.brand  ? 0.065 : 1)
    * (marca.model  ? 0.18  : 1)
    * (pais         ? 0.22  : 1)
    * (precio       ? 0.65  : 1)
    * (ano          ? 0.55  : 1)
  )

  const paisOptions = PAISES.map(p => ({
    label: p.label,
    value: p.code,
    prefix: p.flag ? (
      <img src={p.flag} alt={p.label} style={{ width: 20, height: 14, borderRadius: 2, objectFit: 'cover', flexShrink: 0 }} />
    ) : undefined,
  }))

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#07070f' }}>

      {/* ── NAVBAR ─────────────────────────────────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 400,
        height: 60, display: 'flex', alignItems: 'center',
        padding: '0 clamp(20px,4vw,48px)',
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
            <button key={l} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.5)', fontFamily: 'inherit', transition: 'color 0.18s' }}
              onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
              onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)')}
            >{l}</button>
          ))}
        </div>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12 }}>
          <button onClick={handleEnter} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 500, color: 'rgba(255,255,255,0.5)', fontFamily: 'inherit', transition: 'color 0.18s' }}
            onMouseEnter={e => ((e.target as HTMLElement).style.color = '#fff')}
            onMouseLeave={e => ((e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)')}
          >Log In</button>
          <motion.button onClick={handleEnter} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.14, ease: EXPO }}
            style={{ padding: '7px 20px', borderRadius: 999, background: 'rgba(255,255,255,0.09)', border: '1px solid rgba(255,255,255,0.16)', backdropFilter: 'blur(12px)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >Sign In</motion.button>
        </div>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', width: '100%', height: '100dvh', overflow: 'hidden' }}>
        <img src={HERO_IMG} alt="" fetchPriority="high" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 40%' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(7,7,15,0.2) 0%, rgba(7,7,15,0.04) 25%, rgba(7,7,15,0.62) 68%, rgba(7,7,15,0.97) 100%)' }} />

        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '0 clamp(16px,4vw,40px)', textAlign: 'center', paddingTop: 60 }}>


          {/* Search bar */}
          <motion.form onSubmit={handleSearch} initial={{ opacity: 0, y: 14, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease: EXPO, delay: 0.2 }}
            style={{ display: 'flex', alignItems: 'center', width: '100%', maxWidth: 560, borderRadius: 999, background: 'rgba(255,255,255,0.10)', backdropFilter: 'blur(24px) saturate(180%)', WebkitBackdropFilter: 'blur(24px) saturate(180%)', border: '1px solid rgba(255,255,255,0.17)', boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.13)', padding: '5px 5px 5px 20px', gap: 8 }}>
            <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={2} strokeLinecap="round" style={{ flexShrink: 0 }}><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
            <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="BMW Serie 3, Audi A4, Mercedes Clase C..."
              style={{ flex: 1, background: 'none', border: 'none', outline: 'none', fontSize: 15, color: '#fff', fontFamily: 'inherit' }} />
            <motion.button type="submit" whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} transition={{ duration: 0.12, ease: EXPO }}
              style={{ padding: '10px 22px', borderRadius: 999, flexShrink: 0, background: 'rgba(18,15,52,0.92)', border: '1px solid rgba(255,255,255,0.11)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
              Buscar →
            </motion.button>
          </motion.form>

          {/* Filter box */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EXPO, delay: 0.32 }}
            style={{ width: '100%', maxWidth: 560, marginTop: 8, borderRadius: 16, background: 'rgba(255,255,255,0.07)', backdropFilter: 'blur(32px) saturate(200%)', WebkitBackdropFilter: 'blur(32px) saturate(200%)', border: '1px solid rgba(255,255,255,0.11)', boxShadow: '0 16px 48px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.09)', padding: '12px 12px 10px' }}>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 7, marginBottom: 8 }}>
              <MarcaModeloField value={marca} onChange={setMarca} />
              <GlassSelect
                label="País"
                value={pais}
                options={paisOptions}
                onChange={v => setPais(String(v))}
              />
              <GlassSelect
                label="Precio hasta"
                value={precio}
                options={PRECIOS.map(p => ({ label: p.label, value: p.value }))}
                onChange={v => setPrecio(String(v))}
              />
              <GlassSelect
                label="Año desde"
                value={ano}
                options={ANOS.map(a => ({ label: a.label, value: a.value }))}
                onChange={v => setAno(String(v))}
              />
            </div>

            <motion.button
              onClick={handleSearch}
              whileHover={{ scale: 1.012 }}
              whileTap={{ scale: 0.985 }}
              transition={{ duration: 0.14, ease: EXPO }}
              style={{ width: '100%', padding: '11px 0', borderRadius: 10, background: 'rgba(99,102,241,0.20)', border: '1px solid rgba(99,102,241,0.30)', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', letterSpacing: '-0.01em', transition: 'background 0.2s' }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.28)' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.20)' }}
            >
              Mostrar {count.toLocaleString('de-DE')} resultados
            </motion.button>

            {/* Portal logos — true diamond 1+2+3+1 */}
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              transition={{ duration: 0.5, ease: EXPO, delay: 0.44 }}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 10 }}
            >
              <div style={{ display: 'flex' }}>
                {PORTALS.map((p, i) => (
                  <div
                    key={p.name}
                    title={p.name}
                    style={{
                      width: 26, height: 26,
                      borderRadius: 7,
                      background: p.bg,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      marginLeft: i > 0 ? -5 : 0,
                      boxShadow: '0 4px 12px rgba(0,0,0,0.55)',
                      position: 'relative',
                      zIndex: PORTALS.length - i,
                      flexShrink: 0,
                      border: `1.5px solid ${p.border ?? 'rgba(255,255,255,0.10)'}`,
                      transform: 'rotate(8deg)',
                    }}
                  >
                    {p.favicon
                      ? <img src={p.favicon} alt={p.name} style={{ width: 16, height: 16, objectFit: 'contain' }} />
                      : <span style={{ fontSize: 11, fontWeight: 800, color: p.textColor ?? '#fff', letterSpacing: '-0.03em', lineHeight: 1, fontFamily: 'Inter, sans-serif' }}>{p.initial}</span>
                    }
                  </div>
                ))}
              </div>

              <span style={{ fontSize: 12, fontWeight: 500, color: 'rgba(255,255,255,0.42)', whiteSpace: 'nowrap', letterSpacing: '0.01em' }}>
                28.000+ dealers indexados
              </span>
            </motion.div>
          </motion.div>
        </div>
      </div>

      <style>{`
        input::placeholder { color: rgba(255,255,255,0.33) !important; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 4px; }
      `}</style>
    </div>
  )
}
