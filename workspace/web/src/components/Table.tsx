import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'
import LoadingSpinner from './LoadingSpinner'
import EmptyState from './EmptyState'

interface Column<T> {
  key: string
  header: string
  render?: (row: T) => React.ReactNode
  className?: string
}

interface TableProps<T> {
  columns: Column<T>[]
  data: T[]
  loading?: boolean
  keyExtractor: (row: T) => string
  onRowClick?: (row: T) => void
  emptyMessage?: string
  className?: string
}

export default function Table<T>({
  columns,
  data,
  loading,
  keyExtractor,
  onRowClick,
  emptyMessage = 'No data found',
  className,
}: TableProps<T>) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <LoadingSpinner />
      </div>
    )
  }

  if (data.length === 0) {
    return <EmptyState message={emptyMessage} />
  }

  return (
    <div className={cn('overflow-x-auto -mx-5 px-5', className)}>
      <table className="w-full min-w-[600px]">
        <thead>
          <tr className="border-b border-border-subtle">
            {columns.map((col) => (
              <th
                key={col.key}
                className={cn(
                  'pb-3 text-left text-[11px] font-medium text-text-muted uppercase tracking-wider',
                  col.className
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <motion.tr
              key={keyExtractor(row)}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03, duration: 0.2 }}
              onClick={() => onRowClick?.(row)}
              className={cn(
                'border-b border-border-subtle/50 last:border-0 transition-colors duration-150',
                onRowClick && 'cursor-pointer hover:bg-glass-subtle'
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn('py-3.5 pr-4 text-sm text-text-primary', col.className)}
                >
                  {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? '')}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
