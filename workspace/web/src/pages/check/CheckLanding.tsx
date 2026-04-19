import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldCheck, Globe, Zap,
  ChevronDown, Car, FileText, Key,
} from 'lucide-react'
import VINInput, { validateVIN } from '../../components/VINInput'
import Button from '../../components/Button'
import { cn } from '../../lib/cn'

// ── Animation variants ────────────────────────────────────────────────────────

const contentVariants = {
  hidden:   {},
  visible:  { transition: { staggerChildren: 0.09, delayChildren: 0.05 } },
}

const itemVariants = {
  hidden:  { opacity: 0, y: 20 },
  visible: {
    opacity: 1, y: 0,
    transition: { type: 'spring' as const, stiffness: 320, damping: 28 },
  },
}

const trustVariants = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.4 } },
}

const trustItem = {
  hidden:  { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 400, damping: 30 } },
}

const rightVariants = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.06, delayChildren: 0.25 } },
}

const countryVariants = {
  hidden:  { opacity: 0, scale: 0.88 },
  visible: { opacity: 1, scale: 1, transition: { type: 'spring' as const, stiffness: 360, damping: 24 } },
}

// ── VIN location guide ────────────────────────────────────────────────────────

const vinLocations = [
  {
    Icon: Car,
    label: 'Salpicadero',
    detail: 'Esquina inferior del parabrisas (lado conductor)',
  },
  {
    Icon: FileText,
    label: 'Documentación',
    detail: 'Permiso de circulación y tarjeta técnica',
  },
  {
    Icon: Key,
    label: 'Jamba de puerta',
    detail: 'Umbral interior de la puerta del conductor',
  },
]

// ── Country data ──────────────────────────────────────────────────────────────

const COUNTRIES = [
  { code: 'DE', name: 'Alemania',    sources: 3 },
  { code: 'NL', name: 'Países Bajos', sources: 2 },
  { code: 'BE', name: 'Bélgica',     sources: 2 },
  { code: 'FR', name: 'Francia',     sources: 2 },
  { code: 'ES', name: 'España',      sources: 2 },
  { code: 'CH', name: 'Suiza',       sources: 1 },
]

// ── Floating decoration background ───────────────────────────────────────────

function FloatingBlobs() {
  return (
    <>
      <motion.div
        animate={{ y: [0, -28, 0] }}
        transition={{ duration: 9, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute -top-24 left-[10%] w-[480px] h-[480px] rounded-full bg-blue-500/5 blur-[90px] pointer-events-none"
      />
      <motion.div
        animate={{ y: [0, 20, 0] }}
        transition={{ duration: 13, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
        className="absolute bottom-0 right-[5%] w-[360px] h-[360px] rounded-full bg-blue-400/4 blur-[80px] pointer-events-none"
      />
      <motion.div
        animate={{ y: [0, -16, 0] }}
        transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut', delay: 4 }}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[200px] rounded-full bg-blue-600/3 blur-[100px] pointer-events-none"
      />
    </>
  )
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface CheckLandingProps {
  onSearch: (vin: string) => void
  initialVin?: string
  loading?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CheckLanding({ onSearch, initialVin = '', loading }: CheckLandingProps) {
  const [vin, setVin] = useState(initialVin)
  const [guideOpen, setGuideOpen] = useState(false)

  function handleSubmit() {
    const clean = vin.trim().toUpperCase()
    if (validateVIN(clean)) onSearch(clean)
  }

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-bg-primary flex flex-col">
      <FloatingBlobs />

      {/* Subtle grid texture */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.025]"
        style={{
          backgroundImage:
            'linear-gradient(var(--border-subtle) 1px, transparent 1px), linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      {/* Main content */}
      <div className="relative flex-1 flex items-center">
        <div className="w-full max-w-7xl mx-auto px-5 md:px-8 lg:px-12 py-12 lg:py-0">
          <div className="grid grid-cols-1 lg:grid-cols-[58%_42%] gap-8 lg:gap-16 lg:min-h-[72vh] lg:items-center">

            {/* ── Left column — content ── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              className="flex flex-col items-start gap-0"
            >
              {/* Service badge */}
              <motion.div variants={itemVariants} className="mb-6">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  CARDEX Check
                </span>
              </motion.div>

              {/* Headline — left-aligned, controlled size */}
              <motion.h1
                variants={itemVariants}
                className="text-[2.4rem] md:text-[3rem] lg:text-[3.25rem] font-bold tracking-tight leading-[1.08] text-text-primary mb-4"
              >
                Historial vehicular.
                <br />
                <span className="text-accent-blue">Completo. Gratis.</span>
              </motion.h1>

              <motion.p
                variants={itemVariants}
                className="text-base text-text-secondary leading-relaxed max-w-[48ch] mb-8"
              >
                Inspecciones, recalls, kilometraje y alertas de robos para cualquier
                vehículo en Europa — sin registro, sin coste.
              </motion.p>

              {/* VIN input block */}
              <motion.div variants={itemVariants} className="w-full max-w-lg space-y-3">
                <VINInput
                  value={vin}
                  onChange={setVin}
                  onSubmit={handleSubmit}
                  disabled={loading}
                  large
                />
                <Button
                  variant="primary"
                  size="lg"
                  onClick={handleSubmit}
                  disabled={!validateVIN(vin)}
                  loading={loading}
                  className="w-full text-base py-3.5"
                >
                  {loading ? 'Consultando fuentes…' : 'Verificar historial'}
                </Button>

                {loading && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-xs text-text-muted text-center"
                  >
                    Consultando bases de datos europeas — puede tardar unos segundos.
                  </motion.p>
                )}
              </motion.div>

              {/* Trust row */}
              <motion.div
                variants={trustVariants}
                initial="hidden"
                animate="visible"
                className="flex flex-wrap items-center gap-4 mt-7"
              >
                {[
                  { Icon: ShieldCheck, text: 'Sin registro' },
                  { Icon: Globe,       text: 'Fuentes oficiales EU' },
                  { Icon: Zap,         text: 'Resultado en segundos' },
                ].map(({ Icon, text }) => (
                  <motion.div
                    key={text}
                    variants={trustItem}
                    className="flex items-center gap-1.5 text-xs text-text-muted"
                  >
                    <Icon className="w-3.5 h-3.5 text-accent-blue/70" strokeWidth={1.5} />
                    <span>{text}</span>
                  </motion.div>
                ))}
              </motion.div>

              {/* VIN location guide — expandable */}
              <motion.div variants={itemVariants} className="mt-8 w-full max-w-lg">
                <button
                  onClick={() => setGuideOpen((v) => !v)}
                  className="flex items-center gap-2 text-xs text-text-muted hover:text-text-secondary transition-colors duration-150"
                >
                  <span className="font-medium uppercase tracking-wider">¿Dónde encuentro el VIN?</span>
                  <motion.span
                    animate={{ rotate: guideOpen ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <ChevronDown className="w-3.5 h-3.5" />
                  </motion.span>
                </button>

                <AnimatePresence>
                  {guideOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                      style={{ overflow: 'hidden' }}
                    >
                      <div className="grid grid-cols-3 gap-2.5 mt-4">
                        {vinLocations.map(({ Icon, label, detail }) => (
                          <div
                            key={label}
                            className="glass rounded-lg p-3 flex flex-col items-center gap-1.5 text-center"
                          >
                            <div className="w-7 h-7 rounded-md bg-blue-500/10 ring-1 ring-blue-500/15 flex items-center justify-center">
                              <Icon className="w-3.5 h-3.5 text-accent-blue" strokeWidth={1.5} />
                            </div>
                            <p className="text-[11px] font-medium text-text-primary">{label}</p>
                            <p className="text-[10px] text-text-muted leading-snug">{detail}</p>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </motion.div>

            {/* ── Right column — decoration (hidden on mobile) ── */}
            <div className="hidden lg:flex flex-col items-start justify-center relative">
              {/* Faint watermark */}
              <div
                className="absolute inset-0 flex items-center justify-center select-none pointer-events-none"
                aria-hidden
              >
                <span
                  className="text-[22rem] font-bold tracking-tighter text-white/[0.018] leading-none"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  17
                </span>
              </div>

              <motion.div
                variants={rightVariants}
                initial="hidden"
                animate="visible"
                className="relative z-10 w-full"
              >
                {/* Section label */}
                <motion.p
                  variants={countryVariants}
                  className="text-[10px] font-semibold text-text-muted uppercase tracking-[0.18em] mb-5"
                >
                  Cobertura por país
                </motion.p>

                {/* Country grid — 2 columns */}
                <div className="grid grid-cols-2 gap-2.5 max-w-xs">
                  {COUNTRIES.map(({ code, name, sources }) => (
                    <motion.div
                      key={code}
                      variants={countryVariants}
                      whileHover={{ scale: 1.02, transition: { duration: 0.15 } }}
                      className="glass rounded-lg px-3.5 py-3 flex items-center gap-2.5 cursor-default"
                    >
                      <span className="text-sm font-bold text-accent-blue font-mono">{code}</span>
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-text-primary truncate">{name}</p>
                        <p className="text-[10px] text-text-muted">
                          {sources} fuente{sources !== 1 ? 's' : ''}
                        </p>
                      </div>
                    </motion.div>
                  ))}
                </div>

                {/* Stats row */}
                <motion.div
                  variants={countryVariants}
                  className="flex items-center gap-5 mt-8 pt-6 border-t border-border-subtle"
                >
                  {[
                    { value: '12',    label: 'fuentes de datos' },
                    { value: '< 3s',  label: 'tiempo medio' },
                    { value: '100%',  label: 'gratuito' },
                  ].map(({ value, label }) => (
                    <div key={label}>
                      <p className="text-lg font-bold text-text-primary tracking-tight">{value}</p>
                      <p className="text-[10px] text-text-muted uppercase tracking-wide">{label}</p>
                    </div>
                  ))}
                </motion.div>
              </motion.div>
            </div>

          </div>
        </div>
      </div>

      {/* Bottom disclaimer */}
      <div className="relative border-t border-border-subtle/50 px-5 py-3 text-center">
        <p className="text-[10px] text-text-muted">
          La ausencia de alertas no garantiza que el vehículo esté libre de problemas.
          Consulta siempre un profesional antes de comprar.
        </p>
      </div>
    </div>
  )
}
