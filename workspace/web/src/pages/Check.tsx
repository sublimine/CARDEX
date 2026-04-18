import React, { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Car as CarIcon, AlertTriangle, Clock } from 'lucide-react'
import CheckLanding from './check/CheckLanding'
import CheckReport from './check/CheckReport'
import { useCheck } from '../hooks/useCheck'

// ── Loading skeleton ──────────────────────────────────────────────────────────

function ReportSkeleton() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-4 animate-pulse">
      {/* Header */}
      <div className="h-28 bg-gray-100 dark:bg-gray-800 rounded-xl" />
      {/* Sections */}
      {[100, 200, 140, 120].map((h, i) => (
        <div key={i} className="rounded-xl border border-gray-100 dark:border-gray-700 overflow-hidden">
          <div className="h-10 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-700" />
          <div style={{ height: h }} className="bg-white dark:bg-gray-800 p-5 space-y-3">
            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-3/4" />
            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-1/2" />
            <div className="h-3 bg-gray-100 dark:bg-gray-700 rounded w-5/6" />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Rate-limit countdown ──────────────────────────────────────────────────────

function RateLimitError({ seconds, onRetry }: { seconds: number; onRetry: () => void }) {
  const [remaining, setRemaining] = React.useState(seconds)

  useEffect(() => {
    if (remaining <= 0) return
    const t = setTimeout(() => setRemaining((s) => s - 1), 1000)
    return () => clearTimeout(t)
  }, [remaining])

  return (
    <div className="max-w-md mx-auto px-4 py-12 text-center">
      <div className="w-14 h-14 rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center mx-auto mb-4">
        <Clock className="w-7 h-7 text-yellow-600 dark:text-yellow-400" />
      </div>
      <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
        Límite de consultas alcanzado
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Has realizado demasiadas consultas en poco tiempo. Puedes reintentar en{' '}
        <span className="font-bold tabular-nums text-gray-900 dark:text-white">{remaining}s</span>.
      </p>
      <button
        onClick={onRetry}
        disabled={remaining > 0}
        className="px-5 py-2.5 rounded-lg bg-brand-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-brand-700 transition-colors"
      >
        {remaining > 0 ? `Reintentar en ${remaining}s` : 'Reintentar ahora'}
      </button>
    </div>
  )
}

// ── Generic error ─────────────────────────────────────────────────────────────

function GenericError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="max-w-md mx-auto px-4 py-12 text-center">
      <div className="w-14 h-14 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
        <AlertTriangle className="w-7 h-7 text-red-500" />
      </div>
      <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-2">
        No se pudo obtener el informe
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-5">{message}</p>
      <button
        onClick={onRetry}
        className="px-5 py-2.5 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 transition-colors"
      >
        Intentar de nuevo
      </button>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CheckPage() {
  const { vin: vinParam } = useParams<{ vin?: string }>()
  const navigate = useNavigate()

  const { report, loading, error, checkVIN, reset } = useCheck(vinParam)

  // Update document title
  useEffect(() => {
    if (report) {
      const d = report.vinDecode
      document.title = `${d.make} ${d.model} ${d.year} — CARDEX Check`
    } else {
      document.title = 'CARDEX Check — Historial vehicular gratuito'
    }
    return () => { document.title = 'CARDEX' }
  }, [report])

  function handleSearch(vin: string) {
    navigate(`/check/${vin}`, { replace: vinParam !== undefined })
    checkVIN(vin)
  }

  function handleBack() {
    reset()
    navigate('/check', { replace: true })
  }

  function handleRefresh() {
    if (vinParam) checkVIN(vinParam)
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Minimal public header */}
      <header className="h-14 bg-white/80 dark:bg-gray-900/80 backdrop-blur border-b border-gray-200 dark:border-gray-800 flex items-center px-4 sticky top-0 z-20">
        <a href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-brand-600 rounded-lg flex items-center justify-center">
            <CarIcon className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-gray-900 dark:text-white tracking-tight">
            CARDEX
            <span className="text-brand-600 dark:text-brand-400 ml-1 font-normal">Check</span>
          </span>
        </a>
      </header>

      <main>
        {/* Loading */}
        {loading && <ReportSkeleton />}

        {/* Error states */}
        {!loading && error && (
          <>
            {error.code === 'rate_limit' && error.retryAfterSeconds !== undefined ? (
              <RateLimitError
                seconds={error.retryAfterSeconds}
                onRetry={() => vinParam && checkVIN(vinParam)}
              />
            ) : (
              <div>
                <GenericError
                  message={error.message}
                  onRetry={handleBack}
                />
                {/* Still show landing below so user can search again */}
                <CheckLanding onSearch={handleSearch} initialVin={vinParam} />
              </div>
            )}
          </>
        )}

        {/* Report */}
        {!loading && !error && report && (
          <CheckReport
            report={report}
            onBack={handleBack}
            onRefresh={handleRefresh}
          />
        )}

        {/* Landing (no report, no loading, no error) */}
        {!loading && !error && !report && (
          <CheckLanding
            onSearch={handleSearch}
            initialVin={vinParam}
            loading={loading}
          />
        )}
      </main>
    </div>
  )
}
