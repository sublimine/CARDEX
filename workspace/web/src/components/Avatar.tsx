import { motion } from 'framer-motion'
import { cn } from '../lib/cn'

interface AvatarProps {
  name: string
  src?: string
  size?: 'xs' | 'sm' | 'md' | 'lg'
  status?: 'online' | 'away' | 'offline'
  className?: string
}

const sizeMap = {
  xs: { wrapper: 'w-6 h-6',   text: 'text-[10px]', dot: 'w-1.5 h-1.5' },
  sm: { wrapper: 'w-8 h-8',   text: 'text-xs',     dot: 'w-2 h-2' },
  md: { wrapper: 'w-9 h-9',   text: 'text-sm',     dot: 'w-2 h-2' },
  lg: { wrapper: 'w-11 h-11', text: 'text-base',   dot: 'w-2.5 h-2.5' },
}

const gradients = [
  'from-blue-500 to-violet-600',
  'from-emerald-500 to-teal-600',
  'from-amber-500 to-orange-600',
  'from-rose-500 to-pink-600',
  'from-cyan-500 to-blue-600',
  'from-violet-500 to-purple-600',
]

const statusDot: Record<NonNullable<AvatarProps['status']>, string> = {
  online:  'bg-emerald-400',
  away:    'bg-amber-400',
  offline: 'bg-text-muted',
}

function colorIndex(name: string) {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return Math.abs(h) % gradients.length
}

function initials(name: string) {
  return name.split(' ').slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '').join('')
}

export default function Avatar({ name, src, size = 'md', status, className }: AvatarProps) {
  const s = sizeMap[size]

  return (
    <motion.span
      whileHover={{ scale: 1.05 }}
      transition={{ type: 'spring', stiffness: 400, damping: 20 }}
      className={cn('relative inline-flex shrink-0', s.wrapper, className)}
    >
      {src ? (
        <img
          src={src}
          alt={name}
          className="w-full h-full rounded-full object-cover"
        />
      ) : (
        <span
          className={cn(
            'w-full h-full rounded-full flex items-center justify-center font-semibold text-white bg-gradient-to-br',
            gradients[colorIndex(name)],
            s.text
          )}
          aria-label={name}
        >
          {initials(name)}
        </span>
      )}
      {status && (
        <span
          className={cn(
            'absolute bottom-0 right-0 rounded-full ring-2 ring-bg-primary',
            s.dot,
            statusDot[status]
          )}
        />
      )}
    </motion.span>
  )
}
