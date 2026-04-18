import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../api/client'
import type { VehicleReport, CheckError, CheckErrorCode } from '../types/check'

interface CheckState {
  report: VehicleReport | null
  loading: boolean
  error: CheckError | null
}

export function useCheck(initialVin?: string) {
  const [state, setState] = useState<CheckState>({
    report: null,
    loading: false,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const checkVIN = useCallback(async (vin: string): Promise<void> => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setState({ report: null, loading: true, error: null })

    try {
      const report = await apiRequest<VehicleReport>(`/check/${encodeURIComponent(vin)}`, {
        signal: ctrl.signal,
      })
      setState({ report, loading: false, error: null })
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return

      let code: CheckErrorCode = 'server_error'
      let message = 'Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.'
      let retryAfterSeconds: number | undefined

      if (err instanceof ApiError) {
        if (err.status === 400) {
          code = 'invalid_vin'
          message = 'El VIN introducido no es válido.'
        } else if (err.status === 404) {
          code = 'not_found'
          message = 'No se encontraron datos para este VIN.'
        } else if (err.status === 429) {
          code = 'rate_limit'
          message = 'Límite de consultas alcanzado. Inténtalo en breve.'
          // parse Retry-After if available (best-effort from error message)
          const seconds = parseInt(err.message)
          retryAfterSeconds = isNaN(seconds) ? 60 : seconds
        }
      }

      setState({
        report: null,
        loading: false,
        error: { code, message, retryAfterSeconds },
      })
    }
  }, [])

  useEffect(() => {
    if (initialVin) {
      checkVIN(initialVin)
    }
    return () => abortRef.current?.abort()
  }, [initialVin, checkVIN])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setState({ report: null, loading: false, error: null })
  }, [])

  return { ...state, checkVIN, reset }
}
