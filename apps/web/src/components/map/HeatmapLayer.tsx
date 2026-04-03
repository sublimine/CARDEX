'use client'

/**
 * deck.gl H3HexagonLayer heatmap — geographic density of car listings.
 * Each hexagon = H3 res-4 cell (~86km²). Color = listing density.
 * Hover tooltip shows count + avg price.
 */

import { useEffect, useRef, useState } from 'react'
import { DeckGL } from '@deck.gl/react'
import { H3HexagonLayer } from '@deck.gl/geo-layers'
import { Map } from 'react-map-gl/maplibre'
import type { HexPoint } from '@/lib/api'
import { formatPrice } from '@/lib/format'

// Free OSM-based tiles — no API key
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

const EUROPE_VIEW = {
  longitude: 10.0,
  latitude:  51.0,
  zoom:      4,
  pitch:     40,
  bearing:   0,
}

interface Props {
  hexes: HexPoint[]
  height?: number
}

interface TooltipInfo {
  x: number
  y: number
  hex: HexPoint
}

export function HeatmapLayer({ hexes, height = 500 }: Props) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null)
  const maxCount = hexes.reduce((m, h) => Math.max(m, h.count), 0)

  const layer = new H3HexagonLayer<HexPoint>({
    id: 'cardex-h3-heatmap',
    data: hexes,
    getHexagon: (d) => d.hex_id,
    getElevation: (d) => (d.count / maxCount) * 5000,
    getFillColor: (d) => {
      // Green gradient: low density = dark, high = bright brand green
      const t = d.count / maxCount
      return [
        Math.round(21 + t * 0),
        Math.round(80 + t * 101),
        Math.round(60 + t * 12),
        Math.round(80 + t * 175),
      ] as [number, number, number, number]
    },
    extruded: true,
    elevationScale: 1,
    wireframe: false,
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 60],
    onHover: (info) => {
      if (info.object) {
        setTooltip({ x: info.x, y: info.y, hex: info.object as HexPoint })
      } else {
        setTooltip(null)
      }
    },
    transitions: { getFillColor: 300, getElevation: 300 },
  })

  return (
    <div className="relative w-full rounded-xl overflow-hidden" style={{ height }}>
      <DeckGL
        initialViewState={EUROPE_VIEW}
        controller
        layers={[layer]}
        style={{ width: '100%', height: '100%' }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 rounded-lg border border-surface-border bg-surface-card/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
          style={{ left: tooltip.x + 12, top: tooltip.y - 32 }}
        >
          <p className="font-semibold text-white">{tooltip.hex.count.toLocaleString()} listings</p>
          <p className="text-surface-muted">Avg: {formatPrice(tooltip.hex.avg_price_eur)}</p>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-4 left-4 rounded-lg border border-surface-border bg-surface-card/90 px-3 py-2 text-xs backdrop-blur-sm">
        <p className="mb-1 font-medium text-white">Listing density</p>
        <div className="flex items-center gap-2">
          <div className="h-2 w-24 rounded" style={{
            background: 'linear-gradient(to right, rgba(21,80,60,0.5), rgba(21,181,112,1))'
          }} />
          <span className="text-surface-muted">Low → High</span>
        </div>
      </div>
    </div>
  )
}
