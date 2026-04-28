/**
 * Re-exports class-variance-authority for building component variant systems.
 *
 * Usage:
 *   import { cva, type VariantProps } from '@/lib/variants'
 *   const button = cva('base-classes', { variants: { size: { sm: '...', lg: '...' } } })
 */
export { cva, type VariantProps } from 'class-variance-authority'
