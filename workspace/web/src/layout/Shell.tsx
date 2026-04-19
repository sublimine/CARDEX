import React, { useState, useCallback } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
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
  PanelLeftOpen,
  Sun,
  Moon,
  LogOut,
  X,
  Menu,
} from 'lucide-react'
import MobileNav from './MobileNav'
import Breadcrumb from './Breadcrumb'
import SearchCommand from './SearchCommand'
import NotificationBell from './NotificationBell'
import Avatar from '../components/Avatar'
import { useAuthContext } from '../auth/AuthContext'
import { cn } from '../lib/cn'

// ── Nav definition ─────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { to: '/',          label: 'Dashboard',  icon: LayoutDashboard, end: true  },
  { to: '/vehicles',  label: 'Vehicles',   icon: Car,             end: false },
  { to: '/kanban',    label: 'Kanban',     icon: KanbanSquare,    end: false },
  { to: '/contacts',  label: 'Contacts',   icon: Users,           end: false },
  { to: '/deals',     label: 'Deals',      icon: GitPullRequest,  end: false },
  { to: '/inbox',     label: 'Inbox',      icon: MessageSquare,   end: false },
  { to: '/calendar',  label: 'Calendar',   icon: Calendar,        end: false },
  { to: '/finance',   label: 'Finance',    icon: BarChart3,       end: false },
  { to: '/check',     label: 'VIN Check',  icon: FileSearch,      end: false },
  { to: '/settings',  label: 'Settings',   icon: Settings,        end: false },
] as const

// ── Dark mode hook ─────────────────────────────────────────────────────────────

function useDark() {
  const [dark, setDark] = useState(
    () => !document.documentElement.classList.contains('light'),
  )
  const toggle = useCallback(() => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    document.documentElement.classList.toggle('light', !next)
    setDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }, [dark])
  return { dark, toggle }
}

// ── NavItem ────────────────────────────────────────────────────────────────────

interface NavItemProps {
  to: string
  label: string
  icon: React.ElementType
  end?: boolean
  collapsed: boolean
  onClick?: () => void
}

function NavItem({ to, label, icon: Icon, end, collapsed, onClick }: NavItemProps) {
  return (
    <NavLink to={to} end={end} onClick={onClick} className="block px-2 mb-0.5">
      {({ isActive }) => (
        <div
          className={cn(
            'relative flex items-center rounded-md transition-colors duration-150 cursor-pointer select-none',
            collapsed ? 'justify-center py-2.5 px-2' : 'gap-3 py-2.5 px-3',
            isActive ? 'bg-glass-medium' : 'hover:bg-glass-subtle',
          )}
        >
          {/* Active left-edge indicator */}
          {isActive && (
            <motion.div
              layoutId="sidebar-active"
              className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-accent-blue"
              style={{ boxShadow: '0 0 12px 2px rgba(59,130,246,0.4)' }}
              transition={{ type: 'spring', stiffness: 420, damping: 36 }}
            />
          )}

          {/* Icon */}
          <Icon
            className={cn(
              'flex-shrink-0 transition-colors duration-150',
              collapsed ? 'w-5 h-5' : 'w-[18px] h-[18px]',
              isActive ? 'text-accent-blue' : 'text-text-muted',
            )}
            strokeWidth={isActive ? 2.1 : 1.7}
          />

          {/* Label — fades when collapsed */}
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span
                key="label"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.14 }}
                className={cn(
                  'text-sm font-medium whitespace-nowrap overflow-hidden',
                  isActive ? 'text-text-primary' : 'text-text-secondary',
                )}
              >
                {label}
              </motion.span>
            )}
          </AnimatePresence>

          {/* Subtle active tint */}
          {isActive && (
            <div className="absolute inset-0 rounded-md bg-accent-blue/5 pointer-events-none" />
          )}
        </div>
      )}
    </NavLink>
  )
}

// ── SidebarInner ───────────────────────────────────────────────────────────────

interface SidebarInnerProps {
  collapsed: boolean
  onToggleCollapse?: () => void
  onClose?: () => void
}

function SidebarInner({ collapsed, onToggleCollapse, onClose }: SidebarInnerProps) {
  const { user, logout } = useAuthContext()

  return (
    <div className="flex flex-col h-full">
      {/* ── Logo row ── */}
      <div
        className={cn(
          'flex items-center h-[57px] border-b border-border-subtle flex-shrink-0',
          collapsed ? 'justify-center px-2' : 'px-4',
        )}
      >
        {/* CARDEX wordmark */}
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              key="wordmark"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.18 }}
              className="mr-auto flex flex-col overflow-hidden"
            >
              <span
                className="font-bold text-[13px] tracking-[0.22em] leading-tight"
                style={{
                  background: 'linear-gradient(125deg, var(--color-blue) 0%, #c8d8ff 60%, #ffffff 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                CARDEX
              </span>
              <span className="text-[8px] font-semibold tracking-[0.3em] text-text-muted uppercase leading-tight mt-0.5">
                Workspace
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Collapse toggle (desktop) or close (mobile drawer) */}
        {onClose ? (
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
            aria-label="Close sidebar"
          >
            <X className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={onToggleCollapse}
            className={cn(
              'p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150',
              collapsed && 'mx-auto',
            )}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <motion.div
              animate={{ rotate: collapsed ? 180 : 0 }}
              transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            >
              <PanelLeftOpen className="w-4 h-4" />
            </motion.div>
          </button>
        )}
      </div>

      {/* Car icon shown only when collapsed */}
      <AnimatePresence initial={false}>
        {collapsed && (
          <motion.div
            key="car-icon"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="flex justify-center py-3 border-b border-border-subtle"
          >
            <Car className="w-5 h-5 text-accent-blue" strokeWidth={1.75} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 scrollbar-none">
        {NAV_ITEMS.map((item) => (
          <NavItem
            key={item.to}
            {...item}
            collapsed={collapsed}
            onClick={onClose}
          />
        ))}
      </nav>

      {/* ── User section ── */}
      <div className="border-t border-border-subtle p-3 flex-shrink-0">
        <div
          className={cn(
            'flex items-center gap-2.5 px-2 py-2 rounded-md',
            collapsed && 'justify-center',
          )}
        >
          <Avatar name={user?.name ?? 'User'} size="sm" />

          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div
                key="user-info"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="flex-1 min-w-0 overflow-hidden"
              >
                <p className="text-xs font-semibold text-text-primary truncate leading-tight">
                  {user?.name ?? 'User'}
                </p>
                <p className="text-2xs text-text-muted truncate leading-tight capitalize mt-0.5">
                  {user?.role ?? 'dealer'}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.button
                key="logout-btn"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.12 }}
                onClick={logout}
                className="p-1.5 rounded-md text-text-muted hover:text-accent-rose hover:bg-glass-medium transition-colors duration-150 flex-shrink-0"
                aria-label="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

// ── Shell ──────────────────────────────────────────────────────────────────────

const SIDEBAR_SPRING = { duration: 0.32, ease: [0.25, 0.46, 0.45, 0.94] as const }

export default function Shell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { dark, toggle } = useDark()
  const location = useLocation()

  const sidebarWidth = collapsed ? 72 : 260

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: 'var(--bg-primary)' }}
    >
      {/* ── Mobile drawer overlay ── */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="overlay"
              className="fixed inset-0 z-[60] bg-black/60 md:hidden"
              style={{ backdropFilter: 'blur(4px)' }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="drawer"
              className="fixed top-0 left-0 h-full z-[70] w-72 md:hidden border-r border-border-subtle overflow-hidden"
              style={{
                background: 'rgba(18, 18, 30, 0.98)',
                backdropFilter: 'blur(24px)',
              }}
              initial={{ x: -288 }}
              animate={{ x: 0 }}
              exit={{ x: -288 }}
              transition={{ type: 'spring', stiffness: 310, damping: 32 }}
            >
              <SidebarInner
                collapsed={false}
                onClose={() => setMobileOpen(false)}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ── Desktop sidebar (in flex flow, always visible) ── */}
      <motion.aside
        className="hidden md:flex flex-col flex-shrink-0 border-r border-border-subtle overflow-hidden"
        animate={{ width: sidebarWidth }}
        transition={SIDEBAR_SPRING}
        style={{
          background: 'rgba(22, 22, 38, 0.82)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
        }}
      >
        <SidebarInner
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((c) => !c)}
        />
      </motion.aside>

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Topbar */}
        <header
          className="flex-shrink-0 h-14 flex items-center gap-3 px-4 border-b border-border-subtle z-20"
          style={{
            background: 'rgba(14, 14, 20, 0.80)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
          }}
        >
          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen(true)}
            className="md:hidden w-9 h-9 flex items-center justify-center rounded-md text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Breadcrumb */}
          <div className="flex-1 min-w-0 hidden sm:block">
            <Breadcrumb />
          </div>

          {/* Right cluster */}
          <div className="flex items-center gap-1.5 ml-auto">
            <SearchCommand />

            <div className="w-px h-5 bg-border-subtle mx-0.5" />

            <NotificationBell />

            {/* Dark mode toggle */}
            <button
              onClick={toggle}
              className="w-9 h-9 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={dark ? 'moon' : 'sun'}
                  initial={{ rotate: -30, opacity: 0, scale: 0.7 }}
                  animate={{ rotate: 0, opacity: 1, scale: 1 }}
                  exit={{ rotate: 30, opacity: 0, scale: 0.7 }}
                  transition={{ duration: 0.18 }}
                >
                  {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
                </motion.div>
              </AnimatePresence>
            </button>
          </div>
        </header>

        {/* Page content with route transition */}
        <main
          className="flex-1 overflow-y-auto pb-20 md:pb-0"
          style={{ background: 'var(--bg-primary)' }}
        >
          {/* Subtle gradient overlay at top */}
          <div
            className="pointer-events-none fixed top-14 left-0 right-0 h-24 z-10 md:hidden"
            style={{
              background: 'linear-gradient(to bottom, var(--bg-primary) 0%, transparent 100%)',
            }}
          />

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 7 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="min-h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <MobileNav />
    </div>
  )
}
