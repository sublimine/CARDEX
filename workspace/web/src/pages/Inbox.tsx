import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, MessageSquare, RefreshCw, Inbox as InboxIcon } from 'lucide-react'
import Card from '../components/Card'
import Avatar from '../components/Avatar'
import EmptyState from '../components/EmptyState'
import LoadingSpinner from '../components/LoadingSpinner'
import { Badge } from '../components/Badge'
import { useInbox, useConversation, useInboxMutations } from '../hooks/useInbox'
import { useToast } from '../components/Toast'
import type { Conversation } from '../types'
import { cn } from '../lib/cn'

const MOCK_CONVS: Conversation[] = [
  { id: 'cv1', tenantId: 't', contactId: 'c1', vehicleId: 'v1', dealId: 'd1', sourcePlatform: 'mobile.de',   externalId: 'ext1', subject: 'BMW 320d inquiry',     status: 'open',    unread: true,  lastMessageAt: '2026-04-18T10:15:00Z', createdAt: '2026-04-18T10:00:00Z', contactName: 'Maria Santos',  vehicleName: 'BMW 320d',      previewBody: 'Hello, I am interested in this vehicle…' },
  { id: 'cv2', tenantId: 't', contactId: 'c2', vehicleId: 'v2', dealId: 'd2', sourcePlatform: 'autoscout24', externalId: 'ext2', subject: 'Audi A4 question',       status: 'replied', unread: false, lastMessageAt: '2026-04-17T14:30:00Z', createdAt: '2026-04-17T14:00:00Z', contactName: 'John Doe',      vehicleName: 'Audi A4',       previewBody: 'Is the service history available?' },
  { id: 'cv3', tenantId: 't', contactId: 'c3', vehicleId: 'v3', dealId: 'd3', sourcePlatform: 'mobile.de',   externalId: 'ext3', subject: 'Mercedes C220',         status: 'open',    unread: true,  lastMessageAt: '2026-04-17T11:00:00Z', createdAt: '2026-04-17T10:00:00Z', contactName: 'Anna Weber',    vehicleName: 'Mercedes C220', previewBody: 'Can I arrange a test drive this week?' },
  { id: 'cv4', tenantId: 't', contactId: 'c4', vehicleId: 'v4', dealId: 'd4', sourcePlatform: 'manual',      externalId: 'ext4', subject: 'VW Golf 8',             status: 'closed',  unread: false, lastMessageAt: '2026-04-16T09:00:00Z', createdAt: '2026-04-15T08:00:00Z', contactName: 'Peter Klein',   vehicleName: 'VW Golf 8',     previewBody: 'Thank you for your time.' },
]

const STATUS_COLOR: Record<string, NonNullable<Parameters<typeof Badge>[0]['color']>> = {
  open: 'blue', replied: 'green', closed: 'gray', spam: 'red',
}

type Filter = 'all' | 'unread'

function ConvItem({
  conv, selected, onClick,
}: { conv: Conversation; selected: boolean; onClick: () => void }) {
  const date = new Date(conv.lastMessageAt).toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short',
  })

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-start gap-3 px-4 py-3.5 text-left border-b border-border-subtle',
        'transition-colors duration-100',
        selected ? 'bg-accent-blue/10' : 'hover:bg-glass-subtle',
      )}
    >
      <div className="relative mt-0.5">
        <Avatar name={conv.contactName ?? '?'} size="sm" />
        {conv.unread && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-accent-blue ring-2 ring-bg-primary animate-pulse" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span
            className={cn(
              'text-sm truncate',
              conv.unread ? 'font-semibold text-text-primary' : 'font-medium text-text-secondary',
            )}
          >
            {conv.contactName}
          </span>
          <span className="text-[10px] text-text-muted shrink-0">{date}</span>
        </div>

        <p
          className={cn(
            'text-xs truncate',
            conv.unread ? 'text-text-secondary font-medium' : 'text-text-muted',
          )}
        >
          {conv.subject}
        </p>

        <p className="text-xs text-text-muted truncate mt-0.5">{conv.previewBody}</p>

        <div className="flex items-center gap-1.5 mt-2">
          <Badge color={STATUS_COLOR[conv.status] ?? 'gray'}>{conv.status}</Badge>
          <span className="text-[10px] text-text-muted">{conv.sourcePlatform}</span>
        </div>
      </div>
    </button>
  )
}

export default function Inbox() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [replyBody, setReplyBody]   = useState('')
  const [filter, setFilter]         = useState<Filter>('all')

  const { data, loading, reload }                   = useInbox()
  const conversations                               = data?.conversations ?? MOCK_CONVS
  const { data: thread, loading: threadLoading }    = useConversation(selectedId ?? '')
  const { reply, loading: sending }                 = useInboxMutations()
  const { success, error: toastErr }                = useToast()

  const filtered = filter === 'unread' ? conversations.filter((c) => c.unread) : conversations
  const selected = conversations.find((c) => c.id === selectedId) ?? null
  const unreadCount = conversations.filter((c) => c.unread).length

  async function sendReply() {
    if (!selectedId || !replyBody.trim()) return
    try {
      await reply(selectedId, replyBody.trim())
      setReplyBody('')
      success('Reply sent')
      reload()
    } catch {
      toastErr('Failed to send reply')
    }
  }

  return (
    <div className="p-4 md:p-6 h-full flex flex-col max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-2.5">
          <h1 className="text-xl font-bold text-text-primary">Inbox</h1>
          {unreadCount > 0 && (
            <span className="px-2 py-0.5 bg-accent-blue text-white text-xs font-bold rounded-full shadow-glow-blue">
              {unreadCount}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Filter tabs */}
          <div className="flex bg-glass-subtle border border-border-subtle rounded-lg p-0.5">
            {(['all', 'unread'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  'relative px-3 py-1 text-xs font-medium rounded-md transition-colors duration-150 capitalize',
                  filter === f ? 'text-text-primary' : 'text-text-muted hover:text-text-secondary',
                )}
              >
                {filter === f && (
                  <motion.div
                    layoutId="inbox-filter"
                    className="absolute inset-0 rounded-md bg-glass-medium"
                    transition={{ type: 'spring', stiffness: 420, damping: 36 }}
                  />
                )}
                <span className="relative z-10">{f}</span>
              </button>
            ))}
          </div>

          <button
            onClick={reload}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-glass-medium transition-colors duration-150"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0">
        {/* Conversation list */}
        <Card
          padding={false}
          className="md:w-80 shrink-0 overflow-y-auto"
        >
          {filtered.length === 0 ? (
            <EmptyState icon={<InboxIcon className="w-6 h-6" />} message="No conversations" />
          ) : (
            <AnimatePresence initial={false}>
              {filtered.map((c) => (
                <motion.div
                  key={c.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <ConvItem
                    conv={c}
                    selected={c.id === selectedId}
                    onClick={() => setSelectedId(c.id)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          )}
        </Card>

        {/* Thread pane */}
        {selected ? (
          <Card padding={false} className="flex-1 flex flex-col min-h-0 overflow-hidden">
            {/* Thread header */}
            <div className="px-5 py-4 border-b border-border-subtle shrink-0">
              <p className="text-sm font-semibold text-text-primary">{selected.subject}</p>
              <p className="text-xs text-text-muted mt-0.5">
                {selected.contactName} · {selected.vehicleName} · {selected.sourcePlatform}
              </p>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {threadLoading ? (
                <div className="flex justify-center py-12">
                  <LoadingSpinner />
                </div>
              ) : thread?.messages && thread.messages.length > 0 ? (
                thread.messages.map((m) => {
                  const isOut = m.direction === 'outbound'
                  return (
                    <motion.div
                      key={m.id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2 }}
                      className={cn('flex', isOut ? 'justify-end' : 'justify-start')}
                    >
                      <div
                        className={cn(
                          'max-w-xs md:max-w-md rounded-2xl px-4 py-3 text-sm',
                          isOut
                            ? 'bg-accent-blue text-white rounded-br-sm shadow-glow-blue'
                            : 'bg-glass-medium text-text-primary rounded-bl-sm border border-border-subtle',
                        )}
                      >
                        <p className="leading-relaxed">{m.body}</p>
                        <p className={cn('text-[10px] mt-1.5', isOut ? 'text-white/60' : 'text-text-muted')}>
                          {new Date(m.sentAt).toLocaleTimeString('en-GB', {
                            hour: '2-digit', minute: '2-digit',
                          })}
                        </p>
                      </div>
                    </motion.div>
                  )
                })
              ) : (
                <p className="text-center text-sm text-text-muted py-8">No messages yet</p>
              )}
            </div>

            {/* Reply box */}
            <div className="p-3 border-t border-border-subtle shrink-0">
              <div className="flex gap-2 items-end">
                <textarea
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendReply() }}
                  placeholder="Write a reply… (⌘+Enter to send)"
                  rows={2}
                  className={cn(
                    'flex-1 resize-none px-3.5 py-2.5 rounded-xl text-sm text-text-primary placeholder:text-text-muted',
                    'bg-glass-subtle border border-border-subtle',
                    'focus:outline-none focus:border-border-active focus:ring-2 focus:ring-accent-blue/20',
                    'transition-all duration-150',
                  )}
                />
                <button
                  onClick={sendReply}
                  disabled={!replyBody.trim() || sending}
                  className={cn(
                    'w-11 h-11 flex items-center justify-center rounded-xl',
                    'bg-accent-blue text-white shadow-glow-blue hover:brightness-110',
                    'disabled:opacity-40 disabled:pointer-events-none',
                    'transition-[filter] duration-150 shrink-0',
                  )}
                >
                  {sending ? (
                    <LoadingSpinner size="sm" className="!border-white/30 !border-t-white" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
          </Card>
        ) : (
          <Card className="flex-1 hidden md:flex">
            <EmptyState
              icon={<MessageSquare className="w-6 h-6" />}
              title="Select a conversation"
              message="Pick a thread from the list to read and reply."
            />
          </Card>
        )}
      </div>
    </div>
  )
}
