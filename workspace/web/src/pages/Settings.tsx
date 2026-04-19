import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import { useToast } from '../components/Toast'
import { useAuthContext } from '../auth/AuthContext'
import {
  CheckCircle, XCircle, User, Building2, Globe, FileText,
} from 'lucide-react'
import { cn } from '../lib/cn'

type Tab = 'profile' | 'tenant' | 'platforms' | 'templates'

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'profile',   label: 'Profile',    icon: User },
  { id: 'tenant',    label: 'Workspace',  icon: Building2 },
  { id: 'platforms', label: 'Platforms',  icon: Globe },
  { id: 'templates', label: 'Templates',  icon: FileText },
]

const PLATFORMS = [
  { id: 'mobile_de',   name: 'mobile.de',   countries: ['DE', 'AT'] },
  { id: 'autoscout24', name: 'AutoScout24', countries: ['DE', 'AT', 'BE', 'NL', 'FR', 'IT', 'ES'] },
  { id: 'leboncoin',   name: 'leboncoin',   countries: ['FR'] },
  { id: 'lacentrale',  name: 'La Centrale', countries: ['FR'] },
  { id: 'autotrader',  name: 'AutoTrader',  countries: ['GB'] },
]

// Reusable section heading
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
      {children}
    </h3>
  )
}

function ProfileTab() {
  const { user } = useAuthContext()
  const { success } = useToast()
  const [name,  setName]  = useState(user?.name  ?? '')
  const [email, setEmail] = useState(user?.email ?? '')

  return (
    <div className="space-y-6 max-w-md">
      <div>
        <SectionTitle>Personal info</SectionTitle>
        <div className="space-y-4">
          <Input label="Full name"  value={name}  onChange={(e) => setName(e.target.value)} />
          <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
      </div>

      <div>
        <SectionTitle>Change password</SectionTitle>
        <div className="space-y-4">
          <Input label="Current password" type="password" placeholder="••••••••" />
          <Input label="New password"     type="password" placeholder="••••••••" />
        </div>
      </div>

      <Button onClick={() => success('Profile saved')} size="md">Save changes</Button>
    </div>
  )
}

function TenantTab() {
  const { success } = useToast()
  const [tenantName, setTenantName] = useState('Garage Müller GmbH')
  const [vatId,      setVatId]      = useState('DE123456789')
  const [country,    setCountry]    = useState('DE')

  return (
    <div className="space-y-6 max-w-md">
      <div>
        <SectionTitle>Company details</SectionTitle>
        <div className="space-y-4">
          <Input label="Company name" value={tenantName} onChange={(e) => setTenantName(e.target.value)} />
          <Input label="VAT ID"       value={vatId}      onChange={(e) => setVatId(e.target.value)} />

          <div className="w-full">
            <label className="block text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              Country
            </label>
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className={cn(
                'w-full px-3.5 py-2.5 rounded-md text-sm text-text-primary',
                'bg-glass-subtle border border-border-subtle',
                'focus:outline-none focus:border-border-active focus:ring-2 focus:ring-accent-blue/20',
                'transition-all duration-150',
              )}
            >
              {['DE', 'AT', 'FR', 'ES', 'NL', 'BE', 'CH'].map((c) => (
                <option key={c} value={c} style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <Button onClick={() => success('Workspace settings saved')} size="md">Save</Button>
    </div>
  )
}

function PlatformsTab() {
  const [connected, setConnected] = useState<Record<string, boolean>>({ autoscout24: true })
  const { success } = useToast()

  return (
    <div className="space-y-2.5 max-w-xl">
      <SectionTitle>Marketplace integrations</SectionTitle>
      {PLATFORMS.map((p) => {
        const isConnected = connected[p.id] ?? false
        return (
          <div
            key={p.id}
            className={cn(
              'flex items-center justify-between p-4 rounded-xl border transition-colors duration-150',
              isConnected
                ? 'border-emerald-500/20 bg-emerald-500/5'
                : 'border-border-subtle bg-glass-subtle',
            )}
          >
            <div>
              <p className="text-sm font-semibold text-text-primary">{p.name}</p>
              <p className="text-xs text-text-muted mt-0.5">{p.countries.join(' · ')}</p>
            </div>

            <div className="flex items-center gap-3">
              <span
                className={cn(
                  'flex items-center gap-1 text-xs font-medium',
                  isConnected ? 'text-accent-emerald' : 'text-text-muted',
                )}
              >
                {isConnected ? (
                  <CheckCircle className="w-3.5 h-3.5" />
                ) : (
                  <XCircle className="w-3.5 h-3.5" />
                )}
                {isConnected ? 'Connected' : 'Not connected'}
              </span>

              <button
                onClick={() => {
                  setConnected((c) => ({ ...c, [p.id]: !c[p.id] }))
                  success(isConnected ? `Disconnected from ${p.name}` : `Connected to ${p.name}`)
                }}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors duration-150',
                  isConnected
                    ? 'border-rose-500/30 bg-rose-500/10 text-accent-rose hover:bg-rose-500/20'
                    : 'border-border-subtle bg-glass-subtle text-text-secondary hover:bg-glass-medium hover:text-text-primary',
                )}
              >
                {isConnected ? 'Disconnect' : 'Connect'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TemplatesTab() {
  const templates = [
    { id: 't1', name: 'Inquiry Acknowledgement', language: 'DE', isSystem: true },
    { id: 't2', name: 'Price Offer',             language: 'DE', isSystem: true },
    { id: 't3', name: 'Follow-up',               language: 'EN', isSystem: true },
    { id: 't4', name: 'Visit Invitation',        language: 'FR', isSystem: true },
    { id: 't5', name: 'Rejection',               language: 'DE', isSystem: true },
    { id: 't6', name: 'Custom welcome',          language: 'DE', isSystem: false },
  ]

  return (
    <div className="max-w-xl">
      <SectionTitle>Message templates</SectionTitle>
      <div className="space-y-1.5">
        {templates.map((t) => (
          <div
            key={t.id}
            className={cn(
              'flex items-center justify-between px-4 py-3 rounded-xl border border-border-subtle',
              'hover:bg-glass-medium transition-colors duration-150 cursor-pointer',
            )}
          >
            <div>
              <p className="text-sm font-medium text-text-primary">{t.name}</p>
              <p className="text-xs text-text-muted mt-0.5">
                {t.language} · {t.isSystem ? 'System' : 'Custom'}
              </p>
            </div>
            {!t.isSystem && (
              <button className="text-xs px-2.5 py-1 rounded-lg bg-glass-subtle border border-border-subtle text-text-muted hover:border-rose-500/30 hover:text-accent-rose transition-colors duration-150">
                Delete
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Settings() {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Settings</h1>
        <p className="text-sm text-text-muted mt-0.5">Manage your profile and workspace</p>
      </div>

      <Card padding={false} className="overflow-hidden">
        {/* Tab bar */}
        <div className="flex border-b border-border-subtle overflow-x-auto scrollbar-none">
          {TABS.map(({ id, label, icon: Icon }) => {
            const active = tab === id
            return (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={cn(
                  'relative flex items-center gap-2 px-5 py-3.5 text-sm font-medium whitespace-nowrap',
                  'transition-colors duration-150',
                  active ? 'text-text-primary' : 'text-text-muted hover:text-text-secondary',
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
                {active && (
                  <motion.div
                    layoutId="settings-tab-indicator"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent-blue"
                    transition={{ type: 'spring', stiffness: 420, damping: 36 }}
                  />
                )}
              </button>
            )
          })}
        </div>

        {/* Tab content */}
        <div className="p-6">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
            >
              {tab === 'profile'   && <ProfileTab />}
              {tab === 'tenant'    && <TenantTab />}
              {tab === 'platforms' && <PlatformsTab />}
              {tab === 'templates' && <TemplatesTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </Card>
    </div>
  )
}
