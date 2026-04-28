import { motion, useMotionValue, useSpring, useTransform, AnimatePresence } from 'framer-motion'
import React, { useEffect, useState } from 'react'
import {
  Car, GitPullRequest, TrendingUp, AlertTriangle,
  ArrowUpRight, ArrowDownRight, Minus, Plus, ClipboardList, Search, Zap,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as ChartTooltip, ResponsiveContainer,
} from 'recharts'
import Card from '../components/Card'
import Button from '../components/Button'
import { Badge } from '../components/Badge'
import { Tabs } from '../components/Tabs'
import { PageSkeleton } from '../components/LoadingSpinner'
import { useApi } from '../hooks/useApi'
import { useNavigate } from 'react-router-dom'
import { cn } from '../lib/cn'
import type { KpiData } from '../types'

// ── Mock data ─────────────────────────────────────────────────────────────────
const MOCK_KPI: KpiData = {
  stockCount: 148,
  activeDeals: 34,
  monthMargin: 87400,
  pendingAlerts: 5,
  marginHistory: [
    { month: 'Nov', margin: 61000, revenue: 310000, cost: 249000 },
    { month: 'Dec', margin: 72000, revenue: 360000, cost: 288000 },
    { month: 'Jan', margin: 54000, revenue: 270000, cost: 216000 },
    { month: 'Feb', margin: 79000, revenue: 395000, cost: 316000 },
    { month: 'Mar', margin: 95000, revenue: 475000, cost: 380000 },
    { month: 'Apr', margin: 87400, revenue: 437000, cost: 349600 },
  ],
  recentActivities: [
    { id: '1', tenantId: 't', dealId: 'd1', type: 'inquiry',  body: 'New inquiry for BMW 320d from Maria S.',       createdAt: '2026-04-18T10:15:00Z' },
    { id: '2', tenantId: 't', dealId: 'd2', type: 'call',     body: 'Call with John D. — scheduled test drive',     createdAt: '2026-04-18T09:42:00Z' },
    { id: '3', tenantId: 't', dealId: 'd3', type: 'reply',    body: 'Offer sent for Audi A4 (€26,500)',             createdAt: '2026-04-18T09:10:00Z' },
    { id: '4', tenantId: 't', dealId: 'd4', type: 'note',     body: 'Client wants black interior — check stock',    createdAt: '2026-04-17T16:55:00Z' },
    { id: '5', tenantId: 't', dealId: 'd5', type: 'reminder', body: 'Follow up with Peter K. on Mercedes C220',    createdAt: '2026-04-17T14:30:00Z' },
  ],
}

// ── Animation variants ────────────────────────────────────────────────────────
const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } }
const fadeUp  = {
  hidden: { opacity: 0, y: 14 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' as const } },
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return null
  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min || 1
  const W = 72, H = 32
  const pts = values.map((v, i): [number, number] => [
    (i / (values.length - 1)) * W,
    H - ((v - min) / range) * (H - 6) + 3,
  ])
  const lineStr  = pts.map(([x, y]) => `${x},${y}`).join(' ')
  const areaPath = `M${pts[0][0]},${H} ` + pts.map(([x, y]) => `L${x},${y}`).join(' ') + ` L${pts[pts.length - 1][0]},${H} Z`
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="shrink-0">
      <path d={areaPath} fill={color} fillOpacity="0.12" />
      <polyline points={lineStr} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Animated number ───────────────────────────────────────────────────────────
function AnimatedNumber({ to, prefix = '', suffix = '', decimals = 0 }: {
  to: number; prefix?: string; suffix?: string; decimals?: number
}) {
  const mv      = useMotionValue(0)
  const spring  = useSpring(mv, { stiffness: 80, damping: 18 })
  const display = useTransform(spring, (v) =>
    `${prefix}${decimals > 0 ? v.toFixed(decimals) : Math.round(v)}${suffix}`,
  )
  useEffect(() => { mv.set(to) }, [to, mv])
  return <motion.span>{display}</motion.span>
}

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const activityColorMap: Record<string, 'blue' | 'green' | 'purple' | 'yellow' | 'orange'> = {
  inquiry: 'blue', call: 'green', reply: 'purple', note: 'yellow', reminder: 'orange', visit: 'green',
}

// ── Margin chart ──────────────────────────────────────────────────────────────
function MarginChart({ data }: { data: KpiData['marginHistory'] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="dash-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="var(--color-blue)" stopOpacity="0.25" />
            <stop offset="95%" stopColor="var(--color-blue)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={false} tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={false} tickLine={false}
          tickFormatter={(v: number) => `€${(v / 1000).toFixed(0)}k`}
        />
        <ChartTooltip
          formatter={(v: number) => [`€${v.toLocaleString()}`, 'Margin']}
          contentStyle={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
            borderRadius: '8px', fontSize: '12px', color: 'var(--text-primary)',
          }}
          labelStyle={{ color: 'var(--text-muted)', fontSize: '11px', marginBottom: 2 }}
          itemStyle={{ color: 'var(--text-secondary)' }}
          cursor={{ stroke: 'var(--border-active)', strokeWidth: 1 }}
        />
        <Area type="monotone" dataKey="margin" stroke="var(--color-blue)"
          strokeWidth={2} fill="url(#dash-grad)" dot={false} activeDot={{ r: 4, fill: 'var(--color-blue)' }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── KPI card ──────────────────────────────────────────────────────────────────
interface KpiCardProps {
  label: string
  numericValue: number
  prefix?: string
  suffix?: string
  decimals?: number
  sub: string
  icon: React.ReactNode
  iconBg: string
  trend: 'up' | 'down' | 'neutral'
  sparkValues: number[]
  sparkColor: string
}

function KpiCard({ label, numericValue, prefix, suffix, decimals, sub, icon, iconBg, trend, sparkValues, sparkColor }: KpiCardProps) {
  return (
    <motion.div variants={fadeUp}>
      <Card hover className="relative overflow-hidden">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1">{label}</p>
            <p className="text-2xl font-bold text-text-primary tabular-nums">
              <AnimatedNumber to={numericValue} prefix={prefix} suffix={suffix} decimals={decimals} />
            </p>
            <p className="text-xs text-text-muted mt-0.5">{sub}</p>
          </div>
          <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center shrink-0', iconBg)}>
            {icon}
          </div>
        </div>
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-1">
            {trend === 'up'      && <ArrowUpRight   className="w-3.5 h-3.5 text-accent-emerald" />}
            {trend === 'down'    && <ArrowDownRight  className="w-3.5 h-3.5 text-accent-rose" />}
            {trend === 'neutral' && <Minus className="w-3.5 h-3.5 text-text-muted" />}
            <span className={cn('text-xs font-medium',
              trend === 'up' ? 'text-accent-emerald' : trend === 'down' ? 'text-accent-rose' : 'text-text-muted'
            )}>
              vs last month
            </span>
          </div>
          <Sparkline values={sparkValues} color={sparkColor} />
        </div>
      </Card>
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { data, loading } = useApi<KpiData>('/kpi')
  const navigate = useNavigate()
  const [chartRange, setChartRange] = useState('ytd')
  const kpi: KpiData = data ? { ...MOCK_KPI, ...data } : MOCK_KPI

  if (loading && !data) return <PageSkeleton />

  const rangeSlice: Record<string, number> = { '7d': 2, '30d': 3, '90d': 4, 'ytd': 6 }
  const chartData = kpi.marginHistory.slice(-rangeSlice[chartRange])

  const chartTabs = ['7d', '30d', '90d', 'ytd'].map((r) => ({
    value: r,
    label: r.toUpperCase(),
    content: <MarginChart data={kpi.marginHistory.slice(-rangeSlice[r])} />,
  }))

  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto"
    >
      {/* Header */}
      <motion.div variants={fadeUp} className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-0.5">
            {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <Badge color="blue" dot pulse>{kpi.stockCount} vehicles live</Badge>
      </motion.div>

      {/* KPI grid */}
      <motion.div variants={stagger} className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <KpiCard
          label="In Stock"
          numericValue={kpi.stockCount}
          sub="vehicles active"
          icon={<Car className="w-4 h-4 text-accent-blue" />}
          iconBg="bg-blue-500/10"
          trend="up"
          sparkValues={[130, 138, 142, 145, 147, kpi.stockCount]}
          sparkColor="var(--color-blue)"
        />
        <KpiCard
          label="Active Deals"
          numericValue={kpi.activeDeals}
          sub="in pipeline"
          icon={<GitPullRequest className="w-4 h-4 text-purple-400" />}
          iconBg="bg-purple-500/10"
          trend="neutral"
          sparkValues={[28, 31, 29, 33, 35, kpi.activeDeals]}
          sparkColor="#a855f7"
        />
        <KpiCard
          label="Month Margin"
          numericValue={kpi.monthMargin / 1000}
          prefix="€"
          suffix="k"
          decimals={1}
          sub={new Date().toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}
          icon={<TrendingUp className="w-4 h-4 text-accent-emerald" />}
          iconBg="bg-emerald-500/10"
          trend="up"
          sparkValues={kpi.marginHistory.map((m) => m.margin / 1000)}
          sparkColor="var(--color-emerald)"
        />
        <KpiCard
          label="Alerts"
          numericValue={kpi.pendingAlerts}
          sub="require action"
          icon={<AlertTriangle className="w-4 h-4 text-accent-amber" />}
          iconBg="bg-amber-500/10"
          trend="down"
          sparkValues={[8, 7, 6, 7, 5, kpi.pendingAlerts]}
          sparkColor="var(--color-amber)"
        />
      </motion.div>

      {/* Revenue chart */}
      <motion.div variants={fadeUp}>
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-text-primary">Margin Performance</h2>
          </div>
          <Tabs
            value={chartRange}
            onValueChange={setChartRange}
            items={chartTabs}
            className="[&_.mb-4]:mb-3"
          />
        </Card>
      </motion.div>

      {/* Bottom row: Activity + Quick actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Activity feed */}
        <motion.div variants={fadeUp} className="lg:col-span-2">
          <Card>
            <h2 className="text-sm font-semibold text-text-primary mb-4">Recent Activity</h2>
            <div className="space-y-3">
              {kpi.recentActivities.slice(0, 5).map((a, idx) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + idx * 0.06 }}
                  className="flex items-start gap-3"
                >
                  <Badge color={activityColorMap[a.type] ?? 'gray'} className="shrink-0 mt-0.5">
                    {a.type}
                  </Badge>
                  <p className="text-sm text-text-secondary flex-1 leading-snug">{a.body}</p>
                  <span className="text-xs text-text-muted shrink-0">{timeAgo(a.createdAt)}</span>
                </motion.div>
              ))}
            </div>
          </Card>
        </motion.div>

        {/* Quick actions */}
        <motion.div variants={fadeUp}>
          <Card className="h-full">
            <h2 className="text-sm font-semibold text-text-primary mb-4">Quick Actions</h2>
            <div className="flex flex-col gap-2">
              <Button
                variant="secondary"
                className="w-full justify-start gap-3"
                icon={<Car className="w-4 h-4" />}
                onClick={() => navigate('/vehicles')}
              >
                Add Vehicle
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-start gap-3"
                icon={<ClipboardList className="w-4 h-4" />}
                onClick={() => navigate('/deals')}
              >
                New Deal
              </Button>
              <Button
                variant="secondary"
                className="w-full justify-start gap-3"
                icon={<Search className="w-4 h-4" />}
                onClick={() => navigate('/check')}
              >
                Check VIN
              </Button>
              <Button
                variant="ghost"
                className="w-full justify-start gap-3 mt-1"
                icon={<Zap className="w-4 h-4 text-accent-amber" />}
                onClick={() => navigate('/kanban')}
              >
                Open Board
              </Button>
            </div>
          </Card>
        </motion.div>
      </div>
    </motion.div>
  )
}
