import * as TabsPrimitive from '@radix-ui/react-tabs'
import { motion } from 'framer-motion'
import React from 'react'
import { cn } from '../lib/cn'

export interface TabItem {
  value: string
  label: React.ReactNode
  content: React.ReactNode
  disabled?: boolean
}

interface TabsProps {
  items: TabItem[]
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
  className?: string
}

export function Tabs({ items, defaultValue, value, onValueChange, className }: TabsProps) {
  const controlled = value !== undefined
  const activeValue = controlled ? value : defaultValue ?? items[0]?.value

  return (
    <TabsPrimitive.Root
      defaultValue={defaultValue ?? items[0]?.value}
      value={value}
      onValueChange={onValueChange}
      className={cn('w-full', className)}
    >
      <TabsPrimitive.List className="relative flex gap-1 p-1 glass rounded-lg mb-4">
        {items.map((tab) => (
          <TabsPrimitive.Trigger
            key={tab.value}
            value={tab.value}
            disabled={tab.disabled}
            className={cn(
              'relative z-10 flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-colors duration-150 outline-none',
              'text-text-muted hover:text-text-secondary',
              'disabled:opacity-40 disabled:pointer-events-none',
              'data-[state=active]:text-text-primary'
            )}
          >
            {tab.label}
            {/* Animated indicator — uses layoutId so it slides between tabs */}
            {(controlled ? value : activeValue) === tab.value && (
              <motion.span
                layoutId="tab-indicator"
                className="absolute inset-0 bg-glass-strong rounded-md border border-border-subtle"
                transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                style={{ zIndex: -1 }}
              />
            )}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>

      {items.map((tab) => (
        <TabsPrimitive.Content
          key={tab.value}
          value={tab.value}
          className="outline-none animate-fade-in"
        >
          {tab.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  )
}
