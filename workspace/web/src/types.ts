export interface User {
  id: string
  email: string
  name: string
  tenantId: string
  role: string
}

export interface Vehicle {
  id: string
  tenantId: string
  externalId: string
  vin: string
  make: string
  model: string
  year: number
  status: 'listed' | 'inquiry' | 'sold' | 'withdrawn'
  price: number
  currency: string
  daysInStock: number
  margin: number
  thumbnailUrl?: string
  color?: string
  fuelType?: string
  transmission?: string
  mileageKm?: number
}

export interface Deal {
  id: string
  tenantId: string
  contactId: string
  vehicleId: string
  stage: 'lead' | 'contacted' | 'offer' | 'negotiation' | 'won' | 'lost'
  assigneeId?: string
  priority?: 'low' | 'medium' | 'high'
  createdAt: string
  updatedAt: string
  // enriched
  contactName?: string
  vehicleName?: string
  price?: number
}

export interface Contact {
  id: string
  tenantId: string
  name: string
  email: string
  phone: string
  createdAt: string
  updatedAt: string
  dealCount?: number
}

export interface Activity {
  id: string
  tenantId: string
  dealId: string
  type: 'inquiry' | 'reply' | 'reminder' | 'note' | 'visit' | 'call'
  body: string
  createdAt: string
}

export interface Conversation {
  id: string
  tenantId: string
  contactId: string
  vehicleId: string
  dealId: string
  sourcePlatform: string
  externalId: string
  subject: string
  status: 'open' | 'replied' | 'closed' | 'spam'
  unread: boolean
  lastMessageAt: string
  createdAt: string
  // enriched
  contactName?: string
  vehicleName?: string
  previewBody?: string
}

export interface Message {
  id: string
  conversationId: string
  direction: 'inbound' | 'outbound'
  senderName: string
  senderEmail: string
  body: string
  templateId?: string
  sentVia: string
  sentAt: string
  readAt?: string
}

export interface Template {
  id: string
  tenantId: string
  name: string
  language: string
  subject: string
  body: string
  isSystem: boolean
}

export interface KpiData {
  stockCount: number
  activeDeals: number
  monthMargin: number
  pendingAlerts: number
  marginHistory: { month: string; margin: number; revenue: number; cost: number }[]
  recentActivities: Activity[]
}

export interface FinanceRow {
  vehicleId: string
  vehicleName: string
  buyPrice: number
  sellPrice: number
  margin: number
  marginPct: number
  soldAt?: string
}
