import React from 'react'
import { Car, GitPullRequest, TrendingUp, AlertTriangle } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import Card from '../components/Card'
import { PageSkeleton } from '../components/LoadingSpinner'
import { useApi } from '../hooks/useApi'
import type { KpiData } from '../types'

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
    { id: '1', tenantId: 't', dealId: 'd1', type: 'inquiry',  body: 'New inquiry for BMW 320d from Maria S.', createdAt: '2026-04-18T10:15:00Z' },
    { id: '2', tenantId: 't', dealId: 'd2', type: 'call',     body: 'Call with John D. — scheduled test drive', createdAt: '2026-04-18T09:42:00Z' },
    { id: '3', tenantId: 't', dealId: 'd3', type: 'reply',    body: 'Offer sent for Audi A4 (€26,500)', createdAt: '2026-04-18T09:10:00Z' },
    { id: '4', tenantId: 't', dealId: 'd4', type: 'note',     body: 'Client wants black interior — check stock', createdAt: '2026-04-17T16:55:00Z' },
    { id: '5', tenantId: 't', dealId: 'd5', type: 'reminder', body: 'Follow up with Peter K. on Mercedes C220', createdAt: '2026-04-17T14:30:00Z' },
  ],
}

interface KpiCardProps {
  label: string
  value: string
  sub?: string
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
  accent: string
}

function KpiCard({ label, value, sub, icon, accent }: KpiCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
            {label}
          </p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
        </div>
        <div className={`w-9 h-9 rounded-xl ${accent} flex items-center justify-center`}>{icon}</div>
      </div>
    </Card>
  )
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

const activityColors: Record<string, string> = {
  inquiry:  'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400',
  call:     'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
  reply:    'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400',
  note:     'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400',
  reminder: 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400',
  visit:    'bg-teal-100 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400',
}

export default function Dashboard() {
  const { data, loading } = useApi<KpiData>('/kpi')

  // Use mock data while API isn't connected
  const kpi = data ?? MOCK_KPI

  if (loading && !data) return <PageSkeleton />

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <KpiCard
          label="In Stock"
          value={String(kpi.stockCount)}
          sub="vehicles active"
          icon={<Car className="w-4 h-4 text-blue-600" />}
          accent="bg-blue-50 dark:bg-blue-900/20"
          trend="up"
        />
        <KpiCard
          label="Active Deals"
          value={String(kpi.activeDeals)}
          sub="in pipeline"
          icon={<GitPullRequest className="w-4 h-4 text-purple-600" />}
          accent="bg-purple-50 dark:bg-purple-900/20"
          trend="neutral"
        />
        <KpiCard
          label="Month Margin"
          value={`€${(kpi.monthMargin / 1000).toFixed(1)}k`}
          sub="April 2026"
          icon={<TrendingUp className="w-4 h-4 text-green-600" />}
          accent="bg-green-50 dark:bg-green-900/20"
          trend="up"
        />
        <KpiCard
          label="Alerts"
          value={String(kpi.pendingAlerts)}
          sub="require action"
          icon={<AlertTriangle className="w-4 h-4 text-orange-600" />}
          accent="bg-orange-50 dark:bg-orange-900/20"
          trend="down"
        />
      </div>

      {/* Margin chart */}
      <Card>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">
          Margin — Last 6 months
        </h2>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={kpi.marginHistory} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="margin-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2563eb" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `€${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value: number) => [`€${value.toLocaleString()}`, 'Margin']}
              contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '12px' }}
            />
            <Area
              type="monotone"
              dataKey="margin"
              stroke="#2563eb"
              strokeWidth={2}
              fill="url(#margin-grad)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Recent activities */}
      <Card>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">
          Recent Activity
        </h2>
        <div className="space-y-3">
          {kpi.recentActivities.slice(0, 5).map((a) => (
            <div key={a.id} className="flex items-start gap-3">
              <span
                className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded capitalize ${activityColors[a.type] ?? activityColors.note}`}
              >
                {a.type}
              </span>
              <p className="text-sm text-gray-700 dark:text-gray-300 flex-1 leading-snug">{a.body}</p>
              <span className="text-xs text-gray-400 shrink-0">{timeAgo(a.createdAt)}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
