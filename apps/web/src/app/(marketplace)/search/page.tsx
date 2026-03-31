import type { Metadata } from 'next'
import { Suspense } from 'react'
import { searchListings } from '@/lib/api'
import { SearchBar } from '@/components/search/SearchBar'
import { ListingCard } from '@/components/search/ListingCard'
import { FilterSidebar } from '@/components/search/FilterSidebar'

export const metadata: Metadata = {
  title: 'Search Used Cars — All Europe',
  description: 'Search millions of used car listings from Germany, Spain, France, Netherlands, Belgium and Switzerland.',
}

interface PageProps {
  searchParams: {
    q?: string
    make?: string
    model?: string
    year_min?: string
    year_max?: string
    price_min?: string
    price_max?: string
    mileage_max?: string
    fuel?: string
    tx?: string
    country?: string
    sort?: string
    page?: string
  }
}

export default async function SearchPage({ searchParams: sp }: PageProps) {
  const page = parseInt(sp.page ?? '1', 10)

  const results = await searchListings({
    q: sp.q,
    make: sp.make,
    model: sp.model,
    year_min: sp.year_min ? Number(sp.year_min) : undefined,
    year_max: sp.year_max ? Number(sp.year_max) : undefined,
    price_min: sp.price_min ? Number(sp.price_min) : undefined,
    price_max: sp.price_max ? Number(sp.price_max) : undefined,
    mileage_max: sp.mileage_max ? Number(sp.mileage_max) : undefined,
    fuel: sp.fuel,
    tx: sp.tx,
    country: sp.country,
    sort: sp.sort,
    page,
    per_page: 24,
  }).catch(() => null)

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-6">
      {/* Search bar */}
      <div className="mb-6">
        <Suspense>
          <SearchBar defaultValue={sp.q ?? ''} />
        </Suspense>
      </div>

      <div className="flex gap-8">
        {/* Sidebar */}
        <div className="hidden w-56 shrink-0 lg:block">
          <Suspense>
            <FilterSidebar facets={results?.facet_distribution} />
          </Suspense>
        </div>

        {/* Results */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm text-surface-muted">
              {results
                ? <>{results.total_hits.toLocaleString()} listings &middot; {results.processing_time_ms}ms</>
                : 'Loading…'}
            </p>
            {/* Sort */}
            <Suspense>
              <SortSelect current={sp.sort} />
            </Suspense>
          </div>

          {/* Grid */}
          {results && results.hits.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {results.hits.map(hit => (
                <ListingCard key={hit.vehicle_ulid} hit={hit} />
              ))}
            </div>
          ) : (
            <div className="py-24 text-center text-surface-muted">
              {results ? 'No listings match your filters.' : 'Search error — please try again.'}
            </div>
          )}

          {/* Pagination */}
          {results && results.total_pages > 1 && (
            <Suspense>
              <Pagination page={page} totalPages={results.total_pages} sp={sp} />
            </Suspense>
          )}
        </div>
      </div>
    </div>
  )
}

function SortSelect({ current }: { current?: string }) {
  const options = [
    { value: '', label: 'Relevance' },
    { value: 'price_eur:asc', label: 'Price: Low → High' },
    { value: 'price_eur:desc', label: 'Price: High → Low' },
    { value: 'mileage_km:asc', label: 'Mileage: Lowest' },
    { value: 'year:desc', label: 'Year: Newest' },
  ]
  return (
    <form>
      <select
        name="sort"
        defaultValue={current ?? ''}
        onChange={e => {
          const form = e.target.form!
          // Submit form on change
          const params = new URLSearchParams(window.location.search)
          if (e.target.value) params.set('sort', e.target.value)
          else params.delete('sort')
          window.location.search = params.toString()
        }}
        className="rounded-md border border-surface-border bg-surface-card px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </form>
  )
}

function Pagination({ page, totalPages, sp }: { page: number; totalPages: number; sp: Record<string, string | undefined> }) {
  function href(p: number) {
    const params = new URLSearchParams(
      Object.entries(sp).filter(([, v]) => v !== undefined) as [string, string][]
    )
    params.set('page', String(p))
    return `/search?${params.toString()}`
  }
  return (
    <div className="mt-8 flex items-center justify-center gap-2">
      {page > 1 && (
        <a href={href(page - 1)} className="rounded-md border border-surface-border px-4 py-2 text-sm text-surface-muted hover:text-white transition-colors">
          ← Previous
        </a>
      )}
      <span className="text-sm text-surface-muted">Page {page} of {totalPages}</span>
      {page < totalPages && (
        <a href={href(page + 1)} className="rounded-md border border-surface-border px-4 py-2 text-sm text-surface-muted hover:text-white transition-colors">
          Next →
        </a>
      )}
    </div>
  )
}
