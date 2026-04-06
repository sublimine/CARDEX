import Link from 'next/link'
import { MapPin, Gauge, Fuel, Zap } from 'lucide-react'
import type { SearchHit } from '@/lib/api'
import { formatPrice, formatMileage, COUNTRY_FLAG, FUEL_LABEL } from '@/lib/format'
import { VehicleImage } from '@/components/ui/VehicleImage'
import { clsx } from 'clsx'

interface Props {
  hit: SearchHit
  sdiLabel?: string
}

const SDI_BADGE: Record<string, { label: string; cls: string }> = {
  PANIC_SELLER:     { label: '🔥 Panic Seller', cls: 'bg-brand-500/20 text-brand-400 border-brand-500/30' },
  MOTIVATED_SELLER: { label: '📉 Motivated', cls: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  NEGOTIABLE:       { label: '💬 Negotiable', cls: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
}

export function ListingCard({ hit, sdiLabel }: Props) {
  const flag = COUNTRY_FLAG[hit.source_country] ?? ''
  const fuel = FUEL_LABEL[hit.fuel_type ?? ''] ?? hit.fuel_type
  const sdi = sdiLabel ? SDI_BADGE[sdiLabel] : undefined
  const isElectric = hit.fuel_type === 'ELECTRIC'

  return (
    <article className="group relative flex flex-col overflow-hidden rounded-xl border border-surface-border bg-surface-card transition-all hover:border-brand-500/50 hover:shadow-lg hover:shadow-brand-500/5">
      {/* Thumbnail */}
      <div className="relative aspect-[16/9] w-full overflow-hidden bg-surface-hover">
        <VehicleImage
          vehicleUlid={hit.vehicle_ulid}
          thumbAvailable={!!hit.thumbnail_url}
          thumbUrl={hit.thumbnail_url}
          alt={`${hit.make} ${hit.model}`}
          sourceUrl={hit.source_url}
          sourcePlatform={hit.source_platform}
          make={hit.make}
          model={hit.model}
          className="h-full w-full transition-transform duration-300 group-hover:scale-105"
        />
        {/* Country badge */}
        <span className="absolute right-2 top-2 rounded-md bg-black/60 px-2 py-0.5 text-xs backdrop-blur-sm">
          {flag} {hit.source_country}
        </span>
        {/* SDI badge */}
        {sdi && (
          <span className={clsx('absolute left-2 top-2 rounded-md border px-2 py-0.5 text-xs font-medium', sdi.cls)}>
            {sdi.label}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 p-4">
        {/* Title + price */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold leading-tight text-white">
              {hit.make} {hit.model}
            </h3>
            {hit.variant && (
              <p className="mt-0.5 text-xs text-surface-muted line-clamp-1">{hit.variant}</p>
            )}
          </div>
          <p className="shrink-0 font-mono text-lg font-bold text-brand-400">
            {hit.price_eur ? formatPrice(hit.price_eur) : '—'}
          </p>
        </div>

        {/* Specs row */}
        <div className="flex flex-wrap gap-x-3 gap-y-1.5 text-xs text-surface-muted">
          <span className="flex items-center gap-1">
            <span className="font-medium text-white">{hit.year}</span>
          </span>
          {hit.mileage_km != null && (
            <span className="flex items-center gap-1">
              <Gauge size={12} />
              {formatMileage(hit.mileage_km)}
            </span>
          )}
          {fuel && (
            <span className="flex items-center gap-1">
              {isElectric ? <Zap size={12} className="text-brand-400" /> : <Fuel size={12} />}
              {fuel}
            </span>
          )}
          {hit.transmission && (
            <span>{hit.transmission === 'AUTOMATIC' ? 'Auto' : 'Manual'}</span>
          )}
        </div>

        {/* Footer */}
        <div className="mt-auto flex items-center justify-between gap-2 pt-2 border-t border-surface-border">
          <Link
            href={`/listing/${hit.vehicle_ulid}`}
            className="text-xs text-surface-muted hover:text-white transition-colors"
          >
            Details →
          </Link>
          {/* External redirect — AutoUncle model */}
          <a
            href={hit.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600 transition-colors"
          >
            View listing ↗
          </a>
        </div>
      </div>
    </article>
  )
}
