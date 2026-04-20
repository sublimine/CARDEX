import React, { useId } from 'react'
import { motion } from 'framer-motion'
import {
  ArrowLeft, Copy, Share2, Download, RefreshCw,
  CheckCircle2, AlertTriangle, AlertOctagon,
  Car, MapPin, FileCheck, RotateCcw, Fuel, Gauge,
  Zap, Weight, Leaf, Globe, Calendar, Hash, Shield,
  ShieldAlert, ShieldCheck, Settings2, Flag,
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
  VehicleReport, PlateInfo, InspectionRecord, RecallEntry, MileageRecord,
  MileageConsistency, ReportOverallStatus, TechnicalSpecsRecord,
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

function consistencyToScore(mc: MileageConsistency | null | undefined): number | undefined {
  if (mc == null) return undefined
  if (mc.consistent) return 100
  return Math.max(0, 100 - mc.rollbacks * 30 - mc.highGaps * 15)
}

function deriveOverallStatus(alerts: VehicleReport['alerts']): ReportOverallStatus {
  const list = alerts ?? []
  if (list.some((a) => a.severity === 'critical')) return 'alerts'
  if (list.some((a) => a.severity === 'warning'))  return 'attention'
  return 'clean'
}

function kwToCV(kw: number): number {
  return Math.round(kw * 1.35962)
}

const COUNTRY_FLAG: Record<string, string> = {
  NL: '🇳🇱', ES: '🇪🇸', FR: '🇫🇷', DE: '🇩🇪', BE: '🇧🇪', CH: '🇨🇭',
  IT: '🇮🇹', PT: '🇵🇹', AT: '🇦🇹', SE: '🇸🇪', NO: '🇳🇴', DK: '🇩🇰',
  PL: '🇵🇱', US: '🇺🇸', GB: '🇬🇧', JP: '🇯🇵', KR: '🇰🇷', CN: '🇨🇳',
}

// ── Animation variants ────────────────────────────────────────────────────────

const container = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
}

const sectionItem = {
  hidden:  { opacity: 0, y: 14 },
  visible: {
    opacity: 1, y: 0,
    transition: { type: 'spring' as const, stiffness: 380, damping: 30 },
  },
}

// ── Status indicator ──────────────────────────────────────────────────────────

function StatusIndicator({ status }: { status: ReportOverallStatus }) {
  const configs: Record<ReportOverallStatus, {
    className: string; dot: string; Icon: React.ElementType; label: string
  }> = {
    clean: {
      className: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20',
      dot: 'bg-emerald-400 animate-pulse',
      Icon: CheckCircle2,
      label: 'Sin alertas',
    },
    attention: {
      className: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
      dot: 'bg-amber-400',
      Icon: AlertTriangle,
      label: 'Atención requerida',
    },
    alerts: {
      className: 'bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20',
      dot: 'bg-rose-400 animate-pulse',
      Icon: AlertOctagon,
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
  title, icon, children, count, accent,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  count?: number
  accent?: 'rose' | 'amber'
}) {
  return (
    <motion.div variants={sectionItem} className={cn(
      'glass rounded-xl overflow-hidden',
      accent === 'rose' && 'border border-rose-500/20',
      accent === 'amber' && 'border border-amber-500/20',
    )}>
      <div className={cn(
        'px-5 py-3 border-b border-border-subtle flex items-center gap-2',
        accent === 'rose' && 'bg-rose-500/5 border-rose-500/15',
        accent === 'amber' && 'bg-amber-500/5 border-amber-500/15',
      )}>
        {icon && <span className={cn(
          'shrink-0',
          accent === 'rose' ? 'text-accent-rose' : accent === 'amber' ? 'text-amber-400' : 'text-text-muted',
        )}>{icon}</span>}
        <h2 className={cn(
          'text-[11px] font-semibold uppercase tracking-[0.12em] flex-1',
          accent === 'rose' ? 'text-accent-rose' : accent === 'amber' ? 'text-amber-400' : 'text-text-muted',
        )}>
          {title}
        </h2>
        {count !== undefined && (
          <span className="text-[10px] font-medium text-text-muted tabular-nums">{count}</span>
        )}
      </div>
      <div className="p-5">{children}</div>
    </motion.div>
  )
}

// ── Spec row ──────────────────────────────────────────────────────────────────

function SpecRow({
  icon, label, value, mono,
}: {
  icon: React.ReactNode
  label: string
  value: string | number
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-border-subtle/50 last:border-0">
      <div className="flex items-center gap-2 text-text-muted min-w-0">
        <span className="shrink-0 w-4">{icon}</span>
        <span className="text-xs truncate">{label}</span>
      </div>
      <span className={cn(
        'text-sm font-medium text-text-primary text-right',
        mono && 'font-mono tracking-wide',
      )}>
        {value}
      </span>
    </div>
  )
}

// ── Data field ────────────────────────────────────────────────────────────────

function DataField({ label, value, mono }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] font-medium text-text-muted uppercase tracking-widest mb-0.5">
        {label}
      </dt>
      <dd className={cn(
        'text-sm font-medium text-text-primary',
        mono && 'font-mono tracking-wide',
      )}>
        {value}
      </dd>
    </div>
  )
}

// ── Technical specs ───────────────────────────────────────────────────────────

function TechnicalSpecsSection({ p }: { p: PlateInfo }) {
  const specs: { icon: React.ReactNode; label: string; value: string | number; mono?: boolean }[] = []

  if (p.fuel_type)
    specs.push({ icon: <Fuel className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Combustible', value: p.fuel_type })
  if (p.displacement_cc)
    specs.push({ icon: <Settings2 className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Cilindrada', value: `${p.displacement_cc.toLocaleString()} cm³`, mono: true })
  if (p.power_kw)
    specs.push({ icon: <Zap className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Potencia', value: `${p.power_kw} kW · ${kwToCV(p.power_kw)} CV`, mono: true })
  if (p.empty_weight_kg)
    specs.push({ icon: <Weight className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Peso vacío', value: `${p.empty_weight_kg.toLocaleString()} kg`, mono: true })
  if (p.gross_weight_kg)
    specs.push({ icon: <Weight className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'MMA', value: `${p.gross_weight_kg.toLocaleString()} kg`, mono: true })
  if (p.co2_g_per_km)
    specs.push({ icon: <Leaf className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'CO₂', value: `${p.co2_g_per_km} g/km`, mono: true })
  if (p.euro_norm)
    specs.push({ icon: <Leaf className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Norma Euro', value: p.euro_norm })
  if (p.color)
    specs.push({ icon: <Car className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Color', value: p.color })
  if (p.body_type)
    specs.push({ icon: <Car className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Carrocería', value: p.body_type })
  if (p.number_of_seats)
    specs.push({ icon: <Car className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Plazas', value: p.number_of_seats, mono: true })
  if (p.number_of_cylinders)
    specs.push({ icon: <Settings2 className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Cilindros', value: p.number_of_cylinders, mono: true })
  if (p.environmental_badge)
    specs.push({ icon: <Leaf className="w-3.5 h-3.5" strokeWidth={1.5} />, label: 'Distintivo ambiental', value: p.environmental_badge })

  if (specs.length === 0) return null

  return (
    <Section
      title="Especificaciones técnicas"
      icon={<Gauge className="w-3.5 h-3.5" strokeWidth={1.5} />}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-0 divide-border-subtle/0">
        <div className="sm:pr-5 sm:border-r sm:border-border-subtle/50">
          {specs.slice(0, Math.ceil(specs.length / 2)).map((s) => (
            <SpecRow key={s.label} icon={s.icon} label={s.label} value={s.value} mono={s.mono} />
          ))}
        </div>
        <div className="sm:pl-5">
          {specs.slice(Math.ceil(specs.length / 2)).map((s) => (
            <SpecRow key={s.label} icon={s.icon} label={s.label} value={s.value} mono={s.mono} />
          ))}
        </div>
      </div>
    </Section>
  )
}

// ── Identification grid ───────────────────────────────────────────────────────

function IdentificationSection({
  report,
}: {
  report: VehicleReport
}) {
  const d = report.vinDecode ?? undefined
  const p = report.plateInfo ?? undefined

  const fields: { label: string; value: string | number; mono?: boolean }[] = []

  // VIN
  if (report.vin) fields.push({ label: 'VIN', value: report.vin, mono: true })
  // Plate
  if (p?.plate) fields.push({ label: 'Matrícula', value: p.plate, mono: true })

  // From VIN decode
  if (d?.manufacturer && d.manufacturer !== d.make)
    fields.push({ label: 'Fabricante', value: d.manufacturer })
  if (d?.make)   fields.push({ label: 'Marca', value: d.make })
  if (d?.model)  fields.push({ label: 'Modelo', value: d.model })
  if (d?.year)   fields.push({ label: 'Año', value: d.year, mono: true })
  if (d?.bodyType)  fields.push({ label: 'Carrocería', value: d.bodyType })
  if (d?.fuelType)  fields.push({ label: 'Combustible', value: d.fuelType })
  if (d?.engineDisplacement) fields.push({ label: 'Motor', value: d.engineDisplacement })
  if (d?.driveType) fields.push({ label: 'Tracción', value: d.driveType })
  if (d?.countryOfManufacture) fields.push({ label: 'País fabricación', value: `${COUNTRY_FLAG[d.countryOfManufacture] ?? ''} ${d.countryOfManufacture}`.trim() })
  if (d?.plant)  fields.push({ label: 'Planta', value: d.plant })

  // From plate resolver
  if (!d?.make && p?.make)  fields.push({ label: 'Marca', value: p.make })
  if (!d?.model && p?.model) fields.push({ label: 'Modelo', value: p.model })
  if (p?.variant) fields.push({ label: 'Variante', value: p.variant })
  if (p?.first_registration) fields.push({ label: 'Primera matriculación', value: formatDate(p.first_registration) })
  if (p?.registration_status) fields.push({ label: 'Estado matrícula', value: p.registration_status })
  if (p?.district) fields.push({ label: 'Provincia/Distrito', value: p.district })
  if (p?.mileage_km) fields.push({ label: 'Km registrado', value: fmtKm(p.mileage_km), mono: true })

  if (fields.length === 0) return null

  return (
    <Section
      title="Identificación"
      icon={<Hash className="w-3.5 h-3.5" strokeWidth={1.5} />}
    >
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
        {fields.map(({ label, value, mono }) => (
          <DataField key={label} label={label} value={value} mono={mono} />
        ))}
      </dl>
    </Section>
  )
}

// ── Inspection status ─────────────────────────────────────────────────────────

function inspectionItems(inspections: InspectionRecord[]) {
  return [...inspections]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map((ins, idx) => ({
      id: `${ins.date}-${ins.country}-${ins.center ?? ''}-${idx}`,
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

// ── Inspection status banner ──────────────────────────────────────────────────

function InspectionStatusBanner({ p }: { p: PlateInfo }) {
  if (!p.last_inspection_date && !p.next_inspection_date && !p.last_inspection_result) return null

  const result = p.last_inspection_result
  const isPass = result === 'pass'
  const isFail = result === 'fail'

  return (
    <div className={cn(
      'rounded-lg border p-3.5 mb-4',
      isPass ? 'border-emerald-500/25 bg-emerald-500/8' :
      isFail ? 'border-rose-500/25 bg-rose-500/8' :
      'border-border-subtle bg-glass-subtle',
    )}>
      <div className="flex items-center gap-3">
        {isPass ? <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" strokeWidth={1.5} /> :
         isFail ? <ShieldAlert className="w-5 h-5 text-accent-rose shrink-0" strokeWidth={1.5} /> :
         <Shield className="w-5 h-5 text-text-muted shrink-0" strokeWidth={1.5} />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn(
              'text-xs font-semibold',
              isPass ? 'text-emerald-400' : isFail ? 'text-accent-rose' : 'text-text-secondary',
            )}>
              {isPass ? 'Última ITV: APTO' : isFail ? 'Última ITV: NO APTO' : 'Última inspección'}
            </span>
            {p.last_inspection_date && (
              <span className="text-xs text-text-muted font-mono">{formatDate(p.last_inspection_date)}</span>
            )}
          </div>
          {p.next_inspection_date && (
            <p className="text-xs text-text-muted mt-0.5">
              Próxima inspección: {formatDate(p.next_inspection_date)}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Recall row ────────────────────────────────────────────────────────────────

function RecallRow({ recall }: { recall: RecallEntry }) {
  const isOpen = recall.status === 'open'
  return (
    <div className={cn(
      'rounded-lg border p-3.5',
      isOpen ? 'border-rose-500/25 bg-rose-500/8' : 'border-border-subtle bg-glass-subtle',
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Badge color={isOpen ? 'red' : 'green'} dot={isOpen} pulse={isOpen}>
              {isOpen ? 'Abierto' : 'Completado'}
            </Badge>
            <span className="text-[10px] text-text-muted font-mono">{recall.campaignId}</span>
            {recall.country && (
              <span className="text-[10px] text-text-muted">
                {COUNTRY_FLAG[recall.country] ?? ''} {recall.country}
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-text-primary">{recall.description}</p>
          {recall.affectedComponent && (
            <p className="text-xs text-text-muted mt-0.5">
              Componente: {recall.affectedComponent}
            </p>
          )}
        </div>
      </div>
      <div className="flex gap-4 mt-2 text-[10px] text-text-muted font-mono">
        <span>Inicio: {formatDateShort(recall.startDate)}</span>
        {recall.completionDate && <span>Cierre: {formatDateShort(recall.completionDate)}</span>}
        {recall.source && <span className="truncate max-w-[160px]">{recall.source}</span>}
      </div>
    </div>
  )
}

// ── Mileage chart ─────────────────────────────────────────────────────────────

function MileageSection({
  history, consistencyScore,
}: {
  history: MileageRecord[]
  consistencyScore?: number
}) {
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
    date: formatDateShort(r.date),
    km: r.mileageKm,
    isAnomaly: r.isAnomaly,
  }))
  const anomalies = chartData
    .map((d, i) => ({ ...d, index: i }))
    .filter((d) => d.isAnomaly)

  return (
    <div className="space-y-5">
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
      <div className="h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 12, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="var(--color-blue)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--color-blue)" stopOpacity={0}    />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border-subtle)" vertical={false} />
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

// ── Country data section ──────────────────────────────────────────────────────

function CountryDataSection({ report }: { report: VehicleReport }) {
  const countries = report.countries ?? []
  if (countries.length === 0) return null

  return (
    <Section
      title="Historial por país"
      icon={<Globe className="w-3.5 h-3.5" strokeWidth={1.5} />}
      count={countries.length}
    >
      <div className="space-y-4">
        {countries.map((c) => (
          <div key={c.country} className="rounded-lg border border-border-subtle bg-glass-subtle p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-lg">{COUNTRY_FLAG[c.country] ?? '🌐'}</span>
              <span className="text-sm font-semibold text-text-primary">{c.country}</span>
              {c.stolenFlag && (
                <Badge color="red" dot pulse>Reportado robado</Badge>
              )}
            </div>

            {c.registrations && c.registrations.length > 0 && (
              <div className="mb-3">
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-2">
                  Matriculaciones
                </p>
                <div className="space-y-1">
                  {c.registrations.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-text-secondary">
                      <Calendar className="w-3 h-3 shrink-0 text-text-muted" strokeWidth={1.5} />
                      <span className="font-mono">{formatDate(r.date)}</span>
                      <span className="text-text-muted">·</span>
                      <span className="capitalize">{r.type.replace('_', ' ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {c.technicalSpecs && (c.technicalSpecs.fuelType || c.technicalSpecs.displacementCC || c.technicalSpecs.emptyWeightKg) && (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                {c.technicalSpecs.fuelType && (
                  <div className="flex items-center gap-1.5 text-text-muted">
                    <Fuel className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                    <span>{c.technicalSpecs.fuelType}</span>
                  </div>
                )}
                {c.technicalSpecs.displacementCC && (
                  <div className="flex items-center gap-1.5 text-text-muted font-mono">
                    <Settings2 className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                    <span>{c.technicalSpecs.displacementCC.toLocaleString()} cm³</span>
                  </div>
                )}
                {c.technicalSpecs.emptyWeightKg && (
                  <div className="flex items-center gap-1.5 text-text-muted font-mono">
                    <Weight className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                    <span>{c.technicalSpecs.emptyWeightKg.toLocaleString()} kg</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  )
}

// ── Main report ───────────────────────────────────────────────────────────────

interface CheckReportProps {
  report: VehicleReport
  onBack: () => void
  onRefresh: () => void
}

export default function CheckReport({ report, onBack, onRefresh }: CheckReportProps) {
  const d                   = report.vinDecode ?? undefined
  const p                   = report.plateInfo ?? undefined
  const alerts              = report.alerts ?? []
  const recalls             = report.recalls ?? []
  const mileageHistory      = report.mileageHistory ?? []
  const dataSources         = report.dataSources ?? []
  const inspections         = (report.countries ?? []).flatMap((c) => c.inspections ?? [])

  const overallStatus           = deriveOverallStatus(alerts)
  const mileageConsistencyScore = consistencyToScore(report.mileageConsistency)

  const make  = d?.make  ?? p?.make  ?? ''
  const model = d?.model ?? p?.model ?? ''
  const year  = d?.year  ?? (p?.first_registration ? new Date(p.first_registration).getFullYear() : undefined)
  const vehicleTitle = [make, model, year].filter(Boolean).join(' ') || 'Vehículo'

  const country = p?.country ?? d?.countryOfManufacture
  const countryFlag = country ? (COUNTRY_FLAG[country] ?? '') : ''

  const hasTechSpecs = p != null && (
    p.fuel_type || p.displacement_cc || p.power_kw || p.empty_weight_kg ||
    p.co2_g_per_km || p.euro_norm || p.color || p.body_type || p.number_of_seats
  )

  const openRecalls   = recalls.filter((r) => r.status === 'open')
  const closedRecalls = recalls.filter((r) => r.status !== 'open')

  async function copyVIN() {
    if (report.vin) await navigator.clipboard.writeText(report.vin).catch(() => null)
  }
  function shareLink() {
    const path = report.vin ? `/check/${report.vin}` : '/check'
    navigator.clipboard.writeText(`${window.location.origin}${path}`).catch(() => null)
  }

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

      <div className="max-w-5xl mx-auto px-5 py-6 space-y-5">

        {/* ── Cinematic Hero ── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          className="glass-strong rounded-xl overflow-hidden relative"
        >
          {/* Subtle gradient bar at top */}
          <div className="h-0.5 w-full bg-gradient-to-r from-transparent via-[var(--color-blue)]/40 to-transparent" />

          <div className="px-6 py-6">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5">

              {/* Left: identity */}
              <div className="flex-1 min-w-0">
                {/* Label row */}
                <div className="flex items-center gap-2 mb-3">
                  <Car className="w-3.5 h-3.5 text-text-muted" strokeWidth={1.5} />
                  <span className="text-[10px] font-semibold text-text-muted uppercase tracking-[0.16em]">
                    Informe vehicular
                  </span>
                  {country && (
                    <span className="inline-flex items-center gap-1 text-[10px] font-medium text-text-secondary bg-glass-subtle px-2 py-0.5 rounded-full border border-border-subtle ml-auto sm:ml-1">
                      <span>{countryFlag}</span>
                      <span>{country}</span>
                    </span>
                  )}
                </div>

                {/* Vehicle title */}
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-primary leading-tight">
                  {vehicleTitle}
                </h1>

                {/* VIN row */}
                {report.vin && (
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
                )}

                {/* Plate + partial warning */}
                {p?.plate && (
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="font-mono text-xs text-text-muted tracking-widest border border-border-subtle rounded px-2 py-0.5 bg-glass-subtle">
                      {p.plate}
                    </span>
                    {p.partial && (
                      <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">
                        Datos parciales
                      </span>
                    )}
                  </div>
                )}

                {/* Environmental badge */}
                {p?.environmental_badge && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <Leaf className="w-3 h-3 text-emerald-400" strokeWidth={1.5} />
                    <span className="text-xs font-medium text-emerald-400">
                      Distintivo {p.environmental_badge}
                    </span>
                  </div>
                )}

                {/* Manufacturer */}
                {d && (d.manufacturer || d.countryOfManufacture) && (
                  <p className="mt-2 text-xs text-text-muted">
                    {[d.manufacturer, d.countryOfManufacture ? `${COUNTRY_FLAG[d.countryOfManufacture] ?? ''} ${d.countryOfManufacture}` : ''].filter(Boolean).join(' · ')}
                  </p>
                )}

                {/* Quick specs strip */}
                {p && (p.fuel_type || p.displacement_cc || p.power_kw) && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3">
                    {p.fuel_type && (
                      <div className="flex items-center gap-1 text-xs text-text-muted">
                        <Fuel className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                        <span>{p.fuel_type}</span>
                      </div>
                    )}
                    {p.displacement_cc && (
                      <div className="flex items-center gap-1 text-xs text-text-muted font-mono">
                        <Settings2 className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                        <span>{p.displacement_cc.toLocaleString()} cm³</span>
                      </div>
                    )}
                    {p.power_kw && (
                      <div className="flex items-center gap-1 text-xs text-text-muted font-mono">
                        <Zap className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                        <span>{p.power_kw} kW · {kwToCV(p.power_kw)} CV</span>
                      </div>
                    )}
                    {p.color && (
                      <div className="flex items-center gap-1 text-xs text-text-muted">
                        <Car className="w-3 h-3 shrink-0" strokeWidth={1.5} />
                        <span className="capitalize">{p.color}</span>
                      </div>
                    )}
                  </div>
                )}

                <p className="mt-4 text-[10px] text-text-muted">
                  Informe generado el {formatDate(report.generatedAt)}
                </p>
              </div>

              {/* Right: gauge + status */}
              <div className="flex flex-row sm:flex-col items-center sm:items-end gap-4 shrink-0">
                {mileageConsistencyScore !== undefined && mileageHistory.length >= 3 && (
                  <ScoreGauge score={mileageConsistencyScore} size={120} label="Consistencia" />
                )}
                <StatusIndicator status={overallStatus} />
              </div>
            </div>
          </div>
        </motion.div>

        {/* ── Alerts (full-width, critical first) ── */}
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
            {/* Identification */}
            <IdentificationSection report={report} />

            {/* Technical specs (from plate resolver) */}
            {hasTechSpecs && p && <TechnicalSpecsSection p={p} />}

            {/* Inspections */}
            <Section
              title="Historial de inspecciones"
              icon={<FileCheck className="w-3.5 h-3.5" strokeWidth={1.5} />}
              count={inspections.length > 0 ? inspections.length : undefined}
            >
              {p && <InspectionStatusBanner p={p} />}
              <Timeline
                items={inspectionItems(inspections)}
                emptyMessage="No se encontraron datos de inspección en las fuentes disponibles."
              />
            </Section>

            {/* Recalls */}
            <Section
              title="Recalls"
              icon={<RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />}
              count={recalls.length > 0 ? recalls.length : undefined}
              accent={openRecalls.length > 0 ? 'rose' : undefined}
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

            {/* Country data */}
            <CountryDataSection report={report} />
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

            {/* Plate source note */}
            {p?.source && (
              <motion.div variants={sectionItem} className="glass rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-border-subtle">
                  <h2 className="text-[11px] font-semibold text-text-muted uppercase tracking-[0.12em]">
                    Fuente matrícula
                  </h2>
                </div>
                <div className="px-4 py-3">
                  <p className="text-[11px] text-text-muted leading-relaxed">{p.source}</p>
                  {p.fetched_at && (
                    <p className="text-[10px] text-text-muted/60 mt-1 font-mono">
                      {formatDate(p.fetched_at)}
                    </p>
                  )}
                </div>
              </motion.div>
            )}

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
