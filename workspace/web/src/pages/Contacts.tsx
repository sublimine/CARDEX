import React, { useState } from 'react'
import { Search, Phone, Mail, Users } from 'lucide-react'
import Card from '../components/Card'
import Input from '../components/Input'
import Avatar from '../components/Avatar'
import EmptyState from '../components/EmptyState'
import { useApi } from '../hooks/useApi'
import type { Contact, Activity } from '../types'

interface ContactList { contacts: Contact[]; total: number }
interface ContactDetail { contact: Contact; activities: Activity[] }

const MOCK_CONTACTS: Contact[] = Array.from({ length: 10 }, (_, i) => ({
  id: `c${i}`,
  tenantId: 't1',
  name: ['Maria Santos', 'John Doe', 'Anna Weber', 'Peter Klein', 'Sophie Leblanc',
         'Hans Müller', 'Clara Rossi', 'Tom Brown', 'Lisa Chen', 'David Novak'][i],
  email: `contact${i}@example.com`,
  phone: `+49 170 ${1000000 + i}`,
  createdAt: new Date(Date.now() - i * 86400000 * 3).toISOString(),
  updatedAt: new Date().toISOString(),
  dealCount: i % 4,
}))

const activityIcon: Record<string, string> = {
  inquiry: '📧', reply: '💬', call: '📞', visit: '🚗', note: '📝', reminder: '⏰',
}

export default function Contacts() {
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data } = useApi<ContactList>('/contacts')
  const contacts = data?.contacts ?? MOCK_CONTACTS

  const { data: detail } = useApi<ContactDetail>(
    selectedId ? `/contacts/${selectedId}` : '',
    [selectedId],
  )

  const filtered = search
    ? contacts.filter((c) =>
        `${c.name} ${c.email} ${c.phone}`.toLowerCase().includes(search.toLowerCase()),
      )
    : contacts

  const selected = contacts.find((c) => c.id === selectedId) ?? null

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Contacts</h1>

      <div className="flex flex-col lg:flex-row gap-4 h-full">
        {/* List */}
        <Card padding={false} className="flex-1 lg:max-w-sm">
          <div className="p-3 border-b border-gray-100 dark:border-gray-700">
            <Input
              icon={<Search className="w-4 h-4" />}
              placeholder="Search contacts…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {filtered.length === 0 ? (
            <EmptyState icon={<Users className="w-6 h-6" />} message="No contacts found" />
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {filtered.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelectedId(c.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors ${
                    selectedId === c.id ? 'bg-brand-50 dark:bg-brand-900/20' : ''
                  }`}
                >
                  <Avatar name={c.name} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{c.name}</p>
                    <p className="text-xs text-gray-400 truncate">{c.email}</p>
                  </div>
                  {(c.dealCount ?? 0) > 0 && (
                    <span className="text-xs px-1.5 py-0.5 bg-brand-100 dark:bg-brand-900/30 text-brand-600 rounded-full font-medium shrink-0">
                      {c.dealCount}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </Card>

        {/* Detail */}
        {selected ? (
          <Card className="flex-1 min-w-0">
            <div className="flex items-start gap-4 mb-5">
              <Avatar name={selected.name} size="lg" />
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">{selected.name}</h2>
                <div className="flex flex-col gap-1 mt-1">
                  <a href={`mailto:${selected.email}`} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-600">
                    <Mail className="w-3.5 h-3.5" /> {selected.email}
                  </a>
                  <a href={`tel:${selected.phone}`} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-600">
                    <Phone className="w-3.5 h-3.5" /> {selected.phone}
                  </a>
                </div>
              </div>
            </div>

            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Activity Timeline</h3>

            {detail?.activities && detail.activities.length > 0 ? (
              <div className="space-y-3">
                {detail.activities.map((a) => (
                  <div key={a.id} className="flex items-start gap-3">
                    <span className="text-lg shrink-0">{activityIcon[a.type] ?? '📋'}</span>
                    <div className="flex-1">
                      <p className="text-sm text-gray-700 dark:text-gray-300">{a.body}</p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {new Date(a.createdAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400">No activities recorded yet.</p>
            )}
          </Card>
        ) : (
          <Card className="flex-1 hidden lg:flex">
            <EmptyState
              icon={<Users className="w-6 h-6" />}
              title="Select a contact"
              message="Choose a contact from the list to view details and activity history."
            />
          </Card>
        )}
      </div>
    </div>
  )
}
