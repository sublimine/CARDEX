import React, { useId } from 'react'
import { CheckCircle2, AlertCircle } from 'lucide-react'

// VIN must be exactly 17 chars, no I, O, or Q.
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
  const isEmpty = normalized.length === 0
  const isValid = validateVIN(normalized)
  const hasError = !isEmpty && !isValid

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    // Allow only valid VIN chars; strip spaces and force uppercase.
    const raw = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (raw.length <= 17) onChange(raw)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && isValid && onSubmit) {
      onSubmit()
    }
  }

  const sizeClasses = large
    ? 'text-lg py-4 pl-5 pr-14 tracking-widest rounded-xl'
    : 'text-sm py-2.5 pl-3.5 pr-10 rounded-lg'

  const borderColor = isValid
    ? 'border-green-400 focus:ring-green-400'
    : hasError
    ? 'border-red-400 focus:ring-red-400'
    : 'border-gray-300 dark:border-gray-600 focus:ring-brand-500'

  return (
    <div className="w-full">
      <label
        htmlFor={id}
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
      >
        Número VIN
      </label>
      <div className="relative">
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
          className={`w-full font-mono bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 border ${borderColor} ${sizeClasses} focus:outline-none focus:ring-2 focus:border-transparent transition disabled:opacity-50 disabled:cursor-not-allowed`}
          aria-invalid={hasError}
          aria-describedby={hasError ? `${id}-err` : undefined}
        />
        {/* Status icon */}
        <span className={`absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none transition-opacity ${isEmpty ? 'opacity-0' : 'opacity-100'}`}>
          {isValid
            ? <CheckCircle2 className="w-5 h-5 text-green-500" />
            : hasError
            ? <AlertCircle className="w-5 h-5 text-red-400" />
            : null}
        </span>
      </div>

      {/* Character counter + validation hint */}
      <div className="flex items-center justify-between mt-1.5">
        {hasError ? (
          <p id={`${id}-err`} className="text-xs text-red-600 dark:text-red-400">
            {normalized.length < 17
              ? `Faltan ${17 - normalized.length} caracteres`
              : 'VIN inválido — usa solo letras y números (sin I, O, Q)'}
          </p>
        ) : (
          <span />
        )}
        <span className={`text-xs tabular-nums ${isValid ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
          {normalized.length}/17
        </span>
      </div>
    </div>
  )
}
