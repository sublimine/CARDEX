import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getVINReport } from '@/lib/api'
import { formatMileage, formatPrice, COUNTRY_FLAG } from '@/lib/format'
import {
  CheckCircle, XCircle, AlertTriangle, MapPin,
  Gauge, DollarSign, RefreshCw, FileWarning, Shield
} from 'lucide-react'

interface PageProps {
  params: { vin: string }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  return {
    title: `VIN ${params.vin.toUpperCase()} — Free History Report`,
    description: `Free vehicle history for VIN ${params.vin}: mileage timeline, ownership, accidents, price history.`,
  }
}

const EVENT_ICON: Record<string, React.ReactNode> = {
  MILEAGE:       <Gauge size={14} />,
  ACCIDENT:      <AlertTriangle size={14} className="text-red-400" />,
  OWNERSHIP:     <RefreshCw size={14} className="text-blue-400" />,
  IMPORT:        <MapPin size={14} className="text-yellow-400" />,
  STOLEN_CHECK:  <Shield size={14} className="text-brand-400" />,
  LISTING:       <FileWarning size={14} className="text-surface-muted" />,
  PRICE_CHANGE:  <DollarSign size={14} className="text-orange-400" />,
  MOT:           <CheckCircle size={14} className="text-green-400" />,
  DAMAGE:        <XCircle size={14} className="text-red-400" />,
}

export default async function VINPage({ params }: PageProps) {
  const vin = params.vin.toUpperCase()
  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) notFound()

  const report = await getVINReport(vin).catch(() => null)

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Header */}
      <div className="mb-8">
        <div className="mb-1 text-xs font-medium uppercase tracking-widest text-surface-muted">Free Vehicle History</div>
        <h1 className="font-mono text-3xl font-bold tracking-tight text-white">{vin}</h1>
      </div>

      {!report ? (
        <div className="rounded-xl border border-surface-border bg-surface-card p-8 text-center text-surface-muted">
          No history found for this VIN. This vehicle may not have been listed in our covered markets (DE, ES, FR, NL, BE, CH) yet.
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Times listed" value={String(report.summary.times_listed)} />
            <StatCard label="Ownership changes" value={String(report.summary.ownership_changes)} />
            <StatCard label="Accident records" value={String(report.summary.accident_records)}
              accent={report.summary.accident_records > 0 ? 'text-red-400' : 'text-brand-400'} />
            <StatCard label="Countries seen"
              value={report.summary.countries_seen_in.map(c => COUNTRY_FLAG[c] ?? c).join(' ') || '—'} />
          </div>

          {/* Mileage range */}
          {report.summary.min_mileage_km != null && (
            <div className="mb-6 rounded-xl border border-surface-border bg-surface-card p-4">
              <div className="mb-1 text-xs font-medium uppercase tracking-widest text-surface-muted">Mileage range</div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-lg font-bold text-white">
                  {formatMileage(report.summary.min_mileage_km)}
                </span>
                <span className="text-surface-muted">→</span>
                <span className="font-mono text-lg font-bold text-white">
                  {report.summary.max_mileage_km != null ? formatMileage(report.summary.max_mileage_km) : '?'}
                </span>
                {!report.mileage_ok && (
                  <span className="ml-2 flex items-center gap-1 rounded-md bg-red-500/20 px-2 py-0.5 text-xs font-medium text-red-400">
                    <AlertTriangle size={12} /> Rollback detected
                  </span>
                )}
              </div>
              {report.mileage_warning && (
                <p className="mt-2 text-xs text-red-400">{report.mileage_warning}</p>
              )}
            </div>
          )}

          {/* Stolen status */}
          <div className="mb-6 flex items-center gap-3 rounded-xl border border-surface-border bg-surface-card p-4">
            {report.stolen_status === 'CLEAR' ? (
              <CheckCircle size={20} className="text-brand-400 shrink-0" />
            ) : report.stolen_status === 'STOLEN' ? (
              <XCircle size={20} className="text-red-400 shrink-0" />
            ) : (
              <Shield size={20} className="text-surface-muted shrink-0" />
            )}
            <div>
              <p className="text-sm font-medium text-white">
                Stolen check: <span className={report.stolen_status === 'STOLEN' ? 'text-red-400' : 'text-brand-400'}>
                  {report.stolen_status}
                </span>
              </p>
              <p className="text-xs text-surface-muted">Source: accumulated scraping records</p>
            </div>
          </div>

          {/* Timeline */}
          <div>
            <h2 className="mb-4 text-base font-semibold text-white">Event Timeline</h2>
            {report.events.length === 0 ? (
              <p className="text-sm text-surface-muted">No events recorded.</p>
            ) : (
              <div className="relative flex flex-col gap-0">
                {/* Vertical line */}
                <div className="absolute left-[18px] top-0 h-full w-px bg-surface-border" />
                {report.events.map((e, i) => (
                  <div key={i} className="relative flex items-start gap-4 pb-5">
                    {/* Icon bubble */}
                    <div className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-card text-white">
                      {EVENT_ICON[e.event_type] ?? <span className="text-xs">?</span>}
                    </div>
                    {/* Content */}
                    <div className="flex-1 rounded-lg border border-surface-border bg-surface-card p-3">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="text-xs font-semibold uppercase tracking-wide text-brand-400">
                          {e.event_type.replace(/_/g, ' ')}
                        </span>
                        <span className="text-xs text-surface-muted">{e.event_date}</span>
                        {e.country && (
                          <span className="text-xs text-surface-muted">
                            {COUNTRY_FLAG[e.country] ?? ''} {e.country}
                          </span>
                        )}
                        {e.source_platform && (
                          <span className="text-xs text-surface-muted opacity-60">{e.source_platform}</span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-4 text-sm">
                        {e.mileage_km != null && (
                          <span className="font-mono text-white">{formatMileage(e.mileage_km)}</span>
                        )}
                        {e.price_eur != null && (
                          <span className="font-mono text-white">{formatPrice(e.price_eur)}</span>
                        )}
                        {e.description && (
                          <span className="text-surface-muted">{e.description}</span>
                        )}
                      </div>
                      {/* Confidence */}
                      <div className="mt-1.5">
                        <div className="h-0.5 w-full rounded bg-surface-border">
                          <div
                            className="h-full rounded bg-brand-500"
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

          {/* Disclaimer */}
          <p className="mt-6 text-xs text-surface-muted/60">{report.disclaimer}</p>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, accent = 'text-brand-400' }: {
  label: string; value: string; accent?: string
}) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <p className="text-xs text-surface-muted">{label}</p>
      <p className={`mt-1 font-mono text-xl font-bold ${accent}`}>{value || '0'}</p>
    </div>
  )
}
