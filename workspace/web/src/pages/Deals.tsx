import { motion, AnimatePresence } from 'framer-motion'
import React, { useState } from 'react'
import { Plus, ChevronRight, TrendingUp } from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'
import { DealStageBadge, Badge } from '../components/Badge'
import Avatar from '../components/Avatar'
import Modal from '../components/Modal'
import LoadingSpinner from '../components/LoadingSpinner'
import { cn } from '../lib/cn'
import { useDeals, useDealMutations } from '../hooks/useDeals'
import { STAGES, STAGE_LABELS, type KanbanStage } from '../hooks/useKanban'
import { useToast } from '../components/Toast'
import type { Deal } from '../types'

const MOCK_DEALS: Deal[] = [
  { id: 'd1', tenantId: 't', contactId: 'c1', vehicleId: 'v1', stage: 'lead',        createdAt: '2026-04-15T10:00:00Z', updatedAt: '2026-04-18T10:00:00Z', vehicleName: 'BMW 320d',      contactName: 'Maria Santos', price: 28500 },
  { id: 'd2', tenantId: 't', contactId: 'c2', vehicleId: 'v2', stage: 'contacted',   createdAt: '2026-04-14T09:00:00Z', updatedAt: '2026-04-17T14:00:00Z', vehicleName: 'Audi A4',       contactName: 'John Doe',     price: 31000 },
  { id: 'd3', tenantId: 't', contactId: 'c3', vehicleId: 'v3', stage: 'offer',       createdAt: '2026-04-13T08:00:00Z', updatedAt: '2026-04-16T11:00:00Z', vehicleName: 'Mercedes C220', contactName: 'Anna Weber',   price: 35000 },
  { id: 'd4', tenantId: 't', contactId: 'c4', vehicleId: 'v4', stage: 'negotiation', createdAt: '2026-04-12T07:00:00Z', updatedAt: '2026-04-15T16:00:00Z', vehicleName: 'VW Golf 8',     contactName: 'Peter Klein',  price: 26000 },
  { id: 'd5', tenantId: 't', contactId: 'c5', vehicleId: 'v5', stage: 'won',         createdAt: '2026-04-10T06:00:00Z', updatedAt: '2026-04-14T09:00:00Z', vehicleName: 'BMW X3',        contactName: 'Sophie L.',    price: 44000 },
  { id: 'd6', tenantId: 't', contactId: 'c6', vehicleId: 'v6', stage: 'lost',        createdAt: '2026-04-08T05:00:00Z', updatedAt: '2026-04-11T12:00:00Z', vehicleName: 'Peugeot 308',   contactName: 'Hans Müller',  price: 22500 },
]

const stageColor: Record<KanbanStage, string> = {
  lead:        'text-blue-400',
  contacted:   'text-violet-400',
  offer:       'text-amber-400',
  negotiation: 'text-orange-400',
  won:         'text-emerald-400',
  lost:        'text-rose-400',
}

const stagePill: Record<KanbanStage, string> = {
  lead:        'bg-blue-500/10 border-blue-500/20 text-blue-400',
  contacted:   'bg-violet-500/10 border-violet-500/20 text-violet-400',
  offer:       'bg-amber-500/10 border-amber-500/20 text-amber-400',
  negotiation: 'bg-orange-500/10 border-orange-500/20 text-orange-400',
  won:         'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
  lost:        'bg-rose-500/10 border-rose-500/20 text-rose-400',
}

// ── Deal detail modal ─────────────────────────────────────────────────────────
function DealDetailModal({ deal, onClose, onAdvance, canAdvance }: {
  deal: Deal; onClose: () => void; onAdvance: () => void; canAdvance: boolean
}) {
  return (
    <Modal open onClose={onClose} title={deal.vehicleName ?? 'Deal'} size="sm">
      <div className="space-y-4">
        <div className="flex items-center gap-3 pb-4 border-b border-border-subtle">
          <Avatar name={deal.contactName ?? '?'} size="md" />
          <div>
            <p className="text-sm font-semibold text-text-primary">{deal.contactName}</p>
            <p className="text-xs text-text-muted">{deal.vehicleName}</p>
          </div>
          <div className="ml-auto">
            <DealStageBadge stage={deal.stage} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {[
            ['Value',    deal.price ? `€${deal.price.toLocaleString()}` : '—'],
            ['Stage',    STAGE_LABELS[deal.stage as KanbanStage] ?? deal.stage],
            ['Created',  new Date(deal.createdAt).toLocaleDateString('en-GB')],
            ['Updated',  new Date(deal.updatedAt).toLocaleDateString('en-GB')],
          ].map(([k, v]) => (
            <div key={k} className="glass rounded-md p-3">
              <p className="text-[11px] text-text-muted uppercase tracking-wide mb-1">{k}</p>
              <p className="text-sm font-medium text-text-primary">{v}</p>
            </div>
          ))}
        </div>

        {canAdvance && (
          <Button onClick={onAdvance} className="w-full" icon={<ChevronRight className="w-4 h-4" />}>
            Advance to next stage
          </Button>
        )}
      </div>
    </Modal>
  )
}

// ── Pipeline summary card ─────────────────────────────────────────────────────
function PipelineCard({ stage, deals }: { stage: KanbanStage; deals: Deal[] }) {
  const total = deals.reduce((s, d) => s + (d.price ?? 0), 0)
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: STAGES.indexOf(stage) * 0.04, duration: 0.25 }}
      className="glass rounded-lg p-4 min-w-[140px] flex-1"
    >
      <p className={cn('text-[11px] font-bold uppercase tracking-wider mb-1', stageColor[stage])}>
        {STAGE_LABELS[stage]}
      </p>
      <p className="text-xl font-bold text-text-primary">{deals.length}</p>
      {total > 0 && (
        <p className="text-xs text-text-secondary mt-0.5">€{(total / 1000).toFixed(0)}k</p>
      )}
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Deals() {
  const { data, loading }            = useDeals()
  const { moveStage, loading: mutating } = useDealMutations()
  const { success }                  = useToast()
  const [selectedStage, setSelectedStage] = useState<KanbanStage | 'all'>('all')
  const [selectedDeal, setSelectedDeal]   = useState<Deal | null>(null)

  const deals = data?.deals ?? MOCK_DEALS

  const grouped: Record<KanbanStage, Deal[]> = Object.fromEntries(
    STAGES.map((s) => [s, deals.filter((d) => d.stage === s)]),
  ) as Record<KanbanStage, Deal[]>

  async function handleAdvance(deal: Deal) {
    const idx = STAGES.indexOf(deal.stage as KanbanStage)
    if (idx < 0 || idx >= STAGES.length - 2) return
    const next = STAGES[idx + 1]
    await moveStage(deal.id, next)
    success(`Deal moved to ${STAGE_LABELS[next]}`)
    setSelectedDeal(null)
  }

  const filteredDeals = selectedStage === 'all' ? deals : deals.filter((d) => d.stage === selectedStage)
  const totalPipeline = filteredDeals.reduce((s, d) => s + (d.price ?? 0), 0)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Deals</h1>
          <p className="text-sm text-text-muted mt-0.5">
            {deals.length} deals · €{(totalPipeline / 1000).toFixed(0)}k pipeline
          </p>
        </div>
        <Button icon={<Plus className="w-4 h-4" />} size="sm" loading={mutating}>
          New deal
        </Button>
      </div>

      {/* Pipeline overview */}
      <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
        <div className="flex gap-2 min-w-max md:min-w-0">
          {STAGES.map((s) => (
            <PipelineCard key={s} stage={s} deals={grouped[s]} />
          ))}
        </div>
      </div>

      {/* Stage filter pills */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        <motion.button
          whileTap={{ scale: 0.96 }}
          onClick={() => setSelectedStage('all')}
          className={cn(
            'px-3 py-1.5 text-xs font-medium rounded-full border transition-colors whitespace-nowrap',
            selectedStage === 'all'
              ? 'bg-accent-blue border-accent-blue/30 text-white'
              : 'glass border-border-subtle text-text-secondary hover:text-text-primary',
          )}
        >
          All · {deals.length}
        </motion.button>
        {STAGES.map((s) => (
          <motion.button
            key={s}
            whileTap={{ scale: 0.96 }}
            onClick={() => setSelectedStage(s)}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-full border transition-colors whitespace-nowrap',
              selectedStage === s ? stagePill[s] : 'glass border-border-subtle text-text-secondary hover:text-text-primary',
            )}
          >
            {STAGE_LABELS[s]} · {grouped[s]?.length ?? 0}
          </motion.button>
        ))}
      </div>

      {/* Deal list */}
      <Card>
        {loading ? (
          <div className="flex justify-center py-8"><LoadingSpinner /></div>
        ) : filteredDeals.length === 0 ? (
          <p className="text-sm text-text-muted text-center py-8">No deals in this stage.</p>
        ) : (
          <AnimatePresence mode="popLayout">
            {filteredDeals.map((d, idx) => {
              const stageIdx  = STAGES.indexOf(d.stage as KanbanStage)
              const canAdvance = stageIdx >= 0 && stageIdx < STAGES.length - 2

              return (
                <motion.div
                  key={d.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ delay: idx * 0.04, duration: 0.22 }}
                  onClick={() => setSelectedDeal(d)}
                  className="flex items-center gap-3 py-3 border-b border-border-subtle/50 last:border-0 cursor-pointer hover:bg-glass-subtle rounded-md px-2 -mx-2 transition-colors"
                >
                  <Avatar name={d.contactName ?? '?'} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-text-primary truncate">
                      {d.vehicleName ?? 'Unknown vehicle'}
                    </p>
                    <p className="text-xs text-text-muted">{d.contactName}</p>
                  </div>
                  {d.price && (
                    <span className="text-sm font-semibold text-text-primary shrink-0">
                      €{d.price.toLocaleString()}
                    </span>
                  )}
                  <DealStageBadge stage={d.stage} />
                  {canAdvance && (
                    <motion.button
                      whileTap={{ scale: 0.92 }}
                      onClick={(e) => { e.stopPropagation(); handleAdvance(d) }}
                      className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-md glass border-border-subtle text-text-secondary hover:text-text-primary transition-colors shrink-0"
                    >
                      Advance <ChevronRight className="w-3 h-3" />
                    </motion.button>
                  )}
                </motion.div>
              )
            })}
          </AnimatePresence>
        )}
      </Card>

      {/* Deal detail modal */}
      {selectedDeal && (
        <DealDetailModal
          deal={selectedDeal}
          onClose={() => setSelectedDeal(null)}
          onAdvance={() => handleAdvance(selectedDeal)}
          canAdvance={
            STAGES.indexOf(selectedDeal.stage as KanbanStage) >= 0 &&
            STAGES.indexOf(selectedDeal.stage as KanbanStage) < STAGES.length - 2
          }
        />
      )}
    </motion.div>
  )
}
