import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getVINReport } from '@/lib/api'
import type { VINEvent, VINReportV2 } from '@/lib/api'
import { formatMileage, formatPrice, COUNTRY_FLAG, COUNTRY_NAME } from '@/lib/format'

interface PageProps {
  params: Promise<{ vin: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { vin } = await params
  const v = vin.toUpperCase()
  return {
    title: `VIN ${v} — Free History Report`,
    description: `Free vehicle history for VIN ${v}: mileage timeline, NCAP safety, recalls, ownership, accidents.`,
    openGraph: { title: `VIN ${v} Free History — CARDEX` },
  }
}

// ── Constants ─────────────────────────────────────────────────────────────────

const EVENT_COLOR: Record<string, string> = {
  LISTING:      'border-blue-500/40 bg-blue-500/10 text-blue-400',
  ACCIDENT:     'border-red-500/40 bg-red-500/10 text-red-400',
  DAMAGE:       'border-red-500/40 bg-red-500/10 text-red-400',
  OWNERSHIP:    'border-yellow-500/40 bg-yellow-500/10 text-yellow-400',
  MOT:          'border-brand-500/40 bg-brand-500/10 text-brand-400',
  MILEAGE:      'border-surface-border bg-surface-hover text-surface-muted',
  PRICE_CHANGE: 'border-orange-500/40 bg-orange-500/10 text-orange-400',
  IMPORT:       'border-purple-500/40 bg-purple-500/10 text-purple-400',
  STOLEN_CHECK: 'border-brand-500/40 bg-brand-500/10 text-brand-400',
}

const EVENT_DOT: Record<string, string> = {
  LISTING:      'bg-blue-400',
  ACCIDENT:     'bg-red-400',
  DAMAGE:       'bg-red-400',
  OWNERSHIP:    'bg-yellow-400',
  MOT:          'bg-brand-400',
  MILEAGE:      'bg-surface-muted',
  PRICE_CHANGE: 'bg-orange-400',
  IMPORT:       'bg-purple-400',
  STOLEN_CHECK: 'bg-brand-400',
}

const SOURCE_LABEL: Record<string, string> = {
  nhtsa_vpic:       'NHTSA vPIC',
  nhtsa_vpic_cached:'NHTSA vPIC',
  nhtsa_recalls:    'NHTSA Recalls',
  euro_ncap:        'Euro NCAP',
  cardex_scraping:  'CARDEX Scraping Network',
  cardex_forensics: 'CARDEX Forensics',
  rdw_nl:           'RDW Netherlands',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function NCAPStars({ stars, max = 5 }: { stars: number; max?: number }) {
  return (
    <div className="flex gap-0.5" aria-label={`${stars} out of ${max} stars`}>
      {Array.from({ length: max }, (_, i) => (
        <svg
          key={i}
          viewBox="0 0 20 20"
          className={`h-5 w-5 ${i < stars ? 'text-yellow-400' : 'text-surface-border'}`}
          fill="currentColor"
          aria-hidden
        >
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      ))}
    </div>
  )
}

function NCAPBar({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-28 shrink-0 text-xs text-surface-muted">{label}</span>
      <div className="flex-1 rounded-full bg-surface-border h-1.5">
        <div
          className="h-full rounded-full bg-brand-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-xs text-white">{pct}%</span>
    </div>
  )
}

function MileageTimeline({ events }: { events: VINEvent[] }) {
  const pts = events
    .filter(e => e.mileage_km != null && e.mileage_km > 0)
    .sort((a, b) => a.event_date.localeCompare(b.event_date))

  if (pts.length === 0) {
    return <p className="text-sm text-surface-muted">No mileage data available.</p>
  }

  const maxKM = Math.max(...pts.map(p => p.mileage_km!))
  const svgH = 80
  const svgW = 400
  const pad = { l: 8, r: 8, t: 10, b: 10 }
  const innerW = svgW - pad.l - pad.r
  const innerH = svgH - pad.t - pad.b

  const coords = pts.map((p, i) => ({
    x: pad.l + (pts.length === 1 ? innerW / 2 : (i / (pts.length - 1)) * innerW),
    y: pad.t + innerH - ((p.mileage_km! / maxKM) * innerH * 0.85 + innerH * 0.05),
    km: p.mileage_km!,
    date: p.event_date,
  }))

  const linePath = coords
    .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
    .join(' ')

  // Fill area under curve
  const fillPath =
    `M ${coords[0].x.toFixed(1)} ${(svgH - pad.b).toFixed(1)} ` +
    coords.map(c => `L ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ') +
    ` L ${coords[coords.length - 1].x.toFixed(1)} ${(svgH - pad.b).toFixed(1)} Z`

  return (
    <div className="space-y-2">
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        className="w-full"
        style={{ height: svgH }}
        aria-hidden
      >
        <defs>
          <linearGradient id="milGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#15b570" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#15b570" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Fill */}
        <path d={fillPath} fill="url(#milGrad)" />
        {/* Line */}
        <path d={linePath} fill="none" stroke="#15b570" strokeWidth="1.5" strokeLinejoin="round" />
        {/* Dots */}
        {coords.map((c, i) => (
          <circle key={i} cx={c.x} cy={c.y} r="3" fill="#15b570" stroke="#0d1117" strokeWidth="1.5" />
        ))}
      </svg>
      {/* Labels */}
      <div className="space-y-1">
        {pts.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0 text-surface-muted font-mono">{p.event_date}</span>
            <span className="font-mono font-medium text-white">{formatMileage(p.mileage_km!)}</span>
            {p.source_platform && (
              <span className="text-surface-muted opacity-60">{p.source_platform}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function EventBadge({ type }: { type: string }) {
  const colorClass = EVENT_COLOR[type] ?? 'border-surface-border bg-surface-hover text-surface-muted'
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${colorClass}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${EVENT_DOT[type] ?? 'bg-surface-muted'}`} />
      {type.replace(/_/g, ' ')}
    </span>
  )
}

function StatCard({ label, value, accent = 'text-white' }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <p className="text-[11px] font-medium uppercase tracking-widest text-surface-muted">{label}</p>
      <p className={`mt-1.5 font-mono text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-surface-muted">
      {children}
    </h2>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default async function VINReportPage({ params }: PageProps) {
  const { vin: rawVin } = await params
  const vin = rawVin.toUpperCase()

  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) notFound()

  let report: VINReportV2 | null = null
  let fetchError: string | null = null

  try {
    report = await getVINReport(vin)
  } catch (err) {
    fetchError = err instanceof Error ? err.message : 'Unknown error'
  }

  const generatedAt = report?.report_generated_at
    ? new Date(report.report_generated_at).toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
      })
    : null

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">

      {/* ── Report header ───────────────────────────────────────────────── */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded border border-brand-500/30 bg-brand-500/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-widest text-brand-400">
              Free Report
            </span>
            <span className="text-[11px] uppercase tracking-widest text-surface-muted">CARDEX VIN History</span>
          </div>
          <h1 className="font-mono text-3xl font-bold tracking-tight text-white">{vin}</h1>
          {report?.spec && (
            <p className="mt-1 text-sm text-surface-muted">
              {report.spec.make} {report.spec.model}
              {report.spec.year > 0 && ` · ${report.spec.year}`}
              {report.spec.body_type && ` · ${report.spec.body_type}`}
              {report.spec.fuel_type && ` · ${report.spec.fuel_type}`}
            </p>
          )}
          {report?.spec?.country_of_manufacture && (
            <p className="mt-0.5 text-xs text-surface-muted">
              Country of manufacture:{' '}
              <span className="text-white">
                {COUNTRY_FLAG[report.spec.country_of_manufacture] ?? ''}{' '}
                {COUNTRY_NAME[report.spec.country_of_manufacture] ?? report.spec.country_of_manufacture}
              </span>
            </p>
          )}
          {generatedAt && (
            <p className="mt-0.5 text-xs text-surface-muted">Report generated: {generatedAt}</p>
          )}
        </div>
        <a
          href="/vin"
          className="shrink-0 rounded-lg border border-surface-border px-3 py-2 text-xs text-surface-muted transition-colors hover:border-brand-500/40 hover:text-white"
        >
          New search
        </a>
      </div>

      {/* ── Error / empty state ──────────────────────────────────────────── */}
      {(fetchError || !report) && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-10 text-center">
          <p className="mb-2 text-lg font-semibold text-white">No data found</p>
          <p className="text-sm text-surface-muted">
            {fetchError
              ? `Could not load report: ${fetchError}`
              : 'This VIN has not been observed in our covered markets (DE, ES, FR, NL, BE, CH) yet.'}
          </p>
          <a
            href="/vin"
            className="mt-6 inline-block rounded-lg bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-400 transition-colors"
          >
            Try another VIN
          </a>
        </div>
      )}

      {report && (
        <>
          {/* ── Quick stats ───────────────────────────────────────────────── */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Times listed"
              value={String(report.summary.times_listed)}
            />
            <StatCard
              label="Owners"
              value={String(report.summary.ownership_changes)}
            />
            <StatCard
              label="Accidents"
              value={String(report.summary.accident_records)}
              accent={report.summary.accident_records > 0 ? 'text-red-400' : 'text-brand-400'}
            />
            <StatCard
              label="Recalls"
              value={String(report.safety.recall_count)}
              accent={report.safety.recall_count > 0 ? 'text-amber-400' : 'text-brand-400'}
            />
          </div>

          {/* ── Two-column: Safety + Mileage ──────────────────────────────── */}
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">

            {/* NCAP Safety */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <SectionHeader>
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 text-brand-400" aria-hidden>
                  <path fillRule="evenodd" d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0110 1.944z" clipRule="evenodd" />
                </svg>
                Euro NCAP Safety
              </SectionHeader>

              {report.safety.ncap_stars > 0 ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <NCAPStars stars={report.safety.ncap_stars} />
                    <span className="text-sm font-semibold text-white">{report.safety.ncap_stars} / 5 stars</span>
                    {report.safety.ncap_test_year > 0 && (
                      <span className="text-xs text-surface-muted">tested {report.safety.ncap_test_year}</span>
                    )}
                  </div>
                  <div className="space-y-2">
                    {report.safety.ncap_adult_pct > 0 && (
                      <NCAPBar label="Adult occupant" pct={report.safety.ncap_adult_pct} />
                    )}
                    {report.safety.ncap_child_pct > 0 && (
                      <NCAPBar label="Child occupant" pct={report.safety.ncap_child_pct} />
                    )}
                    {report.safety.ncap_pedestrian_pct > 0 && (
                      <NCAPBar label="Pedestrian" pct={report.safety.ncap_pedestrian_pct} />
                    )}
                    {report.safety.ncap_safety_assist_pct > 0 && (
                      <NCAPBar label="Safety assist" pct={report.safety.ncap_safety_assist_pct} />
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-surface-muted">
                  Euro NCAP data not available for this vehicle. Check{' '}
                  <a
                    href="https://www.euroncap.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-400 hover:underline"
                  >
                    euroncap.com
                  </a>
                  .
                </p>
              )}
            </div>

            {/* Mileage timeline */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <SectionHeader>
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 text-brand-400" aria-hidden>
                  <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
                </svg>
                Mileage Timeline
              </SectionHeader>

              <MileageTimeline events={report.history.events} />

              {/* Rollback / OK indicator */}
              <div className={`mt-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${
                report.history.mileage_ok
                  ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20'
                  : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}>
                {report.history.mileage_ok ? (
                  <>
                    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0" aria-hidden>
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    No odometer rollback detected
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 shrink-0" aria-hidden>
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    Rollback detected — {report.history.mileage_warning}
                  </>
                )}
              </div>

              {report.history.forensic_max_km > 0 && (
                <p className="mt-2 text-xs text-surface-muted">
                  Forensic max:{' '}
                  <span className="font-mono text-white">{formatMileage(report.history.forensic_max_km)}</span>
                  {report.history.forensic_sources.length > 0 && (
                    <> ({report.history.forensic_sources.join(', ')})</>
                  )}
                </p>
              )}
            </div>
          </div>

          {/* ── Recall alerts ─────────────────────────────────────────────── */}
          {report.safety.recall_count > 0 && (
            <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
              <SectionHeader>
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 text-amber-400" aria-hidden>
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <span className="text-amber-400">Recall Alerts ({report.safety.recall_count})</span>
              </SectionHeader>

              <div className="space-y-3">
                {report.safety.recalls.map((recall, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-amber-500/20 bg-surface-card p-4"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-amber-400">
                        {recall.campaign || 'RECALL'}
                      </span>
                      <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-300">
                        {recall.component}
                      </span>
                      {recall.date && (
                        <span className="text-xs text-surface-muted">{recall.date}</span>
                      )}
                    </div>
                    {recall.summary && (
                      <p className="text-xs text-surface-muted leading-relaxed">{recall.summary}</p>
                    )}
                    {recall.remedy && (
                      <p className="mt-1.5 text-xs text-white/80">
                        <span className="font-medium text-brand-400">Remedy: </span>
                        {recall.remedy}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Vehicle spec ──────────────────────────────────────────────── */}
          {report.spec && (report.spec.make || report.spec.model) && (
            <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5">
              <SectionHeader>
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 text-brand-400" aria-hidden>
                  <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                  <path fillRule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clipRule="evenodd" />
                </svg>
                Vehicle Specification
              </SectionHeader>

              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                {[
                  { label: 'Make', value: report.spec.make },
                  { label: 'Model', value: report.spec.model },
                  { label: 'Year', value: report.spec.year > 0 ? String(report.spec.year) : null },
                  { label: 'Body type', value: report.spec.body_type },
                  { label: 'Fuel type', value: report.spec.fuel_type },
                  { label: 'Transmission', value: report.spec.transmission },
                  {
                    label: 'Displacement',
                    value: report.spec.engine_displacement_l > 0
                      ? `${report.spec.engine_displacement_l.toFixed(1)} L`
                      : null,
                  },
                  {
                    label: 'Power',
                    value: report.spec.engine_kw > 0
                      ? `${Math.round(report.spec.engine_kw)} kW (${Math.round(report.spec.engine_kw * 1.36)} hp)`
                      : null,
                  },
                  {
                    label: 'Cylinders',
                    value: report.spec.engine_cylinders > 0 ? String(report.spec.engine_cylinders) : null,
                  },
                  {
                    label: 'Manufactured',
                    value: report.spec.country_of_manufacture
                      ? `${COUNTRY_FLAG[report.spec.country_of_manufacture] ?? ''} ${COUNTRY_NAME[report.spec.country_of_manufacture] ?? report.spec.country_of_manufacture}`
                      : null,
                  },
                ]
                  .filter(row => row.value)
                  .map(row => (
                    <div key={row.label}>
                      <span className="text-surface-muted">{row.label}</span>
                      <span className="ml-2 font-medium text-white">{row.value}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* ── Event timeline ────────────────────────────────────────────── */}
          <div className="mb-6">
            <SectionHeader>
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5 text-brand-400" aria-hidden>
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
              </svg>
              Event Timeline ({report.history.event_count})
            </SectionHeader>

            {report.history.events.length === 0 ? (
              <div className="rounded-xl border border-surface-border bg-surface-card p-8 text-center text-surface-muted text-sm">
                No events recorded for this VIN in our database.
              </div>
            ) : (
              <div className="relative flex flex-col gap-0">
                {/* Vertical connector line */}
                <div className="absolute left-[17px] top-5 bottom-5 w-px bg-surface-border" aria-hidden />

                {report.history.events.map((e, i) => (
                  <div key={i} className="relative flex items-start gap-4 pb-4">
                    {/* Dot */}
                    <div
                      className={`relative z-10 mt-1 h-[18px] w-[18px] shrink-0 rounded-full border-2 border-surface-card ${
                        EVENT_DOT[e.event_type] ?? 'bg-surface-muted'
                      }`}
                      aria-hidden
                    />

                    {/* Card */}
                    <div className="flex-1 min-w-0 rounded-xl border border-surface-border bg-surface-card p-3.5">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <EventBadge type={e.event_type} />
                        <span className="font-mono text-xs text-surface-muted">{e.event_date}</span>
                        {e.country && (
                          <span className="text-xs text-surface-muted">
                            {COUNTRY_FLAG[e.country] ?? ''} {e.country}
                          </span>
                        )}
                        {e.source_platform && (
                          <span className="text-xs text-surface-muted/60">{e.source_platform}</span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-4">
                        {e.mileage_km != null && (
                          <span className="font-mono text-sm font-medium text-white">
                            {formatMileage(e.mileage_km)}
                          </span>
                        )}
                        {e.price_eur != null && (
                          <span className="font-mono text-sm font-medium text-white">
                            {formatPrice(e.price_eur)}
                          </span>
                        )}
                        {e.description && (
                          <span className="text-xs text-surface-muted leading-relaxed">
                            {e.description}
                          </span>
                        )}
                      </div>

                      {/* Confidence bar */}
                      <div className="mt-2">
                        <div className="h-px w-full rounded bg-surface-border">
                          <div
                            className="h-full rounded bg-brand-500/60"
                            style={{ width: `${Math.round(e.confidence * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Additional stats ──────────────────────────────────────────── */}
          {(report.history.first_seen || report.history.last_seen) && (
            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {report.history.first_seen && (
                <StatCard label="First seen" value={report.history.first_seen} />
              )}
              {report.history.last_seen && (
                <StatCard label="Last seen" value={report.history.last_seen} />
              )}
              {report.summary.min_mileage_km != null && (
                <StatCard label="Min mileage" value={formatMileage(report.summary.min_mileage_km)} />
              )}
              {report.summary.max_mileage_km != null && (
                <StatCard label="Max mileage" value={formatMileage(report.summary.max_mileage_km)} />
              )}
            </div>
          )}

          {/* ── Countries seen ────────────────────────────────────────────── */}
          {report.summary.countries_seen_in.length > 0 && (
            <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5">
              <SectionHeader>Countries observed in</SectionHeader>
              <div className="flex flex-wrap gap-2">
                {report.summary.countries_seen_in.map(c => (
                  <span
                    key={c}
                    className="flex items-center gap-1.5 rounded-lg border border-surface-border bg-surface-hover px-3 py-1.5 text-sm"
                  >
                    <span>{COUNTRY_FLAG[c] ?? '🌍'}</span>
                    <span className="font-medium text-white">{COUNTRY_NAME[c] ?? c}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── Price history ─────────────────────────────────────────────── */}
          {report.summary.price_history_eur.length > 0 && (
            <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5">
              <SectionHeader>Price History</SectionHeader>
              <div className="flex flex-wrap gap-2">
                {report.summary.price_history_eur.map((p, i) => (
                  <span
                    key={i}
                    className="rounded-lg border border-surface-border bg-surface-hover px-3 py-1.5 font-mono text-sm font-medium text-white"
                  >
                    {formatPrice(p)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* ── Data sources ──────────────────────────────────────────────── */}
          <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-5">
            <SectionHeader>Data Sources</SectionHeader>
            <div className="flex flex-wrap gap-2">
              {report.data_sources.map(s => (
                <span
                  key={s}
                  className="rounded-md border border-surface-border bg-surface-hover px-2.5 py-1 text-xs text-surface-muted"
                >
                  {SOURCE_LABEL[s] ?? s}
                </span>
              ))}
            </div>
          </div>

          {/* ── Disclaimer ────────────────────────────────────────────────── */}
          <p className="text-xs leading-relaxed text-surface-muted/60">{report.disclaimer}</p>
        </>
      )}
    </div>
  )
}
