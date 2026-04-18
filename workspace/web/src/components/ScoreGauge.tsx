import React from 'react'

interface ScoreGaugeProps {
  score: number   // 0-100
  size?: number   // SVG width (height is ~55% of width)
  label?: string
}

// Semicircular gauge rendered in pure SVG.
// Arc spans 180° (left to right over the top).
export default function ScoreGauge({ score, size = 180, label = 'Consistencia' }: ScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score))
  const cx = size / 2
  const cy = size * 0.56   // center slightly below midpoint for label space
  const r = size * 0.40

  // Semicircle arc path from (cx-r, cy) over the top to (cx+r, cy)
  const bgPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`

  // Arc length for a semicircle = π * r
  const arcLen = Math.PI * r
  const dashOffset = arcLen * (1 - clamped / 100)

  // Color based on score
  const color =
    clamped >= 80 ? '#22c55e'   // green-500
    : clamped >= 50 ? '#eab308' // yellow-500
    : '#ef4444'                  // red-500

  const strokeWidth = size * 0.10

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={size}
        height={Math.round(cy + strokeWidth / 2 + 4)}
        viewBox={`0 0 ${size} ${Math.round(cy + strokeWidth / 2 + 4)}`}
        aria-label={`${label}: ${clamped} de 100`}
        role="img"
      >
        {/* Background track */}
        <path
          d={bgPath}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          className="dark:stroke-gray-700"
        />
        {/* Filled arc */}
        <path
          d={bgPath}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={arcLen}
          strokeDashoffset={dashOffset}
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
        />
        {/* Score number */}
        <text
          x={cx}
          y={cy - r * 0.12}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size * 0.18}
          fontWeight="700"
          fill={color}
          style={{ fontFamily: 'inherit' }}
        >
          {clamped}
        </text>
        {/* /100 subscript */}
        <text
          x={cx}
          y={cy + r * 0.12}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size * 0.09}
          fill="#9ca3af"
          style={{ fontFamily: 'inherit' }}
        >
          /100
        </text>
        {/* Min / Max labels */}
        <text x={cx - r + strokeWidth / 2} y={cy + strokeWidth / 2 + 10} textAnchor="middle" fontSize={size * 0.075} fill="#9ca3af">0</text>
        <text x={cx + r - strokeWidth / 2} y={cy + strokeWidth / 2 + 10} textAnchor="middle" fontSize={size * 0.075} fill="#9ca3af">100</text>
      </svg>
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 -mt-1">{label}</p>
    </div>
  )
}
