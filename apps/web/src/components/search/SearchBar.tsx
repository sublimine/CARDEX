'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useState, useTransition } from 'react'
import { Search } from 'lucide-react'
import { clsx } from 'clsx'

export function SearchBar({ defaultValue = '' }: { defaultValue?: string }) {
  const router = useRouter()
  const sp = useSearchParams()
  const [q, setQ] = useState(defaultValue)
  const [isPending, startTransition] = useTransition()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const params = new URLSearchParams(sp.toString())
    if (q.trim()) {
      params.set('q', q.trim())
    } else {
      params.delete('q')
    }
    params.set('page', '1')
    startTransition(() => router.push(`/search?${params.toString()}`))
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full items-center gap-2">
      <div className="relative flex-1">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-muted"
        />
        <input
          type="text"
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder="Make, model, keyword…"
          className="w-full rounded-lg border border-surface-border bg-surface-card py-2.5 pl-9 pr-4 text-sm text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
        />
      </div>
      <button
        type="submit"
        disabled={isPending}
        className={clsx(
          'rounded-lg bg-brand-500 px-5 py-2.5 text-sm font-medium text-white transition-colors',
          isPending ? 'opacity-60 cursor-not-allowed' : 'hover:bg-brand-600'
        )}
      >
        {isPending ? 'Searching…' : 'Search'}
      </button>
    </form>
  )
}
