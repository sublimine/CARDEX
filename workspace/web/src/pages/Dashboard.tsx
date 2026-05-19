import { motion, useMotionValue, useSpring, useTransform, AnimatePresence } from 'framer-motion'
import React, { useEffect, useState } from 'react'
import {
  TrendingUp, AlertTriangle, ArrowUpRight, ArrowDownRight,
  Minus, Search, Zap, ClipboardList,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as ChartTooltip, ResponsiveContainer, BarChart, Bar,
} from 'recharts'
import { PageSkeleton } from '../components/LoadingSpinner'
import { useApi } from '../hooks/useApi'
import { useNavigate } from 'react-router-dom'
import type { KpiData } from '../types'

// ── Mock ──────────────────────────────────────────────────────────────────────
const MOCK_KPI: KpiData = {
  stockCount: 270,
  activeDeals: 55,
  monthMargin: 87400,
  pendingAlerts: 3,
  marginHistory: [
    { month: 'Nov', margin: 61000, revenue: 310000, cost: 249000 },
    { month: 'Dec', margin: 72000, revenue: 360000, cost: 288000 },
    { month: 'Jan', margin: 54000, revenue: 270000, cost: 216000 },
    { month: 'Feb', margin: 79000, revenue: 395000, cost: 316000 },
    { month: 'Mar', margin: 95000, revenue: 475000, cost: 380000 },
    { month: 'Apr', margin: 87400, revenue: 437000, cost: 349600 },
  ],
  recentActivities: [
    { id: '1', tenantId: 't', dealId: 'd1', type: 'inquiry',  body: 'New inquiry — BMW 320d, Maria S.',       createdAt: '2026-04-18T10:15:00Z' },
    { id: '2', tenantId: 't', dealId: 'd2', type: 'call',     body: 'Test drive scheduled — John D.',         createdAt: '2026-04-18T09:42:00Z' },
    { id: '3', tenantId: 't', dealId: 'd3', type: 'reply',    body: 'Offer sent — Audi A4 2.0 TDI €26,500',  createdAt: '2026-04-18T09:10:00Z' },
    { id: '4', tenantId: 't', dealId: 'd4', type: 'note',     body: 'Client: black interior, check stock',    createdAt: '2026-04-17T16:55:00Z' },
    { id: '5', tenantId: 't', dealId: 'd5', type: 'reminder', body: 'Follow up — Peter K., Mercedes C220d',  createdAt: '2026-04-17T14:30:00Z' },
  ],
}

// ── Animated number ───────────────────────────────────────────────────────────
function AnimNum({ to, prefix = '', suffix = '', decimals = 0 }: { to: number; prefix?: string; suffix?: string; decimals?: number }) {
  const mv = useMotionValue(0)
  const sp = useSpring(mv, { stiffness: 60, damping: 14 })
  const d  = useTransform(sp, v => `${prefix}${decimals ? v.toFixed(decimals) : Math.round(v)}${suffix}`)
  useEffect(() => { mv.set(to) }, [to])
  return <motion.span>{d}</motion.span>
}

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h` : `${Math.floor(h / 24)}d`
}

const TYPE_COLOR: Record<string, string> = {
  inquiry: '#5b8df8', call: '#00d68a', reply: '#9b6dff', note: '#ffb347', reminder: '#ff5577',
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
function Spark({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) return null
  const max = Math.max(...values), min = Math.min(...values), range = max - min || 1
  const W = 56, H = 24
  const pts = values.map((v, i): [number, number] => [
    (i / (values.length - 1)) * W,
    H - ((v - min) / range) * (H - 3) + 1.5,
  ])
  const line = pts.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `M${pts[0][0]},${H} ` + pts.map(([x, y]) => `L${x},${y}`).join(' ') + ` L${pts.at(-1)![0]},${H} Z`
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <path d={area} fill={color} fillOpacity={0.14} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ── Double-Bezel KPI card ──────────────────────────────────────────────────────
interface KpiProps {
  label: string; value: number; prefix?: string; suffix?: string; decimals?: number
  sub: string; accent: string; trend: 'up' | 'down' | 'flat'
  trendLabel: string; spark: number[]
}

function KpiCard({ label, value, prefix, suffix, decimals, sub, accent, trend, trendLabel, spark }: KpiProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18, filter: 'blur(6px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.55, ease: [0.32, 0.72, 0, 1] }}
      whileHover={{ y: -2, boxShadow: `0 0 0 1px ${accent}33, 0 12px 40px rgba(0,0,0,0.7), 0 0 40px ${accent}12` }}
      style={{
        /* Outer bezel shell */
        background: 'rgba(255,255,255,0.025)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 20,
        padding: 2,
        cursor: 'default',
        transition: 'box-shadow 0.3s cubic-bezier(0.32,0.72,0,1), transform 0.3s cubic-bezier(0.32,0.72,0,1)',
      }}
    >
      {/* Inner core */}
      <div style={{
        background: '#0e0e18',
        borderRadius: 18,
        padding: '20px 20px 18px',
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.07)`,
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Accent glow blob */}
        <div style={{
          position: 'absolute', top: -30, right: -20, width: 100, height: 100,
          borderRadius: '50%', background: accent, opacity: 0.08, filter: 'blur(28px)',
          pointerEvents: 'none',
        }} />

        {/* Top row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#38385a' }}>
            {label}
          </span>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: `${accent}20`, border: `1px solid ${accent}30`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}` }} />
          </div>
        </div>

        {/* Big number */}
        <div style={{ fontSize: 46, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1, color: '#f0f0fa', marginBottom: 6 }}>
          <AnimNum to={value} prefix={prefix} suffix={suffix} decimals={decimals} />
        </div>
        <div style={{ fontSize: 12, color: '#38385a', marginBottom: 16 }}>{sub}</div>

        {/* Footer */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {trend === 'up'   && <ArrowUpRight   style={{ width: 12, height: 12, color: '#00d68a' }} />}
            {trend === 'down' && <ArrowDownRight  style={{ width: 12, height: 12, color: '#ff5577' }} />}
            {trend === 'flat' && <Minus style={{ width: 12, height: 12, color: '#38385a' }} />}
            <span style={{ fontSize: 11, fontWeight: 600, color: trend === 'up' ? '#00d68a' : trend === 'down' ? '#ff5577' : '#38385a' }}>
              {trendLabel}
            </span>
          </div>
          <Spark values={spark} color={accent} />
        </div>
      </div>
    </motion.div>
  )
}

// ── Area chart ────────────────────────────────────────────────────────────────
function MarginChart({ data }: { data: KpiData['marginHistory'] }) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={data} margin={{ top: 4, right: 0, left: -28, bottom: 0 }}>
        <defs>
          <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#5b8df8" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#5b8df8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="1 6" stroke="rgba(255,255,255,0.04)" />
        <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#38385a', fontFamily: 'Plus Jakarta Sans' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#38385a', fontFamily: 'Plus Jakarta Sans' }} axisLine={false} tickLine={false} tickFormatter={v => `€${(v/1000).toFixed(0)}k`} />
        <ChartTooltip
          contentStyle={{ background: '#0e0e18', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, fontSize: 12, color: '#f0f0fa', fontFamily: 'Plus Jakarta Sans', boxShadow: '0 8px 32px rgba(0,0,0,0.7)' }}
          formatter={(v: number) => [`€${v.toLocaleString()}`, 'Margin']}
          cursor={{ stroke: 'rgba(255,255,255,0.06)' }}
        />
        <Area type="monotone" dataKey="margin" stroke="#5b8df8" strokeWidth={2} fill="url(#g1)" dot={false} activeDot={{ r: 3, fill: '#5b8df8', strokeWidth: 0 }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function BarChartComp({ data }: { data: KpiData['marginHistory'] }) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 4, right: 0, left: -28, bottom: 0 }} barSize={14}>
        <CartesianGrid strokeDasharray="1 6" stroke="rgba(255,255,255,0.04)" />
        <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#38385a', fontFamily: 'Plus Jakarta Sans' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#38385a', fontFamily: 'Plus Jakarta Sans' }} axisLine={false} tickLine={false} tickFormatter={v => `€${(v/1000).toFixed(0)}k`} />
        <ChartTooltip
          contentStyle={{ background: '#0e0e18', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10, fontSize: 12, color: '#f0f0fa', fontFamily: 'Plus Jakarta Sans' }}
          cursor={{ fill: 'rgba(255,255,255,0.03)' }}
        />
        <Bar dataKey="revenue" fill="rgba(91,141,248,0.18)" radius={[4,4,0,0]} />
        <Bar dataKey="cost"    fill="rgba(155,109,255,0.15)" radius={[4,4,0,0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Quick action button ───────────────────────────────────────────────────────
function ActionBtn({ label, icon, color, onClick }: { label: string; icon: React.ReactNode; color: string; onClick: () => void }) {
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', stiffness: 420, damping: 22 }}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        width: '100%', padding: '11px 14px',
        background: 'rgba(255,255,255,0.025)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 12, cursor: 'pointer',
        transition: 'background 150ms',
        fontFamily: 'Plus Jakarta Sans',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
    >
      <div style={{ width: 30, height: 30, borderRadius: 9, background: `${color}18`, border: `1px solid ${color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {icon}
      </div>
      <span style={{ fontSize: 13, fontWeight: 600, color: '#9090b8' }}>{label}</span>
      <div style={{ marginLeft: 'auto', width: 20, height: 20, borderRadius: '50%', background: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <ArrowUpRight style={{ width: 10, height: 10, color: '#38385a' }} />
      </div>
    </motion.button>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { data, loading } = useApi<KpiData>('/kpi')
  const navigate = useNavigate()
  const [chartTab, setChartTab] = useState<'area' | 'bar'>('area')
  const kpi = data ? { ...MOCK_KPI, ...data } : MOCK_KPI

  if (loading && !data) return <PageSkeleton />

  return (
    <div style={{ padding: '28px 28px 40px', maxWidth: 1280, margin: '0 auto' }}>

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
        style={{ marginBottom: 28, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}
      >
        <div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px', background: 'rgba(91,141,248,0.08)', border: '1px solid rgba(91,141,248,0.18)', borderRadius: 999, marginBottom: 10 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#5b8df8', display: 'block', boxShadow: '0 0 8px #5b8df8' }} />
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#5b8df8' }}>
              {kpi.stockCount} vehicles live
            </span>
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em', color: '#f0f0fa', lineHeight: 1 }}>
            Overview
          </h1>
          <p style={{ fontSize: 13, color: '#38385a', marginTop: 4 }}>
            {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
      </motion.div>

      {/* ── Bento grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gridTemplateRows: 'auto auto auto', gap: 14 }}>

        {/* KPI 1 */}
        <div style={{ gridColumn: '1', gridRow: '1' }}>
          <KpiCard
            label="In Stock" value={kpi.stockCount} sub="vehicles active"
            accent="#5b8df8" trend="up" trendLabel="+12 this month"
            spark={[220, 235, 248, 260, 265, kpi.stockCount]}
          />
        </div>

        {/* KPI 2 */}
        <div style={{ gridColumn: '2', gridRow: '1' }}>
          <KpiCard
            label="Active Deals" value={kpi.activeDeals} sub="in pipeline"
            accent="#9b6dff" trend="flat" trendLabel="stable"
            spark={[42, 48, 51, 53, 54, kpi.activeDeals]}
          />
        </div>

        {/* KPI 3 */}
        <div style={{ gridColumn: '3', gridRow: '1' }}>
          <KpiCard
            label="Month Margin" value={kpi.monthMargin / 1000} prefix="€" suffix="k" decimals={1}
            sub={new Date().toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })}
            accent="#00d68a" trend="up" trendLabel="+8% vs last month"
            spark={kpi.marginHistory.map(m => m.margin / 1000)}
          />
        </div>

        {/* KPI 4 */}
        <div style={{ gridColumn: '4', gridRow: '1' }}>
          <KpiCard
            label="Alerts" value={kpi.pendingAlerts} sub="require action"
            accent="#ffb347" trend="down" trendLabel="down from 8"
            spark={[8, 7, 6, 5, 4, kpi.pendingAlerts]}
          />
        </div>

        {/* Chart — spans 3 cols */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          style={{
            gridColumn: '1 / 4', gridRow: '2',
            background: 'rgba(255,255,255,0.025)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 20, padding: 2,
          }}
        >
          <div style={{ background: '#0e0e18', borderRadius: 18, padding: '22px 22px 18px', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: '#f0f0fa', marginBottom: 2 }}>Margin Performance</h2>
                <p style={{ fontSize: 11, color: '#38385a' }}>6-month gross margin trend</p>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                {(['area', 'bar'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => setChartTab(t)}
                    style={{
                      padding: '5px 14px', borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: 'pointer',
                      fontFamily: 'Plus Jakarta Sans', letterSpacing: '0.04em', textTransform: 'uppercase',
                      background: chartTab === t ? 'rgba(91,141,248,0.18)' : 'transparent',
                      border: chartTab === t ? '1px solid rgba(91,141,248,0.3)' : '1px solid transparent',
                      color: chartTab === t ? '#5b8df8' : '#38385a',
                      transition: 'all 0.2s',
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            {chartTab === 'area' ? <MarginChart data={kpi.marginHistory} /> : <BarChartComp data={kpi.marginHistory} />}
          </div>
        </motion.div>

        {/* Quick actions */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          style={{
            gridColumn: '4', gridRow: '2',
            background: 'rgba(255,255,255,0.025)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 20, padding: 2,
          }}
        >
          <div style={{ background: '#0e0e18', borderRadius: 18, padding: '22px 18px', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.07)', height: '100%' }}>
            <h2 style={{ fontSize: 13, fontWeight: 700, color: '#f0f0fa', marginBottom: 14, letterSpacing: '-0.01em' }}>Quick Actions</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <ActionBtn label="Add Vehicle"  color="#5b8df8"  icon={<TrendingUp  style={{ width: 14, height: 14, color: '#5b8df8'  }} />} onClick={() => navigate('/vehicles')} />
              <ActionBtn label="New Deal"     color="#9b6dff"  icon={<ClipboardList style={{ width: 14, height: 14, color: '#9b6dff' }} />} onClick={() => navigate('/deals')} />
              <ActionBtn label="Check VIN"    color="#00d68a"  icon={<Search       style={{ width: 14, height: 14, color: '#00d68a'  }} />} onClick={() => navigate('/check')} />
              <ActionBtn label="Open Board"   color="#ffb347"  icon={<Zap          style={{ width: 14, height: 14, color: '#ffb347'  }} />} onClick={() => navigate('/kanban')} />
            </div>
          </div>
        </motion.div>

        {/* Activity feed — full width */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          style={{
            gridColumn: '1 / 5', gridRow: '3',
            background: 'rgba(255,255,255,0.025)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 20, padding: 2,
          }}
        >
          <div style={{ background: '#0e0e18', borderRadius: 18, padding: '22px 24px', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.07)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
              <h2 style={{ fontSize: 13, fontWeight: 700, color: '#f0f0fa' }}>Recent Activity</h2>
              <span style={{ fontSize: 11, color: '#38385a' }}>{kpi.recentActivities.length} events today</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
              {kpi.recentActivities.map((a, i) => (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.06, duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
                  style={{
                    padding: '14px 14px',
                    background: 'rgba(255,255,255,0.02)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderRadius: 12,
                    borderLeft: `2px solid ${TYPE_COLOR[a.type] ?? '#5b8df8'}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{
                      fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
                      color: TYPE_COLOR[a.type] ?? '#5b8df8',
                      padding: '2px 8px', borderRadius: 999,
                      background: `${TYPE_COLOR[a.type] ?? '#5b8df8'}18`,
                    }}>
                      {a.type}
                    </span>
                    <span style={{ fontSize: 10, color: '#38385a', fontVariantNumeric: 'tabular-nums' }}>{timeAgo(a.createdAt)}</span>
                  </div>
                  <p style={{ fontSize: 12, color: '#7070a0', lineHeight: 1.5 }}>{a.body}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>

      </div>
    </div>
  )
}
