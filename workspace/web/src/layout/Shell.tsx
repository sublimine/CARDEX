import React, { useState, useCallback } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Car, KanbanSquare, Users, GitPullRequest,
  MessageSquare, Calendar, BarChart3, Settings, FileSearch,
  ChevronLeft, ChevronRight, Sun, Moon, LogOut, X, Menu, Activity,
} from 'lucide-react'
import MobileNav from './MobileNav'
import Breadcrumb from './Breadcrumb'
import SearchCommand from './SearchCommand'
import NotificationBell from './NotificationBell'
import Avatar from '../components/Avatar'
import { useAuthContext } from '../auth/AuthContext'

// ── Navigation groups (QClay-style sectioned layout) ──────────────────────

const NAV_GROUPS = [
  {
    label: null,
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true  },
      { to: '/vehicles',  label: 'Vehicles',  icon: Car,             end: false },
      { to: '/kanban',    label: 'Kanban',    icon: KanbanSquare,    end: false },
    ],
  },
  {
    label: 'CRM',
    items: [
      { to: '/contacts', label: 'Contacts', icon: Users,          end: false },
      { to: '/deals',    label: 'Deals',    icon: GitPullRequest, end: false },
      { to: '/inbox',    label: 'Inbox',    icon: MessageSquare,  end: false },
      { to: '/calendar', label: 'Calendar', icon: Calendar,       end: false },
    ],
  },
  {
    label: 'TOOLS',
    items: [
      { to: '/finance',  label: 'Finance',   icon: BarChart3,  end: false },
      { to: '/terminal',  label: 'Terminal',  icon: Activity,   end: false },
      { to: '/check',    label: 'VIN Check', icon: FileSearch, end: false },
      { to: '/settings', label: 'Settings',  icon: Settings,   end: false },
    ],
  },
] as const

// ── Theme-aware style factories ────────────────────────────────────────────

function sidebarBg(dark: boolean): React.CSSProperties {
  return {
    background: dark
      ? 'rgba(10, 10, 26, 0.64)'
      : 'rgba(255, 255, 255, 0.78)',
    backdropFilter: 'blur(40px) saturate(180%)',
    WebkitBackdropFilter: 'blur(40px) saturate(180%)',
    borderRight: dark
      ? '1px solid rgba(255,255,255,0.10)'
      : '1px solid rgba(0,0,0,0.08)',
    boxShadow: dark
      ? 'inset -1px 0 0 rgba(255,255,255,0.05), 4px 0 40px rgba(0,0,0,0.40)'
      : '4px 0 24px rgba(0,0,0,0.07)',
  }
}

function topbarBg(dark: boolean): React.CSSProperties {
  return {
    background: dark
      ? 'rgba(10, 10, 26, 0.54)'
      : 'rgba(255, 255, 255, 0.76)',
    backdropFilter: 'blur(28px) saturate(180%)',
    WebkitBackdropFilter: 'blur(28px) saturate(180%)',
    borderBottom: dark
      ? '1px solid rgba(255,255,255,0.09)'
      : '1px solid rgba(0,0,0,0.07)',
    boxShadow: dark
      ? 'inset 0 -1px 0 rgba(255,255,255,0.04)'
      : '0 1px 0 rgba(0,0,0,0.05)',
  }
}

// ── Dark mode hook ─────────────────────────────────────────────────────────

function useDark() {
  const [dark, setDark] = useState(() => !document.documentElement.classList.contains('light'))
  const toggle = useCallback(() => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    document.documentElement.classList.toggle('light', !next)
    setDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }, [dark])
  return { dark, toggle }
}

// ── Logomark (collapsed) ───────────────────────────────────────────────────

function Logomark({ dark, neutralAccent }: { dark: boolean; neutralAccent?: boolean }) {
  return (
    <div style={{
      width: 32,
      height: 32,
      borderRadius: 9,
      background: neutralAccent
        ? 'linear-gradient(135deg, #0891b2 0%, #22d3ee 100%)'
        : 'linear-gradient(135deg, #7c3aed 0%, #2563eb 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
      boxShadow: neutralAccent
        ? (dark ? '0 0 22px rgba(34,211,238,0.34)' : '0 2px 10px rgba(8,145,178,0.28)')
        : (dark ? '0 0 22px rgba(124,58,237,0.38)' : '0 2px 10px rgba(124,58,237,0.30)'),
    }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11a2 2 0 012 2v3"/>
        <rect x="9" y="11" width="14" height="10" rx="2"/>
      </svg>
    </div>
  )
}

// ── NavItem ────────────────────────────────────────────────────────────────

interface NavItemProps {
  to: string
  label: string
  icon: React.ElementType
  end?: boolean
  collapsed: boolean
  dark: boolean
  neutralAccent?: boolean
  onClick?: () => void
}

function NavItem({ to, label, icon: Icon, end, collapsed, dark, neutralAccent, onClick }: NavItemProps) {
  const [hovered, setHovered] = useState(false)

  // On the terminal route the active accent goes neutral cyan instead of the
  // brand violet, so the chrome reads as pure dark/white alongside the page.
  const acc = neutralAccent
    ? { bgD: 'rgba(34,211,238,0.16)', bgL: 'rgba(8,145,178,0.10)', bdD: 'rgba(34,211,238,0.34)', bdL: 'rgba(8,145,178,0.24)', icoD: '#67e8f9', icoL: '#0891b2', lblL: '#0e3a44', glow: 'rgba(34,211,238,0.18)', icoGlow: 'rgba(103,232,249,0.45)' }
    : { bgD: 'rgba(124,58,237,0.18)', bgL: 'rgba(124,58,237,0.10)', bdD: 'rgba(124,58,237,0.36)', bdL: 'rgba(124,58,237,0.22)', icoD: '#c4b5fd', icoL: '#7c3aed', lblL: '#3b0764', glow: 'rgba(124,58,237,0.16)', icoGlow: 'rgba(196,181,253,0.50)' }

  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      style={{ display: 'block', padding: collapsed ? '0 8px' : '0 10px', marginBottom: 2 }}
    >
      {({ isActive }) => {
        const activeBg    = dark ? acc.bgD : acc.bgL
        const activeBorder = dark ? acc.bdD : acc.bdL
        const hoverBg     = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
        const iconColor   = isActive ? (dark ? acc.icoD : acc.icoL) : (dark ? '#94a3b8' : '#64748b')
        const labelColor  = isActive ? (dark ? '#f8fafc' : acc.lblL)  : (dark ? '#cbd5e1' : '#374151')

        return (
          <div
            title={collapsed ? label : undefined}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: collapsed ? 0 : 10,
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? '10px' : '9px 12px',
              borderRadius: 10,
              background: isActive ? activeBg : hovered ? hoverBg : 'transparent',
              border: `1px solid ${isActive ? activeBorder : 'transparent'}`,
              boxShadow: isActive
                ? dark
                  ? `0 0 18px ${acc.glow}, inset 0 1px 0 rgba(255,255,255,0.08)`
                  : 'inset 0 1px 0 rgba(255,255,255,0.50)'
                : 'none',
              cursor: 'pointer',
              transition: 'all 170ms cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          >
            <Icon
              style={{
                width: 15,
                height: 15,
                flexShrink: 0,
                color: iconColor,
                filter: isActive && dark ? `drop-shadow(0 0 5px ${acc.icoGlow})` : 'none',
                transition: 'color 170ms, filter 170ms',
              }}
              strokeWidth={isActive ? 2.2 : 1.75}
            />
            <AnimatePresence initial={false}>
              {!collapsed && (
                <motion.span
                  key="lbl"
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{ duration: 0.13 }}
                  style={{
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 450,
                    color: labelColor,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    letterSpacing: '0.006em',
                    fontFamily: 'Inter, system-ui, sans-serif',
                    transition: 'color 170ms',
                  }}
                >
                  {label}
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        )
      }}
    </NavLink>
  )
}

// ── NavGroup ───────────────────────────────────────────────────────────────

interface NavGroupProps {
  label: string | null
  items: ReadonlyArray<{ to: string; label: string; icon: React.ElementType; end?: boolean }>
  collapsed: boolean
  dark: boolean
  neutralAccent?: boolean
  onItemClick?: () => void
}

function NavGroup({ label, items, collapsed, dark, neutralAccent, onItemClick }: NavGroupProps) {
  return (
    <div style={{ marginBottom: 2 }}>
      <AnimatePresence initial={false}>
        {label && !collapsed && (
          <motion.div
            key="glabel"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.13 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              padding: '14px 22px 5px',
              fontSize: 9.5,
              fontWeight: 700,
              letterSpacing: '0.11em',
              color: dark ? 'rgba(255,255,255,0.27)' : 'rgba(0,0,0,0.34)',
              textTransform: 'uppercase',
              fontFamily: 'Inter, system-ui, sans-serif',
            }}>
              {label}
            </div>
          </motion.div>
        )}
        {label && collapsed && (
          <div style={{
            margin: '8px 14px 6px',
            height: 1,
            background: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.09)',
          }} />
        )}
      </AnimatePresence>
      {items.map(item => (
        <NavItem
          key={item.to}
          to={item.to}
          label={item.label}
          icon={item.icon}
          end={item.end}
          collapsed={collapsed}
          dark={dark}
          neutralAccent={neutralAccent}
          onClick={onItemClick}
        />
      ))}
    </div>
  )
}

// ── SidebarInner ───────────────────────────────────────────────────────────

interface SidebarInnerProps {
  collapsed: boolean
  dark: boolean
  neutralAccent?: boolean
  onToggle?: () => void
  onClose?: () => void
}

function SidebarInner({ collapsed, dark, neutralAccent, onToggle, onClose }: SidebarInnerProps) {
  const { user, logout } = useAuthContext()
  const navigate = useNavigate()

  const divider  = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)'
  const btnBg    = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
  const btnBorder = dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.09)'
  const btnColor = dark ? '#94a3b8' : '#64748b'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Logo area ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          height: 60,
          flexShrink: 0,
          padding: collapsed ? '0 10px' : '0 16px',
          justifyContent: collapsed ? 'center' : 'space-between',
          borderBottom: `1px solid ${divider}`,
          cursor: collapsed && onToggle ? 'pointer' : 'default',
        }}
        onClick={collapsed ? onToggle : undefined}
        title={collapsed ? 'Expand sidebar' : 'Back to home'}
        onDoubleClick={collapsed ? () => navigate('/landing') : undefined}
      >
        <AnimatePresence initial={false} mode="wait">
          {collapsed ? (
            <motion.div
              key="mark"
              initial={{ opacity: 0, scale: 0.82 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.82 }}
              transition={{ duration: 0.14 }}
            >
              <Logomark dark={dark} neutralAccent={neutralAccent} />
            </motion.div>
          ) : (
            <motion.div
              key="wordmark"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
              onClick={() => navigate('/landing')}
              style={{ cursor: 'pointer' }}
              title="Back to home"
            >
              <div style={{
                fontSize: 15,
                fontWeight: 900,
                letterSpacing: '0.18em',
                background: neutralAccent
                  ? 'linear-gradient(120deg, #22d3ee 0%, #67e8f9 55%, #cffafe 100%)'
                  : 'linear-gradient(120deg, #a78bfa 0%, #60a5fa 55%, #67e8f9 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
                fontFamily: 'Inter, system-ui, sans-serif',
                lineHeight: 1.1,
              }}>
                CARDEX
              </div>
              <div style={{
                fontSize: 8.5,
                fontWeight: 700,
                letterSpacing: '0.28em',
                color: dark ? '#475569' : '#94a3b8',
                textTransform: 'uppercase',
                marginTop: 2,
                fontFamily: 'Inter, system-ui, sans-serif',
              }}>
                Workspace
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {!collapsed && (
          <button
            onClick={onClose ?? onToggle}
            style={{
              padding: 6,
              borderRadius: 8,
              color: btnColor,
              cursor: 'pointer',
              background: btnBg,
              border: `1px solid ${btnBorder}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 140ms',
              flexShrink: 0,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.10)'
              e.currentTarget.style.color = dark ? '#f8fafc' : '#0f172a'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = btnBg
              e.currentTarget.style.color = btnColor
            }}
          >
            {onClose
              ? <X style={{ width: 13, height: 13 }} />
              : <ChevronLeft style={{ width: 13, height: 13 }} />
            }
          </button>
        )}
      </div>

      {/* ── Nav groups ── */}
      <nav style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px 0' }}>
        {NAV_GROUPS.map((group, i) => (
          <NavGroup
            key={i}
            label={group.label}
            items={group.items}
            collapsed={collapsed}
            dark={dark}
            neutralAccent={neutralAccent}
            onItemClick={onClose}
          />
        ))}
      </nav>

      {/* ── User card ── */}
      <div style={{ borderTop: `1px solid ${divider}`, padding: '10px', flexShrink: 0 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: collapsed ? 0 : 9,
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? '8px' : '9px 11px',
          borderRadius: 10,
          background: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)',
          border: dark ? '1px solid rgba(255,255,255,0.09)' : '1px solid rgba(0,0,0,0.08)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
        }}>
          <Avatar name={user?.name ?? 'User'} size="sm" mono={neutralAccent} />

          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div
                key="uinfo"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.13 }}
                style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}
              >
                <div style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: dark ? '#f1f5f9' : '#0f172a',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  fontFamily: 'Inter, system-ui',
                }}>
                  {user?.name ?? 'User'}
                </div>
                <div style={{
                  fontSize: 10,
                  color: dark ? '#64748b' : '#94a3b8',
                  textTransform: 'capitalize',
                  fontFamily: 'Inter, system-ui',
                  marginTop: 1,
                }}>
                  {user?.role ?? 'dealer'}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.button
                key="logout"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={logout}
                style={{
                  padding: 6,
                  borderRadius: 7,
                  color: dark ? '#94a3b8' : '#64748b',
                  background: 'transparent',
                  border: '1px solid transparent',
                  cursor: 'pointer',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 140ms',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = dark ? 'rgba(225,29,72,0.14)' : 'rgba(225,29,72,0.08)'
                  e.currentTarget.style.borderColor = dark ? 'rgba(225,29,72,0.30)' : 'rgba(225,29,72,0.20)'
                  e.currentTarget.style.color = '#f87171'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'transparent'
                  e.currentTarget.style.borderColor = 'transparent'
                  e.currentTarget.style.color = dark ? '#94a3b8' : '#64748b'
                }}
              >
                <LogOut style={{ width: 12, height: 12 }} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

// ── Shell ──────────────────────────────────────────────────────────────────

const EASE = [0.32, 0.72, 0, 1] as const

export default function Shell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { dark, toggle } = useDark()
  const location = useLocation()
  const neutralAccent = location.pathname.startsWith('/terminal')
  const W = collapsed ? 60 : 232

  const btnColor  = dark ? '#94a3b8' : '#64748b'
  const btnBg     = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
  const btnBorder = dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.09)'

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
      background: 'transparent',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>

      {/* ── Mobile overlay + drawer ── */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="ov"
              className="md:hidden"
              style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(10,10,26,0.60)', backdropFilter: 'blur(12px)' }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="dr"
              className="md:hidden"
              style={{ position: 'fixed', top: 0, left: 0, height: '100%', zIndex: 70, width: 232, ...sidebarBg(dark) }}
              initial={{ x: -232 }}
              animate={{ x: 0 }}
              exit={{ x: -232 }}
              transition={{ type: 'spring', stiffness: 340, damping: 34 }}
            >
              <SidebarInner collapsed={false} dark={dark} neutralAccent={neutralAccent} onClose={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ── Desktop sidebar ── */}
      <motion.aside
        animate={{ width: W }}
        transition={{ duration: 0.26, ease: EASE }}
        className="hidden md:flex flex-col flex-shrink-0 relative"
        style={{ overflow: 'hidden', ...sidebarBg(dark) }}
      >
        <SidebarInner
          collapsed={collapsed}
          dark={dark}
          neutralAccent={neutralAccent}
          onToggle={() => setCollapsed(c => !c)}
        />

        {/* Expand tab — only visible when collapsed */}
        <AnimatePresence>
          {collapsed && (
            <motion.button
              key="expand-tab"
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -4 }}
              transition={{ duration: 0.15 }}
              onClick={() => setCollapsed(false)}
              title="Expand sidebar"
              style={{
                position: 'absolute',
                right: -11,
                top: '50%',
                transform: 'translateY(-50%)',
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: dark ? '#1e1e3a' : '#ffffff',
                border: dark ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(0,0,0,0.12)',
                color: dark ? '#94a3b8' : '#64748b',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: dark ? '0 2px 8px rgba(0,0,0,0.40)' : '0 2px 8px rgba(0,0,0,0.12)',
                zIndex: 20,
                flexShrink: 0,
              }}
            >
              <ChevronRight style={{ width: 11, height: 11 }} />
            </motion.button>
          )}
        </AnimatePresence>
      </motion.aside>

      {/* ── Main content area ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Topbar */}
        <header style={{
          flexShrink: 0,
          height: 60,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '0 22px',
          fontFamily: 'Inter, system-ui, sans-serif',
          ...topbarBg(dark),
        }}>
          <button
            className="md:hidden"
            onClick={() => setMobileOpen(true)}
            style={{
              padding: 8,
              borderRadius: 9,
              color: btnColor,
              background: btnBg,
              border: `1px solid ${btnBorder}`,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Menu style={{ width: 15, height: 15 }} />
          </button>

          <div style={{ flex: 1, minWidth: 0 }} className="hidden sm:block">
            <Breadcrumb />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
            <SearchCommand />
            <div style={{
              width: 1,
              height: 18,
              background: dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.10)',
              margin: '0 4px',
            }} />
            <NotificationBell />

            {/* Theme toggle */}
            <button
              onClick={toggle}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                width: 32,
                height: 32,
                borderRadius: 9,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: btnColor,
                background: btnBg,
                border: `1px solid ${btnBorder}`,
                cursor: 'pointer',
                transition: 'all 140ms',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.09)'
                e.currentTarget.style.color = dark ? '#f8fafc' : '#0f172a'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = btnBg
                e.currentTarget.style.color = btnColor
              }}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={dark ? 'd' : 'l'}
                  initial={{ rotate: -18, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={{ rotate: 18, opacity: 0 }}
                  transition={{ duration: 0.13 }}
                >
                  {dark
                    ? <Sun  style={{ width: 13, height: 13 }} />
                    : <Moon style={{ width: 13, height: 13 }} />
                  }
                </motion.div>
              </AnimatePresence>
            </button>
          </div>
        </header>

        {/* Page */}
        <main style={{ flex: 1, overflowY: 'auto', background: 'transparent' }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: EASE }}
              style={{ minHeight: '100%' }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <MobileNav />
    </div>
  )
}
