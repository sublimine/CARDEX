import { motion } from 'framer-motion'
import React, { useId } from 'react'
import { CheckCircle2, AlertCircle } from 'lucide-react'
import { cn } from '../lib/cn'

const VIN_REGEX = /^[A-HJ-NPR-Z0-9]{17}$/i

export function validateVIN(vin: string): boolean {
  return VIN_REGEX.test(vin.trim().toUpperCase())
}

interface VINInputProps {
  value: string
  onChange: (value: string) => void
  onSubmit?: () => void
  disabled?: boolean
  large?: boolean
}

export default function VINInput({ value, onChange, onSubmit, disabled, large }: VINInputProps) {
  const id = useId()
  const normalized = value.trim().toUpperCase()
  const isEmpty    = normalized.length === 0
  const isValid    = validateVIN(normalized)
  const hasError   = !isEmpty && !isValid

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (raw.length <= 17) onChange(raw)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && isValid && onSubmit) onSubmit()
  }

  const ringColor = isValid
    ? 'border-accent-emerald focus:ring-accent-emerald/30 focus:border-accent-emerald'
    : hasError
    ? 'border-accent-rose focus:ring-accent-rose/30 focus:border-accent-rose'
    : 'border-border-subtle focus:ring-accent-blue/30 focus:border-border-active'

  return (
    <div className="w-full">
      <label
        htmlFor={id}
        className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wide"
      >
        Número VIN
      </label>
      <motion.div
        animate={hasError ? { x: [0, -4, 4, -3, 3, 0] } : { x: 0 }}
        transition={{ duration: 0.35 }}
        className="relative"
      >
        <input
          id={id}
          type="text"
          inputMode="text"
          autoCapitalize="characters"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          maxLength={17}
          placeholder="p.ej. WBA3A5C50CF256985"
          value={normalized}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          aria-invalid={hasError}
          aria-describedby={hasError ? `${id}-err` : undefined}
          className={cn(
            'w-full font-mono bg-glass-subtle border rounded-md transition-all duration-200',
            'text-text-primary placeholder:text-text-muted',
            'focus:outline-none focus:ring-2 focus:ring-offset-0',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            ringColor,
            large
              ? 'text-base py-4 pl-5 pr-14 tracking-[0.2em] rounded-lg'
              : 'text-sm py-2.5 pl-3.5 pr-10'
          )}
        />
        <span
          className={cn(
            'absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none transition-opacity duration-200',
            isEmpty ? 'opacity-0' : 'opacity-100'
          )}
        >
          {isValid ? (
            <CheckCircle2 className="w-5 h-5 text-accent-emerald" />
          ) : hasError ? (
            <AlertCircle className="w-5 h-5 text-accent-rose" />
          ) : null}
        </span>
      </motion.div>

      <div className="flex items-center justify-between mt-1.5">
        {hasError ? (
          <motion.p
            id={`${id}-err`}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-xs text-accent-rose"
          >
            {normalized.length < 17
              ? `Faltan ${17 - normalized.length} caracteres`
              : 'VIN inválido — usa solo letras y números (sin I, O, Q)'}
          </motion.p>
        ) : (
          <span />
        )}
        <span
          className={cn(
            'text-xs tabular-nums font-mono',
            isValid ? 'text-accent-emerald' : 'text-text-muted'
          )}
        >
          {normalized.length}/17
        </span>
      </div>
    </div>
  )
}
