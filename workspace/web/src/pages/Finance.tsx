import React from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import Card from '../components/Card'
import { Badge } from '../components/Badge'
import { TrendingDown } from 'lucide-react'
import type { FinanceRow } from '../types'

const MONTHLY = [
  { month: 'Nov 25', revenue: 310000, cost: 249000, margin: 61000 },
  { month: 'Dec 25', revenue: 360000, cost: 288000, margin: 72000 },
  { month: 'Jan 26', revenue: 270000, cost: 216000, margin: 54000 },
  { month: 'Feb 26', revenue: 395000, cost: 316000, margin: 79000 },
  { month: 'Mar 26', revenue: 475000, cost: 380000, margin: 95000 },
  { month: 'Apr 26', revenue: 437000, cost: 349600, margin: 87400 },
]

const TOP_VEHICLES: FinanceRow[] = [
  { vehicleId: 'v1', vehicleName: 'BMW X5 2021', buyPrice: 38000, sellPrice: 46500, margin: 8500,  marginPct: 22.4, soldAt: '2026-04-15' },
  { vehicleId: 'v2', vehicleName: 'Porsche Macan 2020', buyPrice: 44000, sellPrice: 52000, margin: 8000, marginPct: 18.2, soldAt: '2026-04-12' },
  { vehicleId: 'v3', vehicleName: 'Audi Q5 2021', buyPrice: 32000, sellPrice: 38500, margin: 6500, marginPct: 20.3, soldAt: '2026-04-10' },
  { vehicleId: 'v4', vehicleName: 'Mercedes GLC 2020', buyPrice: 36000, sellPrice: 42000, margin: 6000, marginPct: 16.7, soldAt: '2026-04-08' },
  { vehicleId: 'v5', vehicleName: 'BMW 530d 2020', buyPrice: 28000, sellPrice: 33500, margin: 5500, marginPct: 19.6, soldAt: '2026-04-06' },
  { vehicleId: 'v6', vehicleName: 'VW Tiguan 2022', buyPrice: 24000, sellPrice: 29000, margin: 5000, marginPct: 20.8, soldAt: '2026-04-04' },
  { vehicleId: 'v7', vehicleName: 'Skoda Octavia 2021', buyPrice: 14000, sellPrice: 17500, margin: 3500, marginPct: 25.0, soldAt: '2026-04-02' },
  { vehicleId: 'v8', vehicleName: 'Toyota Yaris 2022', buyPrice: 10500, sellPrice: 13500, margin: 3000, marginPct: 28.6, soldAt: '2026-03-30' },
  // Negative margin alerts
  { vehicleId: 'v9', vehicleName: 'Renault Clio 2020', buyPrice: 9000, sellPrice: 8200, margin: -800,  marginPct: -8.9, soldAt: '2026-04-14' },
  { vehicleId: 'v10', vehicleName: 'Citroën C3 2019',  buyPrice: 7500, sellPrice: 7100, margin: -400,  marginPct: -5.3, soldAt: '2026-04-11' },
]

const ALERTS = TOP_VEHICLES.filter((r) => r.margin < 0)

function fmt(n: number) {
  return `€${Math.abs(n).toLocaleString()}`
}

export default function Finance() {
  const totalRevenue = MONTHLY.reduce((s, m) => s + m.revenue, 0)
  const totalMargin  = MONTHLY.reduce((s, m) => s + m.margin,  0)
  const avgMarginPct = (totalMargin / totalRevenue * 100).toFixed(1)

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 dark:text-white">Finance</h1>

      {/* Summary KPIs */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Revenue (6mo)',  value: `€${(totalRevenue / 1000).toFixed(0)}k` },
          { label: 'Margin (6mo)',   value: `€${(totalMargin / 1000).toFixed(0)}k` },
          { label: 'Avg Margin %',   value: `${avgMarginPct}%` },
        ].map(({ label, value }) => (
          <Card key={label}>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
            <p className="text-xl font-bold text-gray-900 dark:text-white">{value}</p>
          </Card>
        ))}
      </div>

      {/* Negative margin alerts */}
      {ALERTS.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <TrendingDown className="w-4 h-4 text-red-500" />
            <h2 className="text-sm font-semibold text-red-600 dark:text-red-400">
              Negative margin alerts ({ALERTS.length})
            </h2>
          </div>
          <div className="space-y-2">
            {ALERTS.map((r) => (
              <div key={r.vehicleId} className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/10 rounded-lg border border-red-100 dark:border-red-800">
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{r.vehicleName}</p>
                  <p className="text-xs text-gray-500">Sold {r.soldAt} · Buy {fmt(r.buyPrice)} → Sell {fmt(r.sellPrice)}</p>
                </div>
                <Badge color="red">
                  -{fmt(Math.abs(r.margin))} ({r.marginPct.toFixed(1)}%)
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Revenue vs Costs bar chart */}
      <Card>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">
          Revenue vs Costs — Fleet P&L
        </h2>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={MONTHLY} margin={{ top: 0, right: 0, left: 0, bottom: 0 }} barSize={20}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `€${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value: number) => [`€${value.toLocaleString()}`, '']}
              contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', fontSize: '12px' }}
            />
            <Legend wrapperStyle={{ fontSize: '11px' }} />
            <Bar dataKey="revenue" fill="#dbeafe" name="Revenue" radius={[4, 4, 0, 0]} />
            <Bar dataKey="cost"    fill="#fecaca" name="Cost"    radius={[4, 4, 0, 0]} />
            <Bar dataKey="margin"  fill="#bbf7d0" name="Margin"  radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* Top 10 vehicles by margin */}
      <Card>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-4">
          Top 10 Vehicles by Margin
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[500px] text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                {['Vehicle', 'Buy', 'Sell', 'Margin', '%', 'Date'].map((h) => (
                  <th key={h} className="pb-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide pr-4">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {TOP_VEHICLES.map((r) => (
                <tr key={r.vehicleId} className={r.margin < 0 ? 'bg-red-50 dark:bg-red-900/10' : ''}>
                  <td className="py-3 pr-4 font-medium text-gray-900 dark:text-white">{r.vehicleName}</td>
                  <td className="py-3 pr-4 text-gray-500">{fmt(r.buyPrice)}</td>
                  <td className="py-3 pr-4 text-gray-500">{fmt(r.sellPrice)}</td>
                  <td className={`py-3 pr-4 font-semibold ${r.margin < 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {r.margin < 0 ? '-' : '+'}{fmt(r.margin)}
                  </td>
                  <td className={`py-3 pr-4 text-xs font-medium ${r.marginPct < 0 ? 'text-red-500' : 'text-gray-500'}`}>
                    {r.marginPct.toFixed(1)}%
                  </td>
                  <td className="py-3 text-gray-400 text-xs">{r.soldAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
