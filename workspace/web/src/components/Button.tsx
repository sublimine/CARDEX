import { motion, type HTMLMotionProps } from 'framer-motion'
import { cn } from '../lib/cn'
import { cva, type VariantProps } from '../lib/variants'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 font-medium rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-blue/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary disabled:opacity-40 disabled:pointer-events-none select-none',
  {
    variants: {
      variant: {
        primary:   'bg-accent-blue text-white hover:brightness-110 shadow-glow-blue',
        secondary: 'glass text-text-primary hover:bg-glass-strong',
        ghost:     'text-text-secondary hover:text-text-primary hover:bg-glass-subtle',
        danger:    'bg-accent-rose text-white hover:brightness-110',
      },
      size: {
        sm: 'px-3 py-1.5 text-xs min-h-[32px]',
        md: 'px-4 py-2 text-sm min-h-[38px]',
        lg: 'px-5 py-2.5 text-sm min-h-[44px]',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
)

interface ButtonProps
  extends Omit<HTMLMotionProps<'button'>, 'children'>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
  icon?: React.ReactNode
  children?: React.ReactNode
}

export default function Button({
  variant,
  size,
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading
  return (
    <motion.button
      whileTap={{ scale: isDisabled ? 1 : 0.97 }}
      whileHover={{ scale: isDisabled ? 1 : 1.01 }}
      transition={{ type: 'spring', stiffness: 400, damping: 20 }}
      disabled={isDisabled}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading ? (
        <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin shrink-0" />
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children}
    </motion.button>
  )
}
