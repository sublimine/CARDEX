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
      setState({ report: null, loading: false, error: mapVINError(err) })
    }
  }, [])

  const checkByPlate = useCallback(async (country: string, plate: string): Promise<void> => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setState({ report: null, loading: true, error: null })

    try {
      const report = await apiRequest<VehicleReport>(
        `/check/plate/${encodeURIComponent(country)}/${encodeURIComponent(plate)}`,
        { signal: ctrl.signal },
      )
      setState({ report, loading: false, error: null })
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return
      setState({ report: null, loading: false, error: mapPlateError(err) })
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

  return { ...state, checkVIN, checkByPlate, reset }
}

function mapVINError(err: unknown): CheckError {
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
      const seconds = parseInt(err.message)
      retryAfterSeconds = isNaN(seconds) ? 60 : seconds
    }
  }
  return { code, message, retryAfterSeconds }
}

function mapPlateError(err: unknown): CheckError {
  let code: CheckErrorCode = 'server_error'
  let message = 'Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.'
  let retryAfterSeconds: number | undefined

  if (err instanceof ApiError) {
    if (err.status === 404) {
      code = 'plate_not_found'
      message = 'Matrícula no encontrada en el registro.'
    } else if (err.status === 503) {
      code = 'plate_unavailable'
      message = 'Los datos de registro completos no están disponibles públicamente para este país. Se muestran datos NCAP y alertas EU cuando están disponibles.'
    } else if (err.status === 429) {
      code = 'rate_limit'
      message = 'Límite de consultas alcanzado. Inténtalo en breve.'
      const seconds = parseInt(err.message)
      retryAfterSeconds = isNaN(seconds) ? 60 : seconds
    }
  }
  return { code, message, retryAfterSeconds }
}
