import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'

interface CardProps {
  children: React.ReactNode
  className?: string
  padding?: boolean
  hover?: boolean
  onClick?: () => void
}

export default function Card({ children, className, padding = true, hover, onClick }: CardProps) {
  const interactive = hover || !!onClick

  return (
    <motion.div
      onClick={onClick}
      whileHover={interactive ? { y: -2, boxShadow: 'var(--shadow-3)' } : undefined}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className={cn(
        'glass rounded-lg border-border-subtle',
        padding && 'p-5',
        interactive && 'cursor-pointer',
        className
      )}
    >
      {children}
    </motion.div>
  )
}
