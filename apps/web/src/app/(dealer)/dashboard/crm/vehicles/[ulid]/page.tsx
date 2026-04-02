'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Image from 'next/image'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type LifecycleStatus =
  | 'SOURCING'
  | 'PURCHASED'
  | 'RECONDITIONING'
  | 'READY'
  | 'LISTED'
  | 'RESERVED'
  | 'SOLD'
  | 'ARCHIVED'

interface CrmVehicle {
  crm_vehicle_ulid: string
  make: string
  model: string
  year: number
  fuel_type: string
  transmission: string
  mileage_km: number
  co2_gkm: number | null
  power_kw: number | null
  registration_date: string | null
  condition_grade: string | null
  vin: string | null
  lifecycle_status: LifecycleStatus
  asking_price_eur: number
  floor_price_eur: number
  purchase_price_eur: number
  recon_cost_eur: number
  transport_cost_eur: number
  marketing_cost_eur: number
  total_cost_eur: number
  margin_eur: number
  margin_pct: number
  days_in_stock: number
  photos: string[]
}

interface ReconJob {
  job_ulid: string
  job_type: string
  description: string
  supplier_name: string
  cost_estimate_eur: number
  cost_actual_eur: number | null
  status: string
  started_at: string | null
  completed_at: string | null
}

interface Transaction {
  tx_ulid: string
  tx_type: string
  amount_eur: number
  description: string
  tx_date: string
}

interface Communication {
  comm_ulid: string
  channel: string
  direction: string
  subject: string
  outcome: string
  created_at: string
}

interface VehicleDetailResponse {
  vehicle: CrmVehicle
  recon_jobs: ReconJob[]
  transactions: Transaction[]
  communications: Communication[]
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const STATUS_BADGE: Record<LifecycleStatus, string> = {
  SOURCING: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
  PURCHASED: 'bg-blue-900/40 text-blue-400 border border-blue-500/20',
  RECONDITIONING: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  READY: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30',
  LISTED: 'bg-brand-500/20 text-brand-400 border border-brand-500/30',
  RESERVED: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  SOLD: 'bg-surface-hover text-surface-muted border border-surface-border',
  ARCHIVED: 'bg-surface-hover text-surface-muted/60 border border-surface-border',
}

const RECON_STATUS_BADGE: Record<string, string> = {
  PENDING: 'bg-surface-hover text-surface-muted border border-surface-border',
  IN_PROGRESS: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  COMPLETED: 'bg-brand-500/20 text-brand-400 border border-brand-500/30',
  CANCELLED: 'bg-red-500/20 text-red-400 border border-red-500/30',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatEur(value: number): string {
  return '€\u00a0' + value.toLocaleString('en-IE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IE', { day: 'numeric', month: 'short', year: 'numeric' })
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const d = Math.floor(diff / 86_400_000)
  if (d === 0) return 'Today'
  if (d === 1) return 'Yesterday'
  if (d < 30) return `${d} days ago`
  const w = Math.floor(d / 7)
  if (w < 8) return `${w} weeks ago`
  const m = Math.floor(d / 30)
  return `${m} months ago`
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('cardex_token') ?? ''
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// Cost Breakdown Card
interface CostBreakdownProps {
  vehicle: CrmVehicle
  onAskingPriceSaved: (newPrice: number) => void
}

function CostBreakdownCard({ vehicle, onAskingPriceSaved }: CostBreakdownProps) {
  const [editing, setEditing] = useState(false)
  const [draftPrice, setDraftPrice] = useState(vehicle.asking_price_eur.toString())
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const floorWarning = vehicle.asking_price_eur < vehicle.floor_price_eur * 1.05
  const margin = vehicle.asking_price_eur - vehicle.total_cost_eur
  const marginPct = vehicle.total_cost_eur > 0 ? (margin / vehicle.total_cost_eur) * 100 : 0

  async function saveAskingPrice() {
    const newPrice = parseFloat(draftPrice.replace(/[^\d.]/g, ''))
    if (isNaN(newPrice) || newPrice <= 0) { setSaveError('Invalid price'); return }
    setSaving(true)
    setSaveError(null)
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/vehicles/${vehicle.crm_vehicle_ulid}`,
        {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify({ asking_price_eur: newPrice }),
        }
      )
      if (!res.ok) throw new Error(`Error ${res.status}`)
      setEditing(false)
      onAskingPriceSaved(newPrice)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') saveAskingPrice()
    if (e.key === 'Escape') { setEditing(false); setDraftPrice(vehicle.asking_price_eur.toString()) }
  }

  const lineItem = (label: string, value: number, dim = false) => (
    <div className={`flex items-center justify-between py-1.5 ${dim ? 'text-surface-muted' : ''}`}>
      <span className={`text-sm ${dim ? 'text-surface-muted' : 'text-surface-muted'}`}>{label}</span>
      <span className={`font-mono text-sm ${dim ? 'text-surface-muted' : 'text-white'}`}>{formatEur(value)}</span>
    </div>
  )

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-surface-muted">Cost Breakdown</h3>

      <div className="divide-y divide-surface-border/50">
        {/* Costs */}
        <div className="pb-3">
          {lineItem('Purchase price', vehicle.purchase_price_eur)}
          {lineItem('Reconditioning', vehicle.recon_cost_eur)}
          {lineItem('Transport', vehicle.transport_cost_eur)}
          {lineItem('Marketing', vehicle.marketing_cost_eur)}
        </div>

        {/* Total cost */}
        <div className="py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">Total cost</span>
            <span className="font-mono text-sm font-semibold text-white">{formatEur(vehicle.total_cost_eur)}</span>
          </div>
        </div>

        {/* Asking price (editable) */}
        <div className="py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">Asking price</span>
            {editing ? (
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-surface-muted">€</span>
                <input
                  type="number"
                  value={draftPrice}
                  onChange={e => setDraftPrice(e.target.value)}
                  onKeyDown={handleKeyDown}
                  autoFocus
                  className="w-28 rounded-lg border border-brand-500 bg-surface px-2 py-1 font-mono text-sm text-white focus:outline-none"
                />
                <button
                  onClick={saveAskingPrice}
                  disabled={saving}
                  className="rounded-lg bg-brand-500 px-2 py-1 text-xs text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
                >
                  {saving ? '…' : 'Save'}
                </button>
                <button
                  onClick={() => { setEditing(false); setDraftPrice(vehicle.asking_price_eur.toString()) }}
                  className="rounded-lg border border-surface-border px-2 py-1 text-xs text-surface-muted hover:text-white transition-colors"
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setEditing(true); setDraftPrice(vehicle.asking_price_eur.toString()) }}
                className="group flex items-center gap-2 font-mono text-sm text-white"
                title="Click to edit asking price"
              >
                <span>{formatEur(vehicle.asking_price_eur)}</span>
                <span className="text-xs text-surface-muted opacity-0 group-hover:opacity-100 transition-opacity">✎</span>
              </button>
            )}
          </div>
          {saveError && <p className="mt-1 text-xs text-red-400">{saveError}</p>}
        </div>

        {/* Gross margin */}
        <div className="pt-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">Gross margin</span>
            <div className="text-right">
              <span className={`font-mono text-sm font-bold ${margin >= 0 ? 'text-brand-400' : 'text-red-400'}`}>
                {formatEur(margin)}
              </span>
              <span className={`ml-2 font-mono text-xs ${margin >= 0 ? 'text-brand-400' : 'text-red-400'}`}>
                ({marginPct.toFixed(1)}%)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Floor price */}
      <div className={`mt-4 rounded-lg p-3 ${floorWarning ? 'border border-red-500/40 bg-red-500/5' : 'border border-surface-border bg-surface'}`}>
        <div className="flex items-center justify-between">
          <span className="text-xs text-surface-muted">Floor price</span>
          <span className="font-mono text-xs text-surface-muted">{formatEur(vehicle.floor_price_eur)}</span>
        </div>
        {floorWarning && (
          <p className="mt-1 text-xs text-red-400">
            ⚠ Asking price is less than 5% above floor
          </p>
        )}
      </div>
    </div>
  )
}

// Recon Job inline form
interface AddReconJobFormProps {
  vehicleUlid: string
  onAdded: () => void
  onCancel: () => void
}

function AddReconJobForm({ vehicleUlid, onAdded, onCancel }: AddReconJobFormProps) {
  const [form, setForm] = useState({
    job_type: '',
    description: '',
    supplier_name: '',
    cost_estimate_eur: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/recon`,
        {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({
            ...form,
            crm_vehicle_ulid: vehicleUlid,
            cost_estimate_eur: parseFloat(form.cost_estimate_eur) || 0,
          }),
        }
      )
      if (!res.ok) throw new Error(`Error ${res.status}`)
      onAdded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add job')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-brand-500/30 bg-brand-500/5 p-4 space-y-3">
      <p className="text-sm font-semibold text-white">New Recon Job</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs text-surface-muted">Job Type *</label>
          <input
            type="text"
            value={form.job_type}
            onChange={e => set('job_type', e.target.value)}
            placeholder="e.g. Paint, Service, Tyres"
            required
            className="w-full rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-surface-muted">Supplier</label>
          <input
            type="text"
            value={form.supplier_name}
            onChange={e => set('supplier_name', e.target.value)}
            placeholder="Supplier name"
            className="w-full rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div className="col-span-2">
          <label className="mb-1 block text-xs text-surface-muted">Description</label>
          <input
            type="text"
            value={form.description}
            onChange={e => set('description', e.target.value)}
            placeholder="Work description"
            className="w-full rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-surface-muted">Est. Cost (€)</label>
          <input
            type="number"
            value={form.cost_estimate_eur}
            onChange={e => set('cost_estimate_eur', e.target.value)}
            placeholder="0"
            min="0"
            className="w-full rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-surface-border px-4 py-1.5 text-sm text-surface-muted hover:text-white transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Add Job'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tab types
// ---------------------------------------------------------------------------
type Tab = 'recon' | 'communications' | 'documents' | 'transactions'

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function VehicleDetailPage() {
  const router = useRouter()
  const params = useParams()
  const ulid = params?.ulid as string

  const [data, setData] = useState<VehicleDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('recon')
  const [selectedPhoto, setSelectedPhoto] = useState(0)
  const [showAddRecon, setShowAddRecon] = useState(false)

  const fetchVehicle = useCallback(async () => {
    const token = localStorage.getItem('cardex_token')
    if (!token) { router.replace('/dashboard/login'); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/vehicles/${ulid}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      if (res.status === 401) { router.replace('/dashboard/login'); return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json: VehicleDetailResponse = await res.json()
      setData(json)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load vehicle')
    } finally {
      setLoading(false)
    }
  }, [ulid, router])

  useEffect(() => { fetchVehicle() }, [fetchVehicle])

  function handleAskingPriceSaved(newPrice: number) {
    if (!data) return
    setData(prev => prev ? {
      ...prev,
      vehicle: {
        ...prev.vehicle,
        asking_price_eur: newPrice,
        margin_eur: newPrice - prev.vehicle.total_cost_eur,
        margin_pct: prev.vehicle.total_cost_eur > 0
          ? ((newPrice - prev.vehicle.total_cost_eur) / prev.vehicle.total_cost_eur) * 100
          : 0,
      },
    } : prev)
  }

  // ── Loading ──
  if (loading) {
    return (
      <div className="mx-auto max-w-screen-xl px-4 py-8 animate-pulse">
        <div className="mb-6 h-8 w-64 rounded bg-surface-hover" />
        <div className="grid gap-6 lg:grid-cols-[60%_40%]">
          <div className="space-y-4">
            <div className="h-64 rounded-xl bg-surface-hover" />
            <div className="h-48 rounded-xl bg-surface-hover" />
          </div>
          <div className="h-72 rounded-xl bg-surface-hover" />
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-screen-xl px-4 py-8">
        <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-6 text-center">
          <p className="mb-3 text-red-400">{error ?? 'Vehicle not found'}</p>
          <button
            onClick={fetchVehicle}
            className="rounded-lg bg-red-500/20 px-4 py-2 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const { vehicle, recon_jobs, transactions, communications } = data
  const photos = vehicle.photos ?? []

  const TABS: { id: Tab; label: string; count?: number }[] = [
    { id: 'recon', label: 'Recon Jobs', count: recon_jobs.length },
    { id: 'communications', label: 'Communications', count: communications.length },
    { id: 'documents', label: 'Documents' },
    { id: 'transactions', label: 'Transactions', count: transactions.length },
  ]

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Breadcrumb */}
      <div className="mb-4 flex items-center gap-2 text-sm text-surface-muted">
        <button onClick={() => router.push('/dashboard/crm/inventory')} className="hover:text-white transition-colors">
          Inventory
        </button>
        <span>/</span>
        <span className="text-white">{vehicle.year} {vehicle.make} {vehicle.model}</span>
      </div>

      {/* ── Main layout: Left 60% + Right 40% ── */}
      <div className="grid gap-6 lg:grid-cols-[60%_40%]">
        {/* ── LEFT column ── */}
        <div className="space-y-5">
          {/* Vehicle header */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h1 className="text-2xl font-bold text-white">
                  {vehicle.year} {vehicle.make} {vehicle.model}
                </h1>
                <p className="mt-1 text-sm text-surface-muted">
                  {vehicle.fuel_type && <span>{vehicle.fuel_type} · </span>}
                  {vehicle.transmission && <span>{vehicle.transmission}</span>}
                  {vehicle.vin && (
                    <span className="ml-2 font-mono text-xs">VIN: {vehicle.vin}</span>
                  )}
                </p>
              </div>
              <span className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${STATUS_BADGE[vehicle.lifecycle_status]}`}>
                {vehicle.lifecycle_status}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-sm text-surface-muted">
              <span>{vehicle.mileage_km.toLocaleString('en-IE')} km</span>
              <span className={vehicle.days_in_stock > 60 ? 'text-red-400' : vehicle.days_in_stock > 30 ? 'text-amber-400' : ''}>
                {vehicle.days_in_stock} days in stock
              </span>
              {vehicle.condition_grade && <span>Grade: {vehicle.condition_grade}</span>}
            </div>
          </div>

          {/* Photo gallery */}
          {photos.length > 0 ? (
            <div className="rounded-xl border border-surface-border bg-surface-card p-3 space-y-3">
              {/* Main photo */}
              <div className="relative h-56 w-full overflow-hidden rounded-lg bg-surface-hover">
                <Image
                  src={photos[selectedPhoto]}
                  alt={`${vehicle.make} ${vehicle.model} — photo ${selectedPhoto + 1}`}
                  fill
                  className="object-cover"
                  sizes="(min-width: 1024px) 55vw, 100vw"
                />
              </div>
              {/* Thumbnails */}
              {photos.length > 1 && (
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {photos.map((url, idx) => (
                    <button
                      key={idx}
                      onClick={() => setSelectedPhoto(idx)}
                      className={`relative h-14 w-20 flex-shrink-0 overflow-hidden rounded-md transition-all ${
                        idx === selectedPhoto
                          ? 'ring-2 ring-brand-500'
                          : 'opacity-60 hover:opacity-100'
                      }`}
                    >
                      <Image
                        src={url}
                        alt={`Thumbnail ${idx + 1}`}
                        fill
                        className="object-cover"
                        sizes="80px"
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-surface-border text-surface-muted">
              No photos uploaded
            </div>
          )}

          {/* Spec table */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-5">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-surface-muted">Specifications</h3>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {[
                ['Mileage', `${vehicle.mileage_km.toLocaleString('en-IE')} km`],
                ['Fuel type', vehicle.fuel_type || '—'],
                ['Transmission', vehicle.transmission || '—'],
                ['CO₂', vehicle.co2_gkm != null ? `${vehicle.co2_gkm} g/km` : '—'],
                ['Power', vehicle.power_kw != null ? `${vehicle.power_kw} kW` : '—'],
                ['Registration', formatDate(vehicle.registration_date)],
                ['Condition grade', vehicle.condition_grade || '—'],
                ['VIN', vehicle.vin || '—'],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between border-b border-surface-border/40 py-1.5 last:border-0">
                  <span className="text-xs text-surface-muted">{label}</span>
                  <span className="font-mono text-xs text-white">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Tabs */}
          <div className="rounded-xl border border-surface-border bg-surface-card">
            {/* Tab headers */}
            <div className="flex border-b border-surface-border">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? 'border-b-2 border-brand-500 text-white'
                      : 'text-surface-muted hover:text-white'
                  }`}
                >
                  {tab.label}
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className="rounded-full bg-surface-hover px-1.5 py-0.5 font-mono text-xs text-surface-muted">
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="p-5">
              {/* RECON JOBS */}
              {activeTab === 'recon' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-white">Reconditioning Jobs</p>
                    <button
                      onClick={() => setShowAddRecon(v => !v)}
                      className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-600 transition-colors"
                    >
                      + Add Job
                    </button>
                  </div>

                  {showAddRecon && (
                    <AddReconJobForm
                      vehicleUlid={ulid}
                      onAdded={() => { setShowAddRecon(false); fetchVehicle() }}
                      onCancel={() => setShowAddRecon(false)}
                    />
                  )}

                  {recon_jobs.length === 0 ? (
                    <p className="py-4 text-center text-sm text-surface-muted">No recon jobs yet.</p>
                  ) : (
                    <ul className="space-y-2">
                      {recon_jobs.map(job => (
                        <li key={job.job_ulid} className="rounded-lg border border-surface-border p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="font-medium text-white text-sm">{job.job_type}</p>
                              {job.description && (
                                <p className="mt-0.5 text-xs text-surface-muted">{job.description}</p>
                              )}
                              {job.supplier_name && (
                                <p className="mt-0.5 text-xs text-surface-muted">Supplier: {job.supplier_name}</p>
                              )}
                            </div>
                            <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${RECON_STATUS_BADGE[job.status] ?? 'bg-surface-hover text-surface-muted border border-surface-border'}`}>
                              {job.status}
                            </span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-4 text-xs text-surface-muted">
                            <span>Est: {formatEur(job.cost_estimate_eur)}</span>
                            {job.cost_actual_eur != null && (
                              <span className={job.cost_actual_eur > job.cost_estimate_eur ? 'text-amber-400' : 'text-brand-400'}>
                                Actual: {formatEur(job.cost_actual_eur)}
                              </span>
                            )}
                            {job.started_at && <span>Started: {formatDate(job.started_at)}</span>}
                            {job.completed_at && <span>Completed: {formatDate(job.completed_at)}</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* COMMUNICATIONS */}
              {activeTab === 'communications' && (
                <div>
                  <p className="mb-3 text-sm font-semibold text-white">Communication History</p>
                  {communications.length === 0 ? (
                    <p className="py-4 text-center text-sm text-surface-muted">No communications recorded.</p>
                  ) : (
                    <ul className="relative space-y-0 pl-5 before:absolute before:left-2 before:top-0 before:h-full before:w-px before:bg-surface-border">
                      {communications.map(comm => (
                        <li key={comm.comm_ulid} className="relative pb-4">
                          <span className="absolute -left-3 top-1 flex h-3 w-3 items-center justify-center">
                            <span className="h-2 w-2 rounded-full bg-brand-500" />
                          </span>
                          <div className="ml-2 rounded-lg border border-surface-border bg-surface p-3">
                            <div className="flex items-center gap-2">
                              <span className="rounded-full bg-surface-hover px-2 py-0.5 text-xs text-surface-muted">
                                {comm.channel}
                              </span>
                              <span className={`text-xs ${comm.direction === 'INBOUND' ? 'text-brand-400' : 'text-surface-muted'}`}>
                                {comm.direction}
                              </span>
                              <span className="ml-auto text-xs text-surface-muted">{timeAgo(comm.created_at)}</span>
                            </div>
                            {comm.subject && (
                              <p className="mt-1.5 text-sm font-medium text-white">{comm.subject}</p>
                            )}
                            {comm.outcome && (
                              <p className="mt-0.5 text-xs text-surface-muted">{comm.outcome}</p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* DOCUMENTS */}
              {activeTab === 'documents' && (
                <div className="py-8 text-center">
                  <p className="text-surface-muted">Document management coming soon.</p>
                </div>
              )}

              {/* TRANSACTIONS */}
              {activeTab === 'transactions' && (
                <div>
                  <p className="mb-3 text-sm font-semibold text-white">Transactions</p>
                  {transactions.length === 0 ? (
                    <p className="py-4 text-center text-sm text-surface-muted">No transactions recorded.</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b border-surface-border text-left">
                            <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Date</th>
                            <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Type</th>
                            <th className="pb-2 text-xs font-medium uppercase tracking-wider text-surface-muted">Description</th>
                            <th className="pb-2 text-right text-xs font-medium uppercase tracking-wider text-surface-muted">Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-surface-border">
                          {transactions.map(tx => {
                            const isCost = tx.amount_eur < 0
                            return (
                              <tr key={tx.tx_ulid} className="hover:bg-surface-hover transition-colors">
                                <td className="py-2.5 font-mono text-xs text-surface-muted">
                                  {formatDate(tx.tx_date)}
                                </td>
                                <td className="py-2.5">
                                  <span className="rounded-full bg-surface-hover px-2 py-0.5 text-xs text-surface-muted">
                                    {tx.tx_type}
                                  </span>
                                </td>
                                <td className="py-2.5 text-sm text-white">{tx.description}</td>
                                <td className={`py-2.5 text-right font-mono text-sm font-semibold ${isCost ? 'text-red-400' : 'text-brand-400'}`}>
                                  {isCost ? '' : '+'}
                                  {formatEur(tx.amount_eur)}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── RIGHT column ── */}
        <div className="space-y-5">
          <CostBreakdownCard vehicle={vehicle} onAskingPriceSaved={handleAskingPriceSaved} />
        </div>
      </div>
    </div>
  )
}
