// Bloomberg Terminal layout — no navbar, full dark, monospace
export default function ArbitrageLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "'JetBrains Mono', 'IBM Plex Mono', monospace",
        background: '#0a0a0a',
        minHeight: '100vh',
        color: '#cccccc',
      }}
    >
      {children}
    </div>
  )
}
