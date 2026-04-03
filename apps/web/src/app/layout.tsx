import type { Metadata } from 'next'
import './globals.css'
import { Navbar } from '@/components/ui/Navbar'
import { Toaster } from '@/components/ui/Toaster'

// System font used when Google Fonts is unavailable (offline/dev environment)
const inter = { variable: '--font-inter', className: 'font-sans' }

export const metadata: Metadata = {
  title: {
    template: '%s | CARDEX',
    default: 'CARDEX — Pan-European Used Car Intelligence',
  },
  description:
    'Search, compare and analyse used cars across Germany, Spain, France, Netherlands, Belgium and Switzerland. Free VIN history. Real-time market intelligence.',
  openGraph: {
    siteName: 'CARDEX',
    type: 'website',
    locale: 'en_EU',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans bg-surface text-white antialiased`}>
        <Navbar />
        <main className="min-h-screen">{children}</main>
        <Toaster />
      </body>
    </html>
  )
}
