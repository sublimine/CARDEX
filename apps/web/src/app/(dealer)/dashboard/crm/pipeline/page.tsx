'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Deal {
  deal_ulid: string
  title: string
  contact_name: string
  vehicle_label: string
  deal_value_eur: number
  probability_pct: number
  days_since_last_comm: number
}

interface Stage {
  stage_ulid: string
  name: string
  color: string
  position: number
  is_won: boolean
  is_lost: boolean
  deal_count: number
  deals: Deal[]
}

interface PipelineData {
  stages: Stage[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatEur(value: number): string {
  return '€\u00a0' + value.toLocaleString('en-IE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('cardex_token') ?? ''
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

// ---------------------------------------------------------------------------
// Quick-Add Deal Modal
// ---------------------------------------------------------------------------
interface QuickAddModalProps {
  stageUlid: string
  stageName: string
  onClose: () => void
  onAdded: () => void
}

function QuickAddDealModal({ stageUlid, stageName, onClose, onAdded }: QuickAddModalProps) {
  const [title, setTitle] = useState('')
  const [contactSearch, setContactSearch] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/deals`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ title: title.trim(), contact_name: contactSearch.trim(), stage_ulid: stageUlid }),
      })
      if (!res.ok) throw new Error(`Error ${res.status}`)
      onAdded()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create deal')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-xl border border-surface-border bg-surface-card p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <h3 className="mb-4 font-semibold text-white">Add Deal — {stageName}</h3>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-surface-muted">Deal Title *</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. BMW 320d — Carlos M."
              required
              className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-surface-muted">Contact Name</label>
            <input
              type="text"
              value={contactSearch}
              onChange={e => setContactSearch(e.target.value)}
              placeholder="Search or type contact name"
              className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>
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
              disabled={saving || !title.trim()}
              className="flex-1 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
            >
              {saving ? 'Saving…' : 'Add Deal'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Deal Card
// ---------------------------------------------------------------------------
interface DealCardProps {
  deal: Deal
  onDragStart: (dealUlid: string) => void
}

function DealCard({ deal, onDragStart }: DealCardProps) {
  const stale = deal.days_since_last_comm > 7

  return (
    <div
      draggable
      onDragStart={() => onDragStart(deal.deal_ulid)}
      className="cursor-grab rounded-lg border border-surface-border bg-surface p-3 hover:border-brand-500/40 hover:bg-surface-hover transition-colors active:cursor-grabbing select-none"
    >
      {/* Contact + title */}
      <p className="font-semibold text-white text-sm leading-tight">{deal.contact_name}</p>
      <p className="mt-0.5 text-xs text-surface-muted truncate">{deal.title}</p>

      {/* Vehicle */}
      {deal.vehicle_label && (
        <p className="mt-1.5 truncate rounded bg-surface-hover px-2 py-0.5 text-xs text-surface-muted">
          {deal.vehicle_label}
        </p>
      )}

      {/* Value + probability */}
      <div className="mt-2 flex items-center justify-between">
        <span className="font-mono text-sm font-semibold text-white">{formatEur(deal.deal_value_eur)}</span>
        <span className="rounded-full bg-surface-hover px-2 py-0.5 font-mono text-xs text-surface-muted">
          {deal.probability_pct}%
        </span>
      </div>

      {/* Probability bar */}
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-hover">
        <div
          className="h-full rounded-full bg-brand-500"
          style={{ width: `${deal.probability_pct}%` }}
        />
      </div>

      {/* Last contact staleness */}
      <p className={`mt-2 text-xs ${stale ? 'text-red-400' : 'text-surface-muted'}`}>
        {deal.days_since_last_comm === 0
          ? 'Contacted today'
          : `${deal.days_since_last_comm}d since last contact`}
        {stale && ' ⚠'}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage Column
// ---------------------------------------------------------------------------
interface StageColumnProps {
  stage: Stage
  isDragOver: boolean
  onDragOver: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent) => void
  onDragLeave: () => void
  onDragStart: (dealUlid: string) => void
  onAddDeal: () => void
}

function StageColumn({ stage, isDragOver, onDragOver, onDrop, onDragLeave, onDragStart, onAddDeal }: StageColumnProps) {
  const totalValue = stage.deals.reduce((s, d) => s + d.deal_value_eur, 0)

  const borderClass = stage.is_won
    ? 'border-brand-500/60'
    : stage.is_lost
    ? 'border-red-500/60'
    : isDragOver
    ? 'border-brand-500/60'
    : 'border-surface-border'

  const headerClass = stage.is_won
    ? 'bg-brand-500/10'
    : stage.is_lost
    ? 'bg-red-500/10'
    : 'bg-surface-card'

  return (
    <div
      className={`flex flex-shrink-0 flex-col rounded-xl border ${borderClass} ${headerClass} transition-colors`}
      style={{ minWidth: 260, width: 260 }}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragLeave={onDragLeave}
    >
      {/* Column header */}
      <div className="flex items-center gap-2 border-b border-surface-border px-3 py-3">
        <span
          className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
          style={{ backgroundColor: stage.color || '#8b949e' }}
        />
        <span className="flex-1 truncate text-sm font-semibold text-white">{stage.name}</span>
        <span className="rounded-full bg-surface-hover px-2 py-0.5 font-mono text-xs text-surface-muted">
          {stage.deal_count}
        </span>
        <button
          onClick={onAddDeal}
          className="ml-1 flex h-6 w-6 items-center justify-center rounded text-surface-muted hover:bg-surface-hover hover:text-brand-400 transition-colors"
          title="Add deal"
        >
          +
        </button>
      </div>

      {/* Total value */}
      {totalValue > 0 && (
        <div className="border-b border-surface-border px-3 py-1.5">
          <span className="font-mono text-xs text-surface-muted">{formatEur(totalValue)}</span>
        </div>
      )}

      {/* Cards */}
      <div
        className={`flex flex-1 flex-col gap-2 overflow-y-auto p-2 transition-colors ${isDragOver ? 'bg-brand-500/5' : ''}`}
        style={{ minHeight: 80 }}
      >
        {stage.deals.length === 0 ? (
          <p className="py-6 text-center text-xs text-surface-muted">No deals</p>
        ) : (
          stage.deals.map(deal => (
            <DealCard key={deal.deal_ulid} deal={deal} onDragStart={onDragStart} />
          ))
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function PipelinePage() {
  const router = useRouter()
  const [stages, setStages] = useState<Stage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dragDealUlid, setDragDealUlid] = useState<string | null>(null)
  const [dragOverStage, setDragOverStage] = useState<string | null>(null)
  const [quickAddStage, setQuickAddStage] = useState<Stage | null>(null)
  const movingRef = useRef(false)

  const fetchPipeline = useCallback(async () => {
    const token = localStorage.getItem('cardex_token')
    if (!token) { router.replace('/dashboard/login'); return }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/pipeline/kanban`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.status === 401) { router.replace('/dashboard/login'); return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json: PipelineData = await res.json()
      setStages([...json.stages].sort((a, b) => a.position - b.position))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pipeline')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => { fetchPipeline() }, [fetchPipeline])

  // ── Drag and drop ──
  function handleDragStart(dealUlid: string) {
    setDragDealUlid(dealUlid)
  }

  function handleDragOver(e: React.DragEvent, stageUlid: string) {
    e.preventDefault()
    setDragOverStage(stageUlid)
  }

  function handleDragLeave() {
    setDragOverStage(null)
  }

  async function handleDrop(targetStageUlid: string) {
    setDragOverStage(null)
    if (!dragDealUlid || movingRef.current) return

    // Find current stage
    const sourceStage = stages.find(s => s.deals.some(d => d.deal_ulid === dragDealUlid))
    if (!sourceStage || sourceStage.stage_ulid === targetStageUlid) {
      setDragDealUlid(null)
      return
    }

    movingRef.current = true

    // Optimistic update
    const deal = sourceStage.deals.find(d => d.deal_ulid === dragDealUlid)!
    setStages(prev =>
      prev.map(s => {
        if (s.stage_ulid === sourceStage.stage_ulid) {
          return { ...s, deals: s.deals.filter(d => d.deal_ulid !== dragDealUlid), deal_count: s.deal_count - 1 }
        }
        if (s.stage_ulid === targetStageUlid) {
          return { ...s, deals: [...s.deals, deal], deal_count: s.deal_count + 1 }
        }
        return s
      })
    )
    setDragDealUlid(null)

    // Persist
    try {
      const token = localStorage.getItem('cardex_token') ?? ''
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/dealer/crm/deals/${dragDealUlid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ stage_ulid: targetStageUlid }),
      })
      if (!res.ok) {
        // Revert on failure
        fetchPipeline()
      }
    } catch {
      fetchPipeline()
    } finally {
      movingRef.current = false
    }
  }

  // ── Loading ──
  if (loading) {
    return (
      <div className="mx-auto max-w-screen-xl px-4 py-8 animate-pulse">
        <div className="mb-6 h-8 w-40 rounded bg-surface-hover" />
        <div className="flex gap-4 overflow-x-auto pb-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-96 w-64 flex-shrink-0 rounded-xl bg-surface-hover" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-screen-xl px-4 py-8">
        <div className="rounded-xl border border-red-500/50 bg-red-500/10 p-6 text-center">
          <p className="mb-3 text-red-400">{error}</p>
          <button
            onClick={fetchPipeline}
            className="rounded-lg bg-red-500/20 px-4 py-2 text-sm text-red-400 hover:bg-red-500/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      {quickAddStage && (
        <QuickAddDealModal
          stageUlid={quickAddStage.stage_ulid}
          stageName={quickAddStage.name}
          onClose={() => setQuickAddStage(null)}
          onAdded={fetchPipeline}
        />
      )}

      <div className="flex h-[calc(100vh-64px)] flex-col px-4 py-6">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline</h1>
            <p className="mt-1 text-sm text-surface-muted">
              {stages.reduce((s, st) => s + st.deal_count, 0)} deals ·{' '}
              {formatEur(
                stages.reduce((s, st) => s + st.deals.reduce((v, d) => v + d.deal_value_eur, 0), 0)
              )}{' '}
              total value
            </p>
          </div>
          <button
            onClick={fetchPipeline}
            className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-surface-muted hover:text-white transition-colors"
          >
            Refresh
          </button>
        </div>

        {/* Kanban board */}
        {stages.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-xl border border-surface-border">
            <p className="text-surface-muted">No pipeline stages configured.</p>
          </div>
        ) : (
          <div className="flex flex-1 gap-4 overflow-x-auto pb-4">
            {stages.map(stage => (
              <StageColumn
                key={stage.stage_ulid}
                stage={stage}
                isDragOver={dragOverStage === stage.stage_ulid}
                onDragOver={e => handleDragOver(e, stage.stage_ulid)}
                onDrop={() => handleDrop(stage.stage_ulid)}
                onDragLeave={handleDragLeave}
                onDragStart={handleDragStart}
                onAddDeal={() => setQuickAddStage(stage)}
              />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
