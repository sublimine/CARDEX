// JWT stored in module memory — never persisted to localStorage.
let accessToken: string | null = null
let tenantId: string | null = null
let tokenExpiresAt: number | null = null // ms since epoch
let refreshPromise: Promise<void> | null = null // deduplicates concurrent refresh calls

export function setAccessToken(token: string | null): void {
  accessToken = token
  if (!token) tokenExpiresAt = null
}

export function setTenantId(id: string | null): void {
  tenantId = id
}

// Call after login/refresh with the expires_in value from the server response.
export function setTokenExpiry(expiresInSeconds: number): void {
  tokenExpiresAt = Date.now() + expiresInSeconds * 1000
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

// Proactively refreshes the token if it will expire within 5 minutes.
// Multiple concurrent callers share a single in-flight refresh request.
async function refreshIfNeeded(): Promise<void> {
  if (!accessToken || !tokenExpiresAt) return
  const fiveMin = 5 * 60 * 1000
  if (Date.now() + fiveMin < tokenExpiresAt) return

  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    try {
      const res = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (res.ok) {
        const data = await res.json()
        accessToken = data.token
        tokenExpiresAt = Date.now() + (data.expires_in as number) * 1000
      } else {
        accessToken = null
        tokenExpiresAt = null
        window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      }
    } finally {
      refreshPromise = null
    }
  })()

  return refreshPromise
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = opts

  await refreshIfNeeded()

  const res = await fetch(`/api/v1${path}`, {
    method,
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(tenantId ? { 'X-Tenant-ID': tenantId } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })

  if (res.status === 401) {
    setAccessToken(null)
    window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    throw new ApiError(401, 'Unauthorized')
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || `HTTP ${res.status}`)
  }

  if (res.status === 204) return null as T
  return res.json() as Promise<T>
}

// Typed convenience wrappers
export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    apiRequest<T>(path, { signal }),

  post: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'POST', body }),

  put: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'PUT', body }),

  patch: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'PATCH', body }),

  delete: <T>(path: string) =>
    apiRequest<T>(path, { method: 'DELETE' }),
}
