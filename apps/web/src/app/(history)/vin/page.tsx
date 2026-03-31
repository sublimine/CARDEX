import type { Metadata } from 'next'
import { redirect } from 'next/navigation'

export const metadata: Metadata = {
  title: 'Free VIN History Check — CARDEX',
  description: 'Get a free vehicle history report. Mileage timeline, accident records, ownership history, price history. No signup required.',
}

export default function VINLandingPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-20 text-center">
      <h1 className="mb-3 text-4xl font-bold text-white">
        Free VIN History
      </h1>
      <p className="mb-8 text-surface-muted">
        Mileage timeline · Accident records · Ownership history · Price history<br />
        No signup. No credit card. Completely free.
      </p>

      <form action="" onSubmit={(e) => {
        e.preventDefault()
        const vin = (e.currentTarget.elements.namedItem('vin') as HTMLInputElement).value.trim().toUpperCase()
        if (vin.length === 17) window.location.href = `/vin/${vin}`
      }}>
        <div className="flex gap-2">
          <input
            name="vin"
            type="text"
            maxLength={17}
            minLength={17}
            placeholder="Enter 17-character VIN…"
            className="flex-1 rounded-xl border border-surface-border bg-surface-card px-4 py-3 font-mono text-white placeholder:font-sans placeholder:text-surface-muted focus:border-brand-500 focus:outline-none uppercase"
            style={{ textTransform: 'uppercase' }}
          />
          <button
            type="submit"
            className="rounded-xl bg-brand-500 px-6 py-3 font-medium text-white hover:bg-brand-600 transition-colors"
          >
            Check
          </button>
        </div>
        <p className="mt-3 text-xs text-surface-muted">
          Example: <code className="font-mono text-brand-400">WBA3A5C50DF357185</code>
        </p>
      </form>

      {/* What's included */}
      <div className="mt-16 grid grid-cols-2 gap-4 text-left sm:grid-cols-3">
        {[
          { icon: '📍', title: 'Mileage timeline', desc: 'Detect odometer rollbacks across all observed listings' },
          { icon: '🛡️', title: 'Stolen check', desc: 'Cross-referenced against public stolen vehicle databases' },
          { icon: '📋', title: 'Ownership history', desc: 'Number of ownership changes derived from registration data' },
          { icon: '💥', title: 'Accident records', desc: 'Accident and damage events from public sources' },
          { icon: '💸', title: 'Price history', desc: 'Every price this vehicle has been listed at' },
          { icon: '🌍', title: 'Import records', desc: 'Cross-border transfers detected via market presence' },
        ].map(f => (
          <div key={f.title} className="rounded-xl border border-surface-border bg-surface-card p-4">
            <div className="mb-2 text-2xl">{f.icon}</div>
            <h3 className="font-semibold text-white text-sm">{f.title}</h3>
            <p className="mt-1 text-xs text-surface-muted">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
