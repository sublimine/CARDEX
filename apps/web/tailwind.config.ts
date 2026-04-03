import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // CARDEX brand — dark financial terminal aesthetic
        brand: {
          50:  '#edfcf4',
          100: '#d3f8e3',
          200: '#aaf0cc',
          300: '#72e4ad',
          400: '#38cf89',
          500: '#15b570', // primary accent — TradingView green
          600: '#0a9159',
          700: '#097347',
          800: '#0a5b3a',
          900: '#094b31',
          950: '#042a1c',
        },
        surface: {
          DEFAULT: '#0d1117',  // page background — GitHub dark
          card:    '#161b22',  // card background
          border:  '#21262d',  // borders
          hover:   '#1c2128',  // hover state
          muted:   '#8b949e',  // muted text
        },
      },
      fontFamily: {
        sans: ['Inter var', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { transform: 'translateY(8px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
      },
    },
  },
  plugins: [],
}

export default config
