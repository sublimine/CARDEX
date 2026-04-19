import { AnimatePresence, motion } from 'framer-motion'
import React, { useEffect } from 'react'
import { X } from 'lucide-react'
import { cn } from '../lib/cn'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
}

const sizeMap = {
  sm:   'max-w-sm',
  md:   'max-w-md',
  lg:   'max-w-lg',
  xl:   'max-w-2xl',
  full: 'max-w-4xl',
}

const spring = { type: 'spring', stiffness: 380, damping: 30 } as const

export default function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[200] flex items-end sm:items-center justify-center p-0 sm:p-4">
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 12 }}
            transition={spring}
            className={cn(
              'relative w-full glass-strong rounded-t-xl sm:rounded-lg shadow-elevation-4',
              'max-h-[92vh] flex flex-col',
              sizeMap[size]
            )}
          >
            {title && (
              <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle shrink-0">
                <h2 className="text-base font-semibold text-text-primary">{title}</h2>
                <motion.button
                  whileTap={{ scale: 0.92 }}
                  onClick={onClose}
                  className="p-1.5 rounded-md hover:bg-glass-medium text-text-muted hover:text-text-primary transition-colors"
                >
                  <X className="w-4 h-4" />
                </motion.button>
              </div>
            )}
            <div className="overflow-y-auto flex-1 p-5">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
