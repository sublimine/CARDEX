import { useCallback, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../api/client'
import type { VehicleDossier } from '../types/dossier'

export type DossierErrorCode =
  | 'not_found'
  | 'unavailable'
  | 'rate_limit'
  | 'server_error'

export interface DossierError {
  code: DossierErrorCode
  message: string
  retryAfterSeconds?: number
}

interface DossierState {
  dossier: VehicleDossier | null
  loading: boolean
  error: DossierError | null
}

export function useDossier() {
  const [state, setState] = useState<DossierState>({
    dossier: null,
    loading: false,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const fetchDossier = useCallback(async (country: string, plate: string): Promise<void> => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setState({ dossier: null, loading: true, error: null })

    try {
      const dossier = await apiRequest<VehicleDossier>(
        `/dossier/${encodeURIComponent(country)}/${encodeURIComponent(plate)}`,
        { signal: ctrl.signal },
      )
      setState({ dossier, loading: false, error: null })
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return
      setState({ dossier: null, loading: false, error: mapError(err) })
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setState({ dossier: null, loading: false, error: null })
  }, [])

  return { ...state, fetchDossier, reset }
}

function mapError(err: unknown): DossierError {
  let code: DossierErrorCode = 'server_error'
  let message = 'Ha ocurrido un error inesperado.'
  let retryAfterSeconds: number | undefined

  if (err instanceof ApiError) {
    if (err.status === 404) {
      code = 'not_found'
      message = 'Matrícula no encontrada.'
    } else if (err.status === 503) {
      code = 'unavailable'
      message = 'No hay datos públicos disponibles para este país.'
    } else if (err.status === 429) {
      code = 'rate_limit'
      message = 'Límite de consultas alcanzado.'
      const seconds = parseInt(err.message)
      retryAfterSeconds = isNaN(seconds) ? 60 : seconds
    }
  }
  return { code, message, retryAfterSeconds }
}
