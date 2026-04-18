import React from 'react'

type Color = 'blue' | 'green' | 'yellow' | 'red' | 'gray' | 'purple' | 'orange'

interface BadgeProps {
  color?: Color
  children: React.ReactNode
  dot?: boolean
  className?: string
}

const colors: Record<Color, string> = {
  blue:   'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  green:  'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  yellow: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  red:    'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  gray:   'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  purple: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  orange: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
}

const dotColors: Record<Color, string> = {
  blue: 'bg-blue-500', green: 'bg-green-500', yellow: 'bg-yellow-500',
  red: 'bg-red-500', gray: 'bg-gray-400', purple: 'bg-purple-500', orange: 'bg-orange-500',
}

export function Badge({ color = 'gray', children, dot, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${colors[color]} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColors[color]}`} />}
      {children}
    </span>
  )
}

// Helpers for domain entities
export function VehicleStatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: Color; label: string }> = {
    listed:    { color: 'blue',   label: 'Listed' },
    inquiry:   { color: 'yellow', label: 'Inquiry' },
    sold:      { color: 'green',  label: 'Sold' },
    withdrawn: { color: 'gray',   label: 'Withdrawn' },
  }
  const { color, label } = map[status] ?? { color: 'gray', label: status }
  return <Badge color={color} dot>{label}</Badge>
}

export function DealStageBadge({ stage }: { stage: string }) {
  const map: Record<string, { color: Color }> = {
    lead:        { color: 'gray' },
    contacted:   { color: 'blue' },
    offer:       { color: 'purple' },
    negotiation: { color: 'yellow' },
    won:         { color: 'green' },
    lost:        { color: 'red' },
  }
  const { color } = map[stage] ?? { color: 'gray' }
  return <Badge color={color}>{stage.charAt(0).toUpperCase() + stage.slice(1)}</Badge>
}
