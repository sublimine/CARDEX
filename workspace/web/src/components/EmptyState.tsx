import { motion } from 'framer-motion'
import React from 'react'
import { Inbox } from 'lucide-react'
import { cn } from '../lib/cn'

interface EmptyStateProps {
  icon?: React.ReactNode
  title?: string
  message?: string
  action?: React.ReactNode
  className?: string
}

export default function EmptyState({
  icon,
  title = 'Nothing here',
  message,
  action,
  className,
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn('flex flex-col items-center justify-center py-16 px-4 text-center', className)}
    >
      <div className="w-12 h-12 rounded-lg bg-glass-medium border border-border-subtle flex items-center justify-center text-text-muted mb-4">
        {icon ?? <Inbox className="w-6 h-6" />}
      </div>
      <h3 className="text-sm font-medium text-text-secondary mb-1">{title}</h3>
      {message && (
        <p className="text-xs text-text-muted max-w-xs leading-relaxed">{message}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  )
}
