const TOKEN_KEY  = 'cx_token'
const TENANT_KEY = 'cx_tenant'
const EXPIRY_KEY = 'cx_expiry'

// Restore from localStorage on module init
let accessToken: string | null    = localStorage.getItem(TOKEN_KEY)
let tenantId: string | null       = localStorage.getItem(TENANT_KEY)
let tokenExpiresAt: number | null = Number(localStorage.getItem(EXPIRY_KEY)) || null
let refreshPromise: Promise<void> | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else { localStorage.removeItem(TOKEN_KEY); tokenExpiresAt = null; localStorage.removeItem(EXPIRY_KEY) }
}

export function setTenantId(id: string | null): void {
  tenantId = id
  if (id) localStorage.setItem(TENANT_KEY, id)
  else localStorage.removeItem(TENANT_KEY)
}

export function setTokenExpiry(expiresInSeconds: number): void {
  tokenExpiresAt = Date.now() + expiresInSeconds * 1000
  localStorage.setItem(EXPIRY_KEY, String(tokenExpiresAt))
}

export function getStoredToken(): string | null { return accessToken }
export function getStoredTenantId(): string | null { return tenantId }
export function isTokenValid(): boolean {
  if (!accessToken) return false
  if (tokenExpiresAt && Date.now() > tokenExpiresAt) { setAccessToken(null); return false }
  return true
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message); this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

async function refreshIfNeeded(): Promise<void> {
  if (!accessToken || !tokenExpiresAt) return
  if (Date.now() + 5 * 60 * 1000 < tokenExpiresAt) return
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    try {
      const res = await fetch('/api/v1/auth/refresh', {
        method: 'POST', headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (res.ok) {
        const data = await res.json()
        setAccessToken(data.token)
        setTokenExpiry(data.expires_in as number)
      } else {
        setAccessToken(null)
        window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      }
    } finally { refreshPromise = null }
  })()
  return refreshPromise
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = opts
  await refreshIfNeeded()

  const res = await fetch(`/api/v1${path}`, {
    method, signal,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(tenantId    ? { 'X-Tenant-ID': tenantId } : {}),
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

export const api = {
  get:    <T>(path: string, signal?: AbortSignal)  => apiRequest<T>(path, { signal }),
  post:   <T>(path: string, body: unknown)          => apiRequest<T>(path, { method: 'POST',   body }),
  put:    <T>(path: string, body: unknown)          => apiRequest<T>(path, { method: 'PUT',    body }),
  patch:  <T>(path: string, body: unknown)          => apiRequest<T>(path, { method: 'PATCH',  body }),
  delete: <T>(path: string)                         => apiRequest<T>(path, { method: 'DELETE' }),
}
