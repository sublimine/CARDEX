import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'
import { cva, type VariantProps } from '../lib/variants'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium',
  {
    variants: {
      color: {
        blue:   'bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/20',
        green:  'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20',
        yellow: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
        red:    'bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20',
        gray:   'bg-white/5 text-text-secondary ring-1 ring-border-subtle',
        purple: 'bg-purple-500/15 text-purple-400 ring-1 ring-purple-500/20',
        orange: 'bg-orange-500/15 text-orange-400 ring-1 ring-orange-500/20',
      },
    },
    defaultVariants: { color: 'gray' },
  }
)

const dotColorMap: Record<NonNullable<BadgeProps['color']>, string> = {
  blue:   'bg-blue-400',
  green:  'bg-emerald-400',
  yellow: 'bg-amber-400',
  red:    'bg-rose-400',
  gray:   'bg-text-muted',
  purple: 'bg-purple-400',
  orange: 'bg-orange-400',
}

interface BadgeProps extends VariantProps<typeof badgeVariants> {
  children: React.ReactNode
  dot?: boolean
  pulse?: boolean
  className?: string
}

export function Badge({ color = 'gray', children, dot, pulse, className }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ color }), className)}>
      {dot && (
        <span className="relative inline-flex">
          <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dotColorMap[color ?? 'gray'])} />
          {pulse && (
            <span className={cn('absolute inset-0 w-1.5 h-1.5 rounded-full animate-ping opacity-60', dotColorMap[color ?? 'gray'])} />
          )}
        </span>
      )}
      {children}
    </span>
  )
}

export function VehicleStatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: NonNullable<BadgeProps['color']>; label: string }> = {
    listed:    { color: 'blue',   label: 'Listed' },
    inquiry:   { color: 'yellow', label: 'Inquiry' },
    sold:      { color: 'green',  label: 'Sold' },
    withdrawn: { color: 'gray',   label: 'Withdrawn' },
  }
  const { color, label } = map[status] ?? { color: 'gray', label: status }
  return <Badge color={color} dot pulse={status === 'listed'}>{label}</Badge>
}

export function DealStageBadge({ stage }: { stage: string }) {
  const map: Record<string, { color: NonNullable<BadgeProps['color']> }> = {
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

export { motion }
