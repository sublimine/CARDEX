import React from 'react'
import { AlertTriangle, AlertOctagon, Info, Car, RotateCcw, TrendingDown } from 'lucide-react'
import type { VehicleAlert } from '../types/check'

const severityConfig = {
  critical: {
    container: 'bg-red-50 dark:bg-red-950/30 border-red-300 dark:border-red-700',
    icon: 'text-red-600 dark:text-red-400',
    title: 'text-red-800 dark:text-red-300',
    body: 'text-red-700 dark:text-red-400',
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    label: 'CRÍTICO',
    IconComponent: AlertOctagon,
  },
  warning: {
    container: 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-300 dark:border-yellow-700',
    icon: 'text-yellow-600 dark:text-yellow-400',
    title: 'text-yellow-800 dark:text-yellow-300',
    body: 'text-yellow-700 dark:text-yellow-500',
    badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
    label: 'ATENCIÓN',
    IconComponent: AlertTriangle,
  },
  info: {
    container: 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800',
    icon: 'text-blue-600 dark:text-blue-400',
    title: 'text-blue-800 dark:text-blue-300',
    body: 'text-blue-700 dark:text-blue-400',
    badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    label: 'INFO',
    IconComponent: Info,
  },
}

const typeIcon: Record<VehicleAlert['type'], React.ElementType> = {
  stolen: Car,
  recall_open: RotateCcw,
  mileage_inconsistency: TrendingDown,
  total_loss: AlertOctagon,
  other: AlertTriangle,
}

interface AlertCardProps {
  alert: VehicleAlert
}

export default function AlertCard({ alert }: AlertCardProps) {
  const cfg = severityConfig[alert.severity]
  const TypeIcon = typeIcon[alert.type] ?? AlertTriangle

  return (
    <div className={`rounded-xl border p-4 ${cfg.container}`}>
      <div className="flex items-start gap-3">
        <div className={`shrink-0 mt-0.5 ${cfg.icon}`}>
          <TypeIcon className="w-5 h-5" strokeWidth={2} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide ${cfg.badge}`}>
              {cfg.label}
            </span>
            <p className={`text-sm font-semibold ${cfg.title}`}>{alert.title}</p>
          </div>
          <p className={`text-sm ${cfg.body}`}>{alert.description}</p>
          {alert.recommendedAction && (
            <p className={`mt-1.5 text-xs font-medium ${cfg.body} opacity-90`}>
              → {alert.recommendedAction}
            </p>
          )}
          <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">Fuente: {alert.source}</p>
        </div>
      </div>
    </div>
  )
}
