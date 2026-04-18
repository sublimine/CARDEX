import React from 'react'

export interface TimelineItem {
  id: string
  date: string
  title: string
  subtitle?: string
  badge?: React.ReactNode
  body?: React.ReactNode
  accent?: 'green' | 'red' | 'yellow' | 'blue' | 'gray'
}

interface TimelineProps {
  items: TimelineItem[]
  emptyMessage?: string
}

const dotColors: Record<NonNullable<TimelineItem['accent']>, string> = {
  green:  'bg-green-500 ring-green-100 dark:ring-green-900/40',
  red:    'bg-red-500 ring-red-100 dark:ring-red-900/40',
  yellow: 'bg-yellow-400 ring-yellow-100 dark:ring-yellow-900/40',
  blue:   'bg-blue-500 ring-blue-100 dark:ring-blue-900/40',
  gray:   'bg-gray-400 ring-gray-100 dark:ring-gray-800',
}

export default function Timeline({ items, emptyMessage = 'Sin datos disponibles.' }: TimelineProps) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-gray-400 dark:text-gray-500 italic py-4">{emptyMessage}</p>
    )
  }

  return (
    <ol className="relative">
      {items.map((item, idx) => {
        const accent = item.accent ?? 'gray'
        const dot = dotColors[accent]
        const isLast = idx === items.length - 1

        return (
          <li key={item.id} className="relative pl-7 pb-6 last:pb-0">
            {/* Vertical line */}
            {!isLast && (
              <span
                className="absolute left-[7px] top-5 bottom-0 w-px bg-gray-200 dark:bg-gray-700"
                aria-hidden
              />
            )}
            {/* Dot */}
            <span
              className={`absolute left-0 top-1.5 w-3.5 h-3.5 rounded-full ring-2 ring-offset-1 dark:ring-offset-gray-900 ${dot}`}
              aria-hidden
            />
            {/* Content */}
            <div>
              <div className="flex flex-wrap items-center gap-2 mb-0.5">
                <time className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                  {item.date}
                </time>
                {item.badge}
              </div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">{item.title}</p>
              {item.subtitle && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{item.subtitle}</p>
              )}
              {item.body && <div className="mt-1">{item.body}</div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
