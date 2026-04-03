'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const eur = (v: number) =>
  new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

// ── Types ──────────────────────────────────────────────────────────────────────

interface PublishingListing {
  pub_ulid: string
  crm_vehicle_ulid: string
  platform: string
  status: string
  external_id?: string
  external_url?: string
  title?: string
  error_message?: string
  published_at?: string
  expires_at?: string
  created_at: string
  updated_at: string
  make?: string
  model?: string
  year?: number
  mileage_km?: number
  asking_price_eur?: number
}

// ── Config ─────────────────────────────────────────────────────────────────────

const PLATFORMS = [
  { id: 'AUTOSCOUT24',  label: 'AutoScout24',  color: '#3b82f6', textColor: 'text-blue-400',   bg: 'bg-blue-500/10',   export: 'autoscout24.xml', exportLabel: 'XML Feed' },
  { id: 'WALLAPOP',     label: 'Wallapop',     color: '#ef4444', textColor: 'text-red-400',    bg: 'bg-red-500/10',    export: 'wallapop',        exportLabel: 'JSON' },
  { id: 'COCHES_NET',   label: 'Coches.net',   color: '#f97316', textColor: 'text-orange-400', bg: 'bg-orange-500/10', export: 'coches_net',      exportLabel: 'CSV' },
  { id: 'MOBILE_DE',    label: 'Mobile.de',    color: '#10b981', textColor: 'text-emerald-400',bg: 'bg-emerald-500/10',export: 'mobile_de',       exportLabel: 'XML' },
  { id: 'MARKTPLAATS',  label: 'Marktplaats',  color: '#eab308', textColor: 'text-yellow-400', bg: 'bg-yellow-500/10', export: null,              exportLabel: '' },
  { id: 'LACENTRALE',   label: 'La Centrale',  color: '#7c3aed', textColor: 'text-brand-400',  bg: 'bg-brand-500/10',  export: null,              exportLabel: '' },
  { id: 'MILANUNCIOS',  label: 'Milanuncios',  color: '#14b8a6', textColor: 'text-teal-400',   bg: 'bg-teal-500/10',   export: 'milanuncios',     exportLabel: 'CSV' },
  { id: 'MANUAL',       label: 'Manual',       color: '#6b7280', textColor: 'text-gray-400',   bg: 'bg-gray-500/10',   export: null,              exportLabel: '' },
]

const STATUS_CFG: Record<string, { label: string; cls: string }> = {
  DRAFT:    { label: 'Borrador',  cls: 'bg-gray-500/20 text-gray-400' },
  PENDING:  { label: 'Pendiente', cls: 'bg-yellow-500/20 text-yellow-400' },
  ACTIVE:   { label: 'Activo',    cls: 'bg-emerald-500/20 text-emerald-400' },
  PAUSED:   { label: 'Pausado',   cls: 'bg-orange-500/20 text-orange-400' },
  EXPIRED:  { label: 'Expirado',  cls: 'bg-red-500/20 text-red-400' },
  REJECTED: { label: 'Rechazado', cls: 'bg-red-500/20 text-red-400' },
}

// ── Download helper (authenticated) ───────────────────────────────────────────

async function downloadFile(url: string, filename: string) {
  const res = await fetch(url, { headers: authHeader() })
  if (!res.ok) throw new Error(`Error ${res.status}`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}

// ── CreateModal ────────────────────────────────────────────────────────────────

function CreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [vehicleULID, setVehicleULID] = useState('')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [expiresInDays, setExpiresInDays] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function togglePlatform(id: string) {
    setSelectedPlatforms(prev =>
      prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
    )
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!vehicleULID.trim()) { setError('El ULID del vehículo es obligatorio'); return }
    if (selectedPlatforms.length === 0) { setError('Selecciona al menos un portal'); return }

    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/v1/dealer/publishing`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({
          crm_vehicle_ulid: vehicleULID.trim(),
          platforms: selectedPlatforms,
          title: title.trim() || undefined,
          expires_in_days: expiresInDays ? parseInt(expiresInDays) : undefined,
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.message ?? `Error ${res.status}`)
      }
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear publicación')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-lg rounded-2xl border border-surface-border bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-surface-border px-6 py-4">
          <h2 className="text-base font-semibold text-white">Nueva publicación</h2>
          <button
            onClick={onClose}
            className="text-surface-muted hover:text-white transition"
            aria-label="Cerrar"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={submit} className="space-y-5 p-6">
          {/* Vehicle ULID */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-surface-muted">
              ULID del vehículo CRM <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={vehicleULID}
              onChange={e => setVehicleULID(e.target.value)}
              placeholder="01JFKQ..."
              className="w-full rounded-lg border border-surface-border bg-surface-dark px-3 py-2 font-mono text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Platform checkboxes */}
          <div>
            <label className="mb-2 block text-xs font-medium text-surface-muted">
              Portales <span className="text-red-400">*</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              {PLATFORMS.map(p => (
                <label
                  key={p.id}
                  className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm transition ${
                    selectedPlatforms.includes(p.id)
                      ? 'border-brand-500/60 bg-brand-500/10 text-white'
                      : 'border-surface-border text-surface-muted hover:border-surface-muted'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedPlatforms.includes(p.id)}
                    onChange={() => togglePlatform(p.id)}
                  />
                  <span className="h-4 w-4 flex-shrink-0 rounded-sm border border-current flex items-center justify-center">
                    {selectedPlatforms.includes(p.id) && (
                      <svg className="h-3 w-3 text-brand-400" fill="currentColor" viewBox="0 0 12 12">
                        <path d="M10 3L5 8.5 2 5.5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/>
                      </svg>
                    )}
                  </span>
                  {p.label}
                </label>
              ))}
            </div>
          </div>

          {/* Title (optional) */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-surface-muted">
              Título personalizado <span className="text-surface-muted/60">(opcional)</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="BMW Serie 3 · 2020 · 80.000 km"
              className="w-full rounded-lg border border-surface-border bg-surface-dark px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Expires */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-surface-muted">
              Caducidad (días) <span className="text-surface-muted/60">(opcional)</span>
            </label>
            <input
              type="number"
              value={expiresInDays}
              onChange={e => setExpiresInDays(e.target.value)}
              placeholder="30"
              min="1"
              max="365"
              className="w-full rounded-lg border border-surface-border bg-surface-dark px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-surface-border px-4 py-2 text-sm text-surface-muted hover:text-white transition"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition disabled:opacity-50"
            >
              {loading && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              )}
              Crear publicación
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function PublishPage() {
  const router = useRouter()
  const [listings, setListings] = useState<PublishingListing[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [platformFilter, setPlatformFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [showModal, setShowModal] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const fetchListings = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (platformFilter !== 'ALL') params.set('platform', platformFilter)
      if (statusFilter !== 'ALL') params.set('status', statusFilter)

      const res = await fetch(`${API}/api/v1/dealer/publishing?${params}`, {
        headers: authHeader(),
      })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.message ?? `Error ${res.status}`)
      }
      const data = await res.json()
      setListings(data.listings ?? [])
      setTotal(data.total ?? 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando publicaciones')
    } finally {
      setLoading(false)
    }
  }, [router, platformFilter, statusFilter])

  useEffect(() => { fetchListings() }, [fetchListings])

  // Count active listings per platform
  const platformCounts = PLATFORMS.reduce((acc, p) => {
    acc[p.id] = listings.filter(l => l.platform === p.id && l.status === 'ACTIVE').length
    return acc
  }, {} as Record<string, number>)

  async function toggleStatus(pub: PublishingListing) {
    const newStatus = pub.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
    setActionLoading(pub.pub_ulid)
    // Optimistic update
    setListings(prev => prev.map(l => l.pub_ulid === pub.pub_ulid ? { ...l, status: newStatus } : l))
    try {
      const res = await fetch(`${API}/api/v1/dealer/publishing/${pub.pub_ulid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!res.ok) throw new Error(`Error ${res.status}`)
    } catch {
      // Rollback
      setListings(prev => prev.map(l => l.pub_ulid === pub.pub_ulid ? { ...l, status: pub.status } : l))
    } finally {
      setActionLoading(null)
    }
  }

  async function deleteListing(pub: PublishingListing) {
    if (!confirm(`¿Eliminar publicación en ${pub.platform}?`)) return
    setActionLoading(pub.pub_ulid)
    setListings(prev => prev.filter(l => l.pub_ulid !== pub.pub_ulid))
    try {
      const res = await fetch(`${API}/api/v1/dealer/publishing/${pub.pub_ulid}`, {
        method: 'DELETE',
        headers: authHeader(),
      })
      if (!res.ok) throw new Error(`Error ${res.status}`)
    } catch {
      // Restore
      setListings(prev => [...prev, pub])
    } finally {
      setActionLoading(null)
    }
  }

  async function handleDownload(platform: typeof PLATFORMS[number]) {
    setDownloadError(null)
    try {
      if (platform.id === 'AUTOSCOUT24') {
        await downloadFile(
          `${API}/api/v1/dealer/publishing/feed/autoscout24.xml`,
          'autoscout24_feed.xml'
        )
      } else if (platform.export) {
        await downloadFile(
          `${API}/api/v1/dealer/publishing/export?format=${platform.export}`,
          `${platform.export}_export.${platform.exportLabel === 'CSV' ? 'csv' : platform.exportLabel === 'JSON' ? 'json' : 'xml'}`
        )
      }
    } catch {
      setDownloadError(`Error descargando feed de ${platform.label}`)
    }
  }

  const platformMeta = (id: string) => PLATFORMS.find(p => p.id === id)

  return (
    <div className="mx-auto max-w-screen-xl space-y-8">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Multipublicación</h1>
          <p className="mt-1 text-sm text-surface-muted">
            Gestiona la presencia de tu flota en todos los portales desde un solo lugar
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => handleDownload(PLATFORMS[0])}
            className="flex items-center gap-2 rounded-lg border border-surface-border px-4 py-2 text-sm text-surface-muted hover:border-blue-500/50 hover:text-blue-400 transition"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Feed AS24 XML
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Nueva publicación
          </button>
        </div>
      </div>

      {/* Download error */}
      {downloadError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {downloadError}
          <button onClick={() => setDownloadError(null)} className="ml-3 underline">Cerrar</button>
        </div>
      )}

      {/* ── Platform grid ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
        {PLATFORMS.map(p => (
          <div
            key={p.id}
            className={`rounded-xl border border-surface-border ${p.bg} p-3 transition hover:border-surface-muted/60`}
          >
            <div className={`mb-1 text-xs font-medium ${p.textColor}`}>{p.label}</div>
            <div className="text-xl font-bold text-white">{platformCounts[p.id] ?? 0}</div>
            <div className="mb-2 text-xs text-surface-muted">activos</div>
            {p.export && (
              <button
                onClick={() => handleDownload(p)}
                className={`w-full rounded-md border border-surface-border/60 px-2 py-1 text-xs ${p.textColor} hover:bg-surface-hover transition`}
              >
                ↓ {p.exportLabel}
              </button>
            )}
          </div>
        ))}
      </div>

      {/* ── Filters ── */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-xs text-surface-muted">Portal:</label>
          <select
            value={platformFilter}
            onChange={e => setPlatformFilter(e.target.value)}
            className="rounded-lg border border-surface-border bg-surface-dark px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
          >
            <option value="ALL">Todos</option>
            {PLATFORMS.map(p => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-surface-muted">Estado:</label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="rounded-lg border border-surface-border bg-surface-dark px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
          >
            <option value="ALL">Todos</option>
            {Object.entries(STATUS_CFG).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>
        <div className="ml-auto text-xs text-surface-muted">
          {loading ? 'Cargando…' : `${total} publicaciones`}
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
          <button onClick={fetchListings} className="ml-3 underline">Reintentar</button>
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {loading && listings.length === 0 && (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-surface-hover" />
          ))}
        </div>
      )}

      {/* ── Table ── */}
      {!loading || listings.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-surface-border">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-border bg-surface">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-surface-muted">Vehículo</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-surface-muted">Portal</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-surface-muted">Estado</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-surface-muted">Precio</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-surface-muted">URL externa</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-surface-muted">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {listings.map(pub => {
                const pm = platformMeta(pub.platform)
                const sc = STATUS_CFG[pub.status] ?? { label: pub.status, cls: 'bg-gray-500/20 text-gray-400' }
                const vehicleLabel = [pub.make, pub.model, pub.year].filter(Boolean).join(' ')
                const isLoading = actionLoading === pub.pub_ulid
                return (
                  <tr key={pub.pub_ulid} className="hover:bg-surface-hover/40 transition">
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{vehicleLabel || '—'}</div>
                      {pub.mileage_km != null && pub.mileage_km > 0 && (
                        <div className="text-xs text-surface-muted">
                          {new Intl.NumberFormat('es-ES').format(pub.mileage_km)} km
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${pm?.bg ?? 'bg-gray-500/10'} ${pm?.textColor ?? 'text-gray-400'}`}>
                        {pm?.label ?? pub.platform}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${sc.cls}`}>
                        {sc.label}
                      </span>
                      {pub.error_message && (
                        <div className="mt-1 text-xs text-red-400 line-clamp-1" title={pub.error_message}>
                          ⚠ {pub.error_message}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-white">
                      {pub.asking_price_eur ? eur(pub.asking_price_eur) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {pub.external_url ? (
                        <a
                          href={pub.external_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`text-xs underline ${pm?.textColor ?? 'text-brand-400'} hover:opacity-80 transition`}
                        >
                          Ver anuncio →
                        </a>
                      ) : (
                        <span className="text-xs text-surface-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {/* Toggle active/paused — only for ACTIVE/PAUSED/DRAFT/PENDING */}
                        {['ACTIVE', 'PAUSED', 'DRAFT', 'PENDING'].includes(pub.status) && (
                          <button
                            onClick={() => toggleStatus(pub)}
                            disabled={isLoading}
                            className={`rounded-md px-3 py-1 text-xs font-medium transition disabled:opacity-50 ${
                              pub.status === 'ACTIVE'
                                ? 'border border-orange-500/40 text-orange-400 hover:bg-orange-500/10'
                                : 'border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10'
                            }`}
                          >
                            {isLoading
                              ? <span className="h-3 w-3 inline-block animate-spin rounded-full border border-current border-t-transparent" />
                              : pub.status === 'ACTIVE' ? 'Pausar' : 'Activar'
                            }
                          </button>
                        )}
                        {/* Delete */}
                        <button
                          onClick={() => deleteListing(pub)}
                          disabled={isLoading}
                          className="rounded-md border border-surface-border px-2 py-1 text-xs text-surface-muted hover:border-red-500/50 hover:text-red-400 transition disabled:opacity-50"
                          aria-label="Eliminar"
                        >
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}

              {!loading && listings.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center text-surface-muted">
                    <div className="mb-2 text-3xl">📡</div>
                    <div className="text-sm">No hay publicaciones aún.</div>
                    <button
                      onClick={() => setShowModal(true)}
                      className="mt-3 text-sm text-brand-400 underline hover:text-brand-300"
                    >
                      Crear primera publicación →
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* ── Modal ── */}
      {showModal && (
        <CreateModal
          onClose={() => setShowModal(false)}
          onCreated={fetchListings}
        />
      )}
    </div>
  )
}
