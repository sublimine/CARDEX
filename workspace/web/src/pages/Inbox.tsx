import React, { useState } from 'react'
import { Send, MessageSquare, RefreshCw } from 'lucide-react'
import Card from '../components/Card'
import Avatar from '../components/Avatar'
import EmptyState from '../components/EmptyState'
import LoadingSpinner from '../components/LoadingSpinner'
import { Badge } from '../components/Badge'
import { useInbox, useConversation, useInboxMutations } from '../hooks/useInbox'
import { useToast } from '../components/Toast'
import type { Conversation } from '../types'

const MOCK_CONVS: Conversation[] = [
  { id: 'cv1', tenantId: 't', contactId: 'c1', vehicleId: 'v1', dealId: 'd1', sourcePlatform: 'mobile.de', externalId: 'ext1', subject: 'BMW 320d inquiry', status: 'open', unread: true,  lastMessageAt: '2026-04-18T10:15:00Z', createdAt: '2026-04-18T10:00:00Z', contactName: 'Maria Santos',  vehicleName: 'BMW 320d',     previewBody: 'Hello, I am interested in this vehicle…' },
  { id: 'cv2', tenantId: 't', contactId: 'c2', vehicleId: 'v2', dealId: 'd2', sourcePlatform: 'autoscout24', externalId: 'ext2', subject: 'Audi A4 question', status: 'replied', unread: false, lastMessageAt: '2026-04-17T14:30:00Z', createdAt: '2026-04-17T14:00:00Z', contactName: 'John Doe',      vehicleName: 'Audi A4',      previewBody: 'Is the service history available?' },
  { id: 'cv3', tenantId: 't', contactId: 'c3', vehicleId: 'v3', dealId: 'd3', sourcePlatform: 'mobile.de', externalId: 'ext3', subject: 'Mercedes C220', status: 'open', unread: true,  lastMessageAt: '2026-04-17T11:00:00Z', createdAt: '2026-04-17T10:00:00Z', contactName: 'Anna Weber',    vehicleName: 'Mercedes C220', previewBody: 'Can I arrange a test drive this week?' },
  { id: 'cv4', tenantId: 't', contactId: 'c4', vehicleId: 'v4', dealId: 'd4', sourcePlatform: 'manual',     externalId: 'ext4', subject: 'VW Golf 8',      status: 'closed', unread: false, lastMessageAt: '2026-04-16T09:00:00Z', createdAt: '2026-04-15T08:00:00Z', contactName: 'Peter Klein',   vehicleName: 'VW Golf 8',    previewBody: 'Thank you for your time.' },
]

const STATUS_COLOR: Record<string, 'green' | 'blue' | 'gray' | 'red'> = {
  open: 'blue', replied: 'green', closed: 'gray', spam: 'red',
}

function ConvItem({ conv, selected, onClick }: { conv: Conversation; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-start gap-3 px-4 py-3.5 text-left hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors border-b border-gray-100 dark:border-gray-700/50 ${
        selected ? 'bg-brand-50 dark:bg-brand-900/20' : ''
      }`}
    >
      <Avatar name={conv.contactName ?? '?'} size="sm" className="mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className={`text-sm font-medium truncate ${conv.unread ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400'}`}>
            {conv.contactName}
          </span>
          <span className="text-[10px] text-gray-400 shrink-0">
            {new Date(conv.lastMessageAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
          </span>
        </div>
        <p className={`text-xs truncate ${conv.unread ? 'font-semibold text-gray-800 dark:text-gray-200' : 'text-gray-400'}`}>
          {conv.subject}
        </p>
        <p className="text-xs text-gray-400 truncate mt-0.5">{conv.previewBody}</p>
        <div className="flex items-center gap-1.5 mt-1.5">
          <Badge color={STATUS_COLOR[conv.status] ?? 'gray'}>{conv.status}</Badge>
          <span className="text-[10px] text-gray-400">{conv.sourcePlatform}</span>
          {conv.unread && <span className="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />}
        </div>
      </div>
    </button>
  )
}

export default function Inbox() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [replyBody, setReplyBody] = useState('')

  const { data, loading, reload } = useInbox()
  const conversations = data?.conversations ?? MOCK_CONVS

  const { data: thread, loading: threadLoading } = useConversation(selectedId ?? '')
  const { reply, loading: sending } = useInboxMutations()
  const { success, error: toastErr } = useToast()

  const selected = conversations.find((c) => c.id === selectedId) ?? null

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

  const unreadCount = conversations.filter((c) => c.unread).length

  return (
    <div className="p-4 md:p-6 h-full flex flex-col max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Inbox</h1>
          {unreadCount > 0 && (
            <span className="px-2 py-0.5 bg-brand-600 text-white text-xs font-bold rounded-full">
              {unreadCount}
            </span>
          )}
        </div>
        <button
          onClick={reload}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0">
        {/* Conversation list */}
        <Card
          padding={false}
          className="md:w-80 md:max-w-xs shrink-0 overflow-y-auto"
        >
          {conversations.length === 0 ? (
            <EmptyState icon={<MessageSquare className="w-6 h-6" />} message="No conversations" />
          ) : (
            conversations.map((c) => (
              <ConvItem
                key={c.id}
                conv={c}
                selected={c.id === selectedId}
                onClick={() => setSelectedId(c.id)}
              />
            ))
          )}
        </Card>

        {/* Thread */}
        {selected ? (
          <Card padding={false} className="flex-1 flex flex-col min-h-0">
            {/* Header */}
            <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700 shrink-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{selected.subject}</p>
              <p className="text-xs text-gray-400">{selected.contactName} · {selected.vehicleName} · {selected.sourcePlatform}</p>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {threadLoading ? (
                <div className="flex justify-center py-8"><LoadingSpinner /></div>
              ) : thread?.messages && thread.messages.length > 0 ? (
                thread.messages.map((m) => (
                  <div
                    key={m.id}
                    className={`flex ${m.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-xs md:max-w-md rounded-2xl px-4 py-2.5 text-sm ${
                        m.direction === 'outbound'
                          ? 'bg-brand-600 text-white rounded-br-sm'
                          : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-bl-sm'
                      }`}
                    >
                      <p className="leading-relaxed">{m.body}</p>
                      <p className={`text-[10px] mt-1 ${m.direction === 'outbound' ? 'text-white/60' : 'text-gray-400'}`}>
                        {new Date(m.sentAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-center text-sm text-gray-400 py-4">No messages yet</p>
              )}
            </div>

            {/* Reply box */}
            <div className="p-3 border-t border-gray-100 dark:border-gray-700 shrink-0">
              <div className="flex gap-2 items-end">
                <textarea
                  value={replyBody}
                  onChange={(e) => setReplyBody(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendReply() }}
                  placeholder="Write a reply… (Cmd+Enter to send)"
                  rows={2}
                  className="flex-1 resize-none px-3.5 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
                />
                <button
                  onClick={sendReply}
                  disabled={!replyBody.trim() || sending}
                  className="p-3 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-xl transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
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
