import React, { useState } from 'react'
import { Search, Car, FileText, Key } from 'lucide-react'
import VINInput, { validateVIN } from '../../components/VINInput'

interface CheckLandingProps {
  onSearch: (vin: string) => void
  initialVin?: string
  loading?: boolean
}

// Simple VIN location illustration using inline SVG shapes.
function VINLocationsIllustration() {
  return (
    <div className="grid grid-cols-3 gap-3 mt-4">
      {[
        {
          Icon: Car,
          label: 'Salpicadero',
          detail: 'Visible desde el parabrisas',
        },
        {
          Icon: FileText,
          label: 'Documentación',
          detail: 'Permiso de circulación',
        },
        {
          Icon: Key,
          label: 'Puerta conductor',
          detail: 'Jamba o umbral',
        },
      ].map(({ Icon, label, detail }) => (
        <div
          key={label}
          className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-white/60 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 text-center"
        >
          <div className="w-8 h-8 rounded-lg bg-brand-100 dark:bg-brand-900/30 flex items-center justify-center">
            <Icon className="w-4 h-4 text-brand-600 dark:text-brand-400" />
          </div>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">{label}</p>
          <p className="text-[10px] text-gray-400 leading-snug">{detail}</p>
        </div>
      ))}
    </div>
  )
}

export default function CheckLanding({ onSearch, initialVin = '', loading }: CheckLandingProps) {
  const [vin, setVin] = useState(initialVin)

  function handleSubmit() {
    const clean = vin.trim().toUpperCase()
    if (validateVIN(clean)) onSearch(clean)
  }

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-12 text-center">
      {/* Badge */}
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-50 dark:bg-brand-900/30 border border-brand-200 dark:border-brand-700 mb-6">
        <Search className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
        <span className="text-xs font-semibold text-brand-700 dark:text-brand-400 tracking-wide uppercase">
          CARDEX Check
        </span>
      </div>

      {/* Headline */}
      <h1 className="text-3xl sm:text-4xl font-extrabold text-gray-900 dark:text-white leading-tight mb-3 max-w-lg">
        Historial vehicular{' '}
        <span className="text-brand-600 dark:text-brand-400">gratuito</span>
      </h1>
      <p className="text-base text-gray-500 dark:text-gray-400 max-w-md mb-10">
        Consulta alertas, historial de inspecciones, recalls y kilometraje de cualquier vehículo en Europa.
      </p>

      {/* Input + button */}
      <div className="w-full max-w-md space-y-3">
        <VINInput
          value={vin}
          onChange={setVin}
          onSubmit={handleSubmit}
          disabled={loading}
          large
        />

        <button
          onClick={handleSubmit}
          disabled={!validateVIN(vin) || loading}
          className="w-full py-3.5 px-6 rounded-xl font-semibold text-white bg-brand-600 hover:bg-brand-700 active:bg-brand-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-base shadow-sm shadow-brand-200 dark:shadow-none focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              Consultando fuentes…
            </span>
          ) : (
            'Verificar historial'
          )}
        </button>
      </div>

      {/* Loading skeleton hint */}
      {loading && (
        <p className="mt-4 text-xs text-gray-400 dark:text-gray-500 max-w-xs">
          Consultando bases de datos europeas. Esto puede tardar algunos segundos.
        </p>
      )}

      {/* VIN location guide */}
      <div className="mt-10 w-full max-w-md">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
          ¿Dónde encuentro el VIN?
        </p>
        <VINLocationsIllustration />
      </div>

      {/* Trust signals */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-4 text-xs text-gray-400 dark:text-gray-500">
        <span>🔒 Sin registro requerido</span>
        <span>·</span>
        <span>🇪🇺 Fuentes europeas oficiales</span>
        <span>·</span>
        <span>⚡ Resultado en segundos</span>
      </div>
    </div>
  )
}
