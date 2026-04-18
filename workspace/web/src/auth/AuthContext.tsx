import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setAccessToken, setTenantId, setTokenExpiry } from '../api/client'
import type { User } from '../types'

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

interface LoginResponse {
  token: string
  expires_in: number
  user: User
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: false,
    isAuthenticated: false,
  })

  const logout = useCallback(() => {
    setAccessToken(null)
    setTenantId(null)
    setState({ user: null, isLoading: false, isAuthenticated: false })
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      setState((s) => ({ ...s, isLoading: true }))
      try {
        const data = await api.post<LoginResponse>('/auth/login', { email, password })
        setAccessToken(data.token)
        setTokenExpiry(data.expires_in)
        setTenantId(data.user.tenantId)
        setState({ user: data.user, isLoading: false, isAuthenticated: true })
      } catch (err) {
        setState((s) => ({ ...s, isLoading: false }))
        throw err
      }
    },
    [],
  )

  // Auto-logout on 401 from any API call
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
