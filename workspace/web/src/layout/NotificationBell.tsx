import React, { useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, Check, X, Car, GitPullRequest, Wrench } from 'lucide-react'
import { cn } from '../lib/cn'

type NType = 'deal' | 'vehicle' | 'system'

interface Notification {
  id: string
  title: string
  body: string
  time: string
  read: boolean
  type: NType
}

const SEED: Notification[] = [
  { id: '1', title: 'New deal created',    body: 'BMW 3 Series — €28,500',           time: '2m ago',    read: false, type: 'deal'    },
  { id: '2', title: 'Inspection due',      body: 'Mercedes C-Class needs APK by Fri', time: '1h ago',    read: false, type: 'vehicle' },
  { id: '3', title: 'Vehicle sold',        body: 'Audi A4 Avant — deal completed',   time: '3h ago',    read: true,  type: 'deal'    },
  { id: '4', title: 'Service reminder',    body: 'VW Golf VII — oil change overdue',  time: 'Yesterday', read: true,  type: 'system'  },
]

const TYPE_ICON: Record<NType, React.ElementType> = {
  deal:    GitPullRequest,
  vehicle: Car,
  system:  Wrench,
}

const TYPE_COLOR: Record<NType, string> = {
  deal:    'text-accent-emerald',
  vehicle: 'text-accent-amber',
  system:  'text-accent-blue',
}

const TYPE_BG: Record<NType, string> = {
  deal:    'bg-emerald-500/10',
  vehicle: 'bg-amber-500/10',
  system:  'bg-blue-500/10',
}

export default function NotificationBell() {
  const [notifications, setNotifications] = useState<Notification[]>(SEED)
  const [open, setOpen] = useState(false)
  const unread = notifications.filter((n) => !n.read).length

  const markAllRead = () => setNotifications((ns) => ns.map((n) => ({ ...n, read: true })))
  const dismiss = (id: string) => setNotifications((ns) => ns.filter((n) => n.id !== id))

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          aria-label={`${unread} unread notifications`}
          className={cn(
            'relative w-9 h-9 rounded-md flex items-center justify-center',
            'text-text-muted hover:text-text-primary hover:bg-glass-medium',
            'transition-colors duration-150 border border-transparent',
            open && 'bg-glass-medium border-border-subtle text-text-primary',
          )}
        >
          <Bell className="w-4 h-4" />
          <AnimatePresence>
            {unread > 0 && (
              <motion.span
                key="badge"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                exit={{ scale: 0 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                className="absolute top-1.5 right-1.5 min-w-[6px] h-[6px] bg-accent-rose rounded-full"
              />
            )}
          </AnimatePresence>
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <AnimatePresence>
          {open && (
          <Popover.Content
            forceMount
            align="end"
            sideOffset={8}
            className="z-[150] w-[320px] rounded-xl border border-border-active shadow-elevation-4 outline-none"
            style={{ background: 'rgba(22, 22, 38, 0.97)', backdropFilter: 'blur(24px)' }}
            asChild
          >
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text-primary">Notifications</span>
                {unread > 0 && (
                  <span className="text-2xs font-semibold px-1.5 py-0.5 rounded-full bg-accent-blue/10 text-accent-blue border border-accent-blue/20">
                    {unread}
                  </span>
                )}
              </div>
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-xs text-accent-blue hover:text-blue-400 transition-colors duration-150"
                >
                  <Check className="w-3 h-3" />
                  Mark all read
                </button>
              )}
            </div>

            {/* List */}
            <div className="max-h-[360px] overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="py-10 text-center">
                  <p className="text-text-muted text-sm">All caught up ✓</p>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {notifications.map((n) => {
                    const Icon = TYPE_ICON[n.type]
                    return (
                      <motion.div
                        key={n.id}
                        layout
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.18 }}
                        className={cn(
                          'relative flex items-start gap-3 px-4 py-3',
                          'border-b border-border-subtle last:border-0',
                          'hover:bg-glass-subtle transition-colors group',
                          !n.read && 'bg-glass-subtle',
                        )}
                      >
                        {/* Icon */}
                        <div
                          className={cn(
                            'mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
                            TYPE_BG[n.type],
                          )}
                        >
                          <Icon className={cn('w-3.5 h-3.5', TYPE_COLOR[n.type])} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline justify-between gap-2">
                            <span
                              className={cn(
                                'text-sm truncate',
                                n.read
                                  ? 'text-text-secondary font-normal'
                                  : 'text-text-primary font-medium',
                              )}
                            >
                              {n.title}
                            </span>
                            <span className="text-2xs text-text-muted flex-shrink-0">{n.time}</span>
                          </div>
                          <p className="text-xs text-text-muted mt-0.5 truncate">{n.body}</p>
                        </div>

                        {/* Unread indicator */}
                        {!n.read && (
                          <div className="mt-2 w-1.5 h-1.5 rounded-full bg-accent-blue flex-shrink-0" />
                        )}

                        {/* Dismiss */}
                        <button
                          onClick={() => dismiss(n.id)}
                          className="absolute top-2 right-2 w-5 h-5 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-glass-medium text-text-muted hover:text-text-primary transition-all duration-150"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2.5 border-t border-border-subtle">
              <button className="text-xs text-text-muted hover:text-text-secondary transition-colors duration-150">
                View all notifications
              </button>
            </div>
          </motion.div>
        </Popover.Content>
          )}
        </AnimatePresence>
      </Popover.Portal>
    </Popover.Root>
  )
}
