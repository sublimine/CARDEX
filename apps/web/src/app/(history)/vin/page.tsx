'use client'

import type { Metadata } from 'next'
import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { COUNTRY_FLAG } from '@/lib/format'

// Note: metadata export is not supported in Client Components.
// Use a separate layout.tsx or move to a server wrapper if SEO metadata is needed.

const EXAMPLE_VINS = [
  { vin: 'WBA3A5G59FNR85969', label: 'BMW 3 Series (DE)' },
  { vin: 'VF1R9800XHW123456', label: 'Renault Clio (FR)' },
  { vin: 'WAUZZZ8K9BA012345', label: 'Audi A4 (DE)' },
  { vin: 'VS6AA05J574123456', label: 'Seat Ibiza (ES)' },
  { vin: 'WVWZZZ1JZ3W123456', label: 'VW Golf (DE)' },
]

const FEATURES = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    title: 'Euro NCAP Safety',
    desc: 'Star rating, adult/child occupant protection, pedestrian safety and driver assistance scores.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: 'NHTSA Recall Alerts',
    desc: 'Active safety recall campaigns from the US National Highway Traffic Safety Administration database.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: 'Mileage Timeline',
    desc: 'Odometer progression across every observed listing. Rollback detection using forensic multi-source analysis.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    title: 'Ownership History',
    desc: 'Number of ownership changes derived from registration records and cross-border transfer detections.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    title: 'Accident Records',
    desc: 'Accident and structural damage events sourced from public records and scraping networks.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="h-6 w-6 text-brand-400" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064" />
      </svg>
    ),
    title: 'Import & Cross-border',
    desc: 'Cross-border transfers detected via simultaneous presence in multiple national markets.',
  },
]

const SUPPORTED_COUNTRIES = ['DE', 'ES', 'FR', 'NL', 'BE', 'CH'] as const

export default function VINLandingPage() {
  const router = useRouter()
  const inputRef = useRef<HTMLInputElement>(null)
  const [inputValue, setInputValue] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const vin = inputValue.trim().toUpperCase()
    if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) {
      setError('Please enter a valid 17-character VIN (letters and digits, no I, O or Q).')
      return
    }
    setError('')
    setLoading(true)
    router.push(`/vin/${vin}`)
  }

  function fillExample(vin: string) {
    setInputValue(vin)
    setError('')
    inputRef.current?.focus()
  }

  return (
    <div className="mx-auto max-w-3xl px-4 pb-24 pt-16">

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="mb-10 text-center">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-brand-400">
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3" aria-hidden>
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          100% Free — No signup
        </div>

        <h1 className="mb-3 text-4xl font-bold tracking-tight text-white sm:text-5xl">
          Free VIN History Report
        </h1>
        <p className="mx-auto max-w-xl text-base text-surface-muted">
          Better than Carfax. Covers {SUPPORTED_COUNTRIES.map(c => COUNTRY_FLAG[c]).join(' ')}.
          NCAP safety ratings, recall alerts, mileage forensics — instantly.
        </p>
      </div>

      {/* ── Search form ──────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="mb-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            ref={inputRef}
            name="vin"
            type="text"
            value={inputValue}
            onChange={e => {
              setInputValue(e.target.value.toUpperCase())
              setError('')
            }}
            maxLength={17}
            placeholder="Enter 17-character VIN…"
            spellCheck={false}
            autoComplete="off"
            autoCapitalize="characters"
            className="flex-1 rounded-xl border border-surface-border bg-surface-card px-4 py-3.5 font-mono text-base text-white placeholder:font-sans placeholder:text-surface-muted focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500/40 transition-colors"
            aria-label="Vehicle Identification Number"
            aria-describedby={error ? 'vin-error' : undefined}
          />
          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-7 py-3.5 font-semibold text-white transition-colors hover:bg-brand-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Loading…
              </>
            ) : (
              'Get Free Report'
            )}
          </button>
        </div>

        {error && (
          <p id="vin-error" className="mt-2 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </form>

      {/* ── Character counter ─────────────────────────────────────────────── */}
      <div className="mb-2 flex items-center justify-between text-xs text-surface-muted">
        <span>
          {inputValue.length > 0 && (
            <>
              <span className={inputValue.length === 17 ? 'text-brand-400 font-medium' : ''}>
                {inputValue.length}
              </span>
              {' / 17 characters'}
            </>
          )}
        </span>
        <span>Supported: A–H, J–N, P–R, S–Z, 0–9</span>
      </div>

      {/* ── Example VINs ──────────────────────────────────────────────────── */}
      <div className="mb-10 flex flex-wrap gap-2">
        <span className="self-center text-xs text-surface-muted">Try:</span>
        {EXAMPLE_VINS.map(ex => (
          <button
            key={ex.vin}
            type="button"
            onClick={() => fillExample(ex.vin)}
            className="rounded-md border border-surface-border bg-surface-card px-2.5 py-1 font-mono text-xs text-surface-muted transition-colors hover:border-brand-500/40 hover:text-brand-400"
          >
            {ex.label}
          </button>
        ))}
      </div>

      {/* ── Supported countries ──────────────────────────────────────────── */}
      <div className="mb-10 flex flex-wrap items-center justify-center gap-3">
        {SUPPORTED_COUNTRIES.map(c => (
          <div
            key={c}
            className="flex items-center gap-2 rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm"
          >
            <span className="text-base">{COUNTRY_FLAG[c]}</span>
            <span className="text-surface-muted">{c}</span>
          </div>
        ))}
      </div>

      {/* ── Divider ──────────────────────────────────────────────────────── */}
      <div className="mb-10 flex items-center gap-4">
        <div className="flex-1 h-px bg-surface-border" />
        <span className="text-xs text-surface-muted">What&rsquo;s included</span>
        <div className="flex-1 h-px bg-surface-border" />
      </div>

      {/* ── Feature grid ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(f => (
          <div
            key={f.title}
            className="rounded-xl border border-surface-border bg-surface-card p-4 transition-colors hover:border-brand-500/30"
          >
            <div className="mb-3">{f.icon}</div>
            <h3 className="mb-1 text-sm font-semibold text-white">{f.title}</h3>
            <p className="text-xs leading-relaxed text-surface-muted">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* ── Bottom disclaimer ─────────────────────────────────────────────── */}
      <p className="mt-10 text-center text-xs leading-relaxed text-surface-muted/60">
        Data sourced from NHTSA vPIC, NHTSA Recalls, Euro NCAP, RDW Netherlands, and CARDEX scraping network.
        Not a substitute for a mechanical inspection or professional HPI check.
      </p>
    </div>
  )
}
