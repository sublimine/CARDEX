'use client'

import { useState, FormEvent } from 'react'
import Link from 'next/link'
import { ArrowLeft, Mail, CheckCircle2 } from 'lucide-react'

const API = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const res = await fetch(`${API}/api/v1/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.message ?? 'Error enviando el email. Inténtalo de nuevo.')
        return
      }
      setSent(true)
    } catch {
      setError('Error de red. Comprueba tu conexión e inténtalo de nuevo.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Link
          href="/dashboard/login"
          className="mb-6 flex items-center gap-2 text-sm text-surface-muted hover:text-white transition-colors"
        >
          <ArrowLeft size={14} /> Volver al login
        </Link>

        {sent ? (
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-8 text-center">
            <CheckCircle2 size={40} className="mx-auto mb-4 text-emerald-400" strokeWidth={1.5} />
            <h2 className="text-xl font-bold text-white">Email enviado</h2>
            <p className="mt-2 text-sm text-surface-muted">
              Si existe una cuenta con ese email, recibirás un enlace de recuperación en los próximos minutos.
            </p>
            <p className="mt-4 text-xs text-surface-muted">
              Revisa también tu carpeta de spam.
            </p>
            <Link
              href="/dashboard/login"
              className="mt-6 block rounded-xl bg-brand-500 py-2.5 text-center font-medium text-white hover:bg-brand-600 transition-colors"
            >
              Volver al login
            </Link>
          </div>
        ) : (
          <>
            <div className="mb-6">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500/10">
                <Mail size={22} className="text-brand-400" />
              </div>
              <h1 className="text-2xl font-bold text-white">Recuperar contraseña</h1>
              <p className="mt-2 text-sm text-surface-muted">
                Introduce tu email y te enviaremos un enlace para restablecer tu contraseña.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-white">
                  Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="tu@concesionario.com"
                  className="w-full rounded-xl border border-surface-border bg-surface-card px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
                />
              </div>

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
                {loading ? 'Enviando…' : 'Enviar enlace de recuperación'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
