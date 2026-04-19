import forms from '@tailwindcss/forms'
import typography from '@tailwindcss/typography'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',

  theme: {
    extend: {
      // ── Colour palette ───────────────────────────────────────────────────────
      colors: {
        // Legacy brand tokens (kept for backward compat with existing components)
        brand: {
          50:  '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          900: '#1e3a8a',
        },

        // Design-system tokens — resolved via CSS custom properties at runtime.
        // Using rgb(var(--*-ch)) format so that Tailwind opacity modifiers work
        // correctly (bg-bg-surface/70, ring-bg-surface/30, etc.).
        bg: {
          primary:  'rgb(var(--bg-primary-ch))',
          surface:  'rgb(var(--bg-surface-ch))',
          elevated: 'rgb(var(--bg-elevated-ch))',
          overlay:  'rgb(var(--bg-overlay-ch))',
        },
        accent: {
          // rgb(var(--color-*-ch)) lets Tailwind opacity modifiers work correctly
          // (bg-accent-blue/20, ring-accent-blue/50, etc.) — plain var(--color) does not.
          blue:    'rgb(var(--color-blue-ch))',
          amber:   'rgb(var(--color-amber-ch))',
          emerald: 'rgb(var(--color-emerald-ch))',
          rose:    'rgb(var(--color-rose-ch))',
        },
        text: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
        },
        glass: {
          subtle: 'var(--glass-subtle)',
          medium: 'var(--glass-medium)',
          strong: 'var(--glass-strong)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          active: 'var(--border-active)',
        },
      },

      // ── Typography ───────────────────────────────────────────────────────────
      fontFamily: {
        sans: ['Inter Variable', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },

      // ── Border radius (CSS var–backed) ───────────────────────────────────────
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },

      // ── Elevation shadows ────────────────────────────────────────────────────
      boxShadow: {
        'elevation-1': 'var(--shadow-1)',
        'elevation-2': 'var(--shadow-2)',
        'elevation-3': 'var(--shadow-3)',
        'elevation-4': 'var(--shadow-4)',
        'glow-blue':   'var(--shadow-glow-blue)',
        'glow-amber':  'var(--shadow-glow-amber)',
      },

      // ── Backdrop blur extras ─────────────────────────────────────────────────
      backdropBlur: {
        xs: '2px',
      },

      // ── Animation keyframes ──────────────────────────────────────────────────
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        'slide-up': {
          from: { transform: 'translateY(8px)', opacity: '0' },
          to:   { transform: 'translateY(0)',   opacity: '1' },
        },
        'slide-down': {
          from: { transform: 'translateY(-8px)', opacity: '0' },
          to:   { transform: 'translateY(0)',    opacity: '1' },
        },
        'scale-in': {
          from: { transform: 'scale(0.95)', opacity: '0' },
          to:   { transform: 'scale(1)',    opacity: '1' },
        },
        'glow-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0.4' },
        },
        // Preserve existing toast animation
        'slide-in-from-right': {
          from: { transform: 'translateX(100%)', opacity: '0' },
          to:   { transform: 'translateX(0)',    opacity: '1' },
        },
        'shimmer': {
          from: { transform: 'translateX(-100%)' },
          to:   { transform: 'translateX(200%)' },
        },
        'fade-out': {
          from: { opacity: '1' },
          to:   { opacity: '0' },
        },
      },

      // ── Animation shorthands ─────────────────────────────────────────────────
      animation: {
        'fade-in':    'fade-in 250ms ease both',
        'fade-out':   'fade-out 200ms ease both',
        'slide-up':   'slide-up 250ms ease both',
        'slide-down': 'slide-down 250ms ease both',
        'scale-in':   'scale-in 150ms ease both',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'shimmer':    'shimmer 1.5s infinite',
        // Alias used by existing Toast component
        'in': 'slide-in-from-right 200ms ease-out',
      },
    },
  },

  plugins: [
    // strategy:'class' prevents the forms plugin from globally resetting form
    // styles on existing components — opt-in via form-input / form-select etc.
    forms({ strategy: 'class' }),
    typography,
  ],
}
