/** Formatting helpers shared across components */

export function formatPrice(eur: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(eur)
}

export function formatMileage(km: number): string {
  return new Intl.NumberFormat('de-DE').format(km) + ' km'
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('de-DE').format(n)
}

export const COUNTRY_FLAG: Record<string, string> = {
  DE: '🇩🇪', ES: '🇪🇸', FR: '🇫🇷', NL: '🇳🇱', BE: '🇧🇪', CH: '🇨🇭',
}

export const COUNTRY_NAME: Record<string, string> = {
  DE: 'Germany', ES: 'Spain', FR: 'France',
  NL: 'Netherlands', BE: 'Belgium', CH: 'Switzerland',
}

export const FUEL_LABEL: Record<string, string> = {
  PETROL: 'Petrol', DIESEL: 'Diesel', ELECTRIC: 'Electric',
  HYBRID_PETROL: 'Hybrid (Petrol)', HYBRID_DIESEL: 'Hybrid (Diesel)',
  LPG: 'LPG', CNG: 'CNG', HYDROGEN: 'Hydrogen', OTHER: 'Other',
}

export const SDI_COLOR: Record<string, string> = {
  STABLE: 'text-surface-muted',
  NEGOTIABLE: 'text-yellow-400',
  MOTIVATED_SELLER: 'text-orange-400',
  PANIC_SELLER: 'text-brand-400',
}
