'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import { BarChart2, Car, FileSearch, LayoutDashboard } from 'lucide-react'

const NAV = [
  { href: '/search', label: 'Marketplace', icon: Car },
  { href: '/analytics', label: 'Market Intelligence', icon: BarChart2 },
  { href: '/vin', label: 'VIN History', icon: FileSearch },
  { href: '/dashboard', label: 'Dealer Portal', icon: LayoutDashboard },
]

export function Navbar() {
  const pathname = usePathname()
  return (
    <nav className="sticky top-0 z-50 border-b border-surface-border bg-surface-card/80 backdrop-blur-sm">
      <div className="mx-auto flex max-w-screen-xl items-center justify-between px-4 py-3">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-mono text-xl font-bold tracking-tight">
          <span className="text-brand-400">CARD</span>
          <span className="text-white">EX</span>
        </Link>

        {/* Links */}
        <div className="hidden items-center gap-1 md:flex">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors',
                pathname.startsWith(href)
                  ? 'bg-brand-500/10 text-brand-400'
                  : 'text-surface-muted hover:bg-surface-hover hover:text-white'
              )}
            >
              <Icon size={15} />
              {label}
            </Link>
          ))}
        </div>

        {/* CTA */}
        <Link
          href="/dashboard/login"
          className="rounded-md bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors"
        >
          Dealer Login
        </Link>
      </div>
    </nav>
  )
}
