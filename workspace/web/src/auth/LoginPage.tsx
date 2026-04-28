import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { useAuthContext } from './AuthContext'
import { useNavigate, useLocation } from 'react-router-dom'
import { LogIn, Mail, Lock } from 'lucide-react'
import { cn } from '../lib/cn'

export default function LoginPage() {
  const { login, isLoading } = useAuthContext()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string })?.from ?? '/'

  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch {
      setError('Invalid email or password')
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden"
      style={{ background: 'var(--bg-primary)' }}
    >
      {/* Ambient blue orb */}
      <div
        className="pointer-events-none absolute -top-48 -left-48 w-[700px] h-[700px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 65%)',
        }}
      />
      {/* Ambient amber orb */}
      <div
        className="pointer-events-none absolute -bottom-48 -right-48 w-[600px] h-[600px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(245,158,11,0.10) 0%, transparent 65%)',
        }}
      />
      {/* Subtle dot-grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            'radial-gradient(circle, var(--text-muted) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="w-full max-w-sm relative z-10"
      >
        {/* Wordmark */}
        <div className="flex flex-col items-center mb-8">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4 border border-border-subtle"
            style={{
              background: 'var(--glass-medium)',
              backdropFilter: 'blur(16px)',
              boxShadow: 'var(--shadow-glow-blue)',
            }}
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <path
                d="M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h11a2 2 0 012 2v3"
                stroke="var(--color-blue)" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"
              />
              <rect
                x="9" y="11" width="14" height="10" rx="2"
                stroke="var(--color-blue)" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"
              />
            </svg>
          </div>
          <span
            className="text-2xl font-bold tracking-[0.22em] leading-tight"
            style={{
              background:
                'linear-gradient(125deg, var(--color-blue) 0%, #c8d8ff 60%, #ffffff 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            CARDEX
          </span>
          <span className="text-[10px] font-semibold tracking-[0.3em] text-text-muted uppercase mt-1">
            Workspace
          </span>
        </div>

        {/* Card — uses bg-elevated so it's visibly distinct from the near-black page bg */}
        <div
          className="rounded-2xl border border-border-subtle p-7"
          style={{
            background: 'var(--bg-elevated)',
            boxShadow: 'var(--shadow-4)',
          }}
        >
          <h1 className="text-lg font-semibold text-text-primary mb-1">Welcome back</h1>
          <p className="text-sm text-text-muted mb-6">Sign in to your workspace</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-text-secondary uppercase tracking-wide">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
                <input
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@dealership.com"
                  className={cn(
                    'w-full pl-9 pr-3.5 py-2.5 rounded-md text-sm text-text-primary placeholder:text-text-muted',
                    'bg-glass-subtle border border-border-subtle',
                    'focus:outline-none focus:border-border-active focus:ring-2 focus:ring-accent-blue/20',
                    'transition-all duration-150',
                  )}
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-text-secondary uppercase tracking-wide">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className={cn(
                    'w-full pl-9 pr-3.5 py-2.5 rounded-md text-sm text-text-primary placeholder:text-text-muted',
                    'bg-glass-subtle border border-border-subtle',
                    'focus:outline-none focus:border-border-active focus:ring-2 focus:ring-accent-blue/20',
                    'transition-all duration-150',
                  )}
                />
              </div>
            </div>

            {/* Error banner */}
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="text-xs text-accent-rose bg-rose-500/10 border border-rose-500/20 rounded-lg px-3.5 py-2.5"
              >
                {error}
              </motion.div>
            )}

            {/* Submit */}
            <motion.button
              type="submit"
              disabled={isLoading}
              whileTap={{ scale: isLoading ? 1 : 0.97 }}
              whileHover={{ scale: isLoading ? 1 : 1.01 }}
              transition={{ type: 'spring', stiffness: 400, damping: 20 }}
              className={cn(
                'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                'text-sm font-medium text-white min-h-[44px]',
                'bg-accent-blue shadow-glow-blue hover:brightness-110',
                'disabled:opacity-50 disabled:pointer-events-none',
                'transition-[filter] duration-150',
              )}
            >
              {isLoading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <LogIn className="w-4 h-4" />
              )}
              {isLoading ? 'Signing in…' : 'Sign in'}
            </motion.button>
          </form>
        </div>

        <p className="text-center text-xs text-text-muted mt-6">
          CARDEX Workspace © {new Date().getFullYear()}
        </p>
      </motion.div>
    </div>
  )
}
