import React from 'react'
import {
  CheckCircle2, AlertTriangle, AlertOctagon, Copy, Share2, ChevronLeft,
  Download, RefreshCw,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot,
  ResponsiveContainer, Legend,
} from 'recharts'
import { Badge } from '../../components/Badge'
import AlertCard from '../../components/AlertCard'
import Timeline from '../../components/Timeline'
import ScoreGauge from '../../components/ScoreGauge'
import { SourceBadge } from '../../components/SourceBadge'
import type {
  VehicleReport, InspectionRecord, RecallEntry, MileageRecord,
} from '../../types/check'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(navigator.language, {
      year: 'numeric', month: 'long', day: 'numeric',
    })
  } catch {
    return iso
  }
}

function formatDateShort(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(navigator.language, {
      year: 'numeric', month: 'short',
    })
  } catch {
    return iso
  }
}

function fmtKm(km: number): string {
  return new Intl.NumberFormat(navigator.language).format(km) + ' km'
}

// ── Overall status badge ──────────────────────────────────────────────────────

function OverallBadge({ status }: { status: VehicleReport['overallStatus'] }) {
  if (status === 'clean') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 text-sm font-semibold">
        <CheckCircle2 className="w-4 h-4" /> Sin alertas
      </span>
    )
  }
  if (status === 'attention') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400 text-sm font-semibold">
        <AlertTriangle className="w-4 h-4" /> Atención requerida
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 text-sm font-semibold">
      <AlertOctagon className="w-4 h-4" /> Alertas activas
    </span>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, children, className = '' }: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={`bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden ${className}`}>
      <div className="px-5 py-3.5 border-b border-gray-100 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 uppercase tracking-wide">
          {title}
        </h2>
      </div>
      <div className="p-5">{children}</div>
    </section>
  )
}

// ── VIN Decode grid ───────────────────────────────────────────────────────────

function VINDecodeGrid({ decode }: { decode: VehicleReport['vinDecode'] }) {
  const fields: [string, string | number | undefined][] = [
    ['Fabricante', decode.manufacturer],
    ['Marca', decode.make],
    ['Modelo', decode.model],
    ['Año', decode.year],
    ['Carrocería', decode.bodyType],
    ['Combustible', decode.fuelType],
    ['Motorización', decode.engineDisplacement],
    ['Tracción', decode.driveType],
    ['País de fabricación', decode.countryOfManufacture],
    ['Planta de ensamblaje', decode.plant],
  ]

  const available = fields.filter(([, v]) => v !== undefined && v !== '')

  return (
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
      {available.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide">{label}</dt>
          <dd className="text-sm font-medium text-gray-900 dark:text-white mt-0.5">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

// ── Inspections ───────────────────────────────────────────────────────────────

function inspectionItems(inspections: InspectionRecord[]) {
  return [...inspections]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map((ins) => ({
      id: ins.id,
      date: formatDate(ins.date),
      accent: ins.result === 'pass' ? 'green' as const : ins.result === 'fail' ? 'red' as const : 'yellow' as const,
      title: ins.center ? `${ins.center} · ${ins.country}` : ins.country,
      subtitle: ins.mileageKm !== undefined ? fmtKm(ins.mileageKm) : undefined,
      badge: (
        <Badge color={ins.result === 'pass' ? 'green' : ins.result === 'fail' ? 'red' : 'yellow'}>
          {ins.result === 'pass' ? 'PASS' : ins.result === 'fail' ? 'FAIL' : 'AVISO'}
        </Badge>
      ),
      body: ins.nextInspectionDate
        ? <p className="text-xs text-gray-400 mt-0.5">Próxima: {formatDate(ins.nextInspectionDate)}</p>
        : undefined,
    }))
}

// ── Recalls ───────────────────────────────────────────────────────────────────

function RecallRow({ recall }: { recall: RecallEntry }) {
  const isOpen = recall.status === 'open'
  return (
    <div className={`rounded-lg border p-3.5 ${isOpen ? 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20' : 'border-gray-100 dark:border-gray-700'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge color={isOpen ? 'red' : 'green'} dot>
              {isOpen ? 'Abierto' : 'Completado'}
            </Badge>
            <span className="text-[11px] text-gray-400">{recall.campaignId}</span>
          </div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">{recall.description}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Componente: {recall.affectedComponent}
          </p>
        </div>
      </div>
      <div className="flex gap-3 mt-2 text-[11px] text-gray-400">
        <span>Inicio: {formatDateShort(recall.startDate)}</span>
        {recall.completionDate && <span>Cierre: {formatDateShort(recall.completionDate)}</span>}
      </div>
    </div>
  )
}

// ── Mileage chart ─────────────────────────────────────────────────────────────

interface MileageChartProps {
  history: MileageRecord[]
  consistencyScore?: number
}

function MileageSection({ history, consistencyScore }: MileageChartProps) {
  if (history.length === 0) {
    return (
      <p className="text-sm text-gray-400 dark:text-gray-500 italic">
        No se encontraron registros de kilometraje en las fuentes disponibles.
      </p>
    )
  }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date))

  const chartData = sorted.map((r) => ({
    date: formatDateShort(r.date),
    km: r.mileageKm,
    isAnomaly: r.isAnomaly,
    source: r.source,
  }))

  // Simple linear trend line endpoints
  const first = sorted[0].mileageKm
  const last = sorted[sorted.length - 1].mileageKm
  const trendData = sorted.map((r, i) => ({
    date: formatDateShort(r.date),
    trend: Math.round(first + ((last - first) * i) / Math.max(sorted.length - 1, 1)),
  }))

  // Merge
  const merged = chartData.map((d, i) => ({ ...d, trend: trendData[i].trend }))

  return (
    <div className="space-y-5">
      {/* Score gauge — only if enough data points */}
      {consistencyScore !== undefined && history.length >= 3 && (
        <div className="flex flex-col sm:flex-row items-center gap-4 p-4 rounded-xl bg-gray-50 dark:bg-gray-900/40 border border-gray-100 dark:border-gray-700">
          <ScoreGauge score={consistencyScore} size={160} label="Consistencia kilometraje" />
          <div className="text-sm text-gray-600 dark:text-gray-300 text-center sm:text-left">
            <p className="font-medium text-gray-900 dark:text-white">
              {consistencyScore >= 80 ? 'Kilometraje consistente' : consistencyScore >= 50 ? 'Inconsistencias menores' : 'Inconsistencias significativas'}
            </p>
            <p className="text-xs text-gray-400 mt-1 max-w-xs">
              {consistencyScore >= 80
                ? 'El kilometraje registrado sigue una progresión normal y no muestra señales de manipulación.'
                : consistencyScore >= 50
                ? 'Se detectaron algunas variaciones en el kilometraje. Solicita documentación adicional al vendedor.'
                : 'Se detectaron anomalías significativas. Se recomienda una inspección profesional antes de la compra.'}
            </p>
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="h-52 w-full -ml-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={merged} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" className="dark:stroke-gray-700" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#9ca3af" />
            <YAxis
              tick={{ fontSize: 10 }}
              stroke="#9ca3af"
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(value: number, name: string) => [
                fmtKm(value),
                name === 'km' ? 'Kilometraje' : 'Tendencia',
              ]}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend formatter={(v) => v === 'km' ? 'Kilometraje' : 'Tendencia'} iconSize={10} />
            <Line
              type="monotone"
              dataKey="km"
              stroke="#2563eb"
              strokeWidth={2}
              dot={(props: { cx: number; cy: number; payload: { isAnomaly?: boolean } }) => {
                if (props.payload.isAnomaly) {
                  return <circle key={`dot-${props.cx}`} cx={props.cx} cy={props.cy} r={5} fill="#ef4444" stroke="white" strokeWidth={1.5} />
                }
                return <circle key={`dot-${props.cx}`} cx={props.cx} cy={props.cy} r={3} fill="#2563eb" />
              }}
            />
            <Line
              type="linear"
              dataKey="trend"
              stroke="#9ca3af"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {history.some((r) => r.isAnomaly) && (
        <p className="text-xs text-red-600 dark:text-red-400">
          ⚠ Los puntos marcados en rojo son registros con kilometraje anómalo respecto a la tendencia esperada.
        </p>
      )}
    </div>
  )
}

// ── Main report ───────────────────────────────────────────────────────────────

interface CheckReportProps {
  report: VehicleReport
  onBack: () => void
  onRefresh: () => void
}

export default function CheckReport({ report, onBack, onRefresh }: CheckReportProps) {
  const { vinDecode: d, alerts, inspections, recalls, mileageHistory, mileageConsistencyScore, dataSources } = report

  const vehicleTitle = [d.make, d.model, d.year].filter(Boolean).join(' ')

  async function copyVIN() {
    await navigator.clipboard.writeText(report.vin).catch(() => null)
  }

  function shareLink() {
    const url = `${window.location.origin}/check/${report.vin}`
    navigator.clipboard.writeText(url).catch(() => null)
  }

  const openRecalls = recalls.filter((r) => r.status === 'open')
  const closedRecalls = recalls.filter((r) => r.status !== 'open')

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
      {/* Back + actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Nueva consulta
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            title="Actualizar informe"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={shareLink}
            title="Copiar enlace"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <Share2 className="w-4 h-4" />
          </button>
          <button
            title="Descargar PDF (próximamente)"
            disabled
            className="p-2 rounded-lg text-gray-300 dark:text-gray-600 cursor-not-allowed"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Header card */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">{vehicleTitle || 'Vehículo'}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-sm text-gray-500 dark:text-gray-400 tracking-wider">
                {report.vin}
              </span>
              <button onClick={copyVIN} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors" title="Copiar VIN">
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <OverallBadge status={report.overallStatus} />
        </div>
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
          Informe generado el {formatDate(report.generatedAt)}
        </p>
      </div>

      {/* Section 1: Identity */}
      <Section title="Identidad del vehículo">
        <VINDecodeGrid decode={d} />
      </Section>

      {/* Section 2: Alerts (only if present) */}
      {alerts.length > 0 && (
        <Section title={`Alertas (${alerts.length})`}>
          <div className="space-y-3">
            {alerts.map((a) => <AlertCard key={a.id} alert={a} />)}
          </div>
        </Section>
      )}

      {/* Section 3: Inspections */}
      <Section title="Historial de inspecciones">
        <Timeline
          items={inspectionItems(inspections)}
          emptyMessage="No se encontraron datos de inspección en las fuentes disponibles."
        />
      </Section>

      {/* Section 4: Recalls */}
      <Section title={`Recalls${recalls.length > 0 ? ` (${recalls.length})` : ''}`}>
        {recalls.length === 0 ? (
          <p className="text-sm text-gray-400 dark:text-gray-500 italic">
            No se encontraron recalls registrados para este vehículo.
          </p>
        ) : (
          <div className="space-y-3">
            {openRecalls.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wide mb-2">
                  Recalls abiertos ({openRecalls.length})
                </p>
                {openRecalls.map((r) => <RecallRow key={r.campaignId} recall={r} />)}
              </div>
            )}
            {closedRecalls.length > 0 && (
              <div className={openRecalls.length > 0 ? 'mt-4' : ''}>
                {openRecalls.length > 0 && (
                  <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-2">
                    Recalls completados ({closedRecalls.length})
                  </p>
                )}
                {closedRecalls.map((r) => <RecallRow key={r.campaignId} recall={r} />)}
              </div>
            )}
          </div>
        )}
      </Section>

      {/* Section 5: Mileage */}
      <Section title="Historial de kilometraje">
        <MileageSection history={mileageHistory} consistencyScore={mileageConsistencyScore} />
      </Section>

      {/* Section 6: Data sources */}
      <Section title="Fuentes de datos consultadas">
        <div>
          {dataSources.map((s) => <SourceBadge key={s.id} source={s} />)}
        </div>
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
          CARDEX Check consulta fuentes de datos oficiales y públicas. La disponibilidad varía según el país
          y el tipo de dato. La ausencia de alertas no garantiza que el vehículo esté libre de problemas.
        </p>
      </Section>
    </div>
  )
}
