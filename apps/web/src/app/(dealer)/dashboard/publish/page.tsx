'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const fmtEUR = (v: number) =>
  new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)

// ── Types ──────────────────────────────────────────────────────────────────────

interface CRMVehicle {
  crm_vehicle_ulid: string
  make: string
  model: string
  year: number
  mileage_km: number
  asking_price_eur: number
  lifecycle_status: string
}

interface PublishingListing {
  pub_ulid: string
  crm_vehicle_ulid: string
  platform: string
  status: string
  external_url?: string
  error_message?: string
  published_at?: string
  last_synced_at?: string
  updated_at: string
}

// ── Platform config ────────────────────────────────────────────────────────────

const PLATFORMS = [
  { id: 'AUTOSCOUT24', label: 'AutoScout24', reach: '4.2M', textColor: 'text-blue-400',    ring: 'ring-blue-500',    dot: 'bg-blue-400',    export: { url: '/api/v1/dealer/publishing/feed/autoscout24.xml', filename: 'autoscout24_feed.xml', label: 'XML Feed' } },
  { id: 'WALLAPOP',    label: 'Wallapop',    reach: '2.8M', textColor: 'text-red-400',     ring: 'ring-red-500',     dot: 'bg-red-400',     export: { url: '/api/v1/dealer/publishing/export?format=wallapop', filename: 'wallapop.json', label: 'JSON' } },
  { id: 'COCHES_NET',  label: 'Coches.net',  reach: '1.9M', textColor: 'text-orange-400',  ring: 'ring-orange-500',  dot: 'bg-orange-400',  export: { url: '/api/v1/dealer/publishing/export?format=coches_net', filename: 'coches_net.csv', label: 'CSV' } },
  { id: 'MOBILE_DE',   label: 'Mobile.de',   reach: '3.1M', textColor: 'text-emerald-400', ring: 'ring-emerald-500', dot: 'bg-emerald-400', export: { url: '/api/v1/dealer/publishing/export?format=mobile_de', filename: 'mobile_de.xml', label: 'XML' } },
  { id: 'MARKTPLAATS', label: 'Marktplaats', reach: '1.4M', textColor: 'text-yellow-400',  ring: 'ring-yellow-500',  dot: 'bg-yellow-400',  export: null },
  { id: 'LACENTRALE',  label: 'La Centrale', reach: '1.1M', textColor: 'text-brand-400',   ring: 'ring-brand-500',   dot: 'bg-brand-400',   export: null },
  { id: 'MILANUNCIOS', label: 'Milanuncios', reach: '0.8M', textColor: 'text-teal-400',    ring: 'ring-teal-500',    dot: 'bg-teal-400',    export: { url: '/api/v1/dealer/publishing/export?format=milanuncios', filename: 'milanuncios.csv', label: 'CSV' } },
  { id: 'MANUAL',      label: 'Manual',      reach: '—',    textColor: 'text-gray-400',    ring: 'ring-gray-500',    dot: 'bg-gray-500',    export: null },
] as const

type PlatformId = typeof PLATFORMS[number]['id']

// Status visuals
const STATUS = {
  ACTIVE:   { dot: 'bg-emerald-400', label: 'Activo',    ring: 'ring-emerald-500/40' },
  PENDING:  { dot: 'bg-yellow-400',  label: 'Pendiente', ring: 'ring-yellow-500/40' },
  PAUSED:   { dot: 'bg-orange-400',  label: 'Pausado',   ring: 'ring-orange-500/40' },
  DRAFT:    { dot: 'bg-gray-600',    label: 'Borrador',  ring: 'ring-gray-500/40' },
  EXPIRED:  { dot: 'bg-red-500',     label: 'Expirado',  ring: 'ring-red-500/40' },
  REJECTED: { dot: 'bg-red-500',     label: 'Rechazado', ring: 'ring-red-500/40' },
} as const

// ── Download helper ────────────────────────────────────────────────────────────

async function downloadFile(url: string, filename: string) {
  const res = await fetch(`${API}${url}`, { headers: authHeader() })
  if (!res.ok) throw new Error(`Error ${res.status}`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href; a.download = filename; a.click()
  URL.revokeObjectURL(href)
}

// ── Cell component — matrix cell for one vehicle × platform ───────────────────

function MatrixCell({
  vehicle,
  platform,
  listing,
  onToggle,
  busy,
}: {
  vehicle: CRMVehicle
  platform: typeof PLATFORMS[number]
  listing?: PublishingListing
  onToggle: (vehicle: CRMVehicle, platformId: PlatformId, listing?: PublishingListing) => void
  busy: boolean
}) {
  const s = listing ? STATUS[listing.status as keyof typeof STATUS] : null

  return (
    <button
      onClick={() => onToggle(vehicle, platform.id, listing)}
      disabled={busy}
      title={listing
        ? `${platform.label}: ${s?.label}${listing.error_message ? ' — ' + listing.error_message : ''}`
        : `Publicar en ${platform.label}`}
      className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-150 disabled:opacity-40 ${
        listing
          ? `border-transparent ${s?.ring} ring-1 bg-surface-hover hover:ring-2`
          : 'border-surface-border/40 hover:border-surface-muted/60 hover:bg-surface-hover'
      }`}
    >
      {busy ? (
        <span className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent opacity-60" />
      ) : listing ? (
        <span className={`h-2.5 w-2.5 rounded-full ${s?.dot}`} />
      ) : (
        <span className="text-[10px] text-surface-muted/40">+</span>
      )}
    </button>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function PublishPage() {
  const router = useRouter()
  const [vehicles, setVehicles] = useState<CRMVehicle[]>([])
  const [listings, setListings] = useState<PublishingListing[]>([])
  const [loadingVehicles, setLoadingVehicles] = useState(true)
  const [loadingListings, setLoadingListings] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyCells, setBusyCells] = useState<Set<string>>(new Set())
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [feedUrlCopied, setFeedUrlCopied] = useState(false)
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<PlatformId>>(new Set())
  const [lifecycleFilter, setLifecycleFilter] = useState<string>('SELLABLE')

  // ── Fetch CRM vehicles ──────────────────────────────────────────────────────
  const fetchVehicles = useCallback(async () => {
    setLoadingVehicles(true)
    try {
      const res = await fetch(`${API}/api/v1/dealer/crm/vehicles?limit=200`, { headers: authHeader() })
      if (res.status === 401) { router.push('/dashboard/login'); return }
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setVehicles(data.vehicles ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando vehículos')
    } finally {
      setLoadingVehicles(false)
    }
  }, [router])

  // ── Fetch publications ──────────────────────────────────────────────────────
  const fetchListings = useCallback(async () => {
    setLoadingListings(true)
    try {
      const res = await fetch(`${API}/api/v1/dealer/publishing?limit=500`, { headers: authHeader() })
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setListings(data.listings ?? [])
    } catch { /* silent — matrix shows empty cells */ }
    finally { setLoadingListings(false) }
  }, [])

  useEffect(() => { fetchVehicles(); fetchListings() }, [fetchVehicles, fetchListings])

  // ── Lookup helpers ──────────────────────────────────────────────────────────

  function getListing(vehicleULID: string, platformId: string) {
    return listings.find(l => l.crm_vehicle_ulid === vehicleULID && l.platform === platformId)
  }

  function cellKey(vehicleULID: string, platformId: string) {
    return `${vehicleULID}:${platformId}`
  }

  // ── Toggle cell: publish or pause/activate ──────────────────────────────────

  async function toggleCell(vehicle: CRMVehicle, platformId: PlatformId, existing?: PublishingListing) {
    const key = cellKey(vehicle.crm_vehicle_ulid, platformId)
    setBusyCells(prev => new Set(prev).add(key))

    try {
      if (!existing) {
        // Create new publication
        const res = await fetch(`${API}/api/v1/dealer/publishing`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeader() },
          body: JSON.stringify({ crm_vehicle_ulid: vehicle.crm_vehicle_ulid, platforms: [platformId] }),
        })
        if (!res.ok) throw new Error(`Error ${res.status}`)
        await fetchListings()
      } else {
        // Toggle active ↔ paused
        const newStatus = existing.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
        // Optimistic
        setListings(prev => prev.map(l => l.pub_ulid === existing.pub_ulid ? { ...l, status: newStatus } : l))
        const res = await fetch(`${API}/api/v1/dealer/publishing/${existing.pub_ulid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', ...authHeader() },
          body: JSON.stringify({ status: newStatus }),
        })
        if (!res.ok) {
          // Rollback
          setListings(prev => prev.map(l => l.pub_ulid === existing.pub_ulid ? { ...l, status: existing.status } : l))
        }
      }
    } catch { /* swallow */ }
    finally {
      setBusyCells(prev => { const s = new Set(prev); s.delete(key); return s })
    }
  }

  // ── Bulk publish selected platforms for all vehicles ───────────────────────

  async function bulkPublish() {
    if (selectedPlatforms.size === 0) return
    const platformIds = [...selectedPlatforms]
    const toPublish = filteredVehicles.filter(v =>
      platformIds.some(p => !getListing(v.crm_vehicle_ulid, p))
    )
    for (const vehicle of toPublish) {
      const platforms = platformIds.filter(p => !getListing(vehicle.crm_vehicle_ulid, p))
      if (platforms.length === 0) continue
      await fetch(`${API}/api/v1/dealer/publishing`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ crm_vehicle_ulid: vehicle.crm_vehicle_ulid, platforms }),
      })
    }
    await fetchListings()
    setSelectedPlatforms(new Set())
  }

  // ── Download handler ────────────────────────────────────────────────────────

  async function handleDownload(p: typeof PLATFORMS[number]) {
    if (!p.export) return
    setDownloadError(null)
    try { await downloadFile(p.export.url, p.export.filename) }
    catch { setDownloadError(`Error descargando ${p.label}`) }
  }

  async function copyFeedURL() {
    const url = `${API}/api/v1/dealer/publishing/feed/autoscout24.xml`
    await navigator.clipboard.writeText(url)
    setFeedUrlCopied(true)
    setTimeout(() => setFeedUrlCopied(false), 1800)
  }

  // ── Stats ──────────────────────────────────────────────────────────────────

  const totalActive = listings.filter(l => l.status === 'ACTIVE').length
  const totalPending = listings.filter(l => l.status === 'PENDING').length
  const totalDraft = listings.filter(l => l.status === 'DRAFT').length
  const reachM = PLATFORMS.filter(p => listings.some(l => l.platform === p.id && l.status === 'ACTIVE'))
    .reduce((acc, p) => acc + parseFloat(p.reach) || 0, 0)

  // ── Filtered vehicles ─────────────────────────────────────────────────────

  const filteredVehicles = vehicles.filter(v => {
    if (lifecycleFilter === 'SELLABLE') return ['READY', 'LISTED', 'RECONDITIONING'].includes(v.lifecycle_status)
    if (lifecycleFilter === 'ALL') return true
    return v.lifecycle_status === lifecycleFilter
  })

  // ── Gap analysis ──────────────────────────────────────────────────────────

  const unpublishedCount = filteredVehicles.filter(v =>
    !listings.some(l => l.crm_vehicle_ulid === v.crm_vehicle_ulid && l.status === 'ACTIVE')
  ).length

  const loading = loadingVehicles || loadingListings

  return (
    <div className="mx-auto max-w-screen-2xl space-y-6">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Multipublicación</h1>
          <p className="mt-1 text-sm text-surface-muted">
            Publica tu flota en todos los portales europeos desde una sola pantalla
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Feed URL copy */}
          <button
            onClick={copyFeedURL}
            className="flex items-center gap-2 rounded-lg border border-surface-border px-3 py-2 text-xs text-surface-muted hover:border-blue-500/50 hover:text-blue-400 transition"
          >
            {feedUrlCopied ? (
              <>
                <svg className="h-3.5 w-3.5 text-emerald-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/>
                </svg>
                <span className="text-emerald-400">URL copiada</span>
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/>
                </svg>
                Copiar URL Feed AS24
              </>
            )}
          </button>
          <button
            onClick={() => handleDownload(PLATFORMS[0])}
            className="flex items-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-xs text-blue-400 hover:bg-blue-500/10 transition"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            Descargar XML AS24
          </button>
          {selectedPlatforms.size > 0 && (
            <button
              onClick={bulkPublish}
              className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-600 transition"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/>
              </svg>
              Publicar en {selectedPlatforms.size} portales
            </button>
          )}
        </div>
      </div>

      {/* ── KPI bar ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Anuncios activos',  value: totalActive,  color: 'text-emerald-400' },
          { label: 'Pendientes',        value: totalPending, color: 'text-yellow-400' },
          { label: 'Borradores',        value: totalDraft,   color: 'text-surface-muted' },
          { label: 'Alcance estimado',  value: `${reachM.toFixed(1)}M`, color: 'text-brand-400', sub: 'visitas/mes' },
        ].map(kpi => (
          <div key={kpi.label} className="rounded-xl border border-surface-border bg-surface px-5 py-4">
            <div className="text-xs text-surface-muted">{kpi.label}</div>
            <div className={`mt-1 text-2xl font-bold ${kpi.color}`}>{kpi.value}</div>
            {'sub' in kpi && <div className="text-xs text-surface-muted">{kpi.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── Gap alert ── */}
      {unpublishedCount > 0 && !loading && (
        <div className="flex items-start gap-4 rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-5 py-4">
          <svg className="mt-0.5 h-5 w-5 shrink-0 text-yellow-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          </svg>
          <div className="flex-1">
            <div className="text-sm font-semibold text-yellow-400">
              {unpublishedCount} vehículo{unpublishedCount !== 1 ? 's' : ''} sin ningún anuncio activo
            </div>
            <div className="mt-0.5 text-xs text-surface-muted">
              Selecciona portales abajo y usa "Publicar en X portales" para rellenar los huecos de un golpe.
            </div>
          </div>
        </div>
      )}

      {/* ── Platform quick-select + export bar ── */}
      <div className="overflow-x-auto">
        <div className="flex gap-2 pb-1" style={{ minWidth: 'max-content' }}>
          {PLATFORMS.map(p => {
            const activeCount = listings.filter(l => l.platform === p.id && l.status === 'ACTIVE').length
            const sel = selectedPlatforms.has(p.id)
            return (
              <div
                key={p.id}
                className={`group flex flex-col gap-1.5 rounded-xl border px-3 py-3 transition cursor-pointer ${
                  sel ? 'border-brand-500/60 bg-brand-500/10' : 'border-surface-border bg-surface hover:border-surface-muted/60'
                }`}
                style={{ minWidth: '120px' }}
                onClick={() => setSelectedPlatforms(prev => {
                  const n = new Set(prev)
                  n.has(p.id) ? n.delete(p.id) : n.add(p.id)
                  return n
                })}
              >
                <div className="flex items-start justify-between">
                  <span className={`text-xs font-semibold ${sel ? 'text-brand-400' : p.textColor}`}>{p.label}</span>
                  {sel && (
                    <svg className="h-3.5 w-3.5 text-brand-400 shrink-0 ml-1" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/>
                    </svg>
                  )}
                </div>
                <div className="text-lg font-bold text-white">{activeCount}</div>
                <div className="text-[10px] text-surface-muted leading-tight">{p.reach} vis/mes</div>
                {p.export && (
                  <button
                    onClick={e => { e.stopPropagation(); handleDownload(p) }}
                    className={`mt-1 rounded px-2 py-0.5 text-[10px] font-medium ${p.textColor} border border-current/30 hover:bg-current/10 transition`}
                  >
                    ↓ {p.export.label}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {downloadError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {downloadError}
          <button onClick={() => setDownloadError(null)} className="ml-3 underline">Cerrar</button>
        </div>
      )}

      {/* ── Filter + legend ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <label className="text-xs text-surface-muted">Estado:</label>
          <select
            value={lifecycleFilter}
            onChange={e => setLifecycleFilter(e.target.value)}
            className="rounded-lg border border-surface-border bg-surface-dark px-3 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
          >
            <option value="SELLABLE">Vendibles (Ready + Listed + Recon)</option>
            <option value="ALL">Todos</option>
            <option value="READY">Ready</option>
            <option value="LISTED">Listed</option>
            <option value="RECONDITIONING">Reconditioning</option>
          </select>
        </div>
        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-surface-muted">
          {Object.entries(STATUS).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${v.dot}`} /> {v.label}
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="flex h-2 w-2 items-center justify-center rounded border border-surface-border/60 text-[8px] text-surface-muted/40">+</span>
            Sin publicar
          </span>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* ── Publication matrix ── */}
      {loading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-xl bg-surface-hover" />
          ))}
        </div>
      ) : filteredVehicles.length === 0 ? (
        <div className="rounded-xl border border-surface-border bg-surface py-16 text-center text-surface-muted">
          <div className="mb-2 text-3xl">🚗</div>
          <div className="text-sm">No hay vehículos con ese filtro.</div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border">
          <table className="w-full text-sm" style={{ minWidth: '800px' }}>
            <thead className="border-b border-surface-border bg-surface sticky top-0 z-10">
              <tr>
                <th className="w-64 px-4 py-3 text-left text-xs font-medium text-surface-muted">Vehículo</th>
                <th className="w-20 px-2 py-3 text-right text-xs font-medium text-surface-muted">Precio</th>
                <th className="w-16 px-2 py-3 text-right text-xs font-medium text-surface-muted">Km</th>
                {PLATFORMS.map(p => (
                  <th key={p.id} className="w-10 px-1 py-3 text-center">
                    <span className={`text-[10px] font-semibold ${selectedPlatforms.has(p.id) ? 'text-brand-400' : p.textColor}`}>
                      {p.label.slice(0, 4)}
                    </span>
                  </th>
                ))}
                <th className="w-16 px-2 py-3 text-center text-xs font-medium text-surface-muted">Cobertura</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-surface-border/50">
              {filteredVehicles.map(vehicle => {
                const vehicleListings = listings.filter(l => l.crm_vehicle_ulid === vehicle.crm_vehicle_ulid)
                const activeCount = vehicleListings.filter(l => l.status === 'ACTIVE').length
                const totalPortals = PLATFORMS.length

                return (
                  <tr key={vehicle.crm_vehicle_ulid} className="hover:bg-surface-hover/30 transition">
                    {/* Vehicle name */}
                    <td className="px-4 py-3">
                      <div className="font-medium text-white leading-tight">
                        {vehicle.make} {vehicle.model}{' '}
                        <span className="text-surface-muted font-normal">{vehicle.year}</span>
                      </div>
                      <div className="text-[10px] font-mono text-surface-muted/60 truncate" title={vehicle.crm_vehicle_ulid}>
                        {vehicle.crm_vehicle_ulid.slice(0, 16)}…
                      </div>
                    </td>

                    {/* Price */}
                    <td className="px-2 py-3 text-right font-mono text-xs text-white">
                      {vehicle.asking_price_eur > 0 ? fmtEUR(vehicle.asking_price_eur) : '—'}
                    </td>

                    {/* Mileage */}
                    <td className="px-2 py-3 text-right text-xs text-surface-muted">
                      {vehicle.mileage_km > 0 ? `${Math.round(vehicle.mileage_km / 1000)}k` : '—'}
                    </td>

                    {/* Platform cells */}
                    {PLATFORMS.map(platform => {
                      const listing = getListing(vehicle.crm_vehicle_ulid, platform.id)
                      const key = cellKey(vehicle.crm_vehicle_ulid, platform.id)
                      return (
                        <td key={platform.id} className="px-1 py-3 text-center">
                          <MatrixCell
                            vehicle={vehicle}
                            platform={platform}
                            listing={listing}
                            onToggle={toggleCell}
                            busy={busyCells.has(key)}
                          />
                        </td>
                      )
                    })}

                    {/* Coverage bar */}
                    <td className="px-2 py-3">
                      <div className="flex flex-col items-center gap-1">
                        <div className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-hover">
                          <div
                            className={`h-full rounded-full transition-all ${activeCount > 0 ? 'bg-emerald-400' : 'bg-surface-hover'}`}
                            style={{ width: `${(activeCount / totalPortals) * 100}%` }}
                          />
                        </div>
                        <span className="text-[10px] text-surface-muted tabular-nums">
                          {activeCount}/{totalPortals}
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Legend footer ── */}
      <div className="rounded-xl border border-surface-border/50 bg-surface/50 px-5 py-4">
        <div className="text-xs font-semibold text-surface-muted mb-2">Cómo usar la matriz</div>
        <div className="grid gap-2 text-xs text-surface-muted sm:grid-cols-3">
          <div>• <strong className="text-white">Clic en una celda vacía</strong> → publica el vehículo en ese portal (estado: Borrador)</div>
          <div>• <strong className="text-white">Clic en celda verde</strong> → pausa el anuncio</div>
          <div>• <strong className="text-white">Selecciona portales</strong> arriba + "Publicar en X portales" para publicación masiva</div>
        </div>
      </div>

    </div>
  )
}
