import React, { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard, Car, KanbanSquare, Users, GitPullRequest,
  MessageSquare, Calendar, BarChart3, Settings, Menu, X, Bell,
  Car as CarIcon, ChevronRight, Moon, Sun, FileSearch,
} from 'lucide-react'
import MobileNav from './MobileNav'
import Avatar from '../components/Avatar'
import { useAuthContext } from '../auth/AuthContext'

const navItems = [
  { to: '/',          label: 'Dashboard',  icon: LayoutDashboard, end: true },
  { to: '/vehicles',  label: 'Vehicles',   icon: Car },
  { to: '/kanban',    label: 'Kanban',     icon: KanbanSquare },
  { to: '/contacts',  label: 'Contacts',   icon: Users },
  { to: '/deals',     label: 'Deals',      icon: GitPullRequest },
  { to: '/inbox',     label: 'Inbox',      icon: MessageSquare },
  { to: '/calendar',  label: 'Calendar',   icon: Calendar },
  { to: '/finance',   label: 'Finance',    icon: BarChart3 },
  { to: '/check',     label: 'VIN Check',  icon: FileSearch },
  { to: '/settings',  label: 'Settings',   icon: Settings },
]

function useDark() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  function toggle() {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    setDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }
  return { dark, toggle }
}

export default function Shell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuthContext()
  const { dark, toggle } = useDark()

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex">
      {/* Sidebar overlay (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:static top-0 left-0 h-full z-40 w-60 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col transition-transform duration-200 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 h-14 border-b border-gray-200 dark:border-gray-800 shrink-0">
          <div className="w-7 h-7 bg-brand-600 rounded-lg flex items-center justify-center">
            <CarIcon className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-gray-900 dark:text-white tracking-tight">CARDEX</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="ml-auto md:hidden p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium mb-0.5 transition-colors ${
                  isActive
                    ? 'bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-400'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-100'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="border-t border-gray-200 dark:border-gray-800 p-3 shrink-0">
          <div className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer group">
            <Avatar name={user?.name ?? 'User'} size="sm" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{user?.name}</p>
              <p className="text-[10px] text-gray-400 truncate">{user?.email}</p>
            </div>
            <ChevronRight className="w-3 h-3 text-gray-300 group-hover:text-gray-500 transition-colors" />
          </div>
          <button
            onClick={logout}
            className="mt-1 w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:text-red-600 rounded transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-14 bg-white/80 dark:bg-gray-900/80 backdrop-blur border-b border-gray-200 dark:border-gray-800 flex items-center gap-3 px-4 shrink-0 sticky top-0 z-20">
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 min-w-[44px] min-h-[44px] flex items-center justify-center"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex-1" />
          <button
            onClick={toggle}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
            aria-label="Toggle dark mode"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <button className="relative p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center">
            <Bell className="w-4 h-4" />
            <span className="absolute top-2 right-2 w-1.5 h-1.5 bg-red-500 rounded-full" />
          </button>
          <Avatar name={user?.name ?? 'User'} size="sm" className="md:hidden" />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto pb-20 md:pb-6">
          <Outlet />
        </main>
      </div>

      <MobileNav />
    </div>
  )
}
