'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, RefreshCw, Star, Camera, FileText, TrendingUp, Clock, AlertCircle } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080'

function useToken() {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('cardex_token')
}

interface AuditData {
  audit_ulid: string
  overall_score: number
  photo_score: number | null
  description_score: number | null
  pricing_score: number | null
  response_time_score: number | null
  recommendations: string | null
  created_at: string
}

async function getAudit(token: string): Promise<AuditData | null> {
  const res = await fetch(`${API_BASE}/api/v1/dealer/audit`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  if (!res.ok) return null
  return res.json()
}

async function triggerAudit(token: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/dealer/audit/trigger`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
}

function ScoreRing({ score, label, icon: Icon, max = 100 }: {
  score: number | null; label: string; icon: React.FC<{ size?: number; className?: string }>; max?: number
}) {
  const pct = score != null ? Math.round((score / max) * 100) : 0
  const color = pct >= 75 ? 'text-green-400' : pct >= 50 ? 'text-yellow-400' : 'text-brand-400'
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-surface-border bg-surface-card p-5 text-center">
      <Icon size={20} className="text-surface-muted" />
      <p className={`font-mono text-3xl font-bold ${color}`}>{score ?? '—'}</p>
      <p className="text-xs text-surface-muted">{label}</p>
      <div className="h-1 w-full overflow-hidden rounded-full bg-surface-hover">
        <div className={`h-full rounded-full transition-all ${pct >= 75 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-500' : 'bg-brand-500'}`}
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function MarketingAuditPage() {
  const token = useToken()
  const [audit, setAudit] = useState<AuditData | null>(null)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [triggered, setTriggered] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) { setLoading(false); return }
    getAudit(token)
      .then(setAudit)
      .catch(() => setError('Failed to load audit'))
      .finally(() => setLoading(false))
  }, [token])

  async function handleTrigger() {
    if (!token) return
    setTriggering(true)
    await triggerAudit(token).catch(() => null)
    setTriggering(false)
    setTriggered(true)
  }

  if (!token) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <p className="text-surface-muted">Please log in to view your marketing audit.</p>
        <Link href="/dashboard/login" className="rounded-lg bg-brand-500 px-5 py-2 text-sm font-medium text-white hover:bg-brand-600">
          Login
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <Link href="/dashboard" className="flex items-center gap-1.5 text-sm text-surface-muted hover:text-white">
          <ArrowLeft size={14} /> Dashboard
        </Link>
        <button
          onClick={handleTrigger}
          disabled={triggering}
          className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2 text-sm text-surface-muted hover:text-white hover:border-brand-500/50 transition-all disabled:opacity-50"
        >
          <RefreshCw size={14} className={triggering ? 'animate-spin' : ''} />
          {triggering ? 'Running…' : 'Run new audit'}
        </button>
      </div>

      <h1 className="mb-2 text-2xl font-bold text-white">Marketing Audit</h1>
      <p className="mb-6 text-sm text-surface-muted">
        AI-powered analysis of your listings: photos, descriptions, pricing, and response times.
      </p>

      {triggered && (
        <div className="mb-5 rounded-xl border border-green-500/30 bg-green-500/10 px-5 py-4 text-sm text-green-400">
          Audit started. Results will appear here in ~5 minutes.
        </div>
      )}

      {loading && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-8 text-center text-surface-muted">
          Loading audit data…
        </div>
      )}

      {error && !audit && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-8 text-center">
          <AlertCircle size={32} className="mx-auto mb-3 text-surface-muted" />
          <p className="text-surface-muted">No audit available yet.</p>
          <p className="mt-1 text-sm text-surface-muted">Click "Run new audit" to analyse your listings.</p>
        </div>
      )}

      {audit && (
        <div className="space-y-5">
          {/* Overall score */}
          <div className="flex items-center gap-5 rounded-2xl border border-surface-border bg-surface-card p-6">
            <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-4 border-brand-500">
              <span className="font-mono text-2xl font-bold text-brand-400">{audit.overall_score}</span>
              <span className="absolute bottom-3 text-[9px] text-surface-muted">/100</span>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {audit.overall_score >= 75 ? 'Looking great!' : audit.overall_score >= 50 ? 'Room to improve' : 'Needs attention'}
              </h2>
              <p className="text-sm text-surface-muted">Overall marketing score</p>
              <p className="mt-1 text-xs text-surface-muted">Analysed {new Date(audit.created_at).toLocaleDateString('en-GB')}</p>
            </div>
          </div>

          {/* Category scores */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ScoreRing score={audit.photo_score} label="Photos" icon={Camera} />
            <ScoreRing score={audit.description_score} label="Description" icon={FileText} />
            <ScoreRing score={audit.pricing_score} label="Pricing" icon={TrendingUp} />
            <ScoreRing score={audit.response_time_score} label="Response time" icon={Clock} />
          </div>

          {/* Recommendations */}
          {audit.recommendations && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-surface-muted">
                <Star size={14} />
                Recommendations
              </h2>
              <div className="space-y-2">
                {audit.recommendations.split('\n').filter(Boolean).map((line, i) => (
                  <p key={i} className="text-sm text-surface-muted leading-relaxed">
                    {line.startsWith('-') || line.startsWith('•') ? (
                      <><span className="text-brand-400 mr-2">·</span>{line.slice(1).trim()}</>
                    ) : line}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Benchmark */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-5">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-surface-muted">Industry benchmark</h2>
            <div className="space-y-2 text-sm">
              {[
                { label: 'Top 10% dealers score', value: '85+' },
                { label: 'Average dealer score', value: '62' },
                { label: 'Your percentile', value: audit.overall_score >= 85 ? 'Top 10%' : audit.overall_score >= 62 ? 'Above average' : 'Below average' },
              ].map(({ label, value }) => (
                <div key={label} className="flex justify-between">
                  <span className="text-surface-muted">{label}</span>
                  <span className="font-medium text-white">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
