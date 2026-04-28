import React, { useId } from 'react'

interface ScoreGaugeProps {
  score: number
  size?: number
  label?: string
}

export default function ScoreGauge({ score, size = 180, label = 'Consistencia' }: ScoreGaugeProps) {
  const gradId = useId()
  const clamped = Math.max(0, Math.min(100, score))
  const cx = size / 2
  const cy = size * 0.56
  const r  = size * 0.40

  const arcLen    = Math.PI * r
  const dashOffset = arcLen * (1 - clamped / 100)
  const sw        = size * 0.10

  const color =
    clamped >= 80 ? 'var(--color-emerald)'
    : clamped >= 50 ? 'var(--color-amber)'
    : 'var(--color-rose)'

  const bgPath  = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`
  const viewH   = Math.round(cy + sw / 2 + 4)

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={size}
        height={viewH}
        viewBox={`0 0 ${size} ${viewH}`}
        aria-label={`${label}: ${clamped} de 100`}
        role="img"
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor={color} stopOpacity="0.4" />
            <stop offset="100%" stopColor={color} stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* Track */}
        <path d={bgPath} fill="none" stroke="var(--glass-strong)" strokeWidth={sw} strokeLinecap="round" />

        {/* Filled arc */}
        <path
          d={bgPath}
          fill="none"
          stroke={`url(#${gradId})`}
          strokeWidth={sw}
          strokeLinecap="round"
          strokeDasharray={arcLen}
          strokeDashoffset={dashOffset}
          style={{ transition: 'stroke-dashoffset 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
        />

        {/* Score */}
        <text
          x={cx} y={cy - r * 0.12}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={size * 0.18} fontWeight="700" fill={color}
          fontFamily="inherit"
        >
          {clamped}
        </text>
        <text
          x={cx} y={cy + r * 0.14}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={size * 0.09} fill="var(--text-muted)"
          fontFamily="inherit"
        >
          /100
        </text>

        {/* Min/Max labels */}
        <text x={cx - r + sw / 2} y={viewH - 2} textAnchor="middle" fontSize={size * 0.07} fill="var(--text-muted)">0</text>
        <text x={cx + r - sw / 2} y={viewH - 2} textAnchor="middle" fontSize={size * 0.07} fill="var(--text-muted)">100</text>
      </svg>
      <p className="text-xs font-medium text-text-muted -mt-1">{label}</p>
    </div>
  )
}
