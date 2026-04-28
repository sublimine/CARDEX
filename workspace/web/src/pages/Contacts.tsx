import { motion, AnimatePresence } from 'framer-motion'
import React, { useState } from 'react'
import { Search, Phone, Mail, Users, LayoutGrid, List, ChevronRight } from 'lucide-react'
import Card from '../components/Card'
import Input from '../components/Input'
import Avatar from '../components/Avatar'
import { Badge } from '../components/Badge'
import EmptyState from '../components/EmptyState'
import Timeline from '../components/Timeline'
import Modal from '../components/Modal'
import { cn } from '../lib/cn'
import { useApi } from '../hooks/useApi'
import type { Contact, Activity } from '../types'
import type { TimelineItem } from '../components/Timeline'

interface ContactList   { contacts: Contact[]; total: number }
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

const activityAccent: Record<Activity['type'], TimelineItem['accent']> = {
  inquiry:  'blue', reply: 'blue', call: 'green',
  visit: 'green', note: 'yellow', reminder: 'yellow',
}
const activityBadgeColor: Record<Activity['type'], 'blue' | 'green' | 'yellow' | 'orange'> = {
  inquiry: 'blue', reply: 'blue', call: 'green',
  visit: 'green', note: 'yellow', reminder: 'orange',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

// ── Contact card (grid) ───────────────────────────────────────────────────────
function ContactCard({ contact, onClick }: { contact: Contact; onClick: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ y: -2 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      onClick={onClick}
      className="glass rounded-lg p-4 cursor-pointer group flex flex-col items-center text-center gap-3"
    >
      <Avatar name={contact.name} size="lg" />
      <div className="min-w-0 w-full">
        <p className="text-sm font-semibold text-text-primary truncate">{contact.name}</p>
        <p className="text-xs text-text-muted truncate mt-0.5">{contact.email}</p>
      </div>
      {(contact.dealCount ?? 0) > 0 && (
        <Badge color="blue">{contact.dealCount} deal{contact.dealCount !== 1 ? 's' : ''}</Badge>
      )}
    </motion.div>
  )
}

// ── Contact detail modal ──────────────────────────────────────────────────────
function ContactDetailModal({
  contact, activities, onClose,
}: { contact: Contact; activities: Activity[]; onClose: () => void }) {
  const timelineItems: TimelineItem[] = activities.map((a) => ({
    id:     a.id,
    date:   formatDate(a.createdAt),
    title:  a.body,
    accent: activityAccent[a.type] ?? 'gray',
    badge:  <Badge color={activityBadgeColor[a.type] ?? 'gray'}>{a.type}</Badge>,
  }))

  return (
    <Modal open onClose={onClose} title={contact.name} size="md">
      <div className="flex items-start gap-4 mb-6 pb-4 border-b border-border-subtle">
        <Avatar name={contact.name} size="lg" />
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-bold text-text-primary">{contact.name}</h2>
          <div className="mt-2 space-y-1">
            <a href={`mailto:${contact.email}`}
              className="flex items-center gap-2 text-sm text-text-secondary hover:text-accent-blue transition-colors">
              <Mail className="w-3.5 h-3.5 shrink-0" /> {contact.email}
            </a>
            <a href={`tel:${contact.phone}`}
              className="flex items-center gap-2 text-sm text-text-secondary hover:text-accent-blue transition-colors">
              <Phone className="w-3.5 h-3.5 shrink-0" /> {contact.phone}
            </a>
          </div>
        </div>
        {(contact.dealCount ?? 0) > 0 && (
          <Badge color="blue">{contact.dealCount} deals</Badge>
        )}
      </div>

      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
        Activity Timeline
      </h3>
      {timelineItems.length > 0 ? (
        <Timeline items={timelineItems} />
      ) : (
        <p className="text-sm text-text-muted italic">No activities recorded yet.</p>
      )}
    </Modal>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Contacts() {
  const [search, setSearch]       = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [viewMode, setViewMode]   = useState<'list' | 'grid'>('list')
  const [detailOpen, setDetailOpen] = useState(false)

  const { data }        = useApi<ContactList>('/contacts')
  const contacts        = data?.contacts ?? MOCK_CONTACTS
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

  function openDetail(id: string) {
    setSelectedId(id)
    setDetailOpen(true)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="p-4 md:p-6 max-w-7xl mx-auto space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Contacts</h1>
          <p className="text-sm text-text-muted mt-0.5">{filtered.length} contacts</p>
        </div>
      </div>

      {/* Search + view toggle */}
      <div className="flex gap-3 items-center">
        <Input
          icon={<Search className="w-4 h-4" />}
          placeholder="Search contacts…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1"
        />
        <div className="flex gap-1 glass rounded-md p-0.5 shrink-0">
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'p-1.5 rounded transition-colors',
              viewMode === 'list' ? 'bg-glass-strong text-text-primary' : 'text-text-muted hover:text-text-secondary',
            )}
          >
            <List className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={cn(
              'p-1.5 rounded transition-colors',
              viewMode === 'grid' ? 'bg-glass-strong text-text-primary' : 'text-text-muted hover:text-text-secondary',
            )}
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        {filtered.length === 0 ? (
          <EmptyState key="empty" icon={<Users className="w-6 h-6" />} message="No contacts found" />
        ) : viewMode === 'grid' ? (
          <motion.div
            key="grid"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3"
          >
            {filtered.map((c) => (
              <ContactCard key={c.id} contact={c} onClick={() => openDetail(c.id)} />
            ))}
          </motion.div>
        ) : (
          <motion.div
            key="list"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <Card padding={false}>
              <div className="divide-y divide-border-subtle/50">
                {filtered.map((c, idx) => (
                  <motion.button
                    key={c.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.03 }}
                    onClick={() => openDetail(c.id)}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-3 text-left transition-colors',
                      'hover:bg-glass-subtle',
                      selectedId === c.id && 'bg-blue-500/5',
                    )}
                  >
                    <Avatar name={c.name} size="sm" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{c.name}</p>
                      <p className="text-xs text-text-muted truncate">{c.email}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {(c.dealCount ?? 0) > 0 && (
                        <Badge color="blue">{c.dealCount}</Badge>
                      )}
                      <ChevronRight className="w-4 h-4 text-text-muted" />
                    </div>
                  </motion.button>
                ))}
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Detail modal */}
      {selected && detailOpen && (
        <ContactDetailModal
          contact={selected}
          activities={detail?.activities ?? []}
          onClose={() => setDetailOpen(false)}
        />
      )}
    </motion.div>
  )
}
