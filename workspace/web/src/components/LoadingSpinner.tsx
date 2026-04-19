import React from 'react'
import { cn } from '../lib/cn'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }

export default function LoadingSpinner({ size = 'md', className }: LoadingSpinnerProps) {
  const id = React.useId()
  const s = sizes[size]

  return (
    <svg
      role="status"
      aria-label="Loading"
      className={cn(s, 'animate-spin', className)}
      viewBox="0 0 24 24"
      fill="none"
    >
      <defs>
        <linearGradient id={id} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%"   stopColor="var(--color-blue)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--color-blue)" stopOpacity="1" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="9" stroke="var(--glass-strong)" strokeWidth="2.5" />
      <circle
        cx="12" cy="12" r="9"
        stroke={`url(#${id})`}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="28 57"
      />
    </svg>
  )
}

export function PageSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-5">
      <div className="h-7 w-48 bg-glass-medium rounded-md" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-glass-medium rounded-lg" />
        ))}
      </div>
      <div className="h-64 bg-glass-medium rounded-lg" />
    </div>
  )
}
