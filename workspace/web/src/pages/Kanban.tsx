import React, { useState } from 'react'
import {
  DndContext, DragEndEvent, DragOverEvent, DragStartEvent,
  PointerSensor, useSensor, useSensors, DragOverlay, closestCenter,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, AlertCircle } from 'lucide-react'
import { DealStageBadge } from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useKanban, STAGES, STAGE_LABELS, STAGE_WIPS, type KanbanStage } from '../hooks/useKanban'
import type { Deal } from '../types'

// ── Card ──────────────────────────────────────────────────────────────────────
function KanbanCard({ deal, isDragging }: { deal: Deal; isDragging?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id: deal.id,
    data: { stage: deal.stage },
  })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 shadow-sm group"
    >
      <div className="flex items-start gap-2">
        <button
          {...attributes}
          {...listeners}
          className="mt-0.5 text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing touch-none"
        >
          <GripVertical className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
            {deal.vehicleName ?? `Deal #${deal.id.slice(0, 6)}`}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            {deal.contactName ?? 'Unknown contact'}
          </p>
          {deal.price && (
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mt-1.5">
              €{deal.price.toLocaleString()}
            </p>
          )}
          <div className="flex items-center gap-2 mt-2">
            <DealStageBadge stage={deal.stage} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Column ────────────────────────────────────────────────────────────────────
function KanbanColumn({
  stage,
  deals,
  activeId,
}: {
  stage: KanbanStage
  deals: Deal[]
  activeId: string | null
}) {
  const limit = STAGE_WIPS[stage]
  const over = limit > 0 && deals.length > limit

  return (
    <div className="flex flex-col gap-2 min-w-[240px] md:min-w-0 md:flex-1">
      {/* Column header */}
      <div className={`flex items-center justify-between px-1 py-1 rounded-lg ${over ? 'bg-red-50 dark:bg-red-900/20' : ''}`}>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
            {STAGE_LABELS[stage]}
          </span>
          <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 font-medium">
            {deals.length}
          </span>
        </div>
        {over && <AlertCircle className="w-3.5 h-3.5 text-red-500" />}
      </div>

      {/* Cards drop zone */}
      <SortableContext
        id={stage}
        items={deals.map((d) => d.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className={`flex flex-col gap-2 min-h-[80px] p-2 rounded-xl border-2 transition-colors ${
          over
            ? 'border-red-200 bg-red-50/50 dark:bg-red-900/10 dark:border-red-800'
            : 'border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/20'
        }`}>
          {deals.map((deal) => (
            <KanbanCard key={deal.id} deal={deal} isDragging={deal.id === activeId} />
          ))}
        </div>
      </SortableContext>
    </div>
  )
}

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK_BOARD = {
  lead:        [{ id: 'l1', tenantId: 't', contactId: 'c1', vehicleId: 'v1', stage: 'lead' as const,        createdAt: '', updatedAt: '', vehicleName: 'BMW 320d 2021', contactName: 'Maria S.',   price: 28500 }],
  contacted:   [{ id: 'l2', tenantId: 't', contactId: 'c2', vehicleId: 'v2', stage: 'contacted' as const,   createdAt: '', updatedAt: '', vehicleName: 'Audi A4 2020',  contactName: 'John D.',    price: 31000 },
                { id: 'l3', tenantId: 't', contactId: 'c3', vehicleId: 'v3', stage: 'contacted' as const,   createdAt: '', updatedAt: '', vehicleName: 'VW Golf 8 2022', contactName: 'Anna W.',   price: 26000 }],
  offer:       [{ id: 'l4', tenantId: 't', contactId: 'c4', vehicleId: 'v4', stage: 'offer' as const,       createdAt: '', updatedAt: '', vehicleName: 'Mercedes C220',  contactName: 'Peter K.',  price: 35000 }],
  negotiation: [{ id: 'l5', tenantId: 't', contactId: 'c5', vehicleId: 'v5', stage: 'negotiation' as const, createdAt: '', updatedAt: '', vehicleName: 'Peugeot 308 GT', contactName: 'Sophie L.', price: 22500 }],
  won:         [{ id: 'l6', tenantId: 't', contactId: 'c6', vehicleId: 'v6', stage: 'won' as const,         createdAt: '', updatedAt: '', vehicleName: 'BMW X3 2020',   contactName: 'Hans M.',   price: 44000 }],
  lost:        [],
}

export default function Kanban() {
  const { board: apiBoard, loading, moveCard } = useKanban()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [activeStage, setActiveStage] = useState<KanbanStage | null>(null)

  const board = loading ? MOCK_BOARD : apiBoard

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  function findStageOf(id: string): KanbanStage | null {
    for (const s of STAGES) {
      if ((board[s] as Deal[]).some((d) => d.id === id)) return s
    }
    return null
  }

  function onDragStart(e: DragStartEvent) {
    setActiveId(String(e.active.id))
    setActiveStage(findStageOf(String(e.active.id)))
  }

  function onDragOver(_e: DragOverEvent) {}

  async function onDragEnd(e: DragEndEvent) {
    const { active, over } = e
    setActiveId(null)
    setActiveStage(null)
    if (!over) return

    const from = findStageOf(String(active.id))
    // `over` may be a column id or a card id
    const toStage = STAGES.includes(over.id as KanbanStage)
      ? (over.id as KanbanStage)
      : findStageOf(String(over.id))

    if (!from || !toStage || from === toStage) return
    await moveCard(String(active.id), from, toStage)
  }

  const activeDeal = activeId
    ? (board[activeStage ?? 'lead'] as Deal[]).find((d) => d.id === activeId) ?? null
    : null

  return (
    <div className="p-4 md:p-6 space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between shrink-0">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Kanban Board</h1>
        {loading && <LoadingSpinner size="sm" />}
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 md:mx-0 md:px-0 flex-1">
          {STAGES.map((stage) => (
            <KanbanColumn
              key={stage}
              stage={stage}
              deals={board[stage] as Deal[]}
              activeId={activeId}
            />
          ))}
        </div>

        <DragOverlay>
          {activeDeal ? (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-brand-300 shadow-2xl p-3 w-60 rotate-1">
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {activeDeal.vehicleName ?? `Deal #${activeDeal.id.slice(0, 6)}`}
              </p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  )
}
