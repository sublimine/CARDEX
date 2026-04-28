import * as SwitchPrimitive from '@radix-ui/react-switch'
import React from 'react'
import { cn } from '../lib/cn'

interface SwitchProps {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
  label?: string
  description?: string
  id?: string
  className?: string
}

export function Switch({ checked, onCheckedChange, disabled, label, description, id, className }: SwitchProps) {
  const switchId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

  return (
    <div className={cn('flex items-center gap-3', className)}>
      <SwitchPrimitive.Root
        id={switchId}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent',
          'transition-colors duration-200 ease-in-out',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
          'disabled:opacity-40 disabled:cursor-not-allowed',
          'data-[state=checked]:bg-accent-blue data-[state=unchecked]:bg-glass-strong'
        )}
      >
        <SwitchPrimitive.Thumb
          className={cn(
            'pointer-events-none block h-5 w-5 rounded-full bg-white shadow-elevation-1',
            'transition-transform duration-200 ease-in-out',
            'data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0'
          )}
        />
      </SwitchPrimitive.Root>
      {(label || description) && (
        <div className="flex flex-col">
          {label && (
            <label
              htmlFor={switchId}
              className={cn('text-sm font-medium text-text-primary', !disabled && 'cursor-pointer')}
            >
              {label}
            </label>
          )}
          {description && (
            <p className="text-xs text-text-muted">{description}</p>
          )}
        </div>
      )}
    </div>
  )
}
