import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  icon?: React.ReactNode
  iconRight?: React.ReactNode
}

export default function Input({
  label,
  error,
  hint,
  icon,
  iconRight,
  className,
  id,
  ...props
}: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide"
        >
          {label}
        </label>
      )}
      <motion.div
        animate={error ? { x: [0, -4, 4, -3, 3, 0] } : { x: 0 }}
        transition={{ duration: 0.35, ease: 'easeInOut' }}
        className="relative"
      >
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
            {icon}
          </span>
        )}
        <input
          id={inputId}
          className={cn(
            'w-full px-3.5 py-2.5 rounded-md text-sm text-text-primary placeholder:text-text-muted',
            'bg-glass-subtle border transition-all duration-200',
            'focus:outline-none focus:ring-2 focus:ring-offset-0',
            icon ? 'pl-9' : '',
            iconRight ? 'pr-9' : '',
            error
              ? 'border-accent-rose focus:ring-accent-rose/30 focus:border-accent-rose'
              : 'border-border-subtle focus:ring-accent-blue/30 focus:border-border-active',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        {iconRight && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
            {iconRight}
          </span>
        )}
      </motion.div>
      {error && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-1.5 text-xs text-accent-rose"
        >
          {error}
        </motion.p>
      )}
      {hint && !error && (
        <p className="mt-1.5 text-xs text-text-muted">{hint}</p>
      )}
    </div>
  )
}
