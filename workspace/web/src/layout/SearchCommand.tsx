import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search,
  LayoutDashboard,
  Car,
  KanbanSquare,
  Users,
  GitPullRequest,
  MessageSquare,
  Calendar,
  BarChart3,
  Settings,
  FileSearch,
  X,
  CornerDownLeft,
} from 'lucide-react'
import { cn } from '../lib/cn'

interface SearchItem {
  to: string
  label: string
  icon: React.ElementType
  description: string
}

const ALL_ITEMS: SearchItem[] = [
  { to: '/',         label: 'Dashboard',  icon: LayoutDashboard, description: 'Overview, KPIs and activity feed' },
  { to: '/vehicles', label: 'Vehicles',   icon: Car,             description: 'Fleet inventory and stock management' },
  { to: '/kanban',   label: 'Kanban',     icon: KanbanSquare,    description: 'Deal pipeline board with WIP limits' },
  { to: '/contacts', label: 'Contacts',   icon: Users,           description: 'Customer and partner directory' },
  { to: '/deals',    label: 'Deals',      icon: GitPullRequest,  description: 'Sales deals and transactions' },
  { to: '/inbox',    label: 'Inbox',      icon: MessageSquare,   description: 'Messages, conversations and templates' },
  { to: '/calendar', label: 'Calendar',   icon: Calendar,        description: 'Schedule, appointments and events' },
  { to: '/finance',  label: 'Finance',    icon: BarChart3,       description: 'P&L, fleet aggregation and alerts' },
  { to: '/check',    label: 'VIN Check',  icon: FileSearch,      description: 'Vehicle history report by VIN' },
  { to: '/settings', label: 'Settings',   icon: Settings,        description: 'Account, team and preferences' },
]

function highlight(text: string, query: string) {
  if (!query.trim()) return <>{text}</>
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-accent-blue/20 text-accent-blue rounded-sm not-italic">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}

export default function SearchCommand() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIdx, setSelectedIdx] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = query.trim()
    ? ALL_ITEMS.filter(
        (item) =>
          item.label.toLowerCase().includes(query.toLowerCase()) ||
          item.description.toLowerCase().includes(query.toLowerCase()),
      )
    : ALL_ITEMS

  const handleOpen = useCallback(() => {
    setQuery('')
    setSelectedIdx(0)
    setOpen(true)
  }, [])

  // Cmd+K / Ctrl+K global shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        handleOpen()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handleOpen])

  // Auto-focus input when dialog opens
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 30)
      return () => clearTimeout(t)
    }
  }, [open])

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIdx(0)
  }, [query])

  const handleSelect = useCallback(
    (item: SearchItem) => {
      navigate(item.to)
      setOpen(false)
    },
    [navigate],
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && filtered[selectedIdx]) {
      handleSelect(filtered[selectedIdx])
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      {/* Trigger button in topbar */}
      <Dialog.Trigger asChild>
        <button
          onClick={handleOpen}
          className={cn(
            'hidden sm:flex items-center gap-2 h-8 px-3 rounded-md',
            'bg-glass-subtle border border-border-subtle',
            'text-text-muted text-sm hover:text-text-secondary hover:bg-glass-medium hover:border-border-active',
            'transition-all duration-150',
          )}
        >
          <Search className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="hidden md:inline">Search…</span>
          <kbd className="hidden lg:flex items-center gap-0.5 ml-1 px-1.5 py-0.5 rounded text-xs font-mono text-text-muted bg-glass-medium border border-border-subtle leading-none">
            ⌘K
          </kbd>
        </button>
      </Dialog.Trigger>

      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            {/* Overlay */}
            <Dialog.Overlay asChild>
              <motion.div
                className="fixed inset-0 z-[200] bg-black/55"
                style={{ backdropFilter: 'blur(4px)' }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              />
            </Dialog.Overlay>

            {/* Panel */}
            <Dialog.Content asChild>
              <div className="fixed inset-0 z-[201] flex items-start justify-center pt-[14vh] px-4 pointer-events-none">
                <motion.div
                  className="w-full max-w-[540px] rounded-xl overflow-hidden border border-border-active shadow-elevation-4 pointer-events-auto"
                  style={{ background: 'rgba(20, 20, 36, 0.97)', backdropFilter: 'blur(32px)' }}
                  initial={{ scale: 0.96, opacity: 0, y: -10 }}
                  animate={{ scale: 1, opacity: 1, y: 0 }}
                  exit={{ scale: 0.96, opacity: 0, y: -10 }}
                  transition={{ duration: 0.18, ease: [0.25, 0.46, 0.45, 0.94] }}
                  onKeyDown={handleKeyDown}
                >
                  {/* Search row */}
                  <div className="flex items-center gap-3 px-4 h-14 border-b border-border-subtle">
                    <Search className="w-4 h-4 text-text-muted flex-shrink-0" />
                    <Dialog.Title className="sr-only">Search</Dialog.Title>
                    <input
                      ref={inputRef}
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search pages and actions…"
                      className="flex-1 bg-transparent text-text-primary placeholder-text-muted text-sm outline-none"
                      aria-label="Search"
                    />
                    <Dialog.Close asChild>
                      <button className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150">
                        <X className="w-4 h-4" />
                      </button>
                    </Dialog.Close>
                  </div>

                  {/* Results */}
                  <div className="max-h-[360px] overflow-y-auto py-2">
                    {filtered.length === 0 ? (
                      <div className="py-12 text-center">
                        <p className="text-text-muted text-sm">No results for "{query}"</p>
                      </div>
                    ) : (
                      <>
                        <div className="px-4 pb-1.5 pt-0.5">
                          <span className="text-2xs font-semibold uppercase tracking-widest text-text-muted">
                            Navigate
                          </span>
                        </div>

                        {filtered.map((item, i) => {
                          const Icon = item.icon
                          const isSelected = i === selectedIdx
                          return (
                            <button
                              key={item.to}
                              onClick={() => handleSelect(item)}
                              onMouseEnter={() => setSelectedIdx(i)}
                              className={cn(
                                'w-full flex items-center gap-3 px-3 mx-1 py-2.5 rounded-lg text-left',
                                'transition-colors duration-100',
                                isSelected ? 'bg-glass-medium' : 'hover:bg-glass-subtle',
                              )}
                              style={{ width: 'calc(100% - 8px)' }}
                            >
                              <div
                                className={cn(
                                  'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border',
                                  isSelected
                                    ? 'bg-accent-blue/10 border-accent-blue/30'
                                    : 'bg-glass-subtle border-border-subtle',
                                )}
                              >
                                <Icon
                                  className={cn(
                                    'w-4 h-4',
                                    isSelected ? 'text-accent-blue' : 'text-text-secondary',
                                  )}
                                  strokeWidth={1.75}
                                />
                              </div>

                              <div className="flex-1 min-w-0">
                                <div
                                  className={cn(
                                    'text-sm font-medium',
                                    isSelected ? 'text-text-primary' : 'text-text-secondary',
                                  )}
                                >
                                  {highlight(item.label, query)}
                                </div>
                                <div className="text-xs text-text-muted truncate mt-0.5">
                                  {item.description}
                                </div>
                              </div>

                              {isSelected && (
                                <CornerDownLeft className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
                              )}
                            </button>
                          )
                        })}
                      </>
                    )}
                  </div>

                  {/* Footer hints */}
                  <div className="flex items-center gap-4 px-4 py-2.5 border-t border-border-subtle">
                    <span className="text-2xs text-text-muted">
                      <kbd className="font-mono">↑↓</kbd> navigate
                    </span>
                    <span className="text-2xs text-text-muted">
                      <kbd className="font-mono">↵</kbd> open
                    </span>
                    <span className="text-2xs text-text-muted">
                      <kbd className="font-mono">esc</kbd> close
                    </span>
                  </div>
                </motion.div>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  )
}
