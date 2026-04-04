'use client'

const options = [
  { value: '', label: 'Relevance' },
  { value: 'price_eur:asc', label: 'Price: Low → High' },
  { value: 'price_eur:desc', label: 'Price: High → Low' },
  { value: 'mileage_km:asc', label: 'Mileage: Lowest' },
  { value: 'year:desc', label: 'Year: Newest' },
]

export function SortSelect({ current }: { current?: string }) {
  return (
    <form>
      <select
        name="sort"
        defaultValue={current ?? ''}
        onChange={e => {
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
