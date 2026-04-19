import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'

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

const dotColorMap: Record<NonNullable<TimelineItem['accent']>, string> = {
  green:  'bg-accent-emerald ring-emerald-500/20',
  red:    'bg-accent-rose ring-rose-500/20',
  yellow: 'bg-accent-amber ring-amber-500/20',
  blue:   'bg-accent-blue ring-blue-500/20',
  gray:   'bg-text-muted ring-border-subtle',
}

export default function Timeline({ items, emptyMessage = 'Sin datos disponibles.' }: TimelineProps) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-text-muted italic py-4">{emptyMessage}</p>
    )
  }

  return (
    <ol className="relative">
      {items.map((item, idx) => {
        const accent = item.accent ?? 'gray'
        const isLast = idx === items.length - 1

        return (
          <motion.li
            key={item.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.05, duration: 0.25 }}
            className="relative pl-7 pb-6 last:pb-0"
          >
            {/* Vertical connector */}
            {!isLast && (
              <span
                className="absolute left-[7px] top-5 bottom-0 w-px bg-border-subtle"
                aria-hidden
              />
            )}
            {/* Dot */}
            <span
              className={cn(
                'absolute left-0 top-1.5 w-3.5 h-3.5 rounded-full ring-2 ring-offset-2 ring-offset-bg-primary',
                dotColorMap[accent]
              )}
              aria-hidden
            />
            {/* Content */}
            <div className="glass rounded-md p-3">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <time className="text-xs text-text-muted tabular-nums">{item.date}</time>
                {item.badge}
              </div>
              <p className="text-sm font-medium text-text-primary">{item.title}</p>
              {item.subtitle && (
                <p className="text-xs text-text-secondary mt-0.5">{item.subtitle}</p>
              )}
              {item.body && <div className="mt-1.5">{item.body}</div>}
            </div>
          </motion.li>
        )
      })}
    </ol>
  )
}
