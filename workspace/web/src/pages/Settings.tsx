import React, { useState } from 'react'
import Card from '../components/Card'
import Button from '../components/Button'
import Input from '../components/Input'
import { useToast } from '../components/Toast'
import { useAuthContext } from '../auth/AuthContext'
import { CheckCircle, XCircle } from 'lucide-react'

type Tab = 'profile' | 'tenant' | 'platforms' | 'templates'

const TABS: { id: Tab; label: string }[] = [
  { id: 'profile',   label: 'Profile' },
  { id: 'tenant',    label: 'Workspace' },
  { id: 'platforms', label: 'Platforms' },
  { id: 'templates', label: 'Templates' },
]

const PLATFORMS = [
  { id: 'mobile_de',    name: 'mobile.de',    logo: 'mde',  countries: ['DE', 'AT'] },
  { id: 'autoscout24',  name: 'AutoScout24',  logo: 'as24', countries: ['DE', 'AT', 'BE', 'NL', 'FR', 'IT', 'ES'] },
  { id: 'leboncoin',    name: 'leboncoin',    logo: 'lbc',  countries: ['FR'] },
  { id: 'lacentrale',   name: 'La Centrale',  logo: 'lc',   countries: ['FR'] },
  { id: 'autotrader',   name: 'AutoTrader',   logo: 'at',   countries: ['GB'] },
]

function ProfileTab() {
  const { user } = useAuthContext()
  const { success } = useToast()
  const [name, setName] = useState(user?.name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')

  return (
    <div className="space-y-4 max-w-sm">
      <Input label="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input label="Current password" type="password" placeholder="••••••••" />
      <Input label="New password" type="password" placeholder="••••••••" />
      <Button onClick={() => success('Profile saved')} size="md">Save changes</Button>
    </div>
  )
}

function TenantTab() {
  const { success } = useToast()
  const [tenantName, setTenantName] = useState('Garage Müller GmbH')
  const [vatId, setVatId] = useState('DE123456789')
  const [country, setCountry] = useState('DE')

  return (
    <div className="space-y-4 max-w-sm">
      <Input label="Company name" value={tenantName} onChange={(e) => setTenantName(e.target.value)} />
      <Input label="VAT ID" value={vatId} onChange={(e) => setVatId(e.target.value)} />
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Country</label>
        <select
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          className="w-full px-3.5 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          {['DE', 'AT', 'FR', 'ES', 'NL', 'BE', 'CH'].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <Button onClick={() => success('Workspace settings saved')} size="md">Save</Button>
    </div>
  )
}

function PlatformsTab() {
  const [connected, setConnected] = useState<Record<string, boolean>>({ autoscout24: true })
  const { success } = useToast()

  return (
    <div className="space-y-3">
      {PLATFORMS.map((p) => (
        <div
          key={p.id}
          className="flex items-center justify-between p-4 rounded-xl border border-gray-200 dark:border-gray-700"
        >
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-white">{p.name}</p>
            <p className="text-xs text-gray-400">{p.countries.join(', ')}</p>
          </div>
          <div className="flex items-center gap-3">
            {connected[p.id] ? (
              <div className="flex items-center gap-1 text-green-600 text-xs font-medium">
                <CheckCircle className="w-3.5 h-3.5" /> Connected
              </div>
            ) : (
              <div className="flex items-center gap-1 text-gray-400 text-xs font-medium">
                <XCircle className="w-3.5 h-3.5" /> Not connected
              </div>
            )}
            <button
              onClick={() => {
                setConnected((c) => ({ ...c, [p.id]: !c[p.id] }))
                success(connected[p.id] ? `Disconnected from ${p.name}` : `Connected to ${p.name}`)
              }}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                connected[p.id]
                  ? 'bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100'
                  : 'bg-brand-50 dark:bg-brand-900/20 text-brand-600 hover:bg-brand-100'
              }`}
            >
              {connected[p.id] ? 'Disconnect' : 'Connect'}
            </button>
          </div>
        </div>
      ))}
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
    <div className="space-y-2">
      {templates.map((t) => (
        <div
          key={t.id}
          className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer transition-colors"
        >
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{t.name}</p>
            <p className="text-xs text-gray-400">{t.language} · {t.isSystem ? 'System' : 'Custom'}</p>
          </div>
          {!t.isSystem && (
            <button className="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 hover:text-red-500 transition-colors">
              Delete
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

export default function Settings() {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-gray-900 dark:text-white">Settings</h1>

      <Card padding={false}>
        {/* Tab nav */}
        <div className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-5 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
                tab === id
                  ? 'border-b-2 border-brand-600 text-brand-600'
                  : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-5">
          {tab === 'profile'   && <ProfileTab />}
          {tab === 'tenant'    && <TenantTab />}
          {tab === 'platforms' && <PlatformsTab />}
          {tab === 'templates' && <TemplatesTab />}
        </div>
      </Card>
    </div>
  )
}
