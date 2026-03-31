'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Plus, Search, Car, ExternalLink, MoreHorizontal } from 'lucide-react'

interface InventoryItem {
  id: string
  make: string
  model: string
  year: number
  price: number
  mileage: number
  status: 'ACTIVE' | 'SOLD' | 'DRAFT'
  platforms: string[]
  views: number
  leads: number
}

const MOCK_INVENTORY: InventoryItem[] = [
  {
    id: '1', make: 'BMW', model: '320d', year: 2021, price: 28900,
    mileage: 45000, status: 'ACTIVE', platforms: ['AutoScout24', 'mobile.de'], views: 312, leads: 4,
  },
  {
    id: '2', make: 'Volkswagen', model: 'Golf GTI', year: 2020, price: 26500,
    mileage: 52000, status: 'ACTIVE', platforms: ['AutoScout24'], views: 198, leads: 2,
  },
  {
    id: '3', make: 'Mercedes-Benz', model: 'C220d', year: 2019, price: 24200,
    mileage: 78000, status: 'DRAFT', platforms: [], views: 0, leads: 0,
  },
]

const STATUS_BADGE: Record<string, string> = {
  ACTIVE: 'bg-brand-500/20 text-brand-400',
  SOLD: 'bg-surface-hover text-surface-muted',
  DRAFT: 'bg-yellow-500/20 text-yellow-400',
}

export default function InventoryPage() {
  const [search, setSearch] = useState('')
  const filtered = MOCK_INVENTORY.filter(item =>
    `${item.make} ${item.model}`.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Inventory</h1>
          <p className="mt-1 text-sm text-surface-muted">{MOCK_INVENTORY.length} vehicles</p>
        </div>
        <Link
          href="/dashboard/inventory/new"
          className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 font-medium text-white hover:bg-brand-600 transition-colors"
        >
          <Plus size={16} /> Add vehicle
        </Link>
      </div>

      {/* Search */}
      <div className="mb-4 relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-muted" />
        <input
          type="text"
          placeholder="Search inventory…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full rounded-xl border border-surface-border bg-surface-card pl-9 pr-4 py-2.5 text-sm text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="px-4 py-3 text-left font-medium text-surface-muted">Vehicle</th>
              <th className="px-4 py-3 text-right font-medium text-surface-muted">Price</th>
              <th className="px-4 py-3 text-right font-medium text-surface-muted hidden sm:table-cell">Mileage</th>
              <th className="px-4 py-3 text-center font-medium text-surface-muted hidden md:table-cell">Status</th>
              <th className="px-4 py-3 text-right font-medium text-surface-muted hidden lg:table-cell">Views / Leads</th>
              <th className="px-4 py-3 text-left font-medium text-surface-muted hidden lg:table-cell">Platforms</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((item, i) => (
              <tr key={item.id}
                className={`border-b border-surface-border hover:bg-surface-hover transition-colors ${i === filtered.length - 1 ? 'border-0' : ''}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-hover text-surface-muted">
                      <Car size={16} />
                    </div>
                    <div>
                      <p className="font-medium text-white">{item.make} {item.model}</p>
                      <p className="text-xs text-surface-muted">{item.year}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-right font-mono font-semibold text-white">
                  €{item.price.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right font-mono text-surface-muted hidden sm:table-cell">
                  {item.mileage.toLocaleString()} km
                </td>
                <td className="px-4 py-3 text-center hidden md:table-cell">
                  <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[item.status]}`}>
                    {item.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono text-surface-muted hidden lg:table-cell">
                  {item.views} / {item.leads}
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {item.platforms.map(p => (
                      <span key={p} className="rounded bg-surface-hover px-1.5 py-0.5 text-xs text-surface-muted">
                        {p}
                      </span>
                    ))}
                    {item.platforms.length === 0 && (
                      <span className="text-xs text-surface-muted">Not published</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <button className="rounded-lg p-1.5 text-surface-muted hover:bg-surface-hover hover:text-white transition-colors">
                    <MoreHorizontal size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-surface-muted">
                  No vehicles found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
