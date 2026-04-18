import React, { useState } from 'react'
import { Search, Plus, ChevronLeft, ChevronRight, Image } from 'lucide-react'
import Card from '../components/Card'
import Input from '../components/Input'
import Select from '../components/Select'
import Button from '../components/Button'
import Modal from '../components/Modal'
import { VehicleStatusBadge } from '../components/Badge'
import { PageSkeleton } from '../components/LoadingSpinner'
import { useVehicles } from '../hooks/useVehicles'
import type { Vehicle } from '../types'

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'listed', label: 'Listed' },
  { value: 'inquiry', label: 'Inquiry' },
  { value: 'sold', label: 'Sold' },
  { value: 'withdrawn', label: 'Withdrawn' },
]

// ── Mock data used when API not yet connected ─────────────────────────────────
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

function VehicleDetailModal({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const [tab, setTab] = useState<'info' | 'photos' | 'docs' | 'finance' | 'syndication'>('info')
  const tabs = ['info', 'photos', 'docs', 'finance', 'syndication'] as const

  return (
    <Modal open onClose={onClose} title={`${vehicle.make} ${vehicle.model} (${vehicle.year})`} size="xl">
      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-200 dark:border-gray-700 -mt-1 pb-0">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium capitalize rounded-t transition-colors ${
              tab === t
                ? 'text-brand-600 border-b-2 border-brand-600'
                : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'info' && (
        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            ['VIN', vehicle.vin],
            ['Status', vehicle.status],
            ['Year', String(vehicle.year)],
            ['Mileage', `${vehicle.mileageKm?.toLocaleString() ?? '—'} km`],
            ['Fuel', vehicle.fuelType ?? '—'],
            ['Color', vehicle.color ?? '—'],
            ['Price', `€${vehicle.price.toLocaleString()}`],
            ['Days in stock', String(vehicle.daysInStock)],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="text-gray-400 text-xs mb-0.5">{k}</p>
              <p className="font-medium text-gray-900 dark:text-white">{v}</p>
            </div>
          ))}
        </div>
      )}

      {tab === 'photos' && (
        <div className="grid grid-cols-3 gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="aspect-video bg-gray-100 dark:bg-gray-700 rounded-lg flex items-center justify-center"
            >
              <Image className="w-6 h-6 text-gray-300" />
            </div>
          ))}
        </div>
      )}

      {tab === 'docs' && (
        <p className="text-sm text-gray-400">No documents generated yet.</p>
      )}

      {tab === 'finance' && (
        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-700">
            <span className="text-gray-500">Purchase price</span>
            <span className="font-medium">€{(vehicle.price - vehicle.margin).toLocaleString()}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-700">
            <span className="text-gray-500">Listing price</span>
            <span className="font-medium">€{vehicle.price.toLocaleString()}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-gray-500">Estimated margin</span>
            <span className="font-medium text-green-600">€{vehicle.margin.toLocaleString()}</span>
          </div>
        </div>
      )}

      {tab === 'syndication' && (
        <div className="space-y-2">
          {['mobile.de', 'AutoScout24', 'leboncoin'].map((p) => (
            <div
              key={p}
              className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700"
            >
              <span className="text-sm font-medium">{p}</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500">
                Not published
              </span>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

export default function Vehicles() {
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Vehicle | null>(null)

  const { data, loading } = useVehicles({ status: statusFilter, page, pageSize: 20 })
  const vehicles = data?.vehicles ?? MOCK_VEHICLES

  const filtered = search
    ? vehicles.filter((v) =>
        `${v.make} ${v.model} ${v.vin}`.toLowerCase().includes(search.toLowerCase()),
      )
    : vehicles

  if (loading && !data) return <PageSkeleton />

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Vehicles</h1>
        <Button icon={<Plus className="w-4 h-4" />} size="sm">Add vehicle</Button>
      </div>

      {/* Filters */}
      <Card padding={false}>
        <div className="flex flex-col sm:flex-row gap-3 p-4">
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
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="border-y border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                {['Vehicle', 'Year', 'Price', 'Status', 'Days in stock', 'Margin'].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {filtered.map((v) => (
                <tr
                  key={v.id}
                  onClick={() => setSelected(v)}
                  className="hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-9 bg-gray-100 dark:bg-gray-700 rounded-md flex items-center justify-center shrink-0">
                        <Image className="w-4 h-4 text-gray-300" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{v.make} {v.model}</p>
                        <p className="text-xs text-gray-400">{v.vin}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{v.year}</td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                    €{v.price.toLocaleString()}
                  </td>
                  <td className="px-4 py-3"><VehicleStatusBadge status={v.status} /></td>
                  <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{v.daysInStock}d</td>
                  <td className="px-4 py-3 text-sm font-medium text-green-600 dark:text-green-400">
                    €{v.margin.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs text-gray-500">{filtered.length} vehicles</p>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 py-1 text-xs text-gray-600 dark:text-gray-400">Page {page}</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </Card>

      {selected && <VehicleDetailModal vehicle={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
