'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Loader2, Sparkles } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function authHeader(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('cardex_token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

const FUEL_TYPES = ['PETROL', 'DIESEL', 'HYBRID', 'PHEV', 'EV', 'LPG', 'OTHER']
const TRANSMISSIONS = ['MANUAL', 'AUTOMATIC', 'OTHER']
const CONDITION_GRADES = [
  { value: 'A', label: 'A — Excelente' },
  { value: 'B', label: 'B — Bueno' },
  { value: 'C', label: 'C — Aceptable' },
  { value: 'D', label: 'D — Proyecto' },
]
const LIFECYCLE_STATUSES = ['SOURCING', 'PURCHASED', 'RECONDITIONING', 'READY', 'LISTED']
const DESC_LANGUAGES = [
  { code: 'ES', label: 'Español' },
  { code: 'FR', label: 'Français' },
  { code: 'DE', label: 'Deutsch' },
  { code: 'NL', label: 'Nederlands' },
  { code: 'EN', label: 'English' },
]

interface FormData {
  make: string
  model: string
  variant: string
  year: string
  fuel_type: string
  transmission: string
  mileage_km: string
  power_kw: string
  color_exterior: string
  vin: string
  purchase_price_eur: string
  asking_price_eur: string
  recon_cost_eur: string
  transport_cost_eur: string
  condition_grade: string
  notes: string
  lifecycle_status: string
  description: string
}

const INITIAL_FORM: FormData = {
  make: '',
  model: '',
  variant: '',
  year: String(new Date().getFullYear()),
  fuel_type: '',
  transmission: '',
  mileage_km: '',
  power_kw: '',
  color_exterior: '',
  vin: '',
  purchase_price_eur: '',
  asking_price_eur: '',
  recon_cost_eur: '',
  transport_cost_eur: '',
  condition_grade: '',
  notes: '',
  lifecycle_status: 'SOURCING',
  description: '',
}

function InputField({
  label,
  name,
  value,
  onChange,
  type = 'text',
  placeholder = '',
  required = false,
  min,
  max,
  maxLength,
  hint,
}: {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  type?: string
  placeholder?: string
  required?: boolean
  min?: number
  max?: number
  maxLength?: number
  hint?: string
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-surface-muted">
        {label}{required && <span className="ml-1 text-red-400">*</span>}
      </label>
      <input
        type={type}
        name={name}
        value={value}
        onChange={e => onChange(name, e.target.value)}
        placeholder={placeholder}
        required={required}
        min={min}
        max={max}
        maxLength={maxLength}
        className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none"
      />
      {hint && <p className="mt-1 text-xs text-surface-muted">{hint}</p>}
    </div>
  )
}

function SelectField({
  label,
  name,
  value,
  onChange,
  options,
  placeholder = '— Seleccionar —',
  required = false,
}: {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  options: { value: string; label: string }[] | string[]
  placeholder?: string
  required?: boolean
}) {
  const normalized = (options as (string | { value: string; label: string })[]).map(o =>
    typeof o === 'string' ? { value: o, label: o } : o
  )
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-surface-muted">
        {label}{required && <span className="ml-1 text-red-400">*</span>}
      </label>
      <select
        name={name}
        value={value}
        onChange={e => onChange(name, e.target.value)}
        required={required}
        className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white focus:border-brand-500 focus:outline-none"
      >
        <option value="">{placeholder}</option>
        {normalized.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

export default function NewVehiclePage() {
  const router = useRouter()
  const [form, setForm] = useState<FormData>(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [descLang, setDescLang] = useState('ES')
  const [generatingDesc, setGeneratingDesc] = useState(false)
  const [descError, setDescError] = useState<string | null>(null)

  useEffect(() => {
    const token = localStorage.getItem('cardex_token')
    if (!token) router.replace('/dashboard/login')
  }, [router])

  function setField(name: string, value: string) {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  async function generateDescription() {
    setGeneratingDesc(true)
    setDescError(null)
    try {
      const payload: Record<string, unknown> = {
        language: descLang,
        make: form.make || undefined,
        model: form.model || undefined,
        variant: form.variant || undefined,
        year: form.year ? Number(form.year) : undefined,
        fuel_type: form.fuel_type || undefined,
        transmission: form.transmission || undefined,
        mileage_km: form.mileage_km ? Number(form.mileage_km) : undefined,
        power_kw: form.power_kw ? Number(form.power_kw) : undefined,
        color_exterior: form.color_exterior || undefined,
        condition_grade: form.condition_grade || undefined,
      }
      // Remove undefined keys
      Object.keys(payload).forEach(k => payload[k] === undefined && delete payload[k])

      const res = await fetch(`${API}/api/v1/dealer/inventory/generate-description`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.message ?? `Error ${res.status}`)
      }
      const data = await res.json()
      const generated: string = data.description ?? data.text ?? ''
      setField('description', generated)
    } catch (err) {
      setDescError(err instanceof Error ? err.message : 'Error generando descripción')
    } finally {
      setGeneratingDesc(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setSubmitError(null)

    try {
      const payload: Record<string, unknown> = {
        make: form.make,
        model: form.model,
        year: Number(form.year),
      }
      if (form.variant) payload.variant = form.variant
      if (form.fuel_type) payload.fuel_type = form.fuel_type
      if (form.transmission) payload.transmission = form.transmission
      if (form.mileage_km) payload.mileage_km = Number(form.mileage_km)
      if (form.power_kw) payload.power_kw = Number(form.power_kw)
      if (form.color_exterior) payload.color_exterior = form.color_exterior
      if (form.vin) payload.vin = form.vin
      if (form.purchase_price_eur) payload.purchase_price_eur = Number(form.purchase_price_eur)
      if (form.asking_price_eur) payload.asking_price_eur = Number(form.asking_price_eur)
      if (form.recon_cost_eur) payload.recon_cost_eur = Number(form.recon_cost_eur)
      if (form.transport_cost_eur) payload.transport_cost_eur = Number(form.transport_cost_eur)
      if (form.condition_grade) payload.condition_grade = form.condition_grade
      if (form.notes) payload.notes = form.notes
      if (form.description) payload.description = form.description
      if (form.lifecycle_status) payload.lifecycle_status = form.lifecycle_status

      const res = await fetch(`${API}/api/v1/dealer/crm/vehicles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.message ?? `Error ${res.status}`)
      }

      router.push('/dashboard/inventory')
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Error al guardar el vehículo')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-4">
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm text-surface-muted hover:text-white transition-colors"
        >
          <ArrowLeft size={16} /> Volver
        </button>
        <div>
          <h1 className="text-2xl font-bold text-white">Añadir vehículo</h1>
          <p className="mt-0.5 text-sm text-surface-muted">Rellena los datos del vehículo para añadirlo al inventario</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="grid gap-6 lg:grid-cols-2">
          {/* ── COLUMNA IZQUIERDA: Datos básicos ── */}
          <div className="space-y-5">
            {/* Identificación */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Datos básicos</h2>
              <div className="grid grid-cols-2 gap-4">
                <InputField label="Marca" name="make" value={form.make} onChange={setField} required placeholder="e.g. BMW" />
                <InputField label="Modelo" name="model" value={form.model} onChange={setField} required placeholder="e.g. 320d" />
                <div className="col-span-2">
                  <InputField label="Variante / Versión" name="variant" value={form.variant} onChange={setField} placeholder="e.g. M Sport, Business Line" />
                </div>
                <InputField
                  label="Año"
                  name="year"
                  value={form.year}
                  onChange={setField}
                  type="number"
                  required
                  min={1990}
                  max={2030}
                  placeholder="2023"
                />
                <SelectField
                  label="Estado del ciclo"
                  name="lifecycle_status"
                  value={form.lifecycle_status}
                  onChange={setField}
                  options={LIFECYCLE_STATUSES}
                />
              </div>
            </div>

            {/* Especificaciones técnicas */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Especificaciones técnicas</h2>
              <div className="grid grid-cols-2 gap-4">
                <SelectField
                  label="Combustible"
                  name="fuel_type"
                  value={form.fuel_type}
                  onChange={setField}
                  options={FUEL_TYPES}
                />
                <SelectField
                  label="Transmisión"
                  name="transmission"
                  value={form.transmission}
                  onChange={setField}
                  options={TRANSMISSIONS}
                />
                <InputField
                  label="Kilometraje (km)"
                  name="mileage_km"
                  value={form.mileage_km}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
                <InputField
                  label="Potencia (kW)"
                  name="power_kw"
                  value={form.power_kw}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
                <InputField
                  label="Color exterior"
                  name="color_exterior"
                  value={form.color_exterior}
                  onChange={setField}
                  placeholder="e.g. Negro Brillante"
                />
                <SelectField
                  label="Grado de condición"
                  name="condition_grade"
                  value={form.condition_grade}
                  onChange={setField}
                  options={CONDITION_GRADES}
                />
                <div className="col-span-2">
                  <InputField
                    label="VIN"
                    name="vin"
                    value={form.vin}
                    onChange={setField}
                    placeholder="17 caracteres"
                    maxLength={17}
                    hint="Número de identificación del vehículo (opcional)"
                  />
                </div>
              </div>
            </div>

            {/* Notas */}
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Notas internas</h2>
              <textarea
                name="notes"
                value={form.notes}
                onChange={e => setField('notes', e.target.value)}
                placeholder="Notas sobre el vehículo, historial, estado…"
                rows={4}
                className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none resize-none"
              />
            </div>
          </div>

          {/* ── COLUMNA DERECHA: Precios y costes ── */}
          <div className="space-y-5">
            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Precios</h2>
              <div className="space-y-4">
                <InputField
                  label="Precio de compra (€)"
                  name="purchase_price_eur"
                  value={form.purchase_price_eur}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
                <InputField
                  label="Precio de venta (€)"
                  name="asking_price_eur"
                  value={form.asking_price_eur}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
              </div>
            </div>

            <div className="rounded-xl border border-surface-border bg-surface-card p-5">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-muted">Costes adicionales</h2>
              <div className="space-y-4">
                <InputField
                  label="Coste taller/recond. (€)"
                  name="recon_cost_eur"
                  value={form.recon_cost_eur}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
                <InputField
                  label="Coste transporte (€)"
                  name="transport_cost_eur"
                  value={form.transport_cost_eur}
                  onChange={setField}
                  type="number"
                  min={0}
                  placeholder="0"
                />
              </div>

              {/* Resumen de costes */}
              {(form.purchase_price_eur || form.recon_cost_eur || form.transport_cost_eur || form.asking_price_eur) && (
                <div className="mt-5 rounded-lg border border-surface-border bg-surface p-4 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-surface-muted">Resumen financiero</p>
                  {[
                    ['Compra', form.purchase_price_eur],
                    ['Taller', form.recon_cost_eur],
                    ['Transporte', form.transport_cost_eur],
                  ].map(([label, val]) =>
                    val ? (
                      <div key={label as string} className="flex justify-between text-sm">
                        <span className="text-surface-muted">{label}</span>
                        <span className="font-mono text-white">€{Number(val).toLocaleString('es-ES')}</span>
                      </div>
                    ) : null
                  )}
                  {(form.purchase_price_eur || form.recon_cost_eur || form.transport_cost_eur) && (
                    <div className="flex justify-between border-t border-surface-border pt-2 text-sm font-semibold">
                      <span className="text-white">Coste total</span>
                      <span className="font-mono text-white">
                        €{(
                          (Number(form.purchase_price_eur) || 0) +
                          (Number(form.recon_cost_eur) || 0) +
                          (Number(form.transport_cost_eur) || 0)
                        ).toLocaleString('es-ES')}
                      </span>
                    </div>
                  )}
                  {form.asking_price_eur && (
                    (() => {
                      const totalCost =
                        (Number(form.purchase_price_eur) || 0) +
                        (Number(form.recon_cost_eur) || 0) +
                        (Number(form.transport_cost_eur) || 0)
                      const margin = (Number(form.asking_price_eur) || 0) - totalCost
                      const marginPct = totalCost > 0 ? (margin / totalCost) * 100 : 0
                      return (
                        <div className={`flex justify-between border-t border-surface-border pt-2 text-sm font-bold ${margin >= 0 ? 'text-brand-400' : 'text-red-400'}`}>
                          <span>Margen estimado</span>
                          <span className="font-mono">
                            €{margin.toLocaleString('es-ES')} ({marginPct.toFixed(1)}%)
                          </span>
                        </div>
                      )
                    })()
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── SECCIÓN DESCRIPCIÓN IA ── */}
        <div className="mt-6 rounded-xl border border-surface-border bg-surface-card p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-surface-muted">Descripción del anuncio</h2>
              <p className="mt-0.5 text-xs text-surface-muted">Genera una descripción con IA o escríbela manualmente</p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={descLang}
                onChange={e => setDescLang(e.target.value)}
                className="rounded-lg border border-surface-border bg-surface px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
              >
                {DESC_LANGUAGES.map(l => (
                  <option key={l.code} value={l.code}>{l.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={generateDescription}
                disabled={generatingDesc || !form.make || !form.model}
                className="flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
              >
                {generatingDesc ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Sparkles size={14} />
                )}
                Generar descripción con IA
              </button>
            </div>
          </div>

          {descError && (
            <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {descError}
            </div>
          )}

          <textarea
            name="description"
            value={form.description}
            onChange={e => setField('description', e.target.value)}
            placeholder="La descripción aparecerá aquí tras generarla con IA, o puedes escribirla manualmente…"
            rows={8}
            className="w-full rounded-lg border border-surface-border bg-surface px-3 py-2.5 text-sm text-white placeholder-surface-muted focus:border-brand-500 focus:outline-none resize-none"
          />
          {!form.make && !form.model && (
            <p className="mt-1.5 text-xs text-surface-muted">Rellena al menos la marca y el modelo para generar descripción con IA.</p>
          )}
        </div>

        {/* ── Error y botón de submit ── */}
        {submitError && (
          <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {submitError}
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-xl border border-surface-border px-6 py-2.5 text-sm font-medium text-surface-muted hover:text-white transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-8 py-2.5 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            {submitting ? 'Guardando…' : 'Añadir al inventario'}
          </button>
        </div>
      </form>
    </div>
  )
}
