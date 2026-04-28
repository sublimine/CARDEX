import { AnimatePresence, motion } from 'framer-motion'
import React, { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle, XCircle, AlertCircle, Info, X } from 'lucide-react'
import { cn } from '../lib/cn'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: string
  type: ToastType
  message: string
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void
  success: (message: string) => void
  error: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const typeConfig: Record<ToastType, { icon: React.ElementType; bar: string; iconClass: string }> = {
  success: { icon: CheckCircle,  bar: 'bg-accent-emerald', iconClass: 'text-accent-emerald' },
  error:   { icon: XCircle,      bar: 'bg-accent-rose',    iconClass: 'text-accent-rose' },
  warning: { icon: AlertCircle,  bar: 'bg-accent-amber',   iconClass: 'text-accent-amber' },
  info:    { icon: Info,         bar: 'bg-accent-blue',    iconClass: 'text-accent-blue' },
}

let idSeq = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const remove = useCallback((id: string) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const toast = useCallback(
    (message: string, type: ToastType = 'info') => {
      const id = String(++idSeq)
      setToasts((t) => [...t, { id, type, message }])
      setTimeout(() => remove(id), 4000)
    },
    [remove],
  )

  const success = useCallback((msg: string) => toast(msg, 'success'), [toast])
  const error   = useCallback((msg: string) => toast(msg, 'error'),   [toast])

  return (
    <ToastContext.Provider value={{ toast, success, error }}>
      {children}
      <div className="fixed bottom-20 md:bottom-5 right-4 z-[300] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence mode="popLayout">
          {toasts.map((t) => {
            const { icon: Icon, bar, iconClass } = typeConfig[t.type]
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, x: 40, scale: 0.95 }}
                animate={{ opacity: 1, x: 0,  scale: 1 }}
                exit={{ opacity: 0, x: 40, scale: 0.95 }}
                transition={{ type: 'spring', stiffness: 380, damping: 28 }}
                className="pointer-events-auto relative flex items-center gap-3 pr-4 pl-5 py-3 glass-strong rounded-lg shadow-elevation-3 max-w-sm overflow-hidden"
              >
                {/* Colored left border */}
                <span className={cn('absolute left-0 inset-y-0 w-1 rounded-l-lg', bar)} />
                <Icon className={cn('w-4 h-4 shrink-0', iconClass)} />
                <span className="flex-1 text-sm text-text-primary">{t.message}</span>
                <motion.button
                  whileTap={{ scale: 0.9 }}
                  onClick={() => remove(t.id)}
                  className="text-text-muted hover:text-text-secondary transition-colors shrink-0"
                >
                  <X className="w-3.5 h-3.5" />
                </motion.button>
                {/* Auto-dismiss progress bar */}
                <motion.span
                  className={cn('absolute bottom-0 left-0 h-[2px]', bar)}
                  initial={{ width: '100%' }}
                  animate={{ width: '0%' }}
                  transition={{ duration: 4, ease: 'linear' }}
                />
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be inside ToastProvider')
  return ctx
}
