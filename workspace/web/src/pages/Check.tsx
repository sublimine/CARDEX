import React, { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Car, AlertTriangle, Clock } from 'lucide-react'
import CheckLanding from './check/CheckLanding'
import CheckReport from './check/CheckReport'
import { useCheck } from '../hooks/useCheck'

// ── Shimmer skeleton ──────────────────────────────────────────────────────────

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-md bg-bg-surface ${className ?? ''}`}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/5 to-transparent" />
    </div>
  )
}

function ReportSkeleton() {
  return (
    <div className="max-w-3xl mx-auto px-5 pt-8 pb-16 space-y-4">
      {/* Hero card */}
      <div className="glass rounded-xl p-5 space-y-3">
        <SkeletonBar className="h-7 w-48" />
        <SkeletonBar className="h-4 w-72" />
        <SkeletonBar className="h-3 w-36" />
      </div>
      {/* Sections */}
      {[160, 220, 140, 180].map((h, i) => (
        <div key={i} className="glass rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle">
            <SkeletonBar className="h-3 w-28" />
          </div>
          <div className="p-5 space-y-2.5" style={{ minHeight: h }}>
            <SkeletonBar className="h-3 w-4/5" />
            <SkeletonBar className="h-3 w-3/5" />
            <SkeletonBar className="h-3 w-2/3" />
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
    <div className="max-w-sm mx-auto px-5 py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-amber-500/15 ring-1 ring-amber-500/20 flex items-center justify-center mx-auto mb-5">
        <Clock className="w-5 h-5 text-accent-amber" />
      </div>
      <h2 className="text-base font-semibold text-text-primary mb-1.5">
        Límite de consultas alcanzado
      </h2>
      <p className="text-sm text-text-secondary mb-6 leading-relaxed">
        Demasiadas consultas en poco tiempo. Puedes reintentar en{' '}
        <span className="font-mono font-semibold text-text-primary tabular-nums">{remaining}s</span>.
      </p>
      <button
        onClick={onRetry}
        disabled={remaining > 0}
        className="px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition-all"
      >
        {remaining > 0 ? `Reintentar en ${remaining}s` : 'Reintentar ahora'}
      </button>
    </div>
  )
}

// ── Generic error ─────────────────────────────────────────────────────────────

function GenericError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="max-w-sm mx-auto px-5 py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-rose-500/15 ring-1 ring-rose-500/20 flex items-center justify-center mx-auto mb-5">
        <AlertTriangle className="w-5 h-5 text-accent-rose" />
      </div>
      <h2 className="text-base font-semibold text-text-primary mb-1.5">
        No se pudo obtener el informe
      </h2>
      <p className="text-sm text-text-secondary mb-6 leading-relaxed">{message}</p>
      <button
        onClick={onRetry}
        className="px-5 py-2.5 rounded-lg bg-accent-blue text-white text-sm font-semibold hover:brightness-110 transition-all active:scale-[0.97]"
      >
        Intentar de nuevo
      </button>
    </div>
  )
}

// ── Transition wrapper ────────────────────────────────────────────────────────

const fadeSlide = {
  initial:    { opacity: 0, y: 10 },
  animate:    { opacity: 1, y: 0 },
  exit:       { opacity: 0, y: -6 },
  transition: { duration: 0.28, ease: 'easeOut' as const },
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CheckPage() {
  const { vin: vinParam } = useParams<{ vin?: string }>()
  const navigate = useNavigate()
  const { report, loading, error, checkVIN, checkByPlate, reset } = useCheck(vinParam)

  useEffect(() => {
    if (report) {
      const d = report.vinDecode
      document.title = d
        ? `${[d.make, d.model, d.year].filter(Boolean).join(' ')} — CARDEX Check`
        : 'CARDEX Check — Historial vehicular'
    } else {
      document.title = 'CARDEX Check — Historial vehicular gratuito'
    }
    return () => { document.title = 'CARDEX' }
  }, [report])

  function handleSearch(vin: string) {
    navigate(`/check/${vin}`, { replace: vinParam !== undefined })
    checkVIN(vin)
  }

  function handleSearchByPlate(country: string, plate: string) {
    navigate('/check', { replace: vinParam !== undefined })
    checkByPlate(country, plate)
  }

  function handleBack() {
    reset()
    navigate('/check', { replace: true })
  }

  function handleRefresh() {
    if (vinParam) checkVIN(vinParam)
  }

  return (
    <div className="min-h-[100dvh] bg-bg-primary">
      {/* Slim public header */}
      <header className="h-12 sticky top-0 z-[var(--z-overlay)] bg-bg-surface/70 backdrop-blur-md border-b border-border-subtle flex items-center px-5">
        <a href="/" className="flex items-center gap-2.5 group">
          <div className="w-6 h-6 bg-accent-blue rounded-md flex items-center justify-center shadow-glow-blue transition-all duration-200 group-hover:shadow-none">
            <Car className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-semibold tracking-tight text-text-primary text-sm">
            CARDEX
            <span className="text-accent-blue font-normal ml-1.5">Check</span>
          </span>
        </a>
      </header>

      <main>
        <AnimatePresence mode="wait">
          {loading && (
            <motion.div key="loading" {...fadeSlide}>
              <ReportSkeleton />
            </motion.div>
          )}

          {!loading && error && (
            <motion.div key="error" {...fadeSlide}>
              {error.code === 'rate_limit' && error.retryAfterSeconds !== undefined ? (
                <RateLimitError
                  seconds={error.retryAfterSeconds}
                  onRetry={() => vinParam && checkVIN(vinParam)}
                />
              ) : (
                <div className="space-y-0">
                  <GenericError message={error.message} onRetry={handleBack} />
                  <CheckLanding onSearch={handleSearch} onSearchByPlate={handleSearchByPlate} initialVin={vinParam} />
                </div>
              )}
            </motion.div>
          )}

          {!loading && !error && report && (
            <motion.div key="report" {...fadeSlide}>
              <CheckReport
                report={report}
                onBack={handleBack}
                onRefresh={handleRefresh}
              />
            </motion.div>
          )}

          {!loading && !error && !report && (
            <motion.div key="landing" {...fadeSlide}>
              <CheckLanding
                onSearch={handleSearch}
                onSearchByPlate={handleSearchByPlate}
                initialVin={vinParam}
                loading={loading}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
