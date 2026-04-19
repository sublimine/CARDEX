import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'
import { motion, AnimatePresence } from 'framer-motion'
import React, { useState } from 'react'
import { Check, ChevronRight } from 'lucide-react'
import { cn } from '../lib/cn'

export interface DropdownItem {
  label: string
  icon?: React.ReactNode
  shortcut?: string
  destructive?: boolean
  disabled?: boolean
  checked?: boolean
  onSelect?: () => void
}

export interface DropdownSeparator {
  type: 'separator'
}

export type DropdownEntry = DropdownItem | DropdownSeparator

interface DropdownProps {
  trigger: React.ReactNode
  items: DropdownEntry[]
  align?: 'start' | 'center' | 'end'
}

function isSeparator(e: DropdownEntry): e is DropdownSeparator {
  return (e as DropdownSeparator).type === 'separator'
}

export function Dropdown({ trigger, items, align = 'end' }: DropdownProps) {
  const [open, setOpen] = useState(false)

  return (
    <DropdownMenuPrimitive.Root open={open} onOpenChange={setOpen}>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <AnimatePresence>
        {open && (
          <DropdownMenuPrimitive.Portal forceMount>
            <DropdownMenuPrimitive.Content
              align={align}
              sideOffset={6}
              asChild
              forceMount
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.97, y: -4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97, y: -4 }}
                transition={{ type: 'spring', stiffness: 380, damping: 28 }}
                className="z-[100] min-w-[160px] glass-strong rounded-lg shadow-elevation-3 p-1 outline-none"
              >
                {items.map((entry, idx) =>
                  isSeparator(entry) ? (
                    <DropdownMenuPrimitive.Separator
                      key={idx}
                      className="my-1 h-px bg-border-subtle"
                    />
                  ) : (
                    <DropdownMenuPrimitive.Item
                      key={idx}
                      disabled={entry.disabled}
                      onSelect={entry.onSelect}
                      className={cn(
                        'flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm outline-none cursor-pointer select-none transition-colors',
                        entry.destructive
                          ? 'text-accent-rose hover:bg-rose-500/10 focus:bg-rose-500/10'
                          : 'text-text-secondary hover:text-text-primary hover:bg-glass-medium focus:bg-glass-medium',
                        entry.disabled && 'opacity-40 pointer-events-none'
                      )}
                    >
                      {entry.checked !== undefined && (
                        <span className="w-3.5 shrink-0">
                          {entry.checked && <Check className="w-3.5 h-3.5" />}
                        </span>
                      )}
                      {entry.icon && <span className="shrink-0">{entry.icon}</span>}
                      <span className="flex-1">{entry.label}</span>
                      {entry.shortcut && (
                        <span className="text-xs text-text-muted ml-4">{entry.shortcut}</span>
                      )}
                    </DropdownMenuPrimitive.Item>
                  )
                )}
              </motion.div>
            </DropdownMenuPrimitive.Content>
          </DropdownMenuPrimitive.Portal>
        )}
      </AnimatePresence>
    </DropdownMenuPrimitive.Root>
  )
}
