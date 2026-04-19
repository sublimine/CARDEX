import React, { useId } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowLeft, Copy, Share2, Download, RefreshCw,
  CheckCircle2, AlertTriangle, AlertOctagon,
  Car, MapPin, FileCheck, RotateCcw,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceDot,
} from 'recharts'
import { Badge } from '../../components/Badge'
import AlertCard from '../../components/AlertCard'
import Timeline from '../../components/Timeline'
import ScoreGauge from '../../components/ScoreGauge'
import { SourceBadge } from '../../components/SourceBadge'
import { cn } from '../../lib/cn'
import type {
  VehicleReport, InspectionRecord, RecallEntry, MileageRecord,
} from '../../types/check'

// ── Formatters ────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(navigator.language, {
      year: 'numeric', month: 'long', day: 'numeric',
    })
  } catch { return iso }
}

function formatDateShort(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(navigator.language, {
      year: 'numeric', month: 'short',
    })
  } catch { return iso }
}

function fmtKm(km: number): string {
  return new Intl.NumberFormat(navigator.language).format(km) + ' km'
}

// ── Animation variants ────────────────────────────────────────────────────────

const container = {
  hidden:   {},
  visible:  { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
}

const sectionItem = {
  hidden:  { opacity: 0, y: 14 },
  visible: {
    opacity: 1, y: 0,
    transition: { type: 'spring' as const, stiffness: 380, damping: 30 },
  },
}

// ── Status indicator ──────────────────────────────────────────────────────────

function StatusIndicator({ status }: { status: VehicleReport['overallStatus'] }) {
  const configs = {
    clean: {
      className: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20',
      dot:   'bg-emerald-400 animate-pulse',
      Icon:  CheckCircle2,
      label: 'Sin alertas',
    },
    attention: {
      className: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
      dot:   'bg-amber-400',
      Icon:  AlertTriangle,
      label: 'Atención requerida',
    },
    alerts: {
      className: 'bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20',
      dot:   'bg-rose-400 animate-pulse',
      Icon:  AlertOctagon,
      label: 'Alertas activas',
    },
  }
  const cfg = configs[status] ?? configs.attention
  const { Icon } = cfg

  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium', cfg.className)}>
      <Icon className="w-3.5 h-3.5" strokeWidth={2} />
      {cfg.label}
    </span>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({
  title,
  icon,
  children,
  count,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  count?: number
}) {
  return (
    <motion.div variants={sectionItem} className="glass rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle flex items-center gap-2">
        {icon && <span className="text-text-muted shrink-0">{icon}</span>}
        <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-[0.12em] flex-1">
          {title}
        </h2>
        {count !== undefined && (
          <span className="text-[10px] font-medium text-text-muted tabular-nums">
            {count}
          </span>
        )}
      </div>
      <div className="p-5">{children}</div>
    </motion.div>
  )
}

// ── VIN Decode grid ───────────────────────────────────────────────────────────

function VINDecodeGrid({ decode }: { decode: VehicleReport['vinDecode'] }) {
  const fields: [string, string | number | undefined][] = [
    ['Fabricante',       decode.manufacturer],
    ['Marca',            decode.make],
    ['Modelo',           decode.model],
    ['Año',              decode.year],
    ['Carrocería',       decode.bodyType],
    ['Combustible',      decode.fuelType],
    ['Motorización',     decode.engineDisplacement],
    ['Tracción',         decode.driveType],
    ['País fabricación', decode.countryOfManufacture],
    ['Planta',           decode.plant],
  ]
  const visible = fields.filter(([, v]) => v !== undefined && v !== '')

  return (
    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
      {visible.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[10px] font-medium text-text-muted uppercase tracking-widest mb-0.5">
            {label}
          </dt>
          <dd className="text-sm font-medium text-text-primary">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

// ── Inspection timeline ───────────────────────────────────────────────────────

function inspectionItems(inspections: InspectionRecord[]) {
  return [...inspections]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map((ins) => ({
      id: ins.id,
      date: formatDate(ins.date),
      accent: ins.result === 'pass' ? 'green' as const
            : ins.result === 'fail' ? 'red' as const
            : 'yellow' as const,
      title: ins.center ? `${ins.center} · ${ins.country}` : ins.country,
      subtitle: ins.mileageKm !== undefined ? fmtKm(ins.mileageKm) : undefined,
      badge: (
        <Badge color={ins.result === 'pass' ? 'green' : ins.result === 'fail' ? 'red' : 'yellow'}>
          {ins.result === 'pass' ? 'PASS' : ins.result === 'fail' ? 'FAIL' : 'AVISO'}
        </Badge>
      ),
      body: ins.nextInspectionDate
        ? <p className="text-xs text-text-muted mt-0.5">Próxima: {formatDate(ins.nextInspectionDate)}</p>
        : undefined,
    }))
}

// ── Recall row ────────────────────────────────────────────────────────────────

function RecallRow({ recall }: { recall: RecallEntry }) {
  const isOpen = recall.status === 'open'
  return (
    <div className={cn(
      'rounded-lg border p-3.5',
      isOpen
        ? 'border-rose-500/25 bg-rose-500/8'
        : 'border-border-subtle bg-glass-subtle'
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Badge color={isOpen ? 'red' : 'green'} dot={isOpen} pulse={isOpen}>
              {isOpen ? 'Abierto' : 'Completado'}
            </Badge>
            <span className="text-[10px] text-text-muted font-mono">{recall.campaignId}</span>
          </div>
          <p className="text-sm font-medium text-text-primary">{recall.description}</p>
          <p className="text-xs text-text-muted mt-0.5">
            Componente: {recall.affectedComponent}
          </p>
        </div>
      </div>
      <div className="flex gap-4 mt-2 text-[10px] text-text-muted font-mono">
        <span>Inicio: {formatDateShort(recall.startDate)}</span>
        {recall.completionDate && <span>Cierre: {formatDateShort(recall.completionDate)}</span>}
      </div>
    </div>
  )
}

// ── Mileage area chart ────────────────────────────────────────────────────────

interface MileageChartProps {
  history: MileageRecord[]
  consistencyScore?: number
}

function MileageSection({ history, consistencyScore }: MileageChartProps) {
  const gradId = useId()

  if (history.length === 0) {
    return (
      <p className="text-sm text-text-muted italic py-4">
        No se encontraron registros de kilometraje en las fuentes disponibles.
      </p>
    )
  }

  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date))
  const chartData = sorted.map((r) => ({
    date:      formatDateShort(r.date),
    km:        r.mileageKm,
    isAnomaly: r.isAnomaly,
  }))

  const anomalies = chartData
    .map((d, i) => ({ ...d, index: i }))
    .filter((d) => d.isAnomaly)

  return (
    <div className="space-y-5">
      {/* Score — only if enough data points */}
      {consistencyScore !== undefined && history.length >= 3 && (
        <div className="flex flex-col sm:flex-row items-center gap-5 p-4 rounded-xl bg-glass-subtle border border-border-subtle/60">
          <div className="shrink-0">
            <ScoreGauge score={consistencyScore} size={140} label="Consistencia" />
          </div>
          <div className="text-sm text-center sm:text-left">
            <p className="font-semibold text-text-primary">
              {consistencyScore >= 80
                ? 'Kilometraje consistente'
                : consistencyScore >= 50
                ? 'Inconsistencias menores'
                : 'Inconsistencias significativas'}
            </p>
            <p className="text-xs text-text-muted mt-1 max-w-xs leading-relaxed">
              {consistencyScore >= 80
                ? 'La progresión registrada es normal y no presenta señales de manipulación.'
                : consistencyScore >= 50
                ? 'Se detectaron algunas variaciones. Solicita documentación adicional.'
                : 'Anomalías significativas detectadas. Se recomienda inspección profesional.'}
            </p>
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 12, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="var(--color-blue)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--color-blue)" stopOpacity={0}    />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="2 4"
              stroke="var(--border-subtle)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
                fontSize: 12,
                color: 'var(--text-primary)',
              }}
              formatter={(value: number) => [fmtKm(value), 'Kilometraje']}
              labelStyle={{ color: 'var(--text-muted)', marginBottom: 2 }}
            />
            <Area
              type="monotone"
              dataKey="km"
              stroke="var(--color-blue)"
              strokeWidth={2}
              fill={`url(#${gradId})`}
              dot={{ fill: 'var(--color-blue)', r: 3, strokeWidth: 0 }}
              activeDot={{ r: 5, fill: 'var(--color-blue)', strokeWidth: 2, stroke: 'var(--bg-elevated)' }}
            />
            {anomalies.map((a) => (
              <ReferenceDot
                key={a.index}
                x={a.date}
                y={a.km}
                r={6}
                fill="var(--color-rose)"
                stroke="var(--bg-elevated)"
                strokeWidth={2}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {anomalies.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-accent-rose">
          <span className="w-2.5 h-2.5 rounded-full bg-accent-rose shrink-0" />
          Los puntos rojos indican registros con kilometraje anómalo respecto a la tendencia esperada.
        </div>
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

  const openRecalls   = recalls.filter((r) => r.status === 'open')
  const closedRecalls = recalls.filter((r) => r.status !== 'open')

  return (
    <div className="min-h-[100dvh] bg-bg-primary">
      {/* ── Action bar ── */}
      <div className="sticky top-12 z-[var(--z-raised)] bg-bg-surface/60 backdrop-blur border-b border-border-subtle">
        <div className="max-w-5xl mx-auto px-5 h-11 flex items-center justify-between">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-primary transition-colors duration-150 group"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition-transform duration-150 group-hover:-translate-x-0.5" />
            Nueva consulta
          </button>

          <div className="flex items-center gap-1">
            <button
              onClick={onRefresh}
              title="Actualizar"
              className="w-7 h-7 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-glass-subtle transition-all duration-150"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={shareLink}
              title="Copiar enlace"
              className="w-7 h-7 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-glass-subtle transition-all duration-150"
            >
              <Share2 className="w-3.5 h-3.5" />
            </button>
            <button
              title="Descargar PDF (próximamente)"
              disabled
              className="w-7 h-7 rounded-md flex items-center justify-center text-text-muted/30 cursor-not-allowed"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* ── Page content ── */}
      <div className="max-w-5xl mx-auto px-5 py-6 space-y-5">

        {/* ── Hero identity card ── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          className="glass-strong rounded-xl overflow-hidden"
        >
          {/* Top label strip */}
          <div className="px-5 pt-4 pb-0 flex items-center gap-2">
            <Car className="w-3.5 h-3.5 text-text-muted" strokeWidth={1.5} />
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-[0.16em]">
              Informe vehicular
            </span>
          </div>

          {/* Body */}
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5 px-5 py-5">
            {/* Vehicle identity */}
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-primary leading-tight">
                {vehicleTitle || 'Vehículo'}
              </h1>

              {/* VIN row */}
              <div className="flex items-center gap-2 mt-2">
                <span className="font-mono text-sm text-text-secondary tracking-[0.18em] select-all">
                  {report.vin}
                </span>
                <button
                  onClick={copyVIN}
                  title="Copiar VIN"
                  className="text-text-muted hover:text-text-primary transition-colors duration-150 active:scale-90"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Manufacturer + country */}
              {(d.manufacturer || d.countryOfManufacture) && (
                <p className="mt-1.5 text-xs text-text-muted">
                  {[d.manufacturer, d.countryOfManufacture].filter(Boolean).join(' · ')}
                </p>
              )}

              {/* Generated at */}
              <p className="mt-3 text-[10px] text-text-muted">
                Informe generado el {formatDate(report.generatedAt)}
              </p>
            </div>

            {/* Right: gauge + status */}
            <div className="flex flex-row sm:flex-col items-center sm:items-end gap-4">
              {mileageConsistencyScore !== undefined && mileageHistory.length >= 3 && (
                <ScoreGauge score={mileageConsistencyScore} size={120} label="Consistencia" />
              )}
              <StatusIndicator status={report.overallStatus} />
            </div>
          </div>
        </motion.div>

        {/* ── Alert section (full width, only if present) ── */}
        {alerts.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, type: 'spring', stiffness: 300, damping: 28 }}
          >
            <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 overflow-hidden">
              <div className="px-5 py-3 border-b border-rose-500/15 flex items-center gap-2">
                <AlertOctagon className="w-3.5 h-3.5 text-accent-rose shrink-0" />
                <span className="text-[11px] font-semibold text-accent-rose uppercase tracking-[0.12em]">
                  Alertas ({alerts.length})
                </span>
              </div>
              <div className="p-5 space-y-3">
                {alerts.map((a, idx) => (
                  <AlertCard key={a.id} alert={a} index={idx} />
                ))}
              </div>
            </div>
          </motion.div>
        )}

        {/* ── Two-column layout ── */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5 items-start">

          {/* ── Main column ── */}
          <motion.div
            variants={container}
            initial="hidden"
            animate="visible"
            className="space-y-5 min-w-0"
          >
            {/* Identity */}
            <Section
              title="Identidad del vehículo"
              icon={<Car className="w-3.5 h-3.5" strokeWidth={1.5} />}
            >
              <VINDecodeGrid decode={d} />
            </Section>

            {/* Inspections */}
            <Section
              title="Historial de inspecciones"
              icon={<FileCheck className="w-3.5 h-3.5" strokeWidth={1.5} />}
              count={inspections.length > 0 ? inspections.length : undefined}
            >
              <Timeline
                items={inspectionItems(inspections)}
                emptyMessage="No se encontraron datos de inspección en las fuentes disponibles."
              />
            </Section>

            {/* Recalls */}
            <Section
              title={`Recalls`}
              icon={<RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />}
              count={recalls.length > 0 ? recalls.length : undefined}
            >
              {recalls.length === 0 ? (
                <p className="text-sm text-text-muted italic">
                  No se encontraron recalls registrados para este vehículo.
                </p>
              ) : (
                <div className="space-y-3">
                  {openRecalls.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-accent-rose uppercase tracking-widest mb-2.5">
                        Abiertos ({openRecalls.length})
                      </p>
                      <div className="space-y-2.5">
                        {openRecalls.map((r) => <RecallRow key={r.campaignId} recall={r} />)}
                      </div>
                    </div>
                  )}
                  {closedRecalls.length > 0 && (
                    <div className={openRecalls.length > 0 ? 'mt-4' : ''}>
                      {openRecalls.length > 0 && (
                        <p className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-2.5">
                          Completados ({closedRecalls.length})
                        </p>
                      )}
                      <div className="space-y-2.5">
                        {closedRecalls.map((r) => <RecallRow key={r.campaignId} recall={r} />)}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Section>

            {/* Mileage */}
            <Section
              title="Historial de kilometraje"
              icon={<MapPin className="w-3.5 h-3.5" strokeWidth={1.5} />}
              count={mileageHistory.length > 0 ? mileageHistory.length : undefined}
            >
              <MileageSection
                history={mileageHistory}
                consistencyScore={mileageConsistencyScore}
              />
            </Section>
          </motion.div>

          {/* ── Sidebar ── */}
          <motion.div
            variants={container}
            initial="hidden"
            animate="visible"
            className="space-y-5"
          >
            {/* Data sources */}
            <motion.div variants={sectionItem} className="glass rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border-subtle">
                <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-[0.12em]">
                  Fuentes consultadas
                </h2>
              </div>
              <div className="px-4 py-3">
                {dataSources.map((s, i) => (
                  <SourceBadge key={s.id} source={s} index={i} />
                ))}
              </div>
            </motion.div>

            {/* Disclaimer */}
            <motion.div variants={sectionItem}>
              <p className="text-[11px] text-text-muted leading-relaxed px-1">
                CARDEX Check consulta fuentes oficiales y públicas. La disponibilidad varía
                por país y tipo de dato. La ausencia de alertas no garantiza que el vehículo
                esté libre de problemas.
              </p>
            </motion.div>
          </motion.div>

        </div>
      </div>
    </div>
  )
}
