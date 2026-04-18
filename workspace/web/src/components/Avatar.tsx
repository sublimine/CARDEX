import React from 'react'

interface AvatarProps {
  name: string
  src?: string
  size?: 'xs' | 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = { xs: 'w-6 h-6 text-xs', sm: 'w-8 h-8 text-sm', md: 'w-9 h-9 text-sm', lg: 'w-11 h-11 text-base' }

const hues = ['bg-violet-500', 'bg-blue-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-cyan-500']

function colorFor(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return hues[Math.abs(h) % hues.length]
}

function initials(name: string) {
  return name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

export default function Avatar({ name, src, size = 'md', className = '' }: AvatarProps) {
  if (src) {
    return (
      <img
        src={src}
        alt={name}
        className={`${sizes[size]} rounded-full object-cover shrink-0 ${className}`}
      />
    )
  }
  return (
    <span
      className={`${sizes[size]} ${colorFor(name)} rounded-full flex items-center justify-center text-white font-semibold shrink-0 ${className}`}
      aria-label={name}
    >
      {initials(name)}
    </span>
  )
}
