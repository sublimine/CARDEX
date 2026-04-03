'use client'

import { Fragment, useCallback, useEffect, useRef, useState } from 'react'

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:     '#0a0a0a',
  panel:  '#111111',
  border: '#1a1a1a',
  text:   '#cccccc',
  dim:    '#666666',
  green:  '#00ff41',
  amber:  '#ffaa00',
  red:    '#ff4444',
  blue:   '#00aaff',
  white:  '#ffffff',
} as const

// ── API types ─────────────────────────────────────────────────────────────────
interface ArbitrageOpportunity {
  opportunity_id:      string
  scanned_at:          string
  opportunity_type:    string
  make:                string
  model:               string
  year:                number
  fuel_type:           string
  origin_country:      string
  dest_country:        string
  origin_median_eur:   number
  dest_median_eur:     number
  nlc_estimate_eur:    number
  gross_margin_eur:    number
  margin_pct:          number
  confidence_score:    number
  sample_size_origin:  number
  sample_size_dest:    number
  co2_gkm:             number
  bpm_refund_eur:      number
  iedmt_eur:           number
  malus_eur:           number
  example_listing_url: string
  status:              string
}

interface RouteStats {
  route_key:         string
  origin_country:    string
  dest_country:      string
  make:              string
  model_family:      string
  fuel_type:         string
  avg_margin_eur:    number
  avg_margin_pct:    number
  opportunity_count: number
  avg_confidence:    number
  last_updated:      string
}

// ── Constants ─────────────────────────────────────────────────────────────────
const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

const OPP_TYPES = ['ALL', 'PRICE_DIFF', 'BPM_EXPORT', 'EV_SUBSIDY', 'SEASONAL', 'DISTRESSED', 'CLASSIC']
const COUNTRIES = ['ALL', 'DE', 'NL', 'FR', 'ES', 'BE', 'CH']

const COUNTRY_FLAG: Record<string, string> = {
  DE: '🇩🇪', NL: '🇳🇱', FR: '🇫🇷', ES: '🇪🇸', BE: '🇧🇪', CH: '🇨🇭',
}

const SORT_COLS = [
  { key: 'margin_eur', label: 'MARGIN €' },
  { key: 'margin_pct', label: 'MARGIN %' },
  { key: 'confidence', label: 'CONF' },
  { key: 'scanned_at', label: 'TIME' },
] as const

type SortKey = typeof SORT_COLS[number]['key']

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtEur(n: number): string {
  return '€' + Math.round(n).toLocaleString('de-DE')
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return sign + n.toFixed(1) + '%'
}

/** Renders 5 Unicode blocks representing confidence 0–1 */
function confidenceBlocks(score: number): string {
  const filled = Math.round(score * 5)
  return '█'.repeat(filled) + '░'.repeat(5 - filled)
}

function confidenceColor(score: number): string {
  if (score >= 0.8) return C.green
  if (score >= 0.6) return C.amber
  return C.red
}

function marginColor(pct: number): string {
  if (pct >= 15) return C.green
  if (pct >= 8)  return '#88ff88'
  if (pct >= 3)  return C.amber
  return C.red
}

function routeLabel(origin: string, dest: string, type?: string): string {
  const flag = (cc: string) => COUNTRY_FLAG[cc] ?? cc
  let label = `${flag(origin)}→${flag(dest)}`
  if (type === 'BPM_EXPORT') label += ' (BPM)'
  if (type === 'EV_SUBSIDY') label += ' (EV)'
  if (type === 'SEASONAL')   label += ' (SEAS)'
  return label
}

function recommendation(pct: number): { label: string; color: string } {
  if (pct >= 15) return { label: 'STRONG BUY', color: C.green }
  if (pct >= 8)  return { label: 'VIABLE',     color: '#88ff88' }
  if (pct >= 3)  return { label: 'MARGINAL',   color: C.amber }
  return { label: 'AVOID', color: C.red }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FilterButton({
  active, label, onClick,
}: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background:   active ? C.blue : 'transparent',
        color:        active ? C.bg   : C.dim,
        border:       `1px solid ${active ? C.blue : C.border}`,
        padding:      '2px 8px',
        fontSize:     11,
        fontFamily:   'inherit',
        cursor:       'pointer',
        letterSpacing: '0.05em',
        transition:   'all 0.1s',
      }}
    >
      {label}
    </button>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      background:   C.panel,
      borderBottom: `1px solid ${C.border}`,
      borderTop:    `1px solid ${C.border}`,
      padding:      '4px 12px',
      fontSize:     11,
      color:        C.blue,
      letterSpacing: '0.1em',
      fontWeight:   700,
    }}>
      {children}
    </div>
  )
}

function LoadingBar() {
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setPhase(p => (p + 1) % 8), 150)
    return () => clearInterval(id)
  }, [])
  const bars = '████████'.slice(0, phase) + '░░░░░░░░'.slice(phase)
  return (
    <div style={{ padding: '24px 16px', color: C.amber, fontSize: 13, textAlign: 'center' }}>
      FETCHING DATA {bars}
    </div>
  )
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  const [countdown, setCountdown] = useState(5)
  useEffect(() => {
    if (countdown <= 0) { onRetry(); return }
    const id = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(id)
  }, [countdown, onRetry])
  return (
    <div style={{ padding: '24px 16px', color: C.red, fontSize: 12, textAlign: 'center' }}>
      ERROR: {message.toUpperCase()} | RETRY [{countdown}s]
    </div>
  )
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DetailPanel({
  opp, onBook, authToken,
}: {
  opp: ArbitrageOpportunity
  onBook: (id: string) => void
  authToken: string | null
}) {
  const rec = recommendation(opp.margin_pct)
  const rows: [string, string, string?][] = [
    ['Origin (' + opp.origin_country + ') median:', fmtEur(opp.origin_median_eur), `n=${opp.sample_size_origin}`],
    ['Destination (' + opp.dest_country + ') median:', fmtEur(opp.dest_median_eur), `n=${opp.sample_size_dest}`],
  ]
  const nlcRows: [string, string][] = [
    ['Transport ' + opp.origin_country + '→' + opp.dest_country + ':', fmtEur(opp.nlc_estimate_eur - opp.iedmt_eur - opp.bpm_refund_eur - opp.malus_eur)],
  ]
  if (opp.iedmt_eur > 0) nlcRows.push([`IEDMT (ES, ${((opp.iedmt_eur / (opp.origin_median_eur || 1)) * 100).toFixed(2)}%):`, fmtEur(opp.iedmt_eur)])
  if (opp.bpm_refund_eur > 0) nlcRows.push(['BPM Refund (NL):', '+' + fmtEur(opp.bpm_refund_eur)])
  if (opp.malus_eur > 0) nlcRows.push(['Malus (FR):', fmtEur(opp.malus_eur)])
  nlcRows.push(['Total NLC:', fmtEur(opp.nlc_estimate_eur)])

  return (
    <div style={{
      borderTop:  `1px solid ${C.border}`,
      background: '#0d0d0d',
      padding:    '12px 16px',
      fontSize:   12,
    }}>
      <div style={{ color: C.white, fontSize: 13, marginBottom: 8 }}>
        {opp.make.toUpperCase()} {opp.model.toUpperCase()} {opp.year}
        {' · '}
        {COUNTRY_FLAG[opp.origin_country] ?? opp.origin_country}→{COUNTRY_FLAG[opp.dest_country] ?? opp.dest_country}
        {' · '}
        <span style={{ color: C.dim }}>{opp.opportunity_type}</span>
      </div>
      <div style={{ borderBottom: `1px solid ${C.border}`, marginBottom: 8, paddingBottom: 8 }}>
        {rows.map(([label, value, note]) => (
          <div key={label} style={{ display: 'flex', gap: 8, marginBottom: 2 }}>
            <span style={{ color: C.dim, minWidth: 260 }}>{label}</span>
            <span style={{ color: C.text }}>{value}</span>
            {note && <span style={{ color: C.dim }}>{note}</span>}
          </div>
        ))}
      </div>
      <div style={{ color: C.dim, fontSize: 11, marginBottom: 4 }}>NLC BREAKDOWN:</div>
      <div style={{ marginBottom: 8 }}>
        {nlcRows.map(([label, value]) => (
          <div key={label} style={{ display: 'flex', gap: 8, marginBottom: 2, paddingLeft: 8 }}>
            <span style={{ color: C.dim, minWidth: 252 }}>{label}</span>
            <span style={{ color: C.amber }}>{value}</span>
          </div>
        ))}
      </div>
      <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 8, display: 'flex', alignItems: 'center', gap: 24 }}>
        <div>
          <span style={{ color: C.dim }}>GROSS MARGIN:</span>
          {' '}
          <span style={{ color: marginColor(opp.margin_pct), fontWeight: 700, fontSize: 14 }}>
            {fmtEur(opp.gross_margin_eur)}
          </span>
          {' '}
          <span style={{ color: marginColor(opp.margin_pct) }}>({fmtPct(opp.margin_pct)})</span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          <span style={{ color: rec.color, fontWeight: 700, fontSize: 11 }}>▸ {rec.label}</span>
          {opp.co2_gkm > 0 && (
            <span style={{ color: C.dim, fontSize: 11 }}>CO₂: {opp.co2_gkm}g/km</span>
          )}
          {opp.example_listing_url && (
            <a
              href={opp.example_listing_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: C.blue, fontSize: 11, textDecoration: 'none' }}
            >
              [VIEW LISTING →]
            </a>
          )}
          <button
            onClick={() => {
              if (!authToken) {
                alert('Please log in to book opportunities.')
                return
              }
              onBook(opp.opportunity_id)
            }}
            style={{
              background:    C.green,
              color:         C.bg,
              border:        'none',
              padding:       '4px 14px',
              fontSize:      11,
              fontFamily:    'inherit',
              fontWeight:    700,
              cursor:        'pointer',
              letterSpacing: '0.05em',
            }}
          >
            BOOK IT →
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ArbitragePage() {
  // Clock
  const [clock, setClock] = useState('')
  useEffect(() => {
    const tick = () => setClock(new Date().toISOString().replace('T', ' ').slice(0, 19))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // Refresh countdown
  const REFRESH_INTERVAL = 60
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [refreshTick, setRefreshTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) {
          setRefreshTick(t => t + 1)
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [])

  // Filters
  const [selectedType,   setSelectedType]   = useState('ALL')
  const [selectedOrigin, setSelectedOrigin] = useState('ALL')
  const [selectedDest,   setSelectedDest]   = useState('ALL')
  const [minMargin,      setMinMargin]       = useState('')
  const [sortKey,        setSortKey]         = useState<SortKey>('margin_eur')
  const [sortDir,        setSortDir]         = useState<'asc' | 'desc'>('desc')

  // Data
  const [opportunities, setOpportunities] = useState<ArbitrageOpportunity[]>([])
  const [routes,        setRoutes]         = useState<RouteStats[]>([])
  const [loading,       setLoading]        = useState(true)
  const [error,         setError]          = useState<string | null>(null)
  const [loadingRoutes, setLoadingRoutes]  = useState(true)

  // Detail expansion
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Auth (read token from localStorage)
  const [authToken, setAuthToken] = useState<string | null>(null)
  useEffect(() => {
    setAuthToken(localStorage.getItem('cardex_token'))
  }, [])

  // Booked state
  const [bookedIds, setBookedIds] = useState<Set<string>>(new Set())

  // Fetch opportunities
  const fetchOpps = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (selectedType !== 'ALL') params.set('type', selectedType)
      if (selectedOrigin !== 'ALL') params.set('origin', selectedOrigin)
      if (selectedDest !== 'ALL') params.set('dest', selectedDest)
      if (minMargin.trim()) params.set('min_margin', minMargin.trim())
      params.set('sort', sortKey)
      params.set('limit', '50')
      const url = `${API_BASE}/api/v1/arbitrage/opportunities?${params}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      let opps: ArbitrageOpportunity[] = data.opportunities ?? []
      // client-side sort direction (API always returns DESC, we may want ASC)
      if (sortDir === 'asc') opps = [...opps].reverse()
      setOpportunities(opps)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'CONNECTION REFUSED')
    } finally {
      setLoading(false)
    }
  }, [selectedType, selectedOrigin, selectedDest, minMargin, sortKey, sortDir])

  // Fetch route stats
  const fetchRoutes = useCallback(async () => {
    setLoadingRoutes(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/arbitrage/routes`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setRoutes(data.routes ?? [])
    } catch {
      // Routes panel gracefully degrades
    } finally {
      setLoadingRoutes(false)
    }
  }, [])

  useEffect(() => {
    fetchOpps()
    fetchRoutes()
  }, [fetchOpps, fetchRoutes, refreshTick])

  // Column sort handler
  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  // Book handler
  const handleBook = async (opportunityId: string) => {
    if (!authToken) return
    try {
      const res = await fetch(`${API_BASE}/api/v1/arbitrage/book/${opportunityId}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (res.ok) {
        setBookedIds(prev => new Set([...prev, opportunityId]))
      } else {
        const data = await res.json().catch(() => ({}))
        alert('BOOKING FAILED: ' + (data.message ?? res.status))
      }
    } catch (e: unknown) {
      alert('BOOKING ERROR: ' + (e instanceof Error ? e.message : 'unknown'))
    }
  }

  const baseStyle: React.CSSProperties = {
    fontFamily: "inherit",
    fontSize:   12,
    color:      C.text,
  }

  return (
    <div style={{ ...baseStyle, minHeight: '100vh', background: C.bg }}>

      {/* ── Header bar ── */}
      <div style={{
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'space-between',
        background:     C.panel,
        borderBottom:   `2px solid ${C.blue}`,
        padding:        '6px 14px',
        height:         36,
      }}>
        <span style={{ color: C.white, fontWeight: 700, fontSize: 13, letterSpacing: '0.1em' }}>
          CARDEX ARBITRAGE INTELLIGENCE
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11 }}>
          <span style={{ color: C.green }}>
            ● LIVE
          </span>
          <span style={{ color: C.dim }}>
            {clock}
          </span>
          <span style={{ color: C.amber }}>
            REFRESH IN {String(countdown).padStart(2, '0')}s
          </span>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div style={{
        background:   C.panel,
        borderBottom: `1px solid ${C.border}`,
        padding:      '6px 14px',
        display:      'flex',
        flexWrap:     'wrap',
        gap:          '6px 12px',
        alignItems:   'center',
      }}>
        {/* Type filters */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {OPP_TYPES.map(t => (
            <FilterButton
              key={t}
              active={selectedType === t}
              label={t === 'ALL' ? 'ALL' : t.replace('_', ' ')}
              onClick={() => setSelectedType(t)}
            />
          ))}
        </div>

        {/* Separator */}
        <span style={{ color: C.border, fontSize: 16 }}>│</span>

        {/* Origin filter */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ color: C.dim, fontSize: 11 }}>ORIGIN:</span>
          {COUNTRIES.map(c => (
            <FilterButton
              key={'o-' + c}
              active={selectedOrigin === c}
              label={c === 'ALL' ? 'ALL' : (COUNTRY_FLAG[c] ?? '') + ' ' + c}
              onClick={() => setSelectedOrigin(c)}
            />
          ))}
        </div>

        {/* Dest filter */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ color: C.dim, fontSize: 11 }}>DEST:</span>
          {COUNTRIES.map(c => (
            <FilterButton
              key={'d-' + c}
              active={selectedDest === c}
              label={c === 'ALL' ? 'ALL' : (COUNTRY_FLAG[c] ?? '') + ' ' + c}
              onClick={() => setSelectedDest(c)}
            />
          ))}
        </div>

        {/* Min margin */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ color: C.dim, fontSize: 11 }}>MIN MARGIN €:</span>
          <input
            type="text"
            value={minMargin}
            onChange={e => setMinMargin(e.target.value)}
            placeholder="0"
            style={{
              width:      70,
              background: '#0d0d0d',
              border:     `1px solid ${C.border}`,
              color:      C.text,
              fontFamily: 'inherit',
              fontSize:   11,
              padding:    '2px 6px',
              outline:    'none',
            }}
          />
        </div>
      </div>

      {/* ── Opportunities table ── */}
      <SectionHeader>
        ACTIVE OPPORTUNITIES
        {!loading && !error && (
          <span style={{ color: C.dim, fontWeight: 400 }}>
            {'  '}[{opportunities.length} result{opportunities.length !== 1 ? 's' : ''}]
          </span>
        )}
      </SectionHeader>

      {loading ? (
        <LoadingBar />
      ) : error ? (
        <ErrorPanel message={error} onRetry={fetchOpps} />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{
            width:           '100%',
            borderCollapse:  'collapse',
            fontSize:        12,
          }}>
            <thead>
              <tr style={{ background: '#0d0d0d', borderBottom: `1px solid ${C.border}` }}>
                {[
                  { label: 'ROUTE',            key: null          },
                  { label: 'MAKE / MODEL',      key: null          },
                  { label: 'TYPE',              key: null          },
                  { label: 'ORIGIN €',          key: null          },
                  { label: 'DEST €',            key: null          },
                  { label: 'NLC €',             key: null          },
                  { label: 'MARGIN €',          key: 'margin_eur'  },
                  { label: 'MARGIN %',          key: 'margin_pct'  },
                  { label: 'CONF',              key: 'confidence'  },
                  { label: 'SCANNED',           key: 'scanned_at'  },
                ].map(col => (
                  <th
                    key={col.label}
                    onClick={col.key ? () => handleSort(col.key as SortKey) : undefined}
                    style={{
                      padding:       '5px 10px',
                      textAlign:     'left',
                      color:         col.key === sortKey ? C.blue : C.dim,
                      fontSize:      10,
                      letterSpacing: '0.08em',
                      fontWeight:    600,
                      cursor:        col.key ? 'pointer' : 'default',
                      userSelect:    'none',
                      whiteSpace:    'nowrap',
                      borderRight:   `1px solid ${C.border}`,
                    }}
                  >
                    {col.label}
                    {col.key === sortKey && (
                      <span style={{ marginLeft: 4 }}>{sortDir === 'desc' ? '▼' : '▲'}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {opportunities.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ padding: 24, textAlign: 'center', color: C.dim }}>
                    NO OPPORTUNITIES MATCH CURRENT FILTERS
                  </td>
                </tr>
              ) : (
                opportunities.map(opp => {
                  const isExpanded = expandedId === opp.opportunity_id
                  const isBooked   = bookedIds.has(opp.opportunity_id) || opp.status === 'BOOKED'
                  return (
                    <>
                      <tr
                        key={opp.opportunity_id + '-row'}
                        onClick={() => setExpandedId(isExpanded ? null : opp.opportunity_id)}
                        style={{
                          background:    isExpanded ? '#0f1a0f' : (isBooked ? '#0a110a' : 'transparent'),
                          borderBottom:  `1px solid ${C.border}`,
                          cursor:        'pointer',
                          transition:    'background 0.1s',
                        }}
                        onMouseEnter={e => {
                          if (!isExpanded) (e.currentTarget as HTMLTableRowElement).style.background = '#141414'
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLTableRowElement).style.background =
                            isExpanded ? '#0f1a0f' : (isBooked ? '#0a110a' : 'transparent')
                        }}
                      >
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, whiteSpace: 'nowrap' }}>
                          {routeLabel(opp.origin_country, opp.dest_country, opp.opportunity_type)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, color: C.white }}>
                          {opp.make.toUpperCase()} {opp.model.toUpperCase()} {opp.year}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, color: C.dim, fontSize: 10 }}>
                          {opp.opportunity_type}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, textAlign: 'right', color: C.text }}>
                          {fmtEur(opp.origin_median_eur)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, textAlign: 'right', color: C.text }}>
                          {fmtEur(opp.dest_median_eur)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, textAlign: 'right', color: C.amber }}>
                          {fmtEur(opp.nlc_estimate_eur)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, textAlign: 'right', color: marginColor(opp.margin_pct), fontWeight: 700 }}>
                          {fmtEur(opp.gross_margin_eur)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, textAlign: 'right', color: marginColor(opp.margin_pct), fontWeight: 700 }}>
                          {fmtPct(opp.margin_pct)}
                        </td>
                        <td style={{ padding: '5px 10px', borderRight: `1px solid ${C.border}`, color: confidenceColor(opp.confidence_score), fontFamily: 'inherit' }}>
                          {confidenceBlocks(opp.confidence_score)}
                          <span style={{ color: C.dim, marginLeft: 4, fontSize: 10 }}>{opp.confidence_score.toFixed(2)}</span>
                        </td>
                        <td style={{ padding: '5px 10px', color: C.dim, fontSize: 10 }}>
                          {opp.scanned_at.slice(0, 16).replace('T', ' ')}
                          {isBooked && <span style={{ marginLeft: 6, color: C.green, fontSize: 10 }}>✓ BOOKED</span>}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={opp.opportunity_id + '-detail'}>
                          <td colSpan={10} style={{ padding: 0 }}>
                            <DetailPanel opp={opp} onBook={handleBook} authToken={authToken} />
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Bottom panels ── */}
      <div style={{
        display:       'grid',
        gridTemplateColumns: '1fr 1fr',
        borderTop:     `1px solid ${C.border}`,
        marginTop:     'auto',
      }}>

        {/* Top Routes panel */}
        <div style={{ borderRight: `1px solid ${C.border}` }}>
          <SectionHeader>TOP ROUTES — 30-DAY AVG</SectionHeader>
          <div style={{ padding: '8px 0' }}>
            {loadingRoutes ? (
              <div style={{ padding: '8px 12px', color: C.dim, fontSize: 11 }}>LOADING...</div>
            ) : routes.length === 0 ? (
              <div style={{ padding: '8px 12px', color: C.dim, fontSize: 11 }}>NO DATA</div>
            ) : (
              routes.slice(0, 8).map((r, i) => (
                <div
                  key={r.route_key}
                  style={{
                    display:       'flex',
                    alignItems:    'center',
                    padding:       '4px 12px',
                    borderBottom:  `1px solid ${C.border}`,
                    gap:           12,
                    fontSize:      11,
                  }}
                >
                  <span style={{ color: C.dim, minWidth: 18 }}>{i + 1}.</span>
                  <span style={{ color: C.text, flex: 1 }}>
                    {routeLabel(r.origin_country, r.dest_country)} {r.make} {r.model_family}
                  </span>
                  <span style={{ color: marginColor(r.avg_margin_pct), fontWeight: 700, minWidth: 60, textAlign: 'right' }}>
                    {fmtPct(r.avg_margin_pct)} avg
                  </span>
                  <span style={{ color: C.dim, minWidth: 50, textAlign: 'right' }}>
                    n={r.opportunity_count}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Booked positions panel */}
        <div>
          <SectionHeader>BOOKED POSITIONS</SectionHeader>
          <div style={{ padding: '12px 14px', fontSize: 11 }}>
            {!authToken ? (
              <span style={{ color: C.dim }}>LOG IN TO VIEW PORTFOLIO</span>
            ) : bookedIds.size === 0 ? (
              <span style={{ color: C.dim }}>NO ACTIVE POSITIONS</span>
            ) : (
              <div>
                <div style={{ color: C.green, marginBottom: 8 }}>
                  {bookedIds.size} ACTIVE POSITION{bookedIds.size !== 1 ? 'S' : ''}
                </div>
                {[...bookedIds].slice(0, 5).map(id => (
                  <div key={id} style={{ color: C.dim, marginBottom: 4 }}>
                    ▸ {id.slice(0, 16)}…
                    {' '}
                    <span style={{ color: C.green }}>● BOOKED</span>
                  </div>
                ))}
                {bookedIds.size > 5 && (
                  <div style={{ color: C.dim }}>+ {bookedIds.size - 5} more</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
