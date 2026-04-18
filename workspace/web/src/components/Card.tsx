import React from 'react'

interface CardProps {
  children: React.ReactNode
  className?: string
  padding?: boolean
  hover?: boolean
  onClick?: () => void
}

export default function Card({ children, className = '', padding = true, hover, onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm ${
        padding ? 'p-5' : ''
      } ${hover ? 'hover:shadow-md hover:border-brand-200 dark:hover:border-brand-700 cursor-pointer transition-all' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
