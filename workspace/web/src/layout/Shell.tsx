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
    <NavLink to={to} end={end} onClick={onClick} style={{ display: 'block', padding: '0 8px', marginBottom: 2 }}>
      {({ isActive }) => (
        <div
          title={collapsed ? label : undefined}
          style={{
            display: 'flex', alignItems: 'center',
            gap: collapsed ? 0 : 10,
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? '10px' : '9px 12px',
            borderRadius: 12,
            background: isActive ? 'rgba(91,141,248,0.14)' : 'transparent',
            border: isActive ? '1px solid rgba(91,141,248,0.26)' : '1px solid transparent',
            cursor: 'pointer',
            transition: 'all 0.15s cubic-bezier(0.32,0.72,0,1)',
          }}
          onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.04)' }}
          onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
        >
          <Icon
            style={{
              width: 16, height: 16, flexShrink: 0,
              color: isActive ? '#7aabff' : '#2e2e4e',
              transition: 'color 0.15s',
            }}
            strokeWidth={isActive ? 2.2 : 1.7}
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
                  color: isActive ? '#c8d8ff' : '#2e2e4e',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  fontFamily: 'Plus Jakarta Sans',
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
        display: 'flex', alignItems: 'center', height: 57, flexShrink: 0,
        padding: collapsed ? '0 12px' : '0 16px',
        justifyContent: collapsed ? 'center' : 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div key="logo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
              <div style={{
                fontSize: 15, fontWeight: 800, letterSpacing: '0.18em',
                background: 'linear-gradient(120deg, #5b8df8 0%, #9b9fff 55%, #e0e8ff 100%)',
                WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
                fontFamily: 'Plus Jakarta Sans',
              }}>
                CARDEX
              </div>
              <div style={{ fontSize: 8, fontWeight: 600, letterSpacing: '0.3em', color: '#1e1e38', textTransform: 'uppercase', marginTop: 1, fontFamily: 'Plus Jakarta Sans' }}>
                Workspace
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={onClose ?? onToggle}
          style={{ padding: 6, borderRadius: 8, color: '#1e1e38', cursor: 'pointer', background: 'transparent', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          {onClose
            ? <X style={{ width: 15, height: 15 }} />
            : <motion.div animate={{ rotate: collapsed ? 180 : 0 }} transition={{ duration: 0.25 }}>
                <ChevronLeft style={{ width: 15, height: 15 }} />
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
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', padding: '10px 8px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 12 }}>
          <Avatar name={user?.name ?? 'User'} size="sm" />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div key="uinfo" initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: 'auto' }} exit={{ opacity: 0, width: 0 }} transition={{ duration: 0.15 }} style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#9090b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'Plus Jakarta Sans' }}>{user?.name ?? 'User'}</div>
                <div style={{ fontSize: 10, color: '#1e1e38', textTransform: 'capitalize', fontFamily: 'Plus Jakarta Sans' }}>{user?.role ?? 'dealer'}</div>
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.button key="logout" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={logout} style={{ padding: 6, borderRadius: 8, color: '#1e1e38', background: 'transparent', border: 'none', cursor: 'pointer', flexShrink: 0 }}>
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
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#05050a', fontFamily: 'Plus Jakarta Sans' }}>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div key="ov" style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }} className="md:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileOpen(false)} />
            <motion.aside key="dr" style={{ position: 'fixed', top: 0, left: 0, height: '100%', zIndex: 70, width: 240, background: '#09090f', borderRight: '1px solid rgba(255,255,255,0.06)' }} className="md:hidden" initial={{ x: -240 }} animate={{ x: 0 }} exit={{ x: -240 }} transition={{ type: 'spring', stiffness: 320, damping: 32 }}>
              <SidebarInner collapsed={false} onClose={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <motion.aside
        animate={{ width: W }}
        transition={{ duration: 0.28, ease: EASE }}
        className="hidden md:flex flex-col flex-shrink-0 overflow-hidden"
        style={{ background: '#09090f', borderRight: '1px solid rgba(255,255,255,0.06)' }}
      >
        <SidebarInner collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      </motion.aside>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Topbar */}
        <header style={{
          flexShrink: 0, height: 56, display: 'flex', alignItems: 'center', gap: 12, padding: '0 20px',
          background: '#05050a', borderBottom: '1px solid rgba(255,255,255,0.05)',
          fontFamily: 'Plus Jakarta Sans',
        }}>
          <button onClick={() => setMobileOpen(true)} className="md:hidden" style={{ padding: 8, borderRadius: 8, color: '#1e1e38', background: 'transparent', border: 'none', cursor: 'pointer' }}>
            <Menu style={{ width: 18, height: 18 }} />
          </button>

          <div style={{ flex: 1, minWidth: 0 }} className="hidden sm:block">
            <Breadcrumb />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 'auto' }}>
            <SearchCommand />
            <div style={{ width: 1, height: 16, background: 'rgba(255,255,255,0.06)', margin: '0 4px' }} />
            <NotificationBell />
            <button
              onClick={toggle}
              style={{ width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1e1e38', background: 'transparent', border: 'none', cursor: 'pointer' }}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={dark ? 'd' : 'l'} initial={{ rotate: -20, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 20, opacity: 0 }} transition={{ duration: 0.15 }}>
                  {dark ? <Sun style={{ width: 14, height: 14 }} /> : <Moon style={{ width: 14, height: 14 }} />}
                </motion.div>
              </AnimatePresence>
            </button>
          </div>
        </header>

        {/* Content */}
        <main style={{ flex: 1, overflowY: 'auto', background: '#05050a', backgroundImage: 'radial-gradient(ellipse 80% 50% at 15% 15%, rgba(79,126,248,0.055) 0%, transparent 60%), radial-gradient(ellipse 60% 40% at 85% 85%, rgba(155,109,255,0.04) 0%, transparent 60%)' }}>
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
