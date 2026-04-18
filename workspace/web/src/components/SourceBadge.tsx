import React from 'react'
import { CheckCircle2, AlertCircle, XCircle, Lock } from 'lucide-react'
import type { DataSource, DataSourceStatus } from '../types/check'

const statusConfig: Record<DataSourceStatus, {
  icon: React.ElementType
  iconClass: string
  label: string
  rowClass: string
}> = {
  success: {
    icon: CheckCircle2,
    iconClass: 'text-green-500',
    label: 'Datos obtenidos',
    rowClass: '',
  },
  partial: {
    icon: AlertCircle,
    iconClass: 'text-yellow-500',
    label: 'Datos parciales',
    rowClass: '',
  },
  unavailable: {
    icon: XCircle,
    iconClass: 'text-red-400',
    label: 'No disponible',
    rowClass: 'opacity-60',
  },
  requires_owner: {
    icon: Lock,
    iconClass: 'text-gray-400',
    label: 'Requiere acceso del titular',
    rowClass: 'opacity-70',
  },
}

interface SourceBadgeProps {
  source: DataSource
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const cfg = statusConfig[source.status]
  const Icon = cfg.icon

  return (
    <div className={`flex items-start gap-2.5 py-2.5 border-b border-gray-100 dark:border-gray-700 last:border-0 ${cfg.rowClass}`}>
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${cfg.iconClass}`} />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="text-sm font-medium text-gray-900 dark:text-white">{source.name}</span>
          <span className="text-xs text-gray-400">({source.country})</span>
          {source.recordsFound !== undefined && source.recordsFound > 0 && (
            <span className="text-xs text-green-600 dark:text-green-400 font-medium">
              {source.recordsFound} registro{source.recordsFound !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {source.note ?? cfg.label}
        </p>
      </div>
    </div>
  )
}
