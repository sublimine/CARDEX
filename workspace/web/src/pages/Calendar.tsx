import React, { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import Card from '../components/Card'
import { Badge } from '../components/Badge'

interface CalEvent {
  id: string
  title: string
  date: string // YYYY-MM-DD
  time?: string
  type: 'visit' | 'call' | 'reminder' | 'delivery'
  contact?: string
}

const EVENT_COLORS: Record<string, string> = {
  visit:    'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  call:     'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  reminder: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  delivery: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
}

const MOCK_EVENTS: CalEvent[] = [
  { id: 'e1', title: 'Test drive — BMW 320d', date: '2026-04-18', time: '10:00', type: 'visit',    contact: 'Maria Santos' },
  { id: 'e2', title: 'Call with John Doe',    date: '2026-04-18', time: '14:30', type: 'call',     contact: 'John Doe' },
  { id: 'e3', title: 'Follow-up reminder',    date: '2026-04-21', time: '09:00', type: 'reminder', contact: 'Peter Klein' },
  { id: 'e4', title: 'Vehicle delivery — Audi A4', date: '2026-04-23', time: '11:00', type: 'delivery', contact: 'Anna Weber' },
  { id: 'e5', title: 'Test drive — Mercedes', date: '2026-04-24', time: '15:00', type: 'visit',    contact: 'Sophie Leblanc' },
  { id: 'e6', title: 'Negotiation call',       date: '2026-04-25', time: '10:30', type: 'call',     contact: 'Hans Müller' },
]

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function isoDate(d: Date) {
  return d.toISOString().split('T')[0]
}

function startOfMonth(year: number, month: number) {
  return new Date(year, month, 1)
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}

// Returns ISO weekday 0=Mon…6=Sun
function weekdayOf(d: Date) {
  return (d.getDay() + 6) % 7
}

export default function Calendar() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth())
  const [selectedDate, setSelectedDate] = useState(isoDate(now))

  function prev() {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
  }
  function next() {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
  }

  const firstDay = startOfMonth(year, month)
  const totalDays = daysInMonth(year, month)
  const startPad = weekdayOf(firstDay)

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

  const monthLabel = new Date(year, month).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Calendar</h1>
        <button className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium rounded-lg transition-colors min-h-[36px]">
          <Plus className="w-3.5 h-3.5" /> New event
        </button>
      </div>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Month grid */}
        <Card className="flex-1">
          <div className="flex items-center justify-between mb-4">
            <button onClick={prev} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <ChevronLeft className="w-4 h-4 text-gray-500" />
            </button>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">{monthLabel}</h2>
            <button onClick={next} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <ChevronRight className="w-4 h-4 text-gray-500" />
            </button>
          </div>

          <div className="grid grid-cols-7 mb-1">
            {DAYS.map((d) => (
              <div key={d} className="text-center text-[10px] font-semibold text-gray-400 uppercase py-1">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-px">
            {cells.map((day, idx) => {
              if (!day) return <div key={`pad-${idx}`} />
              const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
              const events = eventsByDate[dateStr] ?? []
              const isToday = dateStr === isoDate(now)
              const isSelected = dateStr === selectedDate

              return (
                <button
                  key={dateStr}
                  onClick={() => setSelectedDate(dateStr)}
                  className={`relative aspect-square flex flex-col items-center justify-start pt-1 rounded-lg text-xs transition-colors ${
                    isSelected
                      ? 'bg-brand-600 text-white'
                      : isToday
                      ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400 font-semibold'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  <span className="font-medium">{day}</span>
                  {events.length > 0 && (
                    <span className={`w-1 h-1 rounded-full mt-0.5 ${isSelected ? 'bg-white' : 'bg-brand-500'}`} />
                  )}
                </button>
              )
            })}
          </div>
        </Card>

        {/* Day events */}
        <Card className="lg:w-64">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
            {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' })}
          </h3>

          {selectedEvents.length === 0 ? (
            <p className="text-xs text-gray-400 py-4 text-center">No events scheduled</p>
          ) : (
            <div className="space-y-2.5">
              {selectedEvents.map((e) => (
                <div key={e.id} className="flex items-start gap-2.5">
                  <span className="text-xs text-gray-400 w-10 shrink-0 pt-0.5">{e.time}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-gray-900 dark:text-white truncate">{e.title}</p>
                    {e.contact && <p className="text-[10px] text-gray-400 truncate">{e.contact}</p>}
                    <Badge color={(EVENT_COLORS[e.type] ? e.type : 'gray') as Parameters<typeof Badge>[0]['color']} className="mt-1 !text-[10px] !py-0">
                      {e.type}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
