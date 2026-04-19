import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronLeft, ChevronRight, Plus, Clock, User2 } from 'lucide-react'
import Card from '../components/Card'
import { Badge } from '../components/Badge'
import { cn } from '../lib/cn'

interface CalEvent {
  id: string
  title: string
  date: string
  time?: string
  type: 'visit' | 'call' | 'reminder' | 'delivery'
  contact?: string
}

const TYPE_COLOR: Record<CalEvent['type'], NonNullable<Parameters<typeof Badge>[0]['color']>> = {
  visit:    'blue',
  call:     'green',
  reminder: 'yellow',
  delivery: 'purple',
}

const MOCK_EVENTS: CalEvent[] = [
  { id: 'e1', title: 'Test drive — BMW 320d',      date: '2026-04-18', time: '10:00', type: 'visit',    contact: 'Maria Santos' },
  { id: 'e2', title: 'Call with John Doe',          date: '2026-04-18', time: '14:30', type: 'call',     contact: 'John Doe' },
  { id: 'e3', title: 'Follow-up reminder',          date: '2026-04-21', time: '09:00', type: 'reminder', contact: 'Peter Klein' },
  { id: 'e4', title: 'Vehicle delivery — Audi A4',  date: '2026-04-23', time: '11:00', type: 'delivery', contact: 'Anna Weber' },
  { id: 'e5', title: 'Test drive — Mercedes',       date: '2026-04-24', time: '15:00', type: 'visit',    contact: 'Sophie Leblanc' },
  { id: 'e6', title: 'Negotiation call',            date: '2026-04-25', time: '10:30', type: 'call',     contact: 'Hans Müller' },
]

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function isoDate(d: Date) {
  return d.toISOString().split('T')[0]
}

function weekdayOf(d: Date) {
  return (d.getDay() + 6) % 7
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}

export default function Calendar() {
  const now = new Date()
  const [year, setYear]             = useState(now.getFullYear())
  const [month, setMonth]           = useState(now.getMonth())
  const [selectedDate, setSelected] = useState(isoDate(now))

  function prev() {
    if (month === 0) { setYear((y) => y - 1); setMonth(11) }
    else setMonth((m) => m - 1)
  }
  function next() {
    if (month === 11) { setYear((y) => y + 1); setMonth(0) }
    else setMonth((m) => m + 1)
  }

  const firstDay  = new Date(year, month, 1)
  const totalDays = daysInMonth(year, month)
  const startPad  = weekdayOf(firstDay)

  const cells: (number | null)[] = [
    ...Array<null>(startPad).fill(null),
    ...Array.from({ length: totalDays }, (_, i) => i + 1),
  ]

  const eventsByDate: Record<string, CalEvent[]> = {}
  for (const e of MOCK_EVENTS) {
    if (!eventsByDate[e.date]) eventsByDate[e.date] = []
    eventsByDate[e.date].push(e)
  }

  const selectedEvents = eventsByDate[selectedDate] ?? []
  const monthLabel     = new Date(year, month).toLocaleDateString('en-GB', {
    month: 'long', year: 'numeric',
  })

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Calendar</h1>
          <p className="text-sm text-text-muted mt-0.5">{monthLabel}</p>
        </div>
        <button
          className={cn(
            'flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium',
            'bg-accent-blue text-white shadow-glow-blue hover:brightness-110',
            'transition-[filter] duration-150 min-h-[36px]',
          )}
        >
          <Plus className="w-3.5 h-3.5" /> New event
        </button>
      </div>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Month grid */}
        <Card className="flex-1">
          {/* Month navigation */}
          <div className="flex items-center justify-between mb-5">
            <button
              onClick={prev}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <h2 className="text-sm font-semibold text-text-primary">{monthLabel}</h2>
            <button
              onClick={next}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Day-of-week headers */}
          <div className="grid grid-cols-7 mb-2">
            {DAYS.map((d) => (
              <div key={d} className="text-center text-[10px] font-semibold text-text-muted uppercase py-1 tracking-wider">
                {d}
              </div>
            ))}
          </div>

          {/* Calendar cells */}
          <div className="grid grid-cols-7 gap-1">
            {cells.map((day, idx) => {
              if (!day) return <div key={`pad-${idx}`} />

              const dateStr  = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
              const events   = eventsByDate[dateStr] ?? []
              const isToday  = dateStr === isoDate(now)
              const isSel    = dateStr === selectedDate

              return (
                <button
                  key={dateStr}
                  onClick={() => setSelected(dateStr)}
                  className={cn(
                    'relative aspect-square flex flex-col items-center justify-center rounded-xl text-xs',
                    'transition-all duration-150 cursor-pointer',
                    isSel
                      ? 'bg-accent-blue text-white shadow-glow-blue'
                      : isToday
                      ? 'ring-1 ring-accent-blue/50 text-accent-blue font-semibold bg-accent-blue/10'
                      : 'text-text-secondary hover:bg-glass-medium hover:text-text-primary',
                  )}
                >
                  <span className="font-medium">{day}</span>
                  {events.length > 0 && (
                    <span
                      className={cn(
                        'w-1 h-1 rounded-full mt-0.5',
                        isSel ? 'bg-white/70' : 'bg-accent-blue',
                      )}
                    />
                  )}
                </button>
              )
            })}
          </div>
        </Card>

        {/* Day panel */}
        <Card className="lg:w-64 shrink-0">
          <h3 className="text-sm font-semibold text-text-primary mb-4">
            {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-GB', {
              weekday: 'long', day: 'numeric', month: 'short',
            })}
          </h3>

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={selectedDate}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              {selectedEvents.length === 0 ? (
                <p className="text-xs text-text-muted py-6 text-center">No events scheduled</p>
              ) : (
                <div className="space-y-3">
                  {selectedEvents.map((e) => (
                    <div
                      key={e.id}
                      className="p-3 rounded-xl border border-border-subtle bg-glass-subtle space-y-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-medium text-text-primary leading-snug">{e.title}</p>
                        <Badge color={TYPE_COLOR[e.type]} className="shrink-0 !text-[10px]">
                          {e.type}
                        </Badge>
                      </div>
                      <div className="flex flex-col gap-1">
                        {e.time && (
                          <span className="flex items-center gap-1 text-[10px] text-text-muted">
                            <Clock className="w-3 h-3" /> {e.time}
                          </span>
                        )}
                        {e.contact && (
                          <span className="flex items-center gap-1 text-[10px] text-text-muted">
                            <User2 className="w-3 h-3" /> {e.contact}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </Card>
      </div>
    </div>
  )
}
