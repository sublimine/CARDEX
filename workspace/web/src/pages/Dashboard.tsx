import { motion, useMotionValue, useSpring, useTransform, AnimatePresence } from 'framer-motion'
import React, { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, ArrowDownRight, Minus, Search, Zap, ClipboardList, TrendingUp, AlertTriangle, Clock, ChevronRight } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as ChartTooltip, ResponsiveContainer } from 'recharts'
import { PageSkeleton } from '../components/LoadingSpinner'
import { useApi } from '../hooks/useApi'
import { useNavigate } from 'react-router-dom'
import { useAuthContext } from '../auth/AuthContext'
import type { KpiData } from '../types'

// ── Theme observer ────────────────────────────────────────────────────────────

function useIsDark() {
  const [dark, setDark] = useState(() => !document.documentElement.classList.contains('light'))
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(!document.documentElement.classList.contains('light')))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])
  return dark
}

// ── Mock data ─────────────────────────────────────────────────────────────────

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
    { id: '1', tenantId: 't', dealId: 'd1', type: 'inquiry',  body: 'New inquiry — BMW 320d, Maria S.',      createdAt: '2026-04-18T10:15:00Z' },
    { id: '2', tenantId: 't', dealId: 'd2', type: 'call',     body: 'Test drive scheduled — John D.',        createdAt: '2026-04-18T09:42:00Z' },
    { id: '3', tenantId: 't', dealId: 'd3', type: 'reply',    body: 'Offer sent — Audi A4 €26,500',         createdAt: '2026-04-18T09:10:00Z' },
    { id: '4', tenantId: 't', dealId: 'd4', type: 'note',     body: 'Client wants black interior',           createdAt: '2026-04-17T16:55:00Z' },
    { id: '5', tenantId: 't', dealId: 'd5', type: 'reminder', body: 'Follow up — Peter K., C220d',          createdAt: '2026-04-17T14:30:00Z' },
  ],
}

const DEALER = {
  avgDaysInStock: 38,
  stockValue: 2_140_000,
  soldThisMonth: 23,
  targetSoldMonth: 30,
  dealStages: [
    { label: 'New',         count: 15, color: '#5b8df8' },
    { label: 'Contacted',   count: 12, color: '#a78bfa' },
    { label: 'Offer Sent',  count: 10, color: '#f59e0b' },
    { label: 'Negotiation', count: 10, color: '#fb923c' },
    { label: 'Closed',      count:  8, color: '#22c55e' },
  ],
  staleStock: [
    { id: 's1', make: 'BMW',       model: '320d xDrive',  year: 2021, days: 72, price: 24_900 },
    { id: 's2', make: 'Audi',      model: 'A4 2.0 TDI',   year: 2020, days: 68, price: 22_500 },
    { id: 's3', make: 'Volkswagen',model: 'Golf 2.0 TDI', year: 2019, days: 61, price: 16_800 },
  ],
  followUps: [
    { id: 'f1', name: 'Maria S.',  vehicle: 'BMW 320d',   time: '11:00', type: 'call' },
    { id: 'f2', name: 'John D.',   vehicle: 'VW Tiguan',  time: '14:30', type: 'drive' },
    { id: 'f3', name: 'Peter K.', vehicle: 'Mercedes C220d', time: '16:00', type: 'offer' },
  ],
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function AnimNum({ to, prefix = '', suffix = '', decimals = 0 }: { to: number; prefix?: string; suffix?: string; decimals?: number }) {
  const mv = useMotionValue(0)
  const sp = useSpring(mv, { stiffness: 55, damping: 14 })
  const d  = useTransform(sp, v => `${prefix}${decimals ? v.toFixed(decimals) : Math.round(v)}${suffix}`)
  useEffect(() => { mv.set(to) }, [to])
  return <motion.span>{d}</motion.span>
}

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`
}

function Spark({ values, color, height = 28 }: { values: number[]; color: string; height?: number }) {
  if (values.length < 2) return null
  const max = Math.max(...values), min = Math.min(...values), range = max - min || 1
  const W = 64, H = height
  const pts = values.map((v, i): [number, number] => [
    (i / (values.length - 1)) * W,
    H - ((v - min) / range) * (H - 4) + 2,
  ])
  const line = pts.map(([x, y]) => `${x},${y}`).join(' ')
  const area = `M${pts[0][0]},${H} ` + pts.map(([x, y]) => `L${x},${y}`).join(' ') + ` L${pts.at(-1)![0]},${H} Z`
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      <path d={area} fill={color} fillOpacity={0.12} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function renderBold(text: string, color: string): React.ReactNode {
  return text.split(/\*\*(.*?)\*\*/g).map((p, i) =>
    i % 2 === 1 ? <strong key={i} style={{ fontWeight: 700, color }}>{p}</strong> : <span key={i}>{p}</span>
  )
}

// ── Token helpers ─────────────────────────────────────────────────────────────

function tok(dark: boolean) {
  return {
    t1:   dark ? '#f1f5f9' : '#0f172a',
    t2:   dark ? '#cbd5e1' : '#334155',
    t3:   dark ? '#94a3b8' : '#64748b',
    t4:   dark ? '#475569' : '#94a3b8',
    div:  dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)',
    cardBg:   dark ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.82)',
    cardBord: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    innerBg:  dark ? 'rgba(14,14,26,0.95)'    : 'rgba(255,255,255,0.97)',
    subBg:    dark ? 'rgba(255,255,255,0.03)'  : 'rgba(0,0,0,0.03)',
    subBord:  dark ? 'rgba(255,255,255,0.06)'  : 'rgba(0,0,0,0.07)',
  }
}

// ── Glass card wrapper ────────────────────────────────────────────────────────

function GCard({ dark, children, style }: { dark: boolean; children: React.ReactNode; style?: React.CSSProperties }) {
  const c = tok(dark)
  return (
    <div style={{
      background: c.cardBg,
      border: `1px solid ${c.cardBord}`,
      borderRadius: 18,
      backdropFilter: 'blur(32px) saturate(180%)',
      WebkitBackdropFilter: 'blur(32px) saturate(180%)',
      boxShadow: dark
        ? '0 4px 24px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.07)'
        : '0 4px 20px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.90)',
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  )
}

// ── Metric card (Pin-2 ultra-minimal style) ───────────────────────────────────

interface MetricCardProps {
  dark: boolean
  label: string
  value: number
  prefix?: string
  suffix?: string
  decimals?: number
  sub: string
  trend: 'up' | 'down' | 'flat' | 'good'
  trendLabel: string
  spark: number[]
  accent: string
  delay?: number
}

function MetricCard({ dark, label, value, prefix, suffix, decimals, sub, trend, trendLabel, spark, accent, delay = 0 }: MetricCardProps) {
  const c = tok(dark)
  const trendColor = trend === 'up' || trend === 'good' ? '#22c55e' : trend === 'down' ? '#f87171' : c.t4
  const TrendIcon  = trend === 'up' || trend === 'good' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.42, ease: [0.32, 0.72, 0, 1] }}
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
    >
      <GCard dark={dark} style={{ padding: '20px 22px 16px' }}>
        {/* Label row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.11em', textTransform: 'uppercase', color: c.t3 }}>
            {label}
          </span>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: accent, boxShadow: `0 0 6px ${accent}` }} />
        </div>

        {/* Big number */}
        <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1, color: c.t1, marginBottom: 4 }}>
          <AnimNum to={value} prefix={prefix} suffix={suffix} decimals={decimals} />
        </div>
        <div style={{ fontSize: 11, color: c.t4, marginBottom: 14 }}>{sub}</div>

        {/* Footer */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, borderTop: `1px solid ${c.div}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <TrendIcon style={{ width: 11, height: 11, color: trendColor }} />
            <span style={{ fontSize: 10.5, fontWeight: 600, color: trendColor }}>{trendLabel}</span>
          </div>
          <Spark values={spark} color={accent} height={22} />
        </div>
      </GCard>
    </motion.div>
  )
}

// ── Margin chart ──────────────────────────────────────────────────────────────

function MarginChart({ data, dark }: { data: KpiData['marginHistory']; dark: boolean }) {
  const [tab, setTab] = useState<'area' | 'bar'>('area')
  const c = tok(dark)
  const tickColor = dark ? '#3f3f5a' : '#94a3b8'
  const gridColor = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.05)'

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 20px 14px', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexShrink: 0 }}>
          <div>
            <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1, marginBottom: 2 }}>Gross Margin</h2>
            <p style={{ fontSize: 10.5, color: c.t4 }}>6-month trend</p>
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {(['area', 'bar'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '4px 10px', borderRadius: 7, fontSize: 10, fontWeight: 700, cursor: 'pointer',
                fontFamily: 'Inter, system-ui', textTransform: 'uppercase', letterSpacing: '0.04em',
                background: tab === t ? 'rgba(91,141,248,0.14)' : 'transparent',
                border: tab === t ? '1px solid rgba(91,141,248,0.28)' : '1px solid transparent',
                color: tab === t ? '#5b8df8' : c.t4, transition: 'all 170ms',
              }}>{t}</button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 0, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="gm" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#5b8df8" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#5b8df8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="1 8" stroke={gridColor} />
              <XAxis dataKey="month" tick={{ fontSize: 9.5, fill: tickColor }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9.5, fill: tickColor }} axisLine={false} tickLine={false} tickFormatter={v => `€${(v/1000).toFixed(0)}k`} />
              <ChartTooltip
                contentStyle={{ background: dark ? '#0e0e1a' : '#fff', border: `1px solid ${c.cardBord}`, borderRadius: 10, fontSize: 11.5, color: c.t1, boxShadow: '0 8px 24px rgba(0,0,0,0.18)' }}
                formatter={(v: number) => [`€${v.toLocaleString()}`, 'Margin']}
                cursor={{ stroke: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }}
              />
              <Area type="monotone" dataKey="margin" stroke="#5b8df8" strokeWidth={2} fill="url(#gm)" dot={false} activeDot={{ r: 3, fill: '#5b8df8', strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </GCard>
  )
}

// ── Pipeline stages ───────────────────────────────────────────────────────────

function PipelinePanel({ dark }: { dark: boolean }) {
  const c = tok(dark)
  const total = DEALER.dealStages.reduce((s, d) => s + d.count, 0)

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 18px 16px', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: 16, flexShrink: 0 }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1, marginBottom: 2 }}>Pipeline</h2>
          <p style={{ fontSize: 10.5, color: c.t4 }}>{total} deals total</p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
          {DEALER.dealStages.map((stage, i) => {
            const pct = (stage.count / total) * 100
            return (
              <motion.div key={stage.label} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.07 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: 11, fontWeight: 500, color: c.t2 }}>{stage.label}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: c.t1, fontVariantNumeric: 'tabular-nums' }}>{stage.count}</span>
                </div>
                <div style={{ height: 4, borderRadius: 99, background: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.07)', overflow: 'hidden' }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ delay: 0.3 + i * 0.08, duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
                    style={{ height: '100%', borderRadius: 99, background: stage.color, boxShadow: `0 0 6px ${stage.color}66` }}
                  />
                </div>
              </motion.div>
            )
          })}
        </div>

        {/* Conversion hint */}
        <div style={{
          marginTop: 14,
          padding: '8px 10px',
          borderRadius: 9,
          background: 'rgba(34,197,94,0.09)',
          border: '1px solid rgba(34,197,94,0.18)',
        }}>
          <span style={{ fontSize: 10.5, color: '#22c55e', fontWeight: 600 }}>
            8 deals closing this week ↗
          </span>
        </div>
      </div>
    </GCard>
  )
}

// ── Stale stock panel ─────────────────────────────────────────────────────────

function StalePanel({ dark, onNavigate }: { dark: boolean; onNavigate: () => void }) {
  const c = tok(dark)

  function staleColor(days: number) {
    if (days >= 70) return '#f87171'
    if (days >= 60) return '#fb923c'
    return '#fbbf24'
  }

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 18px 14px', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexShrink: 0 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <AlertTriangle style={{ width: 12, height: 12, color: '#f87171' }} />
              <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1 }}>Stale Stock</h2>
            </div>
            <p style={{ fontSize: 10.5, color: c.t4 }}>Vehicles over 60 days</p>
          </div>
          <button onClick={onNavigate} style={{ background: 'none', border: 'none', cursor: 'pointer', color: c.t4, padding: 0 }}>
            <ChevronRight style={{ width: 14, height: 14 }} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
          {DEALER.staleStock.map((v, i) => (
            <motion.div
              key={v.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + i * 0.08 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 10px',
                borderRadius: 10,
                background: c.subBg,
                border: `1px solid ${c.subBord}`,
                borderLeft: `2px solid ${staleColor(v.days)}`,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: c.t1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {v.make} {v.model}
                </div>
                <div style={{ fontSize: 10, color: c.t4, marginTop: 1 }}>
                  {v.year} · €{v.price.toLocaleString()}
                </div>
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 99,
                background: `${staleColor(v.days)}14`,
                border: `1px solid ${staleColor(v.days)}30`,
                flexShrink: 0,
              }}>
                <Clock style={{ width: 9, height: 9, color: staleColor(v.days) }} />
                <span style={{ fontSize: 10, fontWeight: 700, color: staleColor(v.days) }}>{v.days}d</span>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </GCard>
  )
}

// ── Follow-ups today ──────────────────────────────────────────────────────────

const TYPE_COLOR: Record<string, string> = {
  inquiry: '#5b8df8', call: '#22c55e', reply: '#9b6dff', note: '#f59e0b', reminder: '#fb923c',
  drive: '#0ea5e9', offer: '#a78bfa',
}

function FollowUpsPanel({ dark, onNavigate }: { dark: boolean; onNavigate: () => void }) {
  const c = tok(dark)

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 18px 14px', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexShrink: 0 }}>
          <div>
            <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1, marginBottom: 2 }}>Today's Follow-ups</h2>
            <p style={{ fontSize: 10.5, color: c.t4 }}>{DEALER.followUps.length} scheduled</p>
          </div>
          <button onClick={onNavigate} style={{ background: 'none', border: 'none', cursor: 'pointer', color: c.t4, padding: 0 }}>
            <ChevronRight style={{ width: 14, height: 14 }} />
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
          {DEALER.followUps.map((f, i) => (
            <motion.div
              key={f.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + i * 0.08 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '9px 10px',
                borderRadius: 10,
                background: c.subBg,
                border: `1px solid ${c.subBord}`,
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                background: `${TYPE_COLOR[f.type]}18`,
                border: `1px solid ${TYPE_COLOR[f.type]}28`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontSize: 12 }}>
                  {f.type === 'call' ? '📞' : f.type === 'drive' ? '🚗' : '📋'}
                </span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 11.5, fontWeight: 600, color: c.t1 }}>{f.name}</div>
                <div style={{ fontSize: 10, color: c.t4, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.vehicle}</div>
              </div>
              <div style={{ fontSize: 10.5, fontWeight: 600, color: c.t3, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                {f.time}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </GCard>
  )
}

// ── Activity feed ─────────────────────────────────────────────────────────────

function ActivityFeed({ activities, dark }: { activities: KpiData['recentActivities']; dark: boolean }) {
  const c = tok(dark)

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 18px 14px', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexShrink: 0 }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1 }}>Recent Activity</h2>
          <span style={{ fontSize: 10.5, color: c.t4 }}>{activities.length} events</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1, overflowY: 'auto' }}>
          {activities.map((a, i) => (
            <motion.div
              key={a.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 + i * 0.06, duration: 0.32 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 0',
                borderBottom: i < activities.length - 1 ? `1px solid ${c.div}` : 'none',
              }}
            >
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: TYPE_COLOR[a.type] ?? '#5b8df8', flexShrink: 0 }} />
              <span style={{
                fontSize: 9.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase',
                color: TYPE_COLOR[a.type] ?? '#5b8df8',
                minWidth: 56, flexShrink: 0,
              }}>
                {a.type}
              </span>
              <span style={{ fontSize: 11.5, color: c.t2, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {a.body}
              </span>
              <span style={{ fontSize: 10, color: c.t4, flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                {timeAgo(a.createdAt)}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </GCard>
  )
}

// ── Compact AI chat ───────────────────────────────────────────────────────────

interface ChatMsg { id: string; role: 'user' | 'bot'; text: string }

function botReply(text: string, kpi: KpiData, name: string): string {
  const q = text.toLowerCase()
  if (q.match(/stock|vehicles|inventory/)) return `You have **${kpi.stockCount} vehicles** in stock — total value **€${(DEALER.stockValue / 1_000_000).toFixed(2)}M**. ${kpi.stockCount > 200 ? '✅ Healthy inventory.' : '⚠️ Consider sourcing more.'}`
  if (q.match(/deal|pipeline|active/))    return `**${kpi.activeDeals} deals** in the pipeline. **8 closing this week** — prioritize Negotiation stage. 💼`
  if (q.match(/stale|old|slow|days/))     return `**3 vehicles over 60 days** in stock. BMW 320d at 72 days is the most critical — consider a **price reduction of 5-8%**. ⏱️`
  if (q.match(/alert|warning/))           return `**${kpi.pendingAlerts} alerts** pending. Main issue: 3 stale vehicles and 1 expired listing. ⚠️`
  if (q.match(/margin|profit|revenue/))   return `Gross margin this month: **€${(kpi.monthMargin / 1000).toFixed(1)}k** (+8% vs last month). On track to hit target. 📈`
  if (q.match(/hi|hello|hey/))            return `Hey ${name}! Ask me about stock levels, pipeline, stale vehicles, or margin performance.`
  return `I can help with stock, deals, stale vehicles, alerts, and margins. What do you need, ${name}?`
}

function proactiveInsight(kpi: KpiData): string {
  if (kpi.pendingAlerts > 0) return `⚠️ **${kpi.pendingAlerts} alerts** — 3 vehicles over 60 days. BMW 320d at 72d needs repricing.`
  if (kpi.stockCount < 200) return `📦 Stock at **${kpi.stockCount}** vehicles. Below healthy threshold — consider sourcing.`
  return `✅ All metrics healthy. Gross margin +8% this month. Keep it up!`
}

function ChatCompact({ kpi, dark, username }: { kpi: KpiData; dark: boolean; username: string }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const c = tok(dark)

  const inputBg    = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)'
  const inputBord  = dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.10)'
  const botBubble  = dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.05)'

  function send(text: string) {
    const t = text.trim()
    if (!t || typing) return
    setMsgs(m => [...m, { id: Date.now().toString(), role: 'user', text: t }])
    setInput('')
    setTyping(true)
    setTimeout(() => {
      setTyping(false)
      setMsgs(m => [...m, { id: (Date.now() + 1).toString(), role: 'bot', text: botReply(t, kpi, username.split(' ')[0]) }])
    }, 600 + Math.random() * 300)
  }

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [msgs, typing])

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 14px 10px', borderBottom: `1px solid ${c.div}`, flexShrink: 0 }}>
          <div style={{
            width: 26, height: 26, borderRadius: 8, flexShrink: 0,
            background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 10px rgba(124,58,237,0.30)',
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: c.t1 }}>CARDEX AI</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <motion.span style={{ width: 5, height: 5, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 2, repeat: Infinity }} />
            <span style={{ fontSize: 9.5, color: '#22c55e', fontWeight: 600 }}>Online</span>
          </div>
        </div>

        {/* Proactive insight (shown when no conversation yet) */}
        {msgs.length === 0 && (
          <div style={{ padding: '10px 12px', flexShrink: 0 }}>
            <div style={{
              padding: '9px 11px', borderRadius: 10,
              background: botBubble,
              fontSize: 11.5, lineHeight: 1.5, color: c.t1,
            }}>
              {renderBold(proactiveInsight(kpi), c.t1)}
            </div>
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 6, minHeight: 0 }}>
          <AnimatePresence initial={false}>
            {msgs.map(msg => (
              <motion.div key={msg.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '88%', padding: '7px 10px',
                  borderRadius: msg.role === 'user' ? '12px 12px 3px 12px' : '12px 12px 12px 3px',
                  background: msg.role === 'user' ? 'linear-gradient(135deg, #7c3aed, #2563eb)' : botBubble,
                  fontSize: 11.5, lineHeight: 1.5,
                  color: msg.role === 'user' ? '#fff' : c.t1,
                  boxShadow: msg.role === 'user' ? '0 3px 10px rgba(124,58,237,0.28)' : 'none',
                }}>
                  {msg.role === 'bot' ? renderBold(msg.text, c.t1) : msg.text}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          <AnimatePresence>
            {typing && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ display: 'flex' }}>
                <div style={{ padding: '8px 12px', borderRadius: '12px 12px 12px 3px', background: botBubble, display: 'flex', gap: 3, alignItems: 'center' }}>
                  {[0,1,2].map(i => (
                    <motion.span key={i} style={{ width: 4, height: 4, borderRadius: '50%', background: c.t3, display: 'block' }} animate={{ y: [0, -4, 0] }} transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.13 }} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Input */}
        <div style={{ padding: '8px 10px', borderTop: `1px solid ${c.div}`, display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder="Ask about stock, deals…"
            style={{
              flex: 1, padding: '6px 10px', borderRadius: 9,
              background: inputBg, border: `1px solid ${inputBord}`,
              color: c.t1, fontSize: 11.5, fontFamily: 'Inter, system-ui', outline: 'none',
            }}
            onFocus={e => (e.currentTarget.style.borderColor = 'rgba(124,58,237,0.38)')}
            onBlur={e => (e.currentTarget.style.borderColor = inputBord)}
          />
          <motion.button
            onClick={() => send(input)}
            disabled={!input.trim() || typing}
            whileTap={{ scale: 0.92 }}
            style={{
              width: 28, height: 28, borderRadius: 8, flexShrink: 0,
              background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
              border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              opacity: !input.trim() || typing ? 0.35 : 1,
              transition: 'opacity 130ms',
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </motion.button>
        </div>
      </div>
    </GCard>
  )
}

// ── Quick actions ─────────────────────────────────────────────────────────────

function QuickActions({ dark, onNavigate }: { dark: boolean; onNavigate: (path: string) => void }) {
  const c = tok(dark)
  const actions = [
    { label: 'Add Vehicle', color: '#5b8df8', icon: <TrendingUp    style={{ width: 13, height: 13, color: '#5b8df8'  }} />, path: '/vehicles'  },
    { label: 'New Deal',    color: '#9b6dff', icon: <ClipboardList style={{ width: 13, height: 13, color: '#9b6dff'  }} />, path: '/deals'     },
    { label: 'Check VIN',  color: '#00d68a', icon: <Search        style={{ width: 13, height: 13, color: '#00d68a'  }} />, path: '/check'     },
    { label: 'Kanban',     color: '#f59e0b', icon: <Zap           style={{ width: 13, height: 13, color: '#f59e0b'  }} />, path: '/kanban'    },
  ]

  return (
    <GCard dark={dark} style={{ height: '100%' }}>
      <div style={{ padding: '18px 16px 14px', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <h2 style={{ fontSize: 13, fontWeight: 700, color: c.t1, marginBottom: 14, flexShrink: 0 }}>Quick Actions</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7, flex: 1 }}>
          {actions.map(a => (
            <motion.button
              key={a.label}
              onClick={() => onNavigate(a.path)}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                width: '100%', padding: '9px 11px',
                background: c.subBg, border: `1px solid ${c.subBord}`,
                borderRadius: 10, cursor: 'pointer',
                transition: 'background 130ms', fontFamily: 'Inter, system-ui',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)')}
              onMouseLeave={e => (e.currentTarget.style.background = c.subBg)}
            >
              <div style={{ width: 26, height: 26, borderRadius: 7, background: `${a.color}18`, border: `1px solid ${a.color}28`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {a.icon}
              </div>
              <span style={{ fontSize: 12, fontWeight: 600, color: c.t2 }}>{a.label}</span>
              <ArrowUpRight style={{ width: 11, height: 11, color: c.t4, marginLeft: 'auto', opacity: 0.6 }} />
            </motion.button>
          ))}
        </div>
      </div>
    </GCard>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const dark = useIsDark()
  const { data, loading } = useApi<KpiData>('/kpi')
  const { user } = useAuthContext()
  const navigate = useNavigate()
  const kpi = data ? { ...MOCK_KPI, ...data } : MOCK_KPI

  if (loading && !data) return <PageSkeleton />

  const c = tok(dark)
  const username = user?.name ?? 'User'

  const kpiCards = [
    {
      label: 'In Stock',
      value: kpi.stockCount,
      sub: `€${(DEALER.stockValue / 1_000_000).toFixed(2)}M capital`,
      trend: 'up' as const,
      trendLabel: '+12 this month',
      accent: '#5b8df8',
      spark: [220, 232, 245, 258, 264, kpi.stockCount],
      delay: 0,
    },
    {
      label: 'Active Deals',
      value: kpi.activeDeals,
      sub: '8 closing this week',
      trend: 'flat' as const,
      trendLabel: 'stable',
      accent: '#9b6dff',
      spark: [42, 48, 51, 53, 54, kpi.activeDeals],
      delay: 0.06,
    },
    {
      label: 'Month Margin',
      value: kpi.monthMargin / 1000,
      prefix: '€',
      suffix: 'k',
      decimals: 1,
      sub: new Date().toLocaleDateString('en-GB', { month: 'long', year: 'numeric' }),
      trend: 'up' as const,
      trendLabel: '+8% vs last month',
      accent: '#22c55e',
      spark: kpi.marginHistory.map(m => m.margin / 1000),
      delay: 0.12,
    },
    {
      label: 'Avg Days In Stock',
      value: DEALER.avgDaysInStock,
      suffix: 'd',
      sub: 'target < 45d',
      trend: 'good' as const,
      trendLabel: 'healthy',
      accent: '#0ea5e9',
      spark: [52, 48, 44, 41, 39, DEALER.avgDaysInStock],
      delay: 0.18,
    },
  ]

  return (
    <div style={{ padding: '24px 24px 40px', maxWidth: 1360, margin: '0 auto' }}>

      {/* Page header */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
        style={{ marginBottom: 22, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}
      >
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: c.t1, lineHeight: 1, marginBottom: 4 }}>
            Overview
          </h1>
          <p style={{ fontSize: 11.5, color: c.t4 }}>
            {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>

        {/* Sold this month progress */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10.5, color: c.t4, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>
              Units Sold
            </div>
            <div style={{ fontSize: 12, fontWeight: 700, color: c.t1 }}>
              {DEALER.soldThisMonth} / {DEALER.targetSoldMonth}
            </div>
          </div>
          <div style={{ width: 80, height: 6, borderRadius: 99, background: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)', overflow: 'hidden' }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(DEALER.soldThisMonth / DEALER.targetSoldMonth) * 100}%` }}
              transition={{ duration: 0.8, delay: 0.3, ease: [0.32, 0.72, 0, 1] }}
              style={{ height: '100%', borderRadius: 99, background: '#22c55e', boxShadow: '0 0 6px rgba(34,197,94,0.5)' }}
            />
          </div>
        </div>
      </motion.div>

      {/* Bento grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>

        {/* Row 1 — KPI metric cards */}
        {kpiCards.map(card => (
          <MetricCard key={card.label} dark={dark} {...card} />
        ))}

        {/* Row 2 — Chart (2 cols) + Pipeline (1 col) + AI Chat (1 col) */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '1 / 3', gridRow: '2', minHeight: 260 }}
        >
          <MarginChart data={kpi.marginHistory} dark={dark} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.28, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '3', gridRow: '2' }}
        >
          <PipelinePanel dark={dark} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '4', gridRow: '2' }}
        >
          <ChatCompact kpi={kpi} dark={dark} username={username} />
        </motion.div>

        {/* Row 3 — Stale (1) + Activity (2) + Follow-ups/QA (1) */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.34, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '1', gridRow: '3' }}
        >
          <StalePanel dark={dark} onNavigate={() => navigate('/vehicles')} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.38, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '2 / 4', gridRow: '3' }}
        >
          <ActivityFeed activities={kpi.recentActivities} dark={dark} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.42, duration: 0.44, ease: [0.32, 0.72, 0, 1] }}
          style={{ gridColumn: '4', gridRow: '3' }}
        >
          <FollowUpsPanel dark={dark} onNavigate={() => navigate('/inbox')} />
        </motion.div>

      </div>
    </div>
  )
}
