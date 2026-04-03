import type { Metadata } from 'next'
import Image from 'next/image'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { ArrowLeft, Gauge, Fuel, Zap, Calendar, Palette, Hash, MapPin, ExternalLink } from 'lucide-react'
import { getListing, getSDIScore } from '@/lib/api'
import { formatPrice, formatMileage, COUNTRY_FLAG, COUNTRY_NAME, FUEL_LABEL, SDI_COLOR } from '@/lib/format'

interface PageProps {
  params: { ulid: string }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const listing = await getListing(params.ulid).catch(() => null) as any
  if (!listing) return { title: 'Listing not found — CARDEX' }
  return {
    title: `${listing.make} ${listing.model} ${listing.year ?? ''} — CARDEX`,
    description: `${listing.make} ${listing.model}, ${listing.year}, ${listing.mileage_km != null ? formatMileage(listing.mileage_km) : ''}, ${listing.price_eur ? formatPrice(listing.price_eur) : 'Price on request'}`,
  }
}

export default async function ListingDetailPage({ params }: PageProps) {
  const [listing, sdi] = await Promise.all([
    getListing(params.ulid).catch(() => null),
    getSDIScore(params.ulid).catch(() => null),
  ]) as [any, any]

  if (!listing) notFound()

  const flag = COUNTRY_FLAG[listing.source_country] ?? ''
  const countryName = COUNTRY_NAME[listing.source_country] ?? listing.source_country
  const fuel = FUEL_LABEL[listing.fuel_type ?? ''] ?? listing.fuel_type
  const isElectric = listing.fuel_type === 'ELECTRIC'
  const photos: string[] = listing.photo_urls ?? (listing.thumbnail_url ? [listing.thumbnail_url] : [])

  const sdiLabel: string = sdi?.sdi_label ?? 'STABLE'
  const sdiColor = SDI_COLOR[sdiLabel] ?? 'text-surface-muted'

  const specs = [
    { label: 'Year', value: listing.year, icon: Calendar },
    { label: 'Mileage', value: listing.mileage_km != null ? formatMileage(listing.mileage_km) : null, icon: Gauge },
    { label: 'Fuel', value: fuel, icon: isElectric ? Zap : Fuel },
    { label: 'Transmission', value: listing.transmission, icon: null },
    { label: 'Body type', value: listing.body_type, icon: null },
    { label: 'Color', value: listing.color, icon: Palette },
    { label: 'Power', value: listing.power_kw ? `${listing.power_kw} kW` : null, icon: null },
    { label: 'CO₂', value: listing.co2_gkm ? `${listing.co2_gkm} g/km` : null, icon: null },
    { label: 'VIN', value: listing.vin, icon: Hash },
  ].filter(s => s.value)

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-6">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Link href="/search" className="flex items-center gap-1.5 text-sm text-surface-muted hover:text-white transition-colors">
          <ArrowLeft size={14} />
          Back to search
        </Link>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_380px]">
        {/* Left column: photos + specs */}
        <div className="space-y-6">
          {/* Main photo */}
          <div className="relative aspect-[16/9] w-full overflow-hidden rounded-2xl bg-surface-card">
            {photos.length > 0 ? (
              <Image
                src={photos[0]}
                alt={`${listing.make} ${listing.model}`}
                fill
                className="object-cover"
                priority
                sizes="(max-width: 1024px) 100vw, 60vw"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-6xl">🚗</div>
            )}
          </div>

          {/* Photo strip */}
          {photos.length > 1 && (
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {photos.slice(1, 13).map((url, i) => (
                <div key={i} className="relative aspect-[4/3] overflow-hidden rounded-lg bg-surface-card">
                  <Image src={url} alt="" fill className="object-cover" sizes="120px" />
                </div>
              ))}
            </div>
          )}

          {/* Specs table */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-6">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Specifications</h2>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
              {specs.map(({ label, value }) => (
                <div key={label}>
                  <dt className="text-xs text-surface-muted">{label}</dt>
                  <dd className="mt-0.5 font-medium text-white">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Seller info */}
          {listing.seller_name && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-surface-muted">Seller</h2>
              <p className="font-medium text-white">{listing.seller_name}</p>
              <p className="mt-1 text-sm text-surface-muted flex items-center gap-1">
                <MapPin size={12} />
                {listing.city && `${listing.city}, `}{flag} {countryName}
              </p>
              <p className="mt-1 text-xs text-surface-muted capitalize">
                {listing.seller_type?.toLowerCase()} seller
              </p>
            </div>
          )}
        </div>

        {/* Right column: price box + SDI + CTA */}
        <div className="space-y-4">
          {/* Price card */}
          <div className="rounded-2xl border border-surface-border bg-surface-card p-6">
            {/* Make / Model / Year */}
            <h1 className="text-2xl font-bold text-white leading-tight">
              {listing.make} {listing.model}
              {listing.variant && <span className="ml-2 text-base font-normal text-surface-muted">{listing.variant}</span>}
            </h1>
            <p className="mt-1 text-sm text-surface-muted">{listing.year} · {fuel} · {listing.transmission === 'AUTOMATIC' ? 'Automatic' : listing.transmission}</p>

            {/* Price */}
            <div className="my-5 border-t border-b border-surface-border py-5">
              {listing.price_eur ? (
                <p className="font-mono text-4xl font-bold text-brand-400">{formatPrice(listing.price_eur)}</p>
              ) : (
                <p className="text-xl text-surface-muted">Price on request</p>
              )}
              {listing.last_price_eur && listing.last_price_eur !== listing.price_eur && (
                <p className="mt-1 text-sm text-surface-muted line-through">{formatPrice(listing.last_price_eur)}</p>
              )}
              {(listing.price_drop_count ?? 0) > 0 && (
                <p className="mt-1 text-xs text-orange-400">{listing.price_drop_count} price drop{listing.price_drop_count > 1 ? 's' : ''}</p>
              )}
            </div>

            {/* SDI signal */}
            {sdi && sdiLabel !== 'STABLE' && (
              <div className="mb-4 rounded-lg border border-orange-500/20 bg-orange-500/5 px-4 py-3">
                <p className={`text-sm font-medium ${sdiColor}`}>
                  {sdiLabel === 'PANIC_SELLER' && '🔥 Panic seller signal'}
                  {sdiLabel === 'MOTIVATED_SELLER' && '📉 Motivated seller signal'}
                  {sdiLabel === 'NEGOTIABLE' && '💬 Negotiable signal'}
                </p>
                <ul className="mt-1.5 space-y-0.5">
                  {(sdi.sdi_flags ?? []).map((f: string) => (
                    <li key={f} className="text-xs text-surface-muted">· {f}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* CTA */}
            <a
              href={listing.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 px-6 py-3.5 font-semibold text-white hover:bg-brand-600 transition-colors"
            >
              View on {listing.source_platform?.split(':')[0]?.replace('_', ' ') ?? 'dealer site'}
              <ExternalLink size={14} />
            </a>

            <p className="mt-3 text-center text-xs text-surface-muted">
              CARDEX is a redirect aggregator. You purchase directly from the seller.
            </p>
          </div>

          {/* Market context card */}
          <div className="rounded-xl border border-surface-border bg-surface-card px-5 py-4">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-surface-muted">Market data</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-surface-muted">Platform</span>
                <span className="text-white">{flag} {listing.source_platform}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-muted">Listed since</span>
                <span className="text-white">{listing.first_seen_at ? new Date(listing.first_seen_at).toLocaleDateString('en-GB') : '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-surface-muted">Days on market</span>
                <span className="text-white">{sdi?.days_on_market ?? '—'}</span>
              </div>
              {listing.h3_res4 && (
                <div className="flex justify-between">
                  <span className="text-surface-muted">Region</span>
                  <span className="font-mono text-xs text-surface-muted">{listing.h3_res4}</span>
                </div>
              )}
            </div>
            <div className="mt-3 border-t border-surface-border pt-3">
              <Link
                href={`/analytics?make=${listing.make}&model=${listing.model}&country=${listing.source_country}`}
                className="text-xs text-brand-400 hover:underline"
              >
                See price history for {listing.make} {listing.model} →
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
