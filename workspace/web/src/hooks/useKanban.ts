import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Deal } from '../types'

export type KanbanStage = 'lead' | 'contacted' | 'offer' | 'negotiation' | 'won' | 'lost'

export const STAGES: KanbanStage[] = ['lead', 'contacted', 'offer', 'negotiation', 'won', 'lost']

export const STAGE_LABELS: Record<KanbanStage, string> = {
  lead: 'Lead', contacted: 'Contacted', offer: 'Offer',
  negotiation: 'Negotiation', won: 'Won', lost: 'Lost',
}

export const STAGE_WIPS: Record<KanbanStage, number> = {
  lead: 20, contacted: 10, offer: 8, negotiation: 5, won: 0, lost: 0,
}

export type Board = Record<KanbanStage, Deal[]>

interface DealListResponse {
  deals: Deal[]
  total: number
}

export function useKanban() {
  const [board, setBoard] = useState<Board>(() =>
    Object.fromEntries(STAGES.map((s) => [s, []])) as unknown as Board,
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<DealListResponse>('/deals')
      const next: Board = Object.fromEntries(STAGES.map((s) => [s, []])) as unknown as Board
      for (const deal of res.deals) {
        if (next[deal.stage]) next[deal.stage].push(deal)
      }
      setBoard(next)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const moveCard = useCallback(
    async (dealId: string, fromStage: KanbanStage, toStage: KanbanStage) => {
      // Optimistic update
      setBoard((prev) => {
        const next = { ...prev }
        const card = prev[fromStage].find((d) => d.id === dealId)
        if (!card) return prev
        next[fromStage] = prev[fromStage].filter((d) => d.id !== dealId)
        next[toStage] = [...prev[toStage], { ...card, stage: toStage }]
        return next
      })
      try {
        await api.patch(`/deals/${dealId}`, { stage: toStage })
      } catch {
        load() // rollback on error
      }
    },
    [load],
  )

  return { board, loading, error, moveCard, reload: load }
}
