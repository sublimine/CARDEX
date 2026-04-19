import React from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import { motion } from 'framer-motion'
import Card from '../components/Card'
import { Badge } from '../components/Badge'
import { TrendingDown, TrendingUp, Euro, AlertTriangle } from 'lucide-react'
import type { FinanceRow } from '../types'
import { cn } from '../lib/cn'

const MONTHLY = [
  { month: 'Nov 25', revenue: 310000, cost: 249000, margin: 61000 },
  { month: 'Dec 25', revenue: 360000, cost: 288000, margin: 72000 },
  { month: 'Jan 26', revenue: 270000, cost: 216000, margin: 54000 },
  { month: 'Feb 26', revenue: 395000, cost: 316000, margin: 79000 },
  { month: 'Mar 26', revenue: 475000, cost: 380000, margin: 95000 },
  { month: 'Apr 26', revenue: 437000, cost: 349600, margin: 87400 },
]

const TOP_VEHICLES: FinanceRow[] = [
  { vehicleId: 'v1',  vehicleName: 'BMW X5 2021',         buyPrice: 38000, sellPrice: 46500, margin: 8500,  marginPct: 22.4, soldAt: '2026-04-15' },
  { vehicleId: 'v2',  vehicleName: 'Porsche Macan 2020',   buyPrice: 44000, sellPrice: 52000, margin: 8000,  marginPct: 18.2, soldAt: '2026-04-12' },
  { vehicleId: 'v3',  vehicleName: 'Audi Q5 2021',         buyPrice: 32000, sellPrice: 38500, margin: 6500,  marginPct: 20.3, soldAt: '2026-04-10' },
  { vehicleId: 'v4',  vehicleName: 'Mercedes GLC 2020',    buyPrice: 36000, sellPrice: 42000, margin: 6000,  marginPct: 16.7, soldAt: '2026-04-08' },
  { vehicleId: 'v5',  vehicleName: 'BMW 530d 2020',        buyPrice: 28000, sellPrice: 33500, margin: 5500,  marginPct: 19.6, soldAt: '2026-04-06' },
  { vehicleId: 'v6',  vehicleName: 'VW Tiguan 2022',       buyPrice: 24000, sellPrice: 29000, margin: 5000,  marginPct: 20.8, soldAt: '2026-04-04' },
  { vehicleId: 'v7',  vehicleName: 'Skoda Octavia 2021',   buyPrice: 14000, sellPrice: 17500, margin: 3500,  marginPct: 25.0, soldAt: '2026-04-02' },
  { vehicleId: 'v8',  vehicleName: 'Toyota Yaris 2022',    buyPrice: 10500, sellPrice: 13500, margin: 3000,  marginPct: 28.6, soldAt: '2026-03-30' },
  { vehicleId: 'v9',  vehicleName: 'Renault Clio 2020',    buyPrice:  9000, sellPrice:  8200, margin:  -800, marginPct:  -8.9, soldAt: '2026-04-14' },
  { vehicleId: 'v10', vehicleName: 'Citroën C3 2019',      buyPrice:  7500, sellPrice:  7100, margin:  -400, marginPct:  -5.3, soldAt: '2026-04-11' },
]

const ALERTS = TOP_VEHICLES.filter((r) => r.margin < 0)

function fmt(n: number) {
  return `€${Math.abs(n).toLocaleString()}`
}

const stagger = {
  container: { transition: { staggerChildren: 0.07 } },
  item: { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } },
}

// Custom recharts tooltip styled to match the design system
function CustomTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div
      className="rounded-xl border border-border-subtle px-4 py-3 text-xs space-y-1"
      style={{
        background: 'var(--bg-elevated)',
        backdropFilter: 'blur(16px)',
        boxShadow: 'var(--shadow-3)',
      }}
    >
      <p className="font-semibold text-text-primary mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-6">
          <span className="flex items-center gap-1.5 text-text-secondary">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="font-medium text-text-primary">€{p.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

export default function Finance() {
  const totalRevenue = MONTHLY.reduce((s, m) => s + m.revenue, 0)
  const totalMargin  = MONTHLY.reduce((s, m) => s + m.margin,  0)
  const avgMarginPct = (totalMargin / totalRevenue * 100).toFixed(1)

  const kpis = [
    {
      label: 'Revenue (6mo)',
      value: `€${(totalRevenue / 1000).toFixed(0)}k`,
      sub: '+14% vs prior period',
      positive: true,
      icon: Euro,
    },
    {
      label: 'Gross Margin (6mo)',
      value: `€${(totalMargin / 1000).toFixed(0)}k`,
      sub: '+8% vs prior period',
      positive: true,
      icon: TrendingUp,
    },
    {
      label: 'Avg Margin %',
      value: `${avgMarginPct}%`,
      sub: `${ALERTS.length} alert${ALERTS.length !== 1 ? 's' : ''} this period`,
      positive: ALERTS.length === 0,
      icon: ALERTS.length > 0 ? AlertTriangle : TrendingUp,
    },
  ]

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Finance</h1>
          <p className="text-sm text-text-muted mt-0.5">Fleet P&amp;L · last 6 months</p>
        </div>
      </div>

      {/* KPI cards */}
      <motion.div
        variants={stagger.container}
        initial="initial"
        animate="animate"
        className="grid grid-cols-1 sm:grid-cols-3 gap-3"
      >
        {kpis.map(({ label, value, sub, positive, icon: Icon }) => (
          <motion.div key={label} variants={stagger.item} transition={{ duration: 0.3 }}>
            <Card>
              <div className="flex items-start justify-between mb-3">
                <div
                  className={cn(
                    'w-9 h-9 rounded-lg flex items-center justify-center',
                    positive
                      ? 'bg-emerald-500/10 text-accent-emerald'
                      : 'bg-rose-500/10 text-accent-rose',
                  )}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <span
                  className={cn(
                    'text-[10px] font-medium flex items-center gap-0.5',
                    positive ? 'text-accent-emerald' : 'text-accent-rose',
                  )}
                >
                  {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {sub}
                </span>
              </div>
              <p className="text-2xl font-bold text-text-primary tracking-tight">{value}</p>
              <p className="text-xs text-text-muted mt-1">{label}</p>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* Negative margin alerts */}
      {ALERTS.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.15 }}>
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg bg-rose-500/10 flex items-center justify-center">
                <TrendingDown className="w-3.5 h-3.5 text-accent-rose" />
              </div>
              <h2 className="text-sm font-semibold text-text-primary">
                Negative margin alerts
              </h2>
              <Badge color="red">{ALERTS.length}</Badge>
            </div>
            <div className="space-y-2">
              {ALERTS.map((r) => (
                <div
                  key={r.vehicleId}
                  className="flex items-center justify-between p-3.5 rounded-xl border border-rose-500/20 bg-rose-500/5"
                >
                  <div>
                    <p className="text-sm font-medium text-text-primary">{r.vehicleName}</p>
                    <p className="text-xs text-text-muted mt-0.5">
                      Sold {r.soldAt} · Buy {fmt(r.buyPrice)} → Sell {fmt(r.sellPrice)}
                    </p>
                  </div>
                  <Badge color="red">
                    −{fmt(Math.abs(r.margin))} ({r.marginPct.toFixed(1)}%)
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </motion.div>
      )}

      {/* Bar chart */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.2 }}>
        <Card>
          <h2 className="text-sm font-semibold text-text-primary mb-5">Revenue vs Costs — Fleet P&amp;L</h2>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={MONTHLY} margin={{ top: 0, right: 0, left: 0, bottom: 0 }} barSize={18} barGap={3}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="month"
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `€${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Legend
                wrapperStyle={{ fontSize: '11px', color: 'var(--text-secondary)' }}
                iconType="circle"
                iconSize={7}
              />
              <Bar dataKey="revenue" fill="rgba(59,130,246,0.7)"   name="Revenue" radius={[4, 4, 0, 0]} />
              <Bar dataKey="cost"    fill="rgba(244,63,94,0.5)"    name="Cost"    radius={[4, 4, 0, 0]} />
              <Bar dataKey="margin"  fill="rgba(52,211,153,0.7)"   name="Margin"  radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </motion.div>

      {/* Vehicle table */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.25 }}>
        <Card padding={false}>
          <div className="px-5 py-4 border-b border-border-subtle">
            <h2 className="text-sm font-semibold text-text-primary">Top 10 Vehicles by Margin</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-border-subtle">
                  {['Vehicle', 'Buy', 'Sell', 'Margin', '%', 'Date'].map((h) => (
                    <th
                      key={h}
                      className="px-5 py-3 text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {TOP_VEHICLES.map((r) => (
                  <tr
                    key={r.vehicleId}
                    className={cn(
                      'border-b border-border-subtle last:border-0 transition-colors duration-100',
                      r.margin < 0 ? 'bg-rose-500/5 hover:bg-rose-500/8' : 'hover:bg-glass-subtle',
                    )}
                  >
                    <td className="px-5 py-3.5 font-medium text-text-primary">{r.vehicleName}</td>
                    <td className="px-5 py-3.5 text-text-secondary">{fmt(r.buyPrice)}</td>
                    <td className="px-5 py-3.5 text-text-secondary">{fmt(r.sellPrice)}</td>
                    <td className={cn('px-5 py-3.5 font-semibold', r.margin < 0 ? 'text-accent-rose' : 'text-accent-emerald')}>
                      {r.margin < 0 ? '−' : '+'}{fmt(r.margin)}
                    </td>
                    <td className={cn('px-5 py-3.5 text-xs font-medium', r.marginPct < 0 ? 'text-accent-rose' : 'text-text-muted')}>
                      {r.marginPct.toFixed(1)}%
                    </td>
                    <td className="px-5 py-3.5 text-text-muted text-xs">{r.soldAt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </motion.div>
    </div>
  )
}
