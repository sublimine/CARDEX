import React from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Car, MessageSquare, GitPullRequest, MoreHorizontal } from 'lucide-react'

const tabs = [
  { to: '/',        label: 'Dashboard', icon: LayoutDashboard },
  { to: '/vehicles', label: 'Vehicles',  icon: Car },
  { to: '/inbox',    label: 'Inbox',     icon: MessageSquare },
  { to: '/deals',    label: 'Deals',     icon: GitPullRequest },
  { to: '/settings', label: 'More',      icon: MoreHorizontal },
]

export default function MobileNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-t border-gray-200 dark:border-gray-700 md:hidden">
      <div className="flex items-center justify-around h-16 px-2 safe-area-bottom">
        {tabs.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 flex-1 h-full min-w-[44px] rounded-lg transition-colors ${
                isActive
                  ? 'text-brand-600 dark:text-brand-400'
                  : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300'
              }`
            }
          >
            <Icon className="w-5 h-5" strokeWidth={1.75} />
            <span className="text-[10px] font-medium leading-none">{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
