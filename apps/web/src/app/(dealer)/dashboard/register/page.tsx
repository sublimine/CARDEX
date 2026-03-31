'use client'

import { useState, FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { CheckCircle } from 'lucide-react'

export default function DealerRegisterPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    email: '', password: '', name: '', dealershipName: '', country: 'ES',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function set(key: keyof typeof formData) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setFormData(prev => ({ ...prev, [key]: e.target.value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
          name: formData.name,
          dealership_name: formData.dealershipName,
          country: formData.country,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error || 'Registration failed')
        return
      }
      localStorage.setItem('cardex_token', data.access_token)
      router.push('/dashboard')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const BENEFITS = [
    'Free inventory management',
    'Multiposting to AutoScout24, mobile.de & more',
    'AI-powered pricing intelligence',
    'Marketing audit & recommendations',
  ]

  return (
    <div className="mx-auto flex max-w-screen-md flex-col gap-10 px-4 py-16 lg:flex-row lg:items-start">
      {/* Left: benefits */}
      <div className="flex-1">
        <h1 className="mb-3 text-3xl font-bold text-white">Start free today</h1>
        <p className="mb-6 text-surface-muted">
          Everything your dealership needs to compete across Europe.
          No credit card required.
        </p>
        <ul className="flex flex-col gap-3">
          {BENEFITS.map(b => (
            <li key={b} className="flex items-center gap-3 text-sm text-white">
              <CheckCircle size={16} className="text-brand-400 shrink-0" />
              {b}
            </li>
          ))}
        </ul>
      </div>

      {/* Right: form */}
      <div className="flex-1">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-2xl border border-surface-border bg-surface-card p-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 sm:col-span-1">
              <label className="mb-1.5 block text-sm font-medium text-white">Your name</label>
              <input
                required value={formData.name} onChange={set('name')} type="text"
                placeholder="First Last"
                className="w-full rounded-xl border border-surface-border bg-surface-hover px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="col-span-2 sm:col-span-1">
              <label className="mb-1.5 block text-sm font-medium text-white">Country</label>
              <select
                value={formData.country} onChange={set('country')}
                className="w-full rounded-xl border border-surface-border bg-surface-hover px-4 py-2.5 text-white focus:border-brand-500 focus:outline-none"
              >
                {['ES', 'DE', 'FR', 'NL', 'BE', 'CH'].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-white">Dealership name</label>
            <input
              required value={formData.dealershipName} onChange={set('dealershipName')} type="text"
              placeholder="Auto García SL"
              className="w-full rounded-xl border border-surface-border bg-surface-hover px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-white">Email</label>
            <input
              required value={formData.email} onChange={set('email')} type="email"
              placeholder="you@dealership.com"
              className="w-full rounded-xl border border-surface-border bg-surface-hover px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-white">Password</label>
            <input
              required value={formData.password} onChange={set('password')} type="password"
              placeholder="min. 8 characters"
              minLength={8}
              className="w-full rounded-xl border border-surface-border bg-surface-hover px-4 py-2.5 text-white placeholder:text-surface-muted focus:border-brand-500 focus:outline-none"
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
            {loading ? 'Creating account…' : 'Create free account'}
          </button>

          <p className="text-center text-xs text-surface-muted">
            Already have an account?{' '}
            <Link href="/dashboard/login" className="text-brand-400 hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
