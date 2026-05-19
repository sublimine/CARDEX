import { motion, AnimatePresence } from 'framer-motion'
import React, { useState } from 'react'
import {
  Search, Plus, ChevronLeft, ChevronRight, Car,
  Fuel, Settings2, MapPin, Calendar, Activity,
  Heart, ExternalLink, SlidersHorizontal, LayoutGrid,
  List, ArrowUpDown, CheckCircle2,
} from 'lucide-react'
import Modal from '../components/Modal'
import { Tabs } from '../components/Tabs'
import { PageSkeleton } from '../components/LoadingSpinner'
import EmptyState from '../components/EmptyState'
import { cn } from '../lib/cn'
import { useVehicles } from '../hooks/useVehicles'
import type { Vehicle } from '../types'

const STATUS_OPTIONS = [
  { value: '',            label: 'All statuses' },
  { value: 'available',   label: 'Available' },
  { value: 'inquiry',     label: 'Inquiry' },
  { value: 'reserved',    label: 'Reserved' },
  { value: 'sold',        label: 'Sold' },
]

const SORT_OPTIONS = [
  { value: 'newest',       label: 'Newest first' },
  { value: 'price_asc',    label: 'Price: low → high' },
  { value: 'price_desc',   label: 'Price: high → low' },
  { value: 'days_asc',     label: 'Days in stock' },
]

const MOCK_VEHICLES: Vehicle[] = Array.from({ length: 20 }, (_, i) => ({
  id: `v${i}`,
  tenantId: 't1',
  externalId: `EXT-${100 + i}`,
  vin: `WBA${String(i).padStart(14, '0')}`,
  make: ['BMW', 'Audi', 'Mercedes-Benz', 'Volkswagen', 'Peugeot', 'Renault', 'Skoda', 'Toyota'][i % 8],
  model: ['320d xDrive', 'A4 2.0 TDI', 'C220d AMG Line', 'Golf 8 GTI', '308 GT', 'Mégane RS', 'Octavia 2.0 TDI', 'Corolla Hybrid'][i % 8],
  year: 2018 + (i % 6),
  status: (['available', 'inquiry', 'available', 'sold', 'available', 'reserved'][i % 6] as Vehicle['status']),
  price: [22900, 31500, 38900, 26500, 19900, 24700, 21400, 18900, 29500, 34200, 15900, 27800, 33100, 22300, 19100, 41500, 28700, 17500, 36900, 23400][i],
  currency: 'EUR',
  daysInStock: 3 + i * 5,
  margin: 1400 + i * 280,
  color: ['Mineral White', 'Daytona Violet', 'Selenite Grey', 'Deep Black', 'Pearl White', 'Flame Red', 'Magnetite Blue', 'Platinum Silver'][i % 8],
  fuelType: ['Diesel', 'Petrol', 'Hybrid', 'Diesel', 'Petrol', 'Petrol', 'Diesel', 'Hybrid'][i % 8],
  mileageKm: [28000, 67000, 44000, 12000, 89000, 53000, 31000, 71000, 22000, 58000, 95000, 39000, 17000, 82000, 46000, 9000, 63000, 77000, 34000, 51000][i],
  powerKw: [140, 110, 143, 180, 96, 205, 110, 98, 165, 135, 88, 120, 150, 118, 101, 210, 130, 95, 175, 112][i],
}))

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  available: { bg: 'rgba(0,214,138,0.1)',  text: '#00d68a', dot: '#00d68a' },
  inquiry:   { bg: 'rgba(91,141,248,0.1)', text: '#5b8df8', dot: '#5b8df8' },
  reserved:  { bg: 'rgba(255,179,71,0.1)', text: '#ffb347', dot: '#ffb347' },
  sold:      { bg: 'rgba(255,85,119,0.1)', text: '#ff5577', dot: '#ff5577' },
}

const FUEL_ICONS: Record<string, string> = {
  Diesel: '⛽', Petrol: '🔋', Hybrid: '⚡', Electric: '⚡',
}

// ── Gradient thumbnail per make ───────────────────────────────────────────────
const MAKE_GRAD: Record<string, [string, string]> = {
  'BMW':           ['#1a1a2e', '#0d1b3e'],
  'Audi':          ['#1a1018', '#2a0a0a'],
  'Mercedes-Benz': ['#0d1a14', '#091a0d'],
  'Volkswagen':    ['#0a1020', '#101828'],
  'Peugeot':       ['#18100a', '#200e00'],
  'Renault':       ['#0a1418', '#071820'],
  'Skoda':         ['#0a1a10', '#061408'],
  'Toyota':        ['#1a0a08', '#200800'],
}

function VehicleThumbnail({ make, status }: { make: string; status: string }) {
  const [g1, g2] = MAKE_GRAD[make] ?? ['#0e0e18', '#0a0a14']
  return (
    <div style={{
      width: '100%', height: '100%',
      background: `linear-gradient(135deg, ${g1} 0%, ${g2} 100%)`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Subtle gradient overlay */}
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 30% 50%, rgba(255,255,255,0.04) 0%, transparent 60%)' }} />
      <Car style={{ width: 48, height: 48, opacity: 0.15, color: '#fff' }} strokeWidth={1.1} />
      {/* Make label watermark */}
      <div style={{ position: 'absolute', bottom: 10, left: 12, fontSize: 10, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.12)' }}>
        {make}
      </div>
    </div>
  )
}

// ── mobile.de-style listing row ───────────────────────────────────────────────
function ListingRow({ vehicle, idx, onClick }: { vehicle: Vehicle; idx: number; onClick: () => void }) {
  const [saved, setSaved] = useState(false)
  const sc = STATUS_COLORS[vehicle.status] ?? STATUS_COLORS.available

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ delay: idx * 0.03, duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
      onClick={onClick}
      style={{
        display: 'flex', gap: 0, cursor: 'pointer',
        background: '#0e0e18',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 14,
        overflow: 'hidden',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        position: 'relative',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(91,141,248,0.25)'
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = '0 4px 24px rgba(0,0,0,0.5), 0 0 0 1px rgba(91,141,248,0.12)'
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.07)'
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
      }}
    >
      {/* Thumbnail */}
      <div style={{ width: 240, minWidth: 240, height: 160, flexShrink: 0, position: 'relative', borderRight: '1px solid rgba(255,255,255,0.06)' }}>
        <VehicleThumbnail make={vehicle.make} status={vehicle.status} />
        {/* Status badge over image */}
        <div style={{
          position: 'absolute', top: 10, left: 10,
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '3px 9px', borderRadius: 999,
          background: sc.bg, border: `1px solid ${sc.dot}40`,
        }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: sc.dot, display: 'block' }} />
          <span style={{ fontSize: 10, fontWeight: 700, color: sc.text, textTransform: 'capitalize', letterSpacing: '0.04em' }}>
            {vehicle.status}
          </span>
        </div>
        {/* Days badge */}
        <div style={{ position: 'absolute', bottom: 10, right: 10, padding: '2px 8px', borderRadius: 6, background: 'rgba(0,0,0,0.6)', fontSize: 10, color: 'rgba(255,255,255,0.4)', fontWeight: 500 }}>
          {vehicle.daysInStock}d
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: '16px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', minWidth: 0 }}>
        {/* Top: title + price */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 10 }}>
          <div style={{ minWidth: 0 }}>
            <h3 style={{ fontSize: 16, fontWeight: 800, color: '#e8e8f8', letterSpacing: '-0.01em', marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {vehicle.make} {vehicle.model}
            </h3>
            <p style={{ fontSize: 12, color: '#38385a', fontFamily: 'Plus Jakarta Sans' }}>
              {vehicle.color ?? '—'} · {vehicle.fuelType ?? '—'}
            </p>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 900, color: '#f0f0fa', letterSpacing: '-0.02em', lineHeight: 1 }}>
              €{vehicle.price.toLocaleString()}
            </div>
            <div style={{ fontSize: 11, color: '#00d68a', fontWeight: 600, marginTop: 3 }}>
              +€{vehicle.margin.toLocaleString()} margin
            </div>
          </div>
        </div>

        {/* Specs row — mobile.de style */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'nowrap', marginBottom: 12, overflow: 'hidden' }}>
          {[
            { icon: Calendar,  val: vehicle.year },
            { icon: Activity,  val: `${vehicle.mileageKm?.toLocaleString()} km` },
            { icon: Fuel,      val: vehicle.fuelType ?? '—' },
            { icon: Settings2, val: 'Manual' },
            vehicle.powerKw ? { icon: Zap, val: `${vehicle.powerKw} kW` } : null,
          ].filter(Boolean).map((spec, si) => spec && (
            <React.Fragment key={si}>
              {si > 0 && <span style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.08)', margin: '0 12px', flexShrink: 0 }} />}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
                <spec.icon style={{ width: 13, height: 13, color: '#38385a', flexShrink: 0 }} strokeWidth={1.8} />
                <span style={{ fontSize: 12, color: '#7070a0', fontWeight: 500 }}>{spec.val}</span>
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* Footer: VIN + actions */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <MapPin style={{ width: 12, height: 12, color: '#38385a' }} strokeWidth={1.8} />
            <span style={{ fontSize: 11, color: '#38385a', fontFamily: 'monospace', letterSpacing: '0.05em' }}>
              {vehicle.vin?.slice(0, 17) ?? 'VIN N/A'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <motion.button
              whileTap={{ scale: 0.92 }}
              onClick={e => { e.stopPropagation(); setSaved(s => !s) }}
              style={{
                width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: saved ? 'rgba(255,85,119,0.12)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${saved ? 'rgba(255,85,119,0.3)' : 'rgba(255,255,255,0.08)'}`,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              <Heart style={{ width: 14, height: 14, color: saved ? '#ff5577' : '#38385a', fill: saved ? '#ff5577' : 'none' }} strokeWidth={2} />
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.92 }}
              onClick={e => e.stopPropagation()}
              style={{
                height: 32, padding: '0 14px', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700,
                background: 'rgba(91,141,248,0.12)', border: '1px solid rgba(91,141,248,0.25)',
                color: '#5b8df8', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans',
                transition: 'all 0.15s',
              }}
            >
              Details <ExternalLink style={{ width: 11, height: 11 }} />
            </motion.button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// ── Grid card (mobile.de photo-grid style) ────────────────────────────────────
function GridCard({ vehicle, idx, onClick }: { vehicle: Vehicle; idx: number; onClick: () => void }) {
  const [saved, setSaved] = useState(false)
  const sc = STATUS_COLORS[vehicle.status] ?? STATUS_COLORS.available

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ delay: idx * 0.04, duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
      onClick={onClick}
      style={{
        background: '#0e0e18',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 14, overflow: 'hidden', cursor: 'pointer',
        transition: 'border-color 0.2s, transform 0.2s',
      }}
      whileHover={{ y: -3, borderColor: 'rgba(91,141,248,0.3)' } as any}
    >
      {/* Image */}
      <div style={{ aspectRatio: '16/10', position: 'relative', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <VehicleThumbnail make={vehicle.make} status={vehicle.status} />
        <div style={{ position: 'absolute', top: 10, left: 10, display: 'flex', alignItems: 'center', gap: 5, padding: '3px 9px', borderRadius: 999, background: sc.bg, border: `1px solid ${sc.dot}40` }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: sc.dot, display: 'block' }} />
          <span style={{ fontSize: 10, fontWeight: 700, color: sc.text, textTransform: 'capitalize' }}>{vehicle.status}</span>
        </div>
        <button
          onClick={e => { e.stopPropagation(); setSaved(s => !s) }}
          style={{ position: 'absolute', top: 10, right: 10, width: 28, height: 28, borderRadius: 7, background: 'rgba(0,0,0,0.5)', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <Heart style={{ width: 13, height: 13, color: saved ? '#ff5577' : 'rgba(255,255,255,0.5)', fill: saved ? '#ff5577' : 'none' }} strokeWidth={2} />
        </button>
      </div>

      {/* Info */}
      <div style={{ padding: '14px 14px 12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={{ fontSize: 14, fontWeight: 800, color: '#e8e8f8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', letterSpacing: '-0.01em' }}>
              {vehicle.make} {vehicle.model}
            </p>
            <p style={{ fontSize: 11, color: '#38385a', marginTop: 2 }}>{vehicle.year}</p>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 8 }}>
            <p style={{ fontSize: 16, fontWeight: 900, color: '#f0f0fa', letterSpacing: '-0.02em' }}>€{vehicle.price.toLocaleString()}</p>
          </div>
        </div>
        {/* Specs */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {[
            `${vehicle.mileageKm?.toLocaleString()} km`,
            vehicle.fuelType ?? '—',
            `${vehicle.powerKw ?? '—'} kW`,
          ].map(tag => (
            <span key={tag} style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)', color: '#50507a' }}>
              {tag}
            </span>
          ))}
        </div>
      </div>
    </motion.div>
  )
}

// ── Vehicle detail modal ──────────────────────────────────────────────────────
function VehicleModal({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const [tab, setTab] = useState('info')
  const sc = STATUS_COLORS[vehicle.status] ?? STATUS_COLORS.available

  return (
    <Modal open onClose={onClose} title={`${vehicle.make} ${vehicle.model} (${vehicle.year})`} size="xl">
      <Tabs
        value={tab}
        onValueChange={setTab}
        items={[
          {
            value: 'info',
            label: 'Info',
            content: (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                {[
                  ['Status',       vehicle.status],
                  ['Year',         String(vehicle.year)],
                  ['Mileage',      `${vehicle.mileageKm?.toLocaleString() ?? '—'} km`],
                  ['Fuel',         vehicle.fuelType ?? '—'],
                  ['Power',        vehicle.powerKw ? `${vehicle.powerKw} kW` : '—'],
                  ['Color',        vehicle.color ?? '—'],
                  ['VIN',          vehicle.vin ?? '—'],
                  ['Days in stock', `${vehicle.daysInStock}d`],
                  ['External ID',  vehicle.externalId ?? '—'],
                ].map(([k, v]) => (
                  <div key={k} style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10 }}>
                    <p style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#38385a', marginBottom: 5 }}>{k}</p>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#e0e0f0' }}>{v}</p>
                  </div>
                ))}
              </div>
            ),
          },
          {
            value: 'finance',
            label: 'Finance',
            content: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {[
                  { label: 'Purchase price',   value: `€${(vehicle.price - vehicle.margin).toLocaleString()}`, accent: false },
                  { label: 'Listing price',    value: `€${vehicle.price.toLocaleString()}`,                   accent: false },
                  { label: 'Gross margin',     value: `€${vehicle.margin.toLocaleString()}`,                  accent: true  },
                  { label: 'Margin %',         value: `${((vehicle.margin / vehicle.price) * 100).toFixed(1)}%`, accent: true },
                ].map(({ label, value, accent }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 4px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <span style={{ fontSize: 13, color: '#7070a0' }}>{label}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: accent ? '#00d68a' : '#e0e0f0' }}>{value}</span>
                  </div>
                ))}
              </div>
            ),
          },
          {
            value: 'syndication',
            label: 'Syndication',
            content: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {['mobile.de', 'AutoScout24', 'leboncoin', 'Marktplaats'].map(p => (
                  <div key={p} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#c0c0d8' }}>{p}</span>
                    <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.04)', color: '#38385a', border: '1px solid rgba(255,255,255,0.07)' }}>Not published</span>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </Modal>
  )
}

// ── Zap import needed ─────────────────────────────────────────────────────────
function Zap({ style, strokeWidth }: { style?: React.CSSProperties; strokeWidth?: number }) {
  return <Activity style={style} strokeWidth={strokeWidth} />
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Vehicles() {
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch]             = useState('')
  const [sort, setSort]                 = useState('newest')
  const [page, setPage]                 = useState(1)
  const [selected, setSelected]         = useState<Vehicle | null>(null)
  const [view, setView]                 = useState<'list' | 'grid'>('list')
  const [showFilters, setShowFilters]   = useState(false)

  const { data, loading } = useVehicles({ status: statusFilter, page, pageSize: 20 })
  const vehicles = data?.vehicles ?? MOCK_VEHICLES
  const total    = data?.total ?? MOCK_VEHICLES.length

  const filtered = search
    ? vehicles.filter(v => `${v.make} ${v.model} ${v.vin}`.toLowerCase().includes(search.toLowerCase()))
    : vehicles

  if (loading && !data) return <PageSkeleton />

  return (
    <div style={{ padding: '24px 28px 48px', maxWidth: 1200, margin: '0 auto', fontFamily: 'Plus Jakarta Sans' }}>

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
        style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 24 }}
      >
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 900, letterSpacing: '-0.02em', color: '#f0f0fa', marginBottom: 4 }}>Inventory</h1>
          <p style={{ fontSize: 13, color: '#38385a' }}>{total} vehicles in stock</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
          transition={{ type: 'spring', stiffness: 420, damping: 22 }}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', borderRadius: 10, fontSize: 13, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg, #4f6ef0, #7b45e8)', border: 'none', cursor: 'pointer', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 0 20px rgba(91,141,248,0.2)' }}
        >
          <Plus style={{ width: 15, height: 15 }} />
          Add vehicle
        </motion.button>
      </motion.div>

      {/* Search + filter bar */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05, duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
        style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16 }}
      >
        {/* Search */}
        <div style={{ flex: 1, position: 'relative' }}>
          <Search style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', width: 15, height: 15, color: '#38385a', pointerEvents: 'none' }} />
          <input
            type="text"
            placeholder="Search make, model, VIN…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              width: '100%', padding: '10px 12px 10px 38px', borderRadius: 10,
              background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)',
              color: '#f0f0fa', fontSize: 13, fontFamily: 'Plus Jakarta Sans',
              outline: 'none', transition: 'border-color 0.2s',
            }}
            onFocus={e => (e.target.style.borderColor = 'rgba(91,141,248,0.5)')}
            onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.08)')}
          />
        </div>

        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          style={{ padding: '10px 14px', borderRadius: 10, background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)', color: '#7070a0', fontSize: 13, fontFamily: 'Plus Jakarta Sans', cursor: 'pointer', minWidth: 150 }}
        >
          {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* Sort */}
        <select
          value={sort}
          onChange={e => setSort(e.target.value)}
          style={{ padding: '10px 14px', borderRadius: 10, background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)', color: '#7070a0', fontSize: 13, fontFamily: 'Plus Jakarta Sans', cursor: 'pointer', minWidth: 160 }}
        >
          {SORT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* View toggle */}
        <div style={{ display: 'flex', background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 3, gap: 2 }}>
          {([['list', List], ['grid', LayoutGrid]] as const).map(([v, Icon]) => (
            <button
              key={v}
              onClick={() => setView(v)}
              style={{
                width: 34, height: 34, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: view === v ? 'rgba(91,141,248,0.15)' : 'transparent',
                border: view === v ? '1px solid rgba(91,141,248,0.3)' : '1px solid transparent',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              <Icon style={{ width: 15, height: 15, color: view === v ? '#5b8df8' : '#38385a' }} />
            </button>
          ))}
        </div>
      </motion.div>

      {/* Results count */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <p style={{ fontSize: 12, color: '#38385a' }}>
          {filtered.length} {filtered.length === 1 ? 'result' : 'results'}
          {search && ` for "${search}"`}
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <CheckCircle2 style={{ width: 12, height: 12, color: '#00d68a' }} />
          <span style={{ fontSize: 11, color: '#38385a' }}>Live data</span>
        </div>
      </div>

      {/* Listings */}
      <AnimatePresence mode="wait">
        {filtered.length === 0 ? (
          <EmptyState key="empty" icon={<Search style={{ width: 24, height: 24 }} />} title="No vehicles found" message="Adjust your search or filters." />
        ) : view === 'list' ? (
          <motion.div key="list" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filtered.map((v, i) => (
              <ListingRow key={v.id} vehicle={v} idx={i} onClick={() => setSelected(v)} />
            ))}
          </motion.div>
        ) : (
          <motion.div key="grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 14 }}>
            {filtered.map((v, i) => (
              <GridCard key={v.id} vehicle={v} idx={i} onClick={() => setSelected(v)} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Pagination */}
      {filtered.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, padding: '12px 0', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <span style={{ fontSize: 12, color: '#38385a' }}>Page {page}</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <motion.button
              whileTap={{ scale: 0.93 }}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{ padding: '8px 16px', borderRadius: 9, background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)', color: '#5b8df8', fontSize: 13, fontWeight: 600, cursor: page === 1 ? 'not-allowed' : 'pointer', opacity: page === 1 ? 0.3 : 1, fontFamily: 'Plus Jakarta Sans' }}
            >
              ← Prev
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.93 }}
              onClick={() => setPage(p => p + 1)}
              style={{ padding: '8px 16px', borderRadius: 9, background: '#0e0e18', border: '1px solid rgba(255,255,255,0.08)', color: '#5b8df8', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'Plus Jakarta Sans' }}
            >
              Next →
            </motion.button>
          </div>
        </div>
      )}

      {selected && <VehicleModal vehicle={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
