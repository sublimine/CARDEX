import { motion } from 'framer-motion'
import { AlertTriangle, AlertOctagon, Info, Car, RotateCcw, TrendingDown } from 'lucide-react'
import { cn } from '../lib/cn'
import type { VehicleAlert } from '../types/check'

const severityConfig = {
  critical: {
    bar:   'bg-accent-rose',
    icon:  'text-accent-rose',
    title: 'text-rose-300',
    body:  'text-rose-400/80',
    badge: 'bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20',
    label: 'CRÍTICO',
    Icon:  AlertOctagon,
  },
  warning: {
    bar:   'bg-accent-amber',
    icon:  'text-accent-amber',
    title: 'text-amber-300',
    body:  'text-amber-400/80',
    badge: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
    label: 'ATENCIÓN',
    Icon:  AlertTriangle,
  },
  info: {
    bar:   'bg-accent-blue',
    icon:  'text-accent-blue',
    title: 'text-blue-300',
    body:  'text-blue-400/80',
    badge: 'bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/20',
    label: 'INFO',
    Icon:  Info,
  },
}

const typeIcon: Record<string, React.ElementType> = {
  stolen:                Car,
  recall_open:           RotateCcw,
  mileage_rollback:      TrendingDown,
  mileage_gap:           TrendingDown,
  mileage_inconsistency: TrendingDown, // legacy alias
  total_loss:            AlertOctagon,
  other:                 AlertTriangle,
}

interface AlertCardProps {
  alert: VehicleAlert
  index?: number
}

export default function AlertCard({ alert, index = 0 }: AlertCardProps) {
  const cfg     = severityConfig[alert.severity]
  const TypeIcon = typeIcon[alert.type] ?? AlertTriangle

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.25 }}
      className="relative glass rounded-lg overflow-hidden pl-4"
    >
      {/* Colored left bar */}
      <span className={cn('absolute left-0 inset-y-0 w-1', cfg.bar)} />

      <div className="flex items-start gap-3 p-4">
        <div className={cn('shrink-0 mt-0.5', cfg.icon)}>
          <TypeIcon className="w-5 h-5" strokeWidth={2} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn('inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide', cfg.badge)}>
              {cfg.label}
            </span>
            <p className={cn('text-sm font-semibold', cfg.title)}>{alert.title}</p>
          </div>
          <p className={cn('text-sm', cfg.body)}>{alert.description}</p>
          {alert.recommendedAction && (
            <p className={cn('mt-1.5 text-xs font-medium', cfg.body)}>
              → {alert.recommendedAction}
            </p>
          )}
          <p className="mt-1.5 text-[11px] text-text-muted">Fuente: {alert.source}</p>
        </div>
      </div>
    </motion.div>
  )
}
