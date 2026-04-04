/**
 * CARDEX API client — typed wrappers for all REST endpoints.
 * Used from both Server Components (SSR) and Client Components (SWR).
 */

// SSR (server-side): use internal Docker hostname so container-to-container works.
// Browser (client-side): use the public URL accessible from the user's machine.
const API_BASE =
  typeof window === 'undefined'
    ? (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080')
    : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080')

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'unknown' }))
    throw new Error(err.error ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface SearchHit {
  vehicle_ulid: string
  make: string
  model: string
  variant?: string
  year: number
  mileage_km: number
  price_eur: number
  fuel_type?: string
  transmission?: string
  color?: string
  source_country: string
  source_url: string
  thumbnail_url?: string
  listing_status: string
}

export interface SearchResponse {
  hits: SearchHit[]
  total_hits: number
  page: number
  total_pages: number
  facet_distribution: Record<string, Record<string, number>>
  processing_time_ms: number
}

export interface SearchParams {
  q?: string
  make?: string
  model?: string
  year_min?: number
  year_max?: number
  price_min?: number
  price_max?: number
  mileage_max?: number
  fuel?: string
  tx?: string
  country?: string
  sort?: string
  page?: number
  per_page?: number
}

export interface PriceCandle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  avg_dom: number
}

export interface MarketDepthTier {
  price_tier_eur: number
  count: number
  avg_mileage_km: number
}

export interface HexPoint {
  hex_id: string
  count: number
  avg_price_eur: number
}

export interface VINEvent {
  event_type: string
  event_date: string
  mileage_km?: number
  country?: string
  source_platform?: string
  price_eur?: number
  description?: string
  confidence: number
}

export interface VINReport {
  vin: string
  events: VINEvent[]
  event_count: number
  summary: {
    first_seen_date?: string
    last_seen_date?: string
    ownership_changes: number
    accident_records: number
    import_records: number
    times_listed: number
    min_mileage_km?: number
    max_mileage_km?: number
    countries_seen_in: string[]
    price_history_eur: number[]
  }
  mileage_ok: boolean
  mileage_warning: string
  stolen_status: string
  disclaimer: string
}

// VIN History v2 — enriched with NHTSA, Euro NCAP, forensic mileage

export interface VINSpec {
  make: string
  model: string
  year: number
  body_type: string
  fuel_type: string
  engine_displacement_l: number
  engine_cylinders: number
  engine_kw: number
  transmission: string
  country_of_manufacture: string
}

export interface VINRecall {
  campaign: string
  component: string
  summary: string
  remedy: string
  date: string
}

export interface VINSafety {
  ncap_stars: number
  ncap_adult_pct: number
  ncap_child_pct: number
  ncap_pedestrian_pct: number
  ncap_safety_assist_pct: number
  ncap_test_year: number
  recall_count: number
  recalls: VINRecall[]
}

export interface VINHistory {
  events: VINEvent[]
  event_count: number
  mileage_ok: boolean
  mileage_warning: string
  forensic_max_km: number
  forensic_sources: string[]
  first_seen: string
  last_seen: string
}

export interface VINReportV2 {
  vin: string
  spec: VINSpec | null
  safety: VINSafety
  history: VINHistory
  summary: {
    first_seen_date?: string
    last_seen_date?: string
    ownership_changes: number
    accident_records: number
    import_records: number
    times_listed: number
    min_mileage_km?: number
    max_mileage_km?: number
    countries_seen_in: string[]
    price_history_eur: number[]
  }
  stolen_status: string
  data_sources: string[]
  report_generated_at: string
  disclaimer: string
}

export interface InventoryItem {
  inventory_ulid: string
  vin?: string
  make: string
  model: string
  variant?: string
  year: number
  mileage_km: number
  fuel_type?: string
  transmission?: string
  color?: string
  price_eur: number
  listing_status: string
  photo_urls: string[]
  platform_ids: Record<string, string>
  marketing_score?: number
  created_at: string
  updated_at: string
}

export interface SDIScore {
  vehicle_ulid: string
  sdi_score: number
  sdi_label: 'STABLE' | 'NEGOTIABLE' | 'MOTIVATED_SELLER' | 'PANIC_SELLER'
  sdi_flags: string[]
  price_drop_count: number
  days_on_market: number
  current_price_eur: number
  last_price_eur: number
}

// ── Public marketplace ───────────────────────────────────────────────────────

export function searchListings(params: SearchParams): Promise<SearchResponse> {
  const qs = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => [k, String(v)])
  ).toString()
  return apiFetch<SearchResponse>(`/api/v1/marketplace/search?${qs}`, {
    next: { revalidate: 30 },
  })
}

export function getListing(ulid: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/marketplace/listing/${ulid}`, {
    next: { revalidate: 60 },
  })
}

// ── Analytics ────────────────────────────────────────────────────────────────

export function getPriceIndex(params: { make?: string; model?: string; country?: string; interval?: string }) {
  const qs = new URLSearchParams(params as Record<string, string>).toString()
  return apiFetch<{ series: PriceCandle[] }>(`/api/v1/analytics/price-index?${qs}`, {
    next: { revalidate: 3600 },
  })
}

export function getMarketDepth(params: { make?: string; model?: string; country?: string }) {
  const qs = new URLSearchParams(params as Record<string, string>).toString()
  return apiFetch<{ depth: MarketDepthTier[] }>(`/api/v1/analytics/market-depth?${qs}`)
}

export function getHeatmap(params: { make?: string; country?: string; resolution?: number }) {
  const qs = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)])
  ).toString()
  return apiFetch<{ hexes: HexPoint[] }>(`/api/v1/analytics/heatmap?${qs}`)
}

// ── VIN History ──────────────────────────────────────────────────────────────

export function getVINReport(vin: string) {
  return apiFetch<VINReportV2>(`/api/v1/vin/${vin.toUpperCase()}`, {
    next: { revalidate: 86400 },
  })
}

// ── Dealer SaaS (requires JWT in Authorization header) ───────────────────────

export function getInventory(token: string, params?: { status?: string; page?: number }) {
  const qs = new URLSearchParams(params as Record<string, string>).toString()
  return apiFetch<{ items: InventoryItem[] }>(`/api/v1/dealer/inventory?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function createInventoryItem(token: string, body: Partial<InventoryItem>) {
  return apiFetch<{ inventory_ulid: string }>('/api/v1/dealer/inventory', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
}

export function getLeads(token: string, status?: string) {
  const qs = status ? `?status=${status}` : ''
  return apiFetch<{ leads: unknown[] }>(`/api/v1/dealer/leads${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getPricingIntelligence(token: string, inventoryULID: string) {
  return apiFetch<Record<string, unknown>>(`/api/v1/dealer/pricing/${inventoryULID}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export function getSDIScore(vehicleULID: string) {
  return apiFetch<SDIScore>(`/api/v1/dealer/sdi/${vehicleULID}`)
}
