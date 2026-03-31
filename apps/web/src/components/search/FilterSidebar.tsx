'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useTransition } from 'react'
import { COUNTRY_FLAG, COUNTRY_NAME } from '@/lib/format'

const COUNTRIES = ['DE', 'ES', 'FR', 'NL', 'BE', 'CH']
const FUELS = ['PETROL', 'DIESEL', 'ELECTRIC', 'HYBRID_PETROL', 'HYBRID_DIESEL']
const TX = ['MANUAL', 'AUTOMATIC']

export function FilterSidebar({
  facets,
}: {
  facets?: Record<string, Record<string, number>>
}) {
  const router = useRouter()
  const sp = useSearchParams()
  const [isPending, startTransition] = useTransition()

  function toggle(key: string, value: string) {
    const params = new URLSearchParams(sp.toString())
    const cur = params.get(key) ?? ''
    const vals = cur ? cur.split(',') : []
    const idx = vals.indexOf(value)
    if (idx >= 0) vals.splice(idx, 1)
    else vals.push(value)
    if (vals.length) params.set(key, vals.join(','))
    else params.delete(key)
    params.set('page', '1')
    startTransition(() => router.push(`/search?${params.toString()}`))
  }

  function setRange(key: string, value: string) {
    const params = new URLSearchParams(sp.toString())
    if (value) params.set(key, value)
    else params.delete(key)
    params.set('page', '1')
    startTransition(() => router.push(`/search?${params.toString()}`))
  }

  const activeCountries = (sp.get('country') ?? '').split(',').filter(Boolean)
  const activeFuels = (sp.get('fuel') ?? '').split(',').filter(Boolean)
  const activeTx = (sp.get('tx') ?? '').split(',').filter(Boolean)

  return (
    <aside className={`flex flex-col gap-6 text-sm ${isPending ? 'opacity-60 pointer-events-none' : ''}`}>

      {/* Price range */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Price (EUR)</h3>
        <div className="flex gap-2">
          <input type="number" placeholder="Min" min={0} defaultValue={sp.get('price_min') ?? ''}
            onBlur={e => setRange('price_min', e.target.value)}
            className="w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
          <input type="number" placeholder="Max" min={0} defaultValue={sp.get('price_max') ?? ''}
            onBlur={e => setRange('price_max', e.target.value)}
            className="w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
        </div>
      </section>

      {/* Year range */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Year</h3>
        <div className="flex gap-2">
          <input type="number" placeholder="From" min={1990} max={2025} defaultValue={sp.get('year_min') ?? ''}
            onBlur={e => setRange('year_min', e.target.value)}
            className="w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
          <input type="number" placeholder="To" min={1990} max={2025} defaultValue={sp.get('year_max') ?? ''}
            onBlur={e => setRange('year_max', e.target.value)}
            className="w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
        </div>
      </section>

      {/* Mileage */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Max mileage (km)</h3>
        <input type="number" placeholder="e.g. 100000" min={0} defaultValue={sp.get('mileage_max') ?? ''}
          onBlur={e => setRange('mileage_max', e.target.value)}
          className="w-full rounded-md border border-surface-border bg-surface px-2 py-1.5 text-xs text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none" />
      </section>

      {/* Country */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Country</h3>
        <div className="flex flex-col gap-1.5">
          {COUNTRIES.map(c => {
            const count = facets?.source_country?.[c]
            return (
              <button key={c} onClick={() => toggle('country', c)}
                className={`flex items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors ${
                  activeCountries.includes(c)
                    ? 'bg-brand-500/20 text-brand-400'
                    : 'text-surface-muted hover:bg-surface-hover hover:text-white'
                }`}>
                <span>{COUNTRY_FLAG[c]} {COUNTRY_NAME[c]}</span>
                {count != null && <span className="text-xs opacity-60">{count.toLocaleString()}</span>}
              </button>
            )
          })}
        </div>
      </section>

      {/* Fuel */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Fuel type</h3>
        <div className="flex flex-col gap-1.5">
          {FUELS.map(f => {
            const label = f.replace('_', ' ').replace('HYBRID ', 'Hybrid ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())
            return (
              <button key={f} onClick={() => toggle('fuel', f)}
                className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors ${
                  activeFuels.includes(f)
                    ? 'bg-brand-500/20 text-brand-400'
                    : 'text-surface-muted hover:bg-surface-hover hover:text-white'
                }`}>
                {label}
              </button>
            )
          })}
        </div>
      </section>

      {/* Transmission */}
      <section>
        <h3 className="mb-3 font-semibold text-white">Transmission</h3>
        <div className="flex gap-2">
          {TX.map(t => (
            <button key={t} onClick={() => toggle('tx', t)}
              className={`flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                activeTx.includes(t)
                  ? 'border-brand-500 bg-brand-500/20 text-brand-400'
                  : 'border-surface-border text-surface-muted hover:border-surface-muted hover:text-white'
              }`}>
              {t === 'AUTOMATIC' ? 'Auto' : 'Manual'}
            </button>
          ))}
        </div>
      </section>

    </aside>
  )
}
