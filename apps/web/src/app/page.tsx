import Link from 'next/link'
import { ArrowRight, BarChart2, FileSearch, LayoutDashboard, Globe } from 'lucide-react'

export default function HomePage() {
  return (
    <div className="flex flex-col">

      {/* Hero */}
      <section className="mx-auto flex max-w-screen-xl flex-col items-center px-4 py-24 text-center">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-4 py-1.5 text-sm text-brand-400">
          <Globe size={14} />
          ES · FR · DE · NL · BE · CH
        </div>
        <h1 className="mb-4 max-w-3xl text-5xl font-extrabold leading-tight tracking-tight text-white lg:text-6xl">
          The pan-European<br />
          <span className="text-brand-400">used car intelligence</span><br />
          platform
        </h1>
        <p className="mb-8 max-w-xl text-lg text-surface-muted">
          Every listing, every dealer, every price — aggregated and analysed
          across 6 countries in real time. Free VIN history. Professional dealer tools.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/search"
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-6 py-3 font-semibold text-white hover:bg-brand-600 transition-colors"
          >
            Search cars <ArrowRight size={16} />
          </Link>
          <Link
            href="/analytics"
            className="flex items-center gap-2 rounded-xl border border-surface-border px-6 py-3 font-semibold text-surface-muted hover:text-white hover:border-surface-muted transition-colors"
          >
            Market intelligence
          </Link>
        </div>
      </section>

      {/* 4 Product pillars */}
      <section className="mx-auto w-full max-w-screen-xl px-4 pb-24">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map(p => (
            <Link key={p.title} href={p.href}
              className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface-card p-6 hover:border-brand-500/50 hover:shadow-lg hover:shadow-brand-500/5 transition-all group">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10 text-brand-400 group-hover:bg-brand-500/20 transition-colors">
                <p.icon size={24} />
              </div>
              <div>
                <h3 className="font-semibold text-white">{p.title}</h3>
                <p className="mt-1 text-sm text-surface-muted">{p.desc}</p>
              </div>
              <div className="mt-auto flex items-center gap-1 text-sm font-medium text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity">
                Explore <ArrowRight size={14} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Stats bar */}
      <section className="border-t border-surface-border bg-surface-card">
        <div className="mx-auto grid max-w-screen-xl grid-cols-2 divide-x divide-surface-border px-4 sm:grid-cols-4">
          {[
            { label: 'Listings indexed', value: '5M+' },
            { label: 'Countries', value: '6' },
            { label: 'VIN checks', value: 'Free' },
            { label: 'Avg search latency', value: '<50ms' },
          ].map(s => (
            <div key={s.label} className="py-6 text-center">
              <p className="font-mono text-2xl font-bold text-brand-400">{s.value}</p>
              <p className="mt-1 text-xs text-surface-muted">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

    </div>
  )
}

const PILLARS = [
  {
    title: 'Marketplace',
    href: '/search',
    icon: Globe,
    desc: 'Every used car listing in Europe. Redirect-only model — we send you to the original listing.',
  },
  {
    title: 'Market Intelligence',
    href: '/analytics',
    icon: BarChart2,
    desc: 'TradingView-style price charts, market depth order book, geographic heatmap, volatility index.',
  },
  {
    title: 'VIN History',
    href: '/vin',
    icon: FileSearch,
    desc: 'Free vehicle history report. Mileage timeline, accidents, ownership, stolen check. No signup.',
  },
  {
    title: 'Dealer Portal',
    href: '/dashboard',
    icon: LayoutDashboard,
    desc: 'Inventory management, multiposting, CRM, AI pricing, marketing audit. Beat DealCar.io.',
  },
]
