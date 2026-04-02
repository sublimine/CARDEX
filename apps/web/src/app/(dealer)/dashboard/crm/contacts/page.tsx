'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Contact {
  contact_ulid: string
  full_name: string
  email: string | null
  phone: string | null
  total_purchases: number
  lifetime_value_eur: number
  last_contact_at: string | null
}

interface ContactDetail {
  contact_ulid: string
  linked_deals: Array<{ deal_ulid: string; title: string; deal_value_eur: number; stage_name: string }>
  recent_communications: Array<{ comm_ulid: string; channel: string; subject: string; created_at: string }>
  vehicles_purchased: Array<{ crm_vehicle_ulid: string; make: string; model: string; year: number; sale_price_eur: number }>
}

interface ContactsResponse {
  contacts: Contact[]
  total: number
  page: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatEur(value: number): string {
  return '€\u00a0' + value.toLocaleString('en-IE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function lifetimeValueClass(value: number): string {
  if (value > 30_000) return 'text-green-400'
  if (value > 10_000) return 'text-brand-400'
  return 'text-white'
}

function relativeTime(iso: string | null): { label: string; isStale: boolean } {
  if (!iso) return { label: 'Never', isStale: true }
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  const isStale = days > 30
  if (days === 0) return { label: 'Today', isStale: false }
  if (days === 1) return { label: 'Yesterday', isStale: false }
  if (days < 7) return { label: `${days} days ago`, isStale: false }
  const weeks = Math.floor(days / 7)
  if (weeks < 8) return { label: `${weeks} week${weeks > 1 ? 's' : ''} ago`, isStale }
  const months = Math.floor(days / 30)
  return { label: `${months} month${months > 1 ? 's' : ''} ago`, isStale }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('cardex_token') ?? ''
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

const PAGE_SIZE = 25

// ---------------------------------------------------------------------------
// Add Contact Modal
// ---------------------------------------------------------------------------
interface AddContactModalProps {
  onClose: () => void
  onAdded: () => void
}

function AddContactModal({ onClose, onAdded }: AddContactModalProps) {
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    gdpr_consent: false,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set(field: string, value: string | boolean) {
    setForm(f => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.full_name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/contacts`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          full_name: form.full_name.trim(),
          email: form.email.trim() || null,
          phone: form.phone.trim() || null,
          gdpr_consent: form.gdpr_consent,
        }),
      })
      if (!res.ok) throw new Error(`Error ${res.status}`)
      onAdded()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add contact')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-surface-border bg-surface-card p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="mb-5 text-lg font-semibold text-white">Add Contact</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-surface-muted">Full Name *</label>
            <input
              type="text"
              value={form.full_name}
              onChange={e => set('full_name', e.target.value)}
              required
              autoFocus
              placeholder="e.g. Carlos Martínez"
              className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-surface-muted">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={e => set('email', e.target.value)}
              placeholder="contact@example.com"
              className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-surface-muted">Phone</label>
            <input
              type="tel"
              value={form.phone}
              onChange={e => set('phone', e.target.value)}
              placeholder="+34 612 345 678"
              className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={form.gdpr_consent}
              onChange={e => set('gdpr_consent', e.target.checked)}
              className="mt-0.5 h-4 w-4 cursor-pointer rounded border-surface-border accent-brand-500"
            />
            <span className="text-sm text-surface-muted">
              Customer has given GDPR consent for contact and data processing
            </span>
          </label>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-surface-border px-4 py-2 text-sm text-surface-muted hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !form.full_name.trim()}
              className="flex-1 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : 'Add Contact'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Expanded Row Detail
// ---------------------------------------------------------------------------
interface ExpandedRowProps {
  contactUlid: string
}

function ExpandedRow({ contactUlid }: ExpandedRowProps) {
  const [detail, setDetail] = useState<ContactDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const token = localStorage.getItem('cardex_token') ?? ''
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/contacts/${contactUlid}/detail`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        if (!res.ok) throw new Error(`Error ${res.status}`)
        const json: ContactDetail = await res.json()
        if (!cancelled) setDetail(json)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load detail')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [contactUlid])

  if (loading) {
    return (
      <tr>
        <td colSpan={8} className="px-4 py-4">
          <div className="animate-pulse h-20 rounded-lg bg-surface-hover" />
        </td>
      </tr>
    )
  }

  if (error || !detail) {
    return (
      <tr>
        <td colSpan={8} className="px-4 py-4">
          <p className="text-xs text-red-400">{error ?? 'No detail available'}</p>
        </td>
      </tr>
    )
  }

  return (
    <tr>
      <td colSpan={8} className="px-4 pb-4 pt-0">
        <div className="rounded-xl border border-surface-border bg-surface p-4">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Linked deals */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-surface-muted">Linked Deals</p>
              {detail.linked_deals.length === 0 ? (
                <p className="text-xs text-surface-muted">No active deals</p>
              ) : (
                <ul className="space-y-1.5">
                  {detail.linked_deals.map(d => (
                    <li key={d.deal_ulid} className="flex items-center justify-between text-xs">
                      <div>
                        <p className="text-white">{d.title}</p>
                        <p className="text-surface-muted">{d.stage_name}</p>
                      </div>
                      <span className="font-mono text-brand-400">{formatEur(d.deal_value_eur)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Recent communications */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-surface-muted">
                Last 3 Communications
              </p>
              {detail.recent_communications.length === 0 ? (
                <p className="text-xs text-surface-muted">No communications</p>
              ) : (
                <ul className="space-y-1.5">
                  {detail.recent_communications.slice(0, 3).map(c => (
                    <li key={c.comm_ulid} className="text-xs">
                      <span className="rounded bg-surface-hover px-1.5 py-0.5 text-surface-muted">{c.channel}</span>
                      <span className="ml-2 text-white">{c.subject || '(no subject)'}</span>
                      <span className="ml-2 text-surface-muted">{relativeTime(c.created_at).label}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Vehicles purchased */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-surface-muted">Vehicles Purchased</p>
              {detail.vehicles_purchased.length === 0 ? (
                <p className="text-xs text-surface-muted">No purchases</p>
              ) : (
                <ul className="space-y-1.5">
                  {detail.vehicles_purchased.map(v => (
                    <li key={v.crm_vehicle_ulid} className="flex items-center justify-between text-xs">
                      <span className="text-white">{v.year} {v.make} {v.model}</span>
                      <span className="font-mono text-surface-muted">{formatEur(v.sale_price_eur)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------
function TableSkeleton() {
  return (
    <div className="animate-pulse divide-y divide-surface-border">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <div className="h-4 w-32 rounded bg-surface-hover" />
          <div className="h-4 w-40 rounded bg-surface-hover" />
          <div className="h-4 w-28 rounded bg-surface-hover" />
          <div className="ml-auto h-4 w-20 rounded bg-surface-hover" />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ContactsPage() {
  const router = useRouter()

  const [contacts, setContacts] = useState<Contact[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [expandedUlid, setExpandedUlid] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchContacts = useCallback(async (q: string, pg: number) => {
    const token = localStorage.getItem('cardex_token')
    if (!token) { router.replace('/dashboard/login'); return }
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ page: pg.toString(), per_page: PAGE_SIZE.toString() })
      if (q.trim()) params.set('q', q.trim())

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/contacts?${params}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      if (res.status === 401) { router.replace('/dashboard/login'); return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json: ContactsResponse = await res.json()
      setContacts(json.contacts)
      setTotal(json.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load contacts')
    } finally {
      setLoading(false)
    }
  }, [router])

  // Initial load
  useEffect(() => { fetchContacts('', 1) }, [fetchContacts])

  // Debounced search
  function handleSearchChange(value: string) {
    setSearch(value)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      setPage(1)
      fetchContacts(value, 1)
    }, 300)
  }

  // Page change
  useEffect(() => {
    fetchContacts(search, page)
  }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggleExpand(ulid: string) {
    setExpandedUlid(prev => prev === ulid ? null : ulid)
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <>
      {showAddModal && (
        <AddContactModal
          onClose={() => setShowAddModal(false)}
          onAdded={() => fetchContacts(search, page)}
        />
      )}

      <div className="mx-auto max-w-screen-xl px-4 py-8">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Customer Database</h1>
            <p className="mt-1 text-sm text-surface-muted">{total} contacts</p>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
          >
            + Add Contact
          </button>
        </div>

        {/* Search */}
        <div className="mb-4">
          <input
            type="text"
            value={search}
            onChange={e => handleSearchChange(e.target.value)}
            placeholder="Search by name, email or phone…"
            className="w-full max-w-sm rounded-lg border border-surface-border bg-surface px-4 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 rounded-xl border border-red-500/50 bg-red-500/10 p-4 text-center">
            <p className="mb-2 text-sm text-red-400">{error}</p>
            <button
              onClick={() => fetchContacts(search, page)}
              className="rounded-lg bg-red-500/20 px-4 py-1.5 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* Table */}
        <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-card">
          {loading ? (
            <TableSkeleton />
          ) : contacts.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-surface-muted">
                {search ? 'No contacts match your search.' : 'No contacts yet.'}
              </p>
              {!search && (
                <button
                  onClick={() => setShowAddModal(true)}
                  className="mt-3 text-sm text-brand-400 hover:text-brand-300 transition-colors"
                >
                  Add your first contact →
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-surface-border text-left">
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Name</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Email</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Phone</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Purchases</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Lifetime Value</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Last Contact</th>
                    <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-surface-muted">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map(contact => {
                    const lastContact = relativeTime(contact.last_contact_at)
                    const isExpanded = expandedUlid === contact.contact_ulid

                    return (
                      <React.Fragment key={contact.contact_ulid}>
                        <tr
                          onClick={() => toggleExpand(contact.contact_ulid)}
                          className={`cursor-pointer border-b border-surface-border transition-colors hover:bg-surface-hover ${isExpanded ? 'bg-surface-hover' : ''}`}
                        >
                          {/* Name */}
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-500/10 font-mono text-xs font-semibold text-brand-400">
                                {contact.full_name.charAt(0).toUpperCase()}
                              </div>
                              <span className="font-medium text-white">{contact.full_name}</span>
                            </div>
                          </td>

                          {/* Email */}
                          <td className="px-4 py-3 text-sm text-surface-muted">
                            {contact.email ? (
                              <a
                                href={`mailto:${contact.email}`}
                                onClick={e => e.stopPropagation()}
                                className="hover:text-white transition-colors"
                              >
                                {contact.email}
                              </a>
                            ) : (
                              <span className="text-surface-border">—</span>
                            )}
                          </td>

                          {/* Phone */}
                          <td className="px-4 py-3 font-mono text-sm text-surface-muted">
                            {contact.phone ?? <span className="text-surface-border">—</span>}
                          </td>

                          {/* Purchases */}
                          <td className="px-4 py-3 font-mono text-sm text-white">
                            {contact.total_purchases}
                          </td>

                          {/* Lifetime value */}
                          <td className="px-4 py-3 font-mono text-sm">
                            <span className={lifetimeValueClass(contact.lifetime_value_eur)}>
                              {formatEur(contact.lifetime_value_eur)}
                            </span>
                          </td>

                          {/* Last contact */}
                          <td className="px-4 py-3 text-sm">
                            <span className={lastContact.isStale ? 'text-red-400' : 'text-surface-muted'}>
                              {lastContact.label}
                            </span>
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                              <button
                                onClick={() => router.push(`/dashboard/crm/communications/new?contact=${contact.contact_ulid}`)}
                                className="rounded-lg border border-surface-border px-2.5 py-1 text-xs text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors"
                              >
                                Log Call
                              </button>
                              <button
                                onClick={() => toggleExpand(contact.contact_ulid)}
                                className={`rounded-lg border px-2.5 py-1 text-xs transition-colors ${
                                  isExpanded
                                    ? 'border-brand-500/50 text-brand-400'
                                    : 'border-surface-border text-surface-muted hover:border-brand-500/50 hover:text-white'
                                }`}
                              >
                                {isExpanded ? 'Collapse ▲' : 'Details ▼'}
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* Expanded detail row */}
                        {isExpanded && (
                          <ExpandedRow contactUlid={contact.contact_ulid} />
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-surface-muted">
              Page {page} of {totalPages} · {total} contacts
            </p>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white disabled:opacity-40 transition-colors"
              >
                ← Prev
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white disabled:opacity-40 transition-colors"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
