import React from 'react'
import { NavLink } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { LayoutDashboard, Car, MessageSquare, GitPullRequest, FileSearch } from 'lucide-react'
import { cn } from '../lib/cn'

const TABS = [
  { to: '/',         label: 'Home',     icon: LayoutDashboard, end: true },
  { to: '/vehicles', label: 'Vehicles', icon: Car              },
  { to: '/inbox',    label: 'Inbox',    icon: MessageSquare    },
  { to: '/deals',    label: 'Deals',    icon: GitPullRequest   },
  { to: '/check',    label: 'Check',    icon: FileSearch       },
]

export default function MobileNav() {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 md:hidden border-t border-border-subtle"
      style={{
        background: 'rgba(14, 14, 22, 0.94)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
      }}
    >
      <div className="flex h-16">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="flex-1 min-w-0">
            {({ isActive }) => (
              <motion.div
                className="relative flex flex-col items-center justify-center gap-1 h-full w-full"
                whileTap={{ scale: 0.84 }}
                transition={{ type: 'spring', stiffness: 450, damping: 22 }}
              >
                {/* Glow dot above icon when active */}
                <AnimatePresence>
                  {isActive && (
                    <motion.div
                      layoutId="mobile-tab-dot"
                      className="absolute top-1.5 w-1 h-1 rounded-full"
                      style={{
                        background: 'var(--color-blue)',
                        boxShadow: '0 0 6px 2px rgba(59,130,246,0.6)',
                      }}
                      initial={{ opacity: 0, scale: 0 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0 }}
                      transition={{ duration: 0.2, ease: 'easeOut' }}
                    />
                  )}
                </AnimatePresence>

                {/* Icon */}
                <motion.div
                  animate={{
                    scale: isActive ? 1.12 : 1,
                  }}
                  transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                >
                  <Icon
                    className={cn(
                      'w-[22px] h-[22px] transition-colors duration-150',
                      isActive ? 'text-accent-blue' : 'text-text-muted',
                    )}
                    strokeWidth={isActive ? 2.1 : 1.6}
                  />
                </motion.div>

                {/* Label */}
                <span
                  className={cn(
                    'text-[10px] font-medium leading-none tracking-tight transition-colors duration-150',
                    isActive ? 'text-accent-blue' : 'text-text-muted',
                  )}
                >
                  {label}
                </span>
              </motion.div>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
