import React, { useState, useCallback } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Car, KanbanSquare, Users, GitPullRequest,
  MessageSquare, Calendar, BarChart3, Settings, FileSearch,
  ChevronLeft, ChevronRight, Sun, Moon, LogOut, X, Menu,
} from 'lucide-react'
import MobileNav from './MobileNav'
import Breadcrumb from './Breadcrumb'
import SearchCommand from './SearchCommand'
import NotificationBell from './NotificationBell'
import Avatar from '../components/Avatar'
import { useAuthContext } from '../auth/AuthContext'
import { cn } from '../lib/cn'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true  },
  { to: '/vehicles',  label: 'Vehicles',  icon: Car,             end: false },
  { to: '/kanban',    label: 'Kanban',    icon: KanbanSquare,    end: false },
  { to: '/contacts',  label: 'Contacts',  icon: Users,           end: false },
  { to: '/deals',     label: 'Deals',     icon: GitPullRequest,  end: false },
  { to: '/inbox',     label: 'Inbox',     icon: MessageSquare,   end: false },
  { to: '/calendar',  label: 'Calendar',  icon: Calendar,        end: false },
  { to: '/finance',   label: 'Finance',   icon: BarChart3,       end: false },
  { to: '/check',     label: 'VIN Check', icon: FileSearch,      end: false },
  { to: '/settings',  label: 'Settings',  icon: Settings,        end: false },
] as const

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

interface NavItemProps { to: string; label: string; icon: React.ElementType; end?: boolean; collapsed: boolean; onClick?: () => void }

function NavItem({ to, label, icon: Icon, end, collapsed, onClick }: NavItemProps) {
  return (
    <NavLink to={to} end={end} onClick={onClick} style={{ display: 'block', padding: '0 10px', marginBottom: 3 }}>
      {({ isActive }) => (
        <div
          title={collapsed ? label : undefined}
          style={{
            display: 'flex', alignItems: 'center',
            gap: collapsed ? 0 : 11,
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? '11px' : '10px 13px',
            borderRadius: 12,
            background: isActive
              ? 'rgba(124,58,237,0.20)'
              : 'transparent',
            border: isActive
              ? '1px solid rgba(124,58,237,0.40)'
              : '1px solid transparent',
            boxShadow: isActive
              ? '0 0 24px rgba(124,58,237,0.20), inset 0 1px 0 rgba(255,255,255,0.10)'
              : 'none',
            backdropFilter: isActive ? 'blur(16px) saturate(180%)' : undefined,
            WebkitBackdropFilter: isActive ? 'blur(16px) saturate(180%)' : undefined,
            cursor: 'pointer',
            transition: 'all 0.2s cubic-bezier(0.22,1,0.36,1)',
          }}
          onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.07)' }}
          onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
        >
          <Icon
            style={{
              width: 16, height: 16, flexShrink: 0,
              color: isActive ? '#c4b5fd' : '#94a3b8',
              filter: isActive ? 'drop-shadow(0 0 6px rgba(196,181,253,0.55))' : 'none',
              transition: 'color 0.2s, filter 0.2s',
            }}
            strokeWidth={isActive ? 2.3 : 1.8}
          />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span
                key="lbl"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                style={{
                  fontSize: 13,
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? '#f8fafc' : '#cbd5e1',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  fontFamily: 'Inter, system-ui, sans-serif',
                  letterSpacing: isActive ? '0.01em' : '0',
                }}
              >
                {label}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      )}
    </NavLink>
  )
}

function SidebarInner({ collapsed, onToggle, onClose }: { collapsed: boolean; onToggle?: () => void; onClose?: () => void }) {
  const { user, logout } = useAuthContext()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Logo */}
      <div style={{
        display: 'flex', alignItems: 'center', height: 60, flexShrink: 0,
        padding: collapsed ? '0 12px' : '0 18px',
        justifyContent: collapsed ? 'center' : 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
      }}>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div key="logo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
              <div style={{
                fontSize: 15, fontWeight: 900, letterSpacing: '0.20em',
                background: 'linear-gradient(120deg, #a78bfa 0%, #60a5fa 55%, #67e8f9 100%)',
                WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
                fontFamily: 'Inter, system-ui, sans-serif',
              }}>
                CARDEX
              </div>
              <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: '0.32em', color: '#64748b', textTransform: 'uppercase', marginTop: 2, fontFamily: 'Inter, system-ui, sans-serif' }}>
                Workspace
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={onClose ?? onToggle}
          style={{
            padding: 7, borderRadius: 9, color: '#cbd5e1', cursor: 'pointer',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.10)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.color = '#f8fafc' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = '#cbd5e1' }}
        >
          {onClose
            ? <X style={{ width: 14, height: 14 }} />
            : <motion.div animate={{ rotate: collapsed ? 180 : 0 }} transition={{ duration: 0.25 }}>
                <ChevronLeft style={{ width: 14, height: 14 }} />
              </motion.div>
          }
        </button>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '10px 0' }}>
        {NAV.map(item => (
          <NavItem key={item.to} {...item} collapsed={collapsed} onClick={onClose} />
        ))}
      </nav>

      {/* User */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', padding: '12px 10px', flexShrink: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 12px', borderRadius: 12,
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.10)',
          backdropFilter: 'blur(12px)',
        }}>
          <Avatar name={user?.name ?? 'User'} size="sm" />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div key="uinfo" initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: 'auto' }} exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.15 }} style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#f8fafc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'Inter, system-ui' }}>{user?.name ?? 'User'}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', textTransform: 'capitalize', fontFamily: 'Inter, system-ui' }}>{user?.role ?? 'dealer'}</div>
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.button
                key="logout"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onClick={logout}
                style={{
                  padding: 7, borderRadius: 8,
                  color: '#cbd5e1',
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.10)',
                  cursor: 'pointer', flexShrink: 0,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(225,29,72,0.15)'; e.currentTarget.style.borderColor = 'rgba(225,29,72,0.35)'; e.currentTarget.style.color = '#fca5a5' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.10)'; e.currentTarget.style.color = '#cbd5e1' }}
              >
                <LogOut style={{ width: 13, height: 13 }} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

const EASE = [0.32, 0.72, 0, 1] as const

export default function Shell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { dark, toggle } = useDark()
  const location = useLocation()
  const W = collapsed ? 64 : 240

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
      background: 'transparent', /* The global .cx-mesh paints behind */
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              key="ov"
              style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(10,10,26,0.6)', backdropFilter: 'blur(12px)' }}
              className="md:hidden"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              key="dr"
              style={{
                position: 'fixed', top: 0, left: 0, height: '100%', zIndex: 70, width: 240,
                background: 'rgba(10,10,26,0.65)',
                backdropFilter: 'blur(32px) saturate(180%)',
                WebkitBackdropFilter: 'blur(32px) saturate(180%)',
                borderRight: '1px solid rgba(255,255,255,0.12)',
                boxShadow: '8px 0 32px rgba(0,0,0,0.5)',
              }}
              className="md:hidden"
              initial={{ x: -240 }} animate={{ x: 0 }} exit={{ x: -240 }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            >
              <SidebarInner collapsed={false} onClose={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Desktop sidebar — REAL glass: mesh colors visible through */}
      <motion.aside
        animate={{ width: W }}
        transition={{ duration: 0.28, ease: EASE }}
        className="hidden md:flex flex-col flex-shrink-0 overflow-hidden"
        style={{
          background: 'rgba(10,10,26,0.55)',
          backdropFilter: 'blur(32px) saturate(180%)',
          WebkitBackdropFilter: 'blur(32px) saturate(180%)',
          borderRight: '1px solid rgba(255,255,255,0.12)',
          boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.06), 4px 0 32px rgba(0,0,0,0.35)',
        }}
      >
        <SidebarInner collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      </motion.aside>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Topbar — REAL glass */}
        <header style={{
          flexShrink: 0,
          height: 60,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '0 22px',
          background: 'rgba(10,10,26,0.50)',
          backdropFilter: 'blur(24px) saturate(180%)',
          WebkitBackdropFilter: 'blur(24px) saturate(180%)',
          borderBottom: '1px solid rgba(255,255,255,0.10)',
          boxShadow: 'inset 0 -1px 0 rgba(255,255,255,0.04)',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}>
          <button
            onClick={() => setMobileOpen(true)}
            className="md:hidden"
            style={{
              padding: 9, borderRadius: 10, color: '#cbd5e1',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.10)',
              cursor: 'pointer',
            }}
          >
            <Menu style={{ width: 16, height: 16 }} />
          </button>

          <div style={{ flex: 1, minWidth: 0 }} className="hidden sm:block">
            <Breadcrumb />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
            <SearchCommand />
            <div style={{ width: 1, height: 20, background: 'rgba(255,255,255,0.10)', margin: '0 6px' }} />
            <NotificationBell />
            <button
              onClick={toggle}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                width: 34, height: 34, borderRadius: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#cbd5e1',
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.10)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.color = '#f8fafc' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#cbd5e1' }}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={dark ? 'd' : 'l'}
                  initial={{ rotate: -20, opacity: 0 }}
                  animate={{ rotate: 0, opacity: 1 }}
                  exit={{ rotate: 20, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  {dark ? <Sun style={{ width: 14, height: 14 }} /> : <Moon style={{ width: 14, height: 14 }} />}
                </motion.div>
              </AnimatePresence>
            </button>
          </div>
        </header>

        {/* Content — transparent so the mesh shows through */}
        <main style={{
          flex: 1,
          overflowY: 'auto',
          background: 'transparent',
        }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: EASE }}
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
