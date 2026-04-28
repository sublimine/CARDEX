import { useCallback, useState } from 'react'
import { api } from '../api/client'
import { useApi } from './useApi'
import type { Conversation, Message } from '../types'

interface ConversationList {
  conversations: Conversation[]
  total: number
}

interface ConvWithMessages {
  conversation: Conversation
  messages: Message[]
}

export function useInbox(status = '') {
  const query = status ? `?status=${status}` : ''
  return useApi<ConversationList>(`/inbox${query}`, [query])
}

export function useConversation(id: string) {
  return useApi<ConvWithMessages>(`/inbox/${id}`, [id])
}

export function useInboxMutations() {
  const [loading, setLoading] = useState(false)

  const reply = useCallback(async (id: string, body: string, templateId?: string) => {
    setLoading(true)
    try {
      return await api.post<Message>(`/inbox/${id}/reply`, {
        body,
        template_id: templateId,
        send_via: 'email',
      })
    } finally {
      setLoading(false)
    }
  }, [])

  const patch = useCallback(async (id: string, data: { status?: string; unread?: boolean }) => {
    setLoading(true)
    try {
      return await api.patch<Conversation>(`/inbox/${id}`, data)
    } finally {
      setLoading(false)
    }
  }, [])

  return { reply, patch, loading }
}
