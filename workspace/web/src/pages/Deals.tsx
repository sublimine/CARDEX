import React, { useState } from 'react'
import { Plus } from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'
import { DealStageBadge } from '../components/Badge'
import Avatar from '../components/Avatar'
import LoadingSpinner from '../components/LoadingSpinner'
import { useDeals, useDealMutations } from '../hooks/useDeals'
import { STAGES, STAGE_LABELS, type KanbanStage } from '../hooks/useKanban'
import { useToast } from '../components/Toast'
import type { Deal } from '../types'

const MOCK_DEALS: Deal[] = [
  { id: 'd1', tenantId: 't', contactId: 'c1', vehicleId: 'v1', stage: 'lead',        createdAt: '2026-04-15T10:00:00Z', updatedAt: '2026-04-18T10:00:00Z', vehicleName: 'BMW 320d',     contactName: 'Maria Santos', price: 28500 },
  { id: 'd2', tenantId: 't', contactId: 'c2', vehicleId: 'v2', stage: 'contacted',   createdAt: '2026-04-14T09:00:00Z', updatedAt: '2026-04-17T14:00:00Z', vehicleName: 'Audi A4',      contactName: 'John Doe',     price: 31000 },
  { id: 'd3', tenantId: 't', contactId: 'c3', vehicleId: 'v3', stage: 'offer',       createdAt: '2026-04-13T08:00:00Z', updatedAt: '2026-04-16T11:00:00Z', vehicleName: 'Mercedes C220', contactName: 'Anna Weber',   price: 35000 },
  { id: 'd4', tenantId: 't', contactId: 'c4', vehicleId: 'v4', stage: 'negotiation', createdAt: '2026-04-12T07:00:00Z', updatedAt: '2026-04-15T16:00:00Z', vehicleName: 'VW Golf 8',    contactName: 'Peter Klein',  price: 26000 },
  { id: 'd5', tenantId: 't', contactId: 'c5', vehicleId: 'v5', stage: 'won',         createdAt: '2026-04-10T06:00:00Z', updatedAt: '2026-04-14T09:00:00Z', vehicleName: 'BMW X3',       contactName: 'Sophie L.',    price: 44000 },
  { id: 'd6', tenantId: 't', contactId: 'c6', vehicleId: 'v6', stage: 'lost',        createdAt: '2026-04-08T05:00:00Z', updatedAt: '2026-04-11T12:00:00Z', vehicleName: 'Peugeot 308',  contactName: 'Hans Müller',  price: 22500 },
]

function DealRow({ deal }: { deal: Deal }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-gray-100 dark:border-gray-700/50 last:border-0">
      <Avatar name={deal.contactName ?? '?'} size="sm" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
          {deal.vehicleName ?? 'Unknown vehicle'}
        </p>
        <p className="text-xs text-gray-400">{deal.contactName}</p>
      </div>
      {deal.price && (
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 shrink-0">
          €{deal.price.toLocaleString()}
        </span>
      )}
      <DealStageBadge stage={deal.stage} />
    </div>
  )
}

function PipelineColumn({ stage, deals }: { stage: KanbanStage; deals: Deal[] }) {
  const total = deals.reduce((s, d) => s + (d.price ?? 0), 0)
  return (
    <Card padding={false} className="min-w-[220px] flex-1">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
            {STAGE_LABELS[stage]}
          </span>
          <span className="text-xs font-medium text-gray-400">{deals.length}</span>
        </div>
        {total > 0 && (
          <p className="text-sm font-semibold text-gray-600 dark:text-gray-300 mt-0.5">
            €{total.toLocaleString()}
          </p>
        )}
      </div>
      <div className="px-4">
        {deals.length === 0 ? (
          <p className="text-xs text-gray-400 py-4 text-center">No deals</p>
        ) : (
          deals.map((d) => <DealRow key={d.id} deal={d} />)
        )}
      </div>
    </Card>
  )
}

export default function Deals() {
  const { data, loading } = useDeals()
  const { moveStage, loading: mutating } = useDealMutations()
  const { success } = useToast()
  const [selectedStage, setSelectedStage] = useState<KanbanStage | 'all'>('all')

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
  }

  const filteredDeals = selectedStage === 'all' ? deals : deals.filter((d) => d.stage === selectedStage)

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Deals</h1>
        <Button icon={<Plus className="w-4 h-4" />} size="sm" loading={mutating}>New deal</Button>
      </div>

      {/* Stage filter */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {(['all', ...STAGES] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSelectedStage(s)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors whitespace-nowrap ${
              selectedStage === s
                ? 'bg-brand-600 text-white'
                : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400'
            }`}
          >
            {s === 'all' ? 'All' : STAGE_LABELS[s]}
            {s !== 'all' && (
              <span className="ml-1.5 opacity-70">{grouped[s]?.length ?? 0}</span>
            )}
          </button>
        ))}
      </div>

      {/* Pipeline visual */}
      <div className="overflow-x-auto -mx-4 px-4">
        <div className="flex gap-3 min-w-max pb-2">
          {STAGES.map((s) => (
            <PipelineColumn key={s} stage={s} deals={grouped[s]} />
          ))}
        </div>
      </div>

      {/* Table for filtered */}
      {selectedStage !== 'all' && (
        <Card>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
            {STAGE_LABELS[selectedStage]} — {filteredDeals.length} deals
          </h2>
          {loading ? (
            <div className="flex justify-center py-8"><LoadingSpinner /></div>
          ) : (
            filteredDeals.map((d) => (
              <div key={d.id} className="flex items-center gap-3 py-3 border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                <Avatar name={d.contactName ?? '?'} size="sm" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{d.vehicleName}</p>
                  <p className="text-xs text-gray-400">{d.contactName}</p>
                </div>
                {d.price && <span className="text-sm font-semibold">€{d.price.toLocaleString()}</span>}
                <button
                  onClick={() => handleAdvance(d)}
                  disabled={d.stage === 'won' || d.stage === 'lost'}
                  className="text-xs px-2.5 py-1 rounded-lg bg-brand-50 dark:bg-brand-900/20 text-brand-600 hover:bg-brand-100 disabled:opacity-40 transition-colors"
                >
                  Advance →
                </button>
              </div>
            ))
          )}
        </Card>
      )}
    </div>
  )
}
