import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

interface UseApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export function useApi<T>(path: string, deps: unknown[] = []) {
  const [state, setState] = useState<UseApiState<T>>({ data: null, loading: true, error: null })
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(() => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setState((s) => ({ ...s, loading: true, error: null }))
    api
      .get<T>(path, ctrl.signal)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((err: Error) => {
        if (err.name === 'AbortError') return
        setState({ data: null, loading: false, error: err.message })
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps])

  useEffect(() => {
    load()
    return () => abortRef.current?.abort()
  }, [load])

  return { ...state, reload: load }
}
