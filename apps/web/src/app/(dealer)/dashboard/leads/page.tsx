'use client'

import { useState } from 'react'
import { MessageCircle, Phone, Mail, Clock, ChevronRight } from 'lucide-react'

interface Lead {
  id: string
  vehicle: string
  name: string
  contact: string
  type: 'CALL' | 'EMAIL' | 'MESSAGE'
  status: 'NEW' | 'IN_PROGRESS' | 'CLOSED'
  receivedAt: string
  message?: string
}

const MOCK_LEADS: Lead[] = [
  {
    id: '1', vehicle: 'BMW 320d 2021', name: 'Carlos Martínez',
    contact: '+34 612 345 678', type: 'CALL', status: 'NEW',
    receivedAt: '2026-03-31T09:12:00Z',
    message: 'Interested in test drive this weekend.',
  },
  {
    id: '2', vehicle: 'VW Golf GTI 2020', name: 'Anna Müller',
    contact: 'anna.m@email.de', type: 'EMAIL', status: 'IN_PROGRESS',
    receivedAt: '2026-03-30T15:44:00Z',
    message: 'Is the price negotiable? I can pay cash.',
  },
  {
    id: '3', vehicle: 'BMW 320d 2021', name: 'Pierre Dubois',
    contact: 'p.dubois@mail.fr', type: 'MESSAGE', status: 'NEW',
    receivedAt: '2026-03-30T11:22:00Z',
    message: 'Full service history available?',
  },
]

const TYPE_ICON = { CALL: Phone, EMAIL: Mail, MESSAGE: MessageCircle }
const STATUS_BADGE: Record<string, string> = {
  NEW: 'bg-brand-500/20 text-brand-400',
  IN_PROGRESS: 'bg-yellow-500/20 text-yellow-400',
  CLOSED: 'bg-surface-hover text-surface-muted',
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3600000)
  if (h < 1) return `${Math.floor(diff / 60000)}m ago`
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function LeadsPage() {
  const [filter, setFilter] = useState<'ALL' | 'NEW' | 'IN_PROGRESS' | 'CLOSED'>('ALL')
  const filtered = MOCK_LEADS.filter(l => filter === 'ALL' || l.status === filter)

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Leads</h1>
          <p className="mt-1 text-sm text-surface-muted">{MOCK_LEADS.filter(l => l.status === 'NEW').length} new</p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="mb-4 flex gap-2">
        {(['ALL', 'NEW', 'IN_PROGRESS', 'CLOSED'] as const).map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === s
                ? 'bg-brand-500 text-white'
                : 'border border-surface-border text-surface-muted hover:text-white'
            }`}
          >
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Lead list */}
      <div className="flex flex-col gap-3">
        {filtered.map(lead => {
          const Icon = TYPE_ICON[lead.type]
          return (
            <div key={lead.id}
              className="flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-4 hover:border-brand-500/40 transition-colors cursor-pointer">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-hover text-surface-muted">
                <Icon size={18} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-medium text-white">{lead.name}</span>
                  <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[lead.status]}`}>
                    {lead.status.replace('_', ' ')}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-surface-muted">
                    <Clock size={11} /> {timeAgo(lead.receivedAt)}
                  </span>
                </div>
                <p className="mt-0.5 text-sm text-surface-muted truncate">{lead.vehicle}</p>
                {lead.message && (
                  <p className="mt-1.5 text-sm text-white/70 line-clamp-1">&ldquo;{lead.message}&rdquo;</p>
                )}
                <p className="mt-1 text-xs font-mono text-surface-muted">{lead.contact}</p>
              </div>
              <ChevronRight size={16} className="text-surface-muted shrink-0 mt-1" />
            </div>
          )
        })}
        {filtered.length === 0 && (
          <div className="rounded-xl border border-surface-border bg-surface-card p-12 text-center text-surface-muted">
            No leads found.
          </div>
        )}
      </div>
    </div>
  )
}
