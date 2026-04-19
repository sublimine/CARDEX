import { motion, AnimatePresence } from 'framer-motion'
import React, { useState } from 'react'
import { Search, Plus, ChevronLeft, ChevronRight, Image, LayoutGrid, List } from 'lucide-react'
import Card from '../components/Card'
import Input from '../components/Input'
import Select from '../components/Select'
import Button from '../components/Button'
import Modal from '../components/Modal'
import { VehicleStatusBadge } from '../components/Badge'
import { Tabs } from '../components/Tabs'
import { PageSkeleton } from '../components/LoadingSpinner'
import EmptyState from '../components/EmptyState'
import { cn } from '../lib/cn'
import { useVehicles } from '../hooks/useVehicles'
import type { Vehicle } from '../types'

const STATUS_OPTIONS = [
  { value: '',           label: 'All statuses' },
  { value: 'listed',     label: 'Listed' },
  { value: 'inquiry',    label: 'Inquiry' },
  { value: 'sold',       label: 'Sold' },
  { value: 'withdrawn',  label: 'Withdrawn' },
]

const MOCK_VEHICLES: Vehicle[] = Array.from({ length: 12 }, (_, i) => ({
  id: `v${i}`,
  tenantId: 't1',
  externalId: `EXT-${100 + i}`,
  vin: `WBA${String(i).padStart(14, '0')}`,
  make: ['BMW', 'Audi', 'Mercedes', 'VW', 'Peugeot'][i % 5],
  model: ['320d', 'A4 2.0 TDI', 'C220d', 'Golf 8', '308 GT'][i % 5],
  year: 2019 + (i % 5),
  status: (['listed', 'inquiry', 'listed', 'sold', 'listed', 'withdrawn'][i % 6] as Vehicle['status']),
  price: 18000 + i * 2500,
  currency: 'EUR',
  daysInStock: 5 + i * 7,
  margin: 1200 + i * 300,
  color: ['Black', 'White', 'Silver', 'Blue', 'Grey'][i % 5],
  fuelType: ['Diesel', 'Petrol', 'Hybrid'][i % 3],
  mileageKm: 30000 + i * 8000,
}))

// ── Vehicle card (grid view) ──────────────────────────────────────────────────
function VehicleCard({ vehicle, onClick }: { vehicle: Vehicle; onClick: () => void }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97 }}
      whileHover={{ y: -3 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      onClick={onClick}
      className="glass rounded-lg overflow-hidden cursor-pointer group"
    >
      <div className="aspect-video bg-glass-medium flex items-center justify-center border-b border-border-subtle">
        <Image className="w-8 h-8 text-text-muted opacity-30 group-hover:opacity-50 transition-opacity" />
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-text-primary truncate">{vehicle.make} {vehicle.model}</p>
            <p className="text-xs text-text-muted mt-0.5">{vehicle.year} · {vehicle.fuelType ?? '—'}</p>
          </div>
          <VehicleStatusBadge status={vehicle.status} />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-base font-bold text-text-primary">€{vehicle.price.toLocaleString()}</span>
          {vehicle.mileageKm && (
            <span className="text-xs text-text-muted">{vehicle.mileageKm.toLocaleString()} km</span>
          )}
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-xs text-text-muted">{vehicle.daysInStock}d in stock</span>
          <span className="text-xs font-medium text-accent-emerald">+€{vehicle.margin.toLocaleString()}</span>
        </div>
      </div>
    </motion.div>
  )
}

// ── Vehicle detail modal ──────────────────────────────────────────────────────
function VehicleDetailModal({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const [tab, setTab] = useState('info')

  const tabItems = [
    {
      value: 'info',
      label: 'Info',
      content: (
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            ['VIN',           vehicle.vin],
            ['Status',        vehicle.status],
            ['Year',          String(vehicle.year)],
            ['Mileage',       `${vehicle.mileageKm?.toLocaleString() ?? '—'} km`],
            ['Fuel',          vehicle.fuelType ?? '—'],
            ['Color',         vehicle.color ?? '—'],
            ['Price',         `€${vehicle.price.toLocaleString()}`],
            ['Days in stock', String(vehicle.daysInStock)],
          ].map(([k, v]) => (
            <div key={k} className="glass rounded-md p-3">
              <p className="text-[11px] text-text-muted uppercase tracking-wide mb-1">{k}</p>
              <p className="font-medium text-text-primary text-sm">{v}</p>
            </div>
          ))}
        </div>
      ),
    },
    {
      value: 'photos',
      label: 'Photos',
      content: (
        <div className="grid grid-cols-3 gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aspect-video bg-glass-medium rounded-md flex items-center justify-center border border-border-subtle">
              <Image className="w-5 h-5 text-text-muted opacity-40" />
            </div>
          ))}
        </div>
      ),
    },
    {
      value: 'docs',
      label: 'Docs',
      content: (
        <p className="text-sm text-text-muted py-4 text-center">No documents generated yet.</p>
      ),
    },
    {
      value: 'finance',
      label: 'Finance',
      content: (
        <div className="space-y-0.5">
          {[
            { label: 'Purchase price',   value: `€${(vehicle.price - vehicle.margin).toLocaleString()}`, accent: false },
            { label: 'Listing price',    value: `€${vehicle.price.toLocaleString()}`,                   accent: false },
            { label: 'Estimated margin', value: `€${vehicle.margin.toLocaleString()}`,                  accent: true  },
          ].map(({ label, value, accent }) => (
            <div key={label} className="flex justify-between py-3 border-b border-border-subtle last:border-0">
              <span className="text-sm text-text-secondary">{label}</span>
              <span className={cn('text-sm font-semibold', accent ? 'text-accent-emerald' : 'text-text-primary')}>
                {value}
              </span>
            </div>
          ))}
        </div>
      ),
    },
    {
      value: 'syndication',
      label: 'Syndication',
      content: (
        <div className="space-y-2">
          {['mobile.de', 'AutoScout24', 'leboncoin'].map((p) => (
            <div key={p} className="flex items-center justify-between p-3 glass rounded-md">
              <span className="text-sm font-medium text-text-primary">{p}</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-glass-medium text-text-muted border border-border-subtle">
                Not published
              </span>
            </div>
          ))}
        </div>
      ),
    },
  ]

  return (
    <Modal open onClose={onClose} title={`${vehicle.make} ${vehicle.model} (${vehicle.year})`} size="xl">
      <Tabs value={tab} onValueChange={setTab} items={tabItems} />
    </Modal>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Vehicles() {
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch]             = useState('')
  const [page, setPage]                 = useState(1)
  const [selected, setSelected]         = useState<Vehicle | null>(null)
  const [viewMode, setViewMode]         = useState<'list' | 'grid'>('list')

  const { data, loading } = useVehicles({ status: statusFilter, page, pageSize: 20 })
  const vehicles = data?.vehicles ?? MOCK_VEHICLES

  const filtered = search
    ? vehicles.filter((v) =>
        `${v.make} ${v.model} ${v.vin}`.toLowerCase().includes(search.toLowerCase()),
      )
    : vehicles

  if (loading && !data) return <PageSkeleton />

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Vehicles</h1>
          <p className="text-sm text-text-muted mt-0.5">{filtered.length} in inventory</p>
        </div>
        <Button icon={<Plus className="w-4 h-4" />} size="sm">Add vehicle</Button>
      </div>

      {/* Filter bar */}
      <div className="glass rounded-lg p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <Input
          icon={<Search className="w-4 h-4" />}
          placeholder="Search make, model, VIN…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
        />
        <Select
          options={STATUS_OPTIONS}
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="sm:w-40"
        />
        {/* View toggle */}
        <div className="flex gap-1 glass rounded-md p-0.5 shrink-0">
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'p-1.5 rounded transition-colors',
              viewMode === 'list' ? 'bg-glass-strong text-text-primary' : 'text-text-muted hover:text-text-secondary',
            )}
          >
            <List className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={cn(
              'p-1.5 rounded transition-colors',
              viewMode === 'grid' ? 'bg-glass-strong text-text-primary' : 'text-text-muted hover:text-text-secondary',
            )}
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {filtered.length === 0 ? (
          <EmptyState
            key="empty"
            icon={<Search className="w-6 h-6" />}
            title="No vehicles found"
            message="Try adjusting your search or filter."
          />
        ) : viewMode === 'grid' ? (
          <motion.div
            key="grid"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3"
          >
            {filtered.map((v) => (
              <VehicleCard key={v.id} vehicle={v} onClick={() => setSelected(v)} />
            ))}
          </motion.div>
        ) : (
          <motion.div
            key="list"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <Card padding={false}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px]">
                  <thead>
                    <tr className="border-b border-border-subtle">
                      {['Vehicle', 'Year', 'Price', 'Status', 'Days in stock', 'Margin'].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-[11px] font-medium text-text-muted uppercase tracking-wider">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((v, idx) => (
                      <motion.tr
                        key={v.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.025, duration: 0.2 }}
                        onClick={() => setSelected(v)}
                        className="border-b border-border-subtle/50 last:border-0 hover:bg-glass-subtle cursor-pointer transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="w-12 h-9 bg-glass-medium rounded-md flex items-center justify-center shrink-0 border border-border-subtle">
                              <Image className="w-4 h-4 text-text-muted opacity-40" />
                            </div>
                            <div>
                              <p className="text-sm font-medium text-text-primary">{v.make} {v.model}</p>
                              <p className="text-xs text-text-muted font-mono tracking-wide">{v.vin}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-text-secondary">{v.year}</td>
                        <td className="px-4 py-3 text-sm font-semibold text-text-primary">€{v.price.toLocaleString()}</td>
                        <td className="px-4 py-3"><VehicleStatusBadge status={v.status} /></td>
                        <td className="px-4 py-3 text-sm text-text-secondary">{v.daysInStock}d</td>
                        <td className="px-4 py-3 text-sm font-semibold text-accent-emerald">€{v.margin.toLocaleString()}</td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-border-subtle">
                <p className="text-xs text-text-muted">{filtered.length} vehicles</p>
                <div className="flex items-center gap-1">
                  <motion.button
                    whileTap={{ scale: 0.92 }}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="p-1.5 rounded-md hover:bg-glass-medium text-text-muted disabled:opacity-30 transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </motion.button>
                  <span className="px-2 py-1 text-xs text-text-secondary">Page {page}</span>
                  <motion.button
                    whileTap={{ scale: 0.92 }}
                    onClick={() => setPage((p) => p + 1)}
                    className="p-1.5 rounded-md hover:bg-glass-medium text-text-muted transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </motion.button>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {selected && (
        <VehicleDetailModal vehicle={selected} onClose={() => setSelected(null)} />
      )}
    </motion.div>
  )
}
