import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setAccessToken, setTenantId, setTokenExpiry, getStoredToken, getStoredTenantId, isTokenValid } from '../api/client'
import type { User } from '../types'

// DEV BYPASS — set to false to re-enable real auth
const DEV_BYPASS = true

const DEV_USER: User = {
  id: 'dev-001',
  email: 'demo@cardex.dev',
  name: 'Demo User',
  tenantId: 'tenant-dev',
  role: 'admin',
}

interface AuthState {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

interface LoginResponse { token: string; expires_in: number; user: User }

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    if (DEV_BYPASS) return { user: DEV_USER, isLoading: false, isAuthenticated: true }
    // Restore session from localStorage on init
    if (isTokenValid()) {
      const tid = getStoredTenantId()
      if (tid) setTenantId(tid)
      return { user: null, isLoading: true, isAuthenticated: false }
    }
    return { user: null, isLoading: false, isAuthenticated: false }
  })

  // Hydrate user from /auth/me if we have a stored token
  useEffect(() => {
    if (DEV_BYPASS) return
    if (!isTokenValid()) return
    api.get<{ user: User }>('/auth/me')
      .then(data => {
        const raw = data.user as unknown as Record<string, unknown>
        const user = { ...data.user, tenantId: (raw.tenantId ?? raw.tenant_id ?? '') as string }
        setState({ user, isLoading: false, isAuthenticated: true })
      })
      .catch(() => {
        setAccessToken(null)
        setState({ user: null, isLoading: false, isAuthenticated: false })
      })
  }, [])

  const logout = useCallback(() => {
    if (DEV_BYPASS) return
    setAccessToken(null)
    setTenantId(null)
    setState({ user: null, isLoading: false, isAuthenticated: false })
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    if (DEV_BYPASS) {
      setState({ user: { ...DEV_USER, email: email || DEV_USER.email }, isLoading: false, isAuthenticated: true })
      return
    }
    setState(s => ({ ...s, isLoading: true }))
    try {
      const data = await api.post<LoginResponse>('/auth/login', { email, password })
      const raw  = data.user as unknown as Record<string, unknown>
      const user = { ...data.user, tenantId: (raw.tenantId ?? raw.tenant_id ?? '') as string }
      setAccessToken(data.token)
      setTokenExpiry(data.expires_in)
      setTenantId(user.tenantId)
      setState({ user, isLoading: false, isAuthenticated: true })
    } catch (err) {
      setState(s => ({ ...s, isLoading: false }))
      throw err
    }
  }, [])

  useEffect(() => {
    window.addEventListener('auth:unauthorized', logout)
    return () => window.removeEventListener('auth:unauthorized', logout)
  }, [logout])

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuthContext must be used inside AuthProvider')
  return ctx
}
