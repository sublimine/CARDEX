import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { cn } from '../lib/cn'

const ROUTE_LABELS: Record<string, string> = {
  vehicles: 'Vehicles',
  kanban: 'Kanban',
  contacts: 'Contacts',
  deals: 'Deals',
  inbox: 'Inbox',
  calendar: 'Calendar',
  finance: 'Finance',
  check: 'VIN Check',
  settings: 'Settings',
}

function labelFor(segment: string) {
  return ROUTE_LABELS[segment] ?? segment.charAt(0).toUpperCase() + segment.slice(1)
}

export default function Breadcrumb() {
  const location = useLocation()
  const segments = location.pathname.split('/').filter(Boolean)

  if (segments.length === 0) {
    return (
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5">
        <Home className="w-3.5 h-3.5 text-text-muted" />
        <span className="text-sm font-medium text-text-primary">Dashboard</span>
      </nav>
    )
  }

  const crumbs = segments.map((seg, i) => ({
    label: labelFor(seg),
    to: '/' + segments.slice(0, i + 1).join('/'),
  }))

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm min-w-0">
      <Link
        to="/"
        className="text-text-muted hover:text-text-secondary transition-colors duration-150 flex-shrink-0"
      >
        <Home className="w-3.5 h-3.5" />
      </Link>

      {crumbs.map((crumb, i) => (
        <React.Fragment key={crumb.to}>
          <ChevronRight className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
          {i === crumbs.length - 1 ? (
            <span className={cn('font-medium text-text-primary truncate', 'max-w-[160px]')}>
              {crumb.label}
            </span>
          ) : (
            <Link
              to={crumb.to}
              className="text-text-secondary hover:text-text-primary transition-colors duration-150 flex-shrink-0"
            >
              {crumb.label}
            </Link>
          )}
        </React.Fragment>
      ))}
    </nav>
  )
}
