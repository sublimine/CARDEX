import { motion } from 'framer-motion'
import { CheckCircle2, AlertCircle, XCircle, Lock } from 'lucide-react'
import { cn } from '../lib/cn'
import type { DataSource, DataSourceStatus } from '../types/check'

const statusConfig: Record<DataSourceStatus, {
  Icon: React.ElementType
  iconClass: string
  label: string
  opacity: string
}> = {
  success: {
    Icon:      CheckCircle2,
    iconClass: 'text-accent-emerald',
    label:     'Datos obtenidos',
    opacity:   '',
  },
  partial: {
    Icon:      AlertCircle,
    iconClass: 'text-accent-amber',
    label:     'Datos parciales',
    opacity:   '',
  },
  unavailable: {
    Icon:      XCircle,
    iconClass: 'text-accent-rose',
    label:     'No disponible',
    opacity:   'opacity-50',
  },
  requires_owner: {
    Icon:      Lock,
    iconClass: 'text-text-muted',
    label:     'Requiere acceso del titular',
    opacity:   'opacity-60',
  },
}

interface SourceBadgeProps {
  source: DataSource
  index?: number
}

export function SourceBadge({ source, index = 0 }: SourceBadgeProps) {
  const cfg  = statusConfig[source.status]
  const Icon = cfg.Icon

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.2 }}
      className={cn(
        'flex items-start gap-2.5 py-2.5 border-b border-border-subtle/50 last:border-0',
        cfg.opacity
      )}
    >
      <Icon className={cn('w-4 h-4 mt-0.5 shrink-0', cfg.iconClass)} />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="text-sm font-medium text-text-primary">{source.name}</span>
          <span className="text-xs text-text-muted">({source.country})</span>
          {source.recordsFound !== undefined && source.recordsFound > 0 && (
            <span className="text-xs text-accent-emerald font-medium">
              {source.recordsFound} registro{source.recordsFound !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <p className="text-xs text-text-muted mt-0.5">{source.note ?? cfg.label}</p>
      </div>
    </motion.div>
  )
}
