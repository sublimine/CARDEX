'use client'

import { useState, FormEvent, useEffect, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import { KeyRound, CheckCircle2, XCircle } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

function ResetPasswordForm() {
  const router = useRouter()
  const params = useSearchParams()
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!token) setError('Enlace inválido. Solicita un nuevo enlace de recuperación.')
  }, [token])

  // Auto-redirect after successful reset — cleanup prevents memory leak if user navigates away
  useEffect(() => {
    if (!success) return
    const timer = setTimeout(() => router.push('/dashboard/login'), 3000)
    return () => clearTimeout(timer)
  }, [success, router])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError('Las contraseñas no coinciden.')
      return
    }
    if (password.length < 10) {
      setError('La contraseña debe tener al menos 10 caracteres.')
      return
    }
    setLoading(true)
    setError('')

    try {
      const res = await fetch(`${API}/api/v1/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(data.message ?? 'Error al restablecer la contraseña.')
        return
      }
      setSuccess(true)
    } catch {
      setError('Error de red. Inténtalo de nuevo.')
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-8 text-center">
        <CheckCircle2 size={40} className="mx-auto mb-4 text-emerald-400" strokeWidth={1.5} />
        <h2 className="text-xl font-bold text-white">Contraseña actualizada</h2>
        <p className="mt-2 text-sm text-surface-muted">
          Tu contraseña ha sido restablecida correctamente. Redirigiendo al login…
        </p>
      </div>
    )
  }

  if (!token) {
    return (
      <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-8 text-center">
        <XCircle size={40} className="mx-auto mb-4 text-red-400" strokeWidth={1.5} />
        <h2 className="text-xl font-bold text-white">Enlace inválido</h2>
        <p className="mt-2 text-sm text-surface-muted">
          Este enlace no es válido o ha expirado.
        </p>
        <Link
          href="/dashboard/forgot-password"
          className="mt-6 block rounded-xl bg-brand-500 py-2.5 text-center font-medium text-white hover:bg-brand-600 transition-colors"
        >
          Solicitar nuevo enlace
        </Link>
      </div>
    )
  }

  return (
    <>
      <div className="mb-6">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10">
          <KeyRound size={22} className="text-brand-400" />
        </div>
        <h1 className="text-2xl font-bold text-white">Nueva contraseña</h1>
        <p className="mt-2 text-sm text-surface-muted">
          Elige una contraseña segura de al menos 10 caracteres.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-white">
            Nueva contraseña
          </label>
          <input
            type="password"
            required
            minLength={10}
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Mínimo 10 caracteres"
            className="w-full rounded-xl border border-surface-border bg-surface-card px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-white">
            Confirmar contraseña
          </label>
          <input
            type="password"
            required
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            placeholder="Repite la contraseña"
            className="w-full rounded-xl border border-surface-border bg-surface-card px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
          />
        </div>

        {/* Password strength indicator — thresholds: 10 (min), 12, 14, 16 (strong) */}
        {password && (
          <div className="space-y-1">
            <div className="flex gap-1">
              {[10, 12, 14, 16].map(threshold => (
                <div
                  key={threshold}
                  className={`h-1 flex-1 rounded-full transition-colors ${
                    password.length >= threshold
                      ? password.length >= 16 ? 'bg-emerald-500'
                        : password.length >= 14 ? 'bg-yellow-500'
                        : 'bg-red-500'
                      : 'bg-surface-border'
                  }`}
                />
              ))}
            </div>
            <p className="text-[10px] text-surface-muted">
              {password.length < 10 ? `Mínimo 10 caracteres (faltan ${10 - password.length})`
                : password.length < 14 ? 'Contraseña aceptable'
                : password.length < 16 ? 'Contraseña buena'
                : 'Contraseña fuerte'}
            </p>
          </div>
        )}

        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-sm text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="rounded-xl bg-brand-500 py-3 font-semibold text-white hover:bg-brand-600 transition-colors disabled:opacity-60"
        >
          {loading ? 'Guardando…' : 'Establecer nueva contraseña'}
        </button>
      </form>
    </>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Suspense fallback={<div className="text-surface-muted text-sm">Cargando…</div>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  )
}
