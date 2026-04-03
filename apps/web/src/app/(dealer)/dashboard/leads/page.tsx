'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { MessageCircle, Phone, Mail, Clock, Loader2, AlertCircle, RefreshCw } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Types ──────────────────────────────────────────────────────────────────

type LeadStatus = 'NEW' | 'CONTACTED' | 'NEGOTIATING' | 'SOLD' | 'LOST'

interface Lead {
  lead_ulid: string
  vehicle_ulid?: string
  make?: string
  model?: string
  contact_name: string
  contact_email?: string
  contact_phone?: string
  message?: string
  status: LeadStatus
  created_at: string
}

// ── Config ────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<LeadStatus | string, string> = {
  NEW: 'bg-brand-500/20 text-brand-400',
  CONTACTED: 'bg-blue-500/20 text-blue-400',
  NEGOTIATING: 'bg-yellow-500/20 text-yellow-400',
  SOLD: 'bg-emerald-500/20 text-emerald-400',
  LOST: 'bg-surface-hover text-surface-muted',
}

const STATUS_LABEL: Record<LeadStatus | string, string> = {
  NEW: 'Nuevo',
  CONTACTED: 'Contactado',
  NEGOTIATING: 'Negociando',
  SOLD: 'Vendido',
  LOST: 'Perdido',
}

const NEXT_STATUSES: Record<LeadStatus, LeadStatus[]> = {
  NEW: ['CONTACTED', 'LOST'],
  CONTACTED: ['NEGOTIATING', 'LOST'],
  NEGOTIATING: ['SOLD', 'LOST'],
  SOLD: [],
  LOST: [],
}

// ── Helpers ───────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return `${Math.floor(diff / 60_000)}m`
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

function guessContactType(lead: Lead): 'CALL' | 'EMAIL' | 'MESSAGE' {
  if (lead.contact_phone && !lead.contact_email) return 'CALL'
  if (lead.contact_email && !lead.contact_phone) return 'EMAIL'
  return 'MESSAGE'
}

const TYPE_ICON = {
  CALL: Phone,
  EMAIL: Mail,
  MESSAGE: MessageCircle,
}

// ── Filter tabs ───────────────────────────────────────────────────────────

type FilterOption = 'ALL' | LeadStatus

const FILTERS: { value: FilterOption; label: string }[] = [
  { value: 'ALL', label: 'Todos' },
  { value: 'NEW', label: 'Nuevos' },
  { value: 'CONTACTED', label: 'Contactados' },
  { value: 'NEGOTIATING', label: 'Negociando' },
  { value: 'SOLD', label: 'Vendidos' },
  { value: 'LOST', label: 'Perdidos' },
]

// ── Status changer inline component ──────────────────────────────────────

function StatusChanger({
  lead,
  onStatusChanged,
}: {
  lead: Lead
  onStatusChanged: (leadUlid: string, newStatus: LeadStatus) => void
}) {
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nextStatuses = NEXT_STATUSES[lead.status] ?? []

  if (nextStatuses.length === 0) return null

  async function changeStatus(newStatus: LeadStatus) {
    setUpdating(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/v1/dealer/leads/${lead.lead_ulid}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.message ?? `Error ${res.status}`)
      }
      onStatusChanged(lead.lead_ulid, newStatus)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al actualizar')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" onClick={e => e.stopPropagation()}>
      {error && <span className="text-xs text-red-400">{error}</span>}
      {nextStatuses.map(s => (
        <button
          key={s}
          onClick={() => changeStatus(s)}
          disabled={updating}
          className="rounded-md border border-surface-border px-2 py-0.5 text-xs text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
        >
          {updating ? <Loader2 size={10} className="inline animate-spin" /> : null}
          {' '}Marcar como {STATUS_LABEL[s]}
        </button>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function LeadsPage() {
  const router = useRouter()
  const [leads, setLeads] = useState<Lead[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterOption>('ALL')

  const fetchLeads = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/v1/dealer/leads`, { headers: authHeader() })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.message ?? `Error ${res.status}`)
      }
      const data = await res.json()
      setLeads(data.leads ?? [])
      setTotal(data.total ?? (data.leads ?? []).length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando leads')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => { fetchLeads() }, [fetchLeads])

  function handleStatusChanged(leadUlid: string, newStatus: LeadStatus) {
    setLeads(prev =>
      prev.map(l => l.lead_ulid === leadUlid ? { ...l, status: newStatus } : l)
    )
  }

  const filtered = filter === 'ALL' ? leads : leads.filter(l => l.status === filter)
  const newCount = leads.filter(l => l.status === 'NEW').length

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Leads</h1>
          <p className="mt-1 text-sm text-surface-muted">
            {loading ? 'Cargando…' : `${total} leads${newCount > 0 ? ` · ${newCount} nuevos` : ''}`}
          </p>
        </div>
        <button
          onClick={fetchLeads}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-surface-border px-4 py-2 text-sm text-surface-muted hover:border-brand-500/50 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Actualizar
        </button>
      </div>

      {/* Filter tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.value
                ? 'bg-brand-500 text-white'
                : 'border border-surface-border text-surface-muted hover:text-white'
            }`}
          >
            {f.label}
            {f.value !== 'ALL' && (
              <span className="ml-1.5 font-mono text-xs opacity-70">
                {leads.filter(l => l.status === f.value).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertCircle size={16} className="shrink-0" />
          {error}
          <button onClick={fetchLeads} className="ml-auto text-red-300 underline hover:text-red-200">
            Reintentar
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && leads.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 size={28} className="animate-spin text-brand-400" />
        </div>
      ) : (
        /* Lead list */
        <div className="flex flex-col gap-3">
          {filtered.map(lead => {
            const contactType = guessContactType(lead)
            const Icon = TYPE_ICON[contactType]
            const vehicleLabel = [lead.make, lead.model].filter(Boolean).join(' ')
            return (
              <div
                key={lead.lead_ulid}
                className="flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-4 hover:border-brand-500/40 transition-colors"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-hover text-surface-muted">
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="font-medium text-white">{lead.contact_name}</span>
                    <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[lead.status] ?? 'bg-surface-hover text-surface-muted'}`}>
                      {STATUS_LABEL[lead.status] ?? lead.status}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-surface-muted">
                      <Clock size={11} /> {timeAgo(lead.created_at)}
                    </span>
                  </div>
                  {vehicleLabel && (
                    <p className="mt-0.5 text-sm text-surface-muted truncate">{vehicleLabel}</p>
                  )}
                  {lead.message && (
                    <p className="mt-1.5 text-sm text-white/70 line-clamp-1">&ldquo;{lead.message}&rdquo;</p>
                  )}
                  <div className="mt-1 flex flex-wrap gap-3 text-xs font-mono text-surface-muted">
                    {lead.contact_email && <span>{lead.contact_email}</span>}
                    {lead.contact_phone && <span>{lead.contact_phone}</span>}
                  </div>
                  <StatusChanger lead={lead} onStatusChanged={handleStatusChanged} />
                </div>
              </div>
            )
          })}
          {!loading && filtered.length === 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-12 text-center text-surface-muted">
              {filter === 'ALL' ? 'No hay leads aún.' : `No hay leads con estado "${STATUS_LABEL[filter]}".`}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
