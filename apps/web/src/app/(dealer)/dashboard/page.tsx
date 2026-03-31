'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Car, Users, BarChart2, Megaphone, TrendingUp, AlertCircle } from 'lucide-react'

/**
 * Dealer Dashboard — home page for logged-in dealers.
 * In production this fetches real data via useEffect + SWR.
 * For now renders the layout + key metric placeholders.
 */
export default function DealerDashboard() {
  // Token would come from cookie/localStorage in production
  const [token] = useState<string | null>(null)

  if (!token) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center px-4">
        <h1 className="text-3xl font-bold text-white">Dealer Portal</h1>
        <p className="text-surface-muted max-w-md">
          Manage your inventory, multipost to all platforms, track leads and get AI-powered pricing intelligence.
        </p>
        <div className="flex gap-3">
          <Link href="/dashboard/login"
            className="rounded-lg bg-brand-500 px-6 py-2.5 font-medium text-white hover:bg-brand-600 transition-colors">
            Login
          </Link>
          <Link href="/dashboard/register"
            className="rounded-lg border border-surface-border px-6 py-2.5 font-medium text-surface-muted hover:text-white transition-colors">
            Register free
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-white">Dashboard</h1>

      {/* KPI cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: 'Active listings', value: '—', icon: Car, href: '/dashboard/inventory' },
          { label: 'Open leads', value: '—', icon: Users, href: '/dashboard/leads' },
          { label: 'Market position', value: '—', icon: TrendingUp, href: '/analytics' },
          { label: 'Marketing score', value: '—', icon: BarChart2, href: '/dashboard/audit' },
        ].map(({ label, value, icon: Icon, href }) => (
          <Link key={label} href={href}
            className="flex items-center gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/50 transition-colors group">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-400 group-hover:bg-brand-500/20">
              <Icon size={20} />
            </div>
            <div>
              <p className="text-xs text-surface-muted">{label}</p>
              <p className="font-mono text-2xl font-bold text-white">{value}</p>
            </div>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid gap-4 sm:grid-cols-3">
        <QuickAction
          href="/dashboard/inventory/new"
          icon={Car}
          title="Add vehicle"
          desc="Manual entry or import from URL"
        />
        <QuickAction
          href="/dashboard/publish"
          icon={Megaphone}
          title="Multipost"
          desc="Publish to AutoScout24, mobile.de & more"
        />
        <QuickAction
          href="/dashboard/audit"
          icon={AlertCircle}
          title="Marketing audit"
          desc="AI-powered improvement suggestions"
        />
      </div>
    </div>
  )
}

function QuickAction({ href, icon: Icon, title, desc }: {
  href: string; icon: React.FC<{ size?: number }>; title: string; desc: string
}) {
  return (
    <Link href={href}
      className="flex items-start gap-4 rounded-xl border border-surface-border bg-surface-card p-5 hover:border-brand-500/50 transition-colors group">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-hover text-surface-muted group-hover:bg-brand-500/10 group-hover:text-brand-400 transition-colors">
        <Icon size={18} />
      </div>
      <div>
        <p className="font-medium text-white">{title}</p>
        <p className="mt-0.5 text-xs text-surface-muted">{desc}</p>
      </div>
    </Link>
  )
}
