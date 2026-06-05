// Strips full-canvas background shapes (<rect>/<path>) from local logo SVGs.
// Such a background becomes a solid white SQUARE under the UI's
// filter: brightness(0) invert(1) — turning the logo into a blank box.
// Removing it lets the actual mark show as a clean white silhouette.
import { readdirSync, readFileSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const HERE = dirname(fileURLToPath(import.meta.url))
const DIR = join(HERE, '..', '..', 'public', 'logos')
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

let fixed = []
for (const f of readdirSync(DIR)) {
  if (!f.endsWith('.svg')) continue
  const p = join(DIR, f)
  let svg = readFileSync(p, 'utf8')
  const orig = svg

  const vb = svg.match(/viewBox\s*=\s*["']\s*0\s+0\s+([\d.]+)\s+([\d.]+)/i)
  let W = vb && vb[1], H = vb && vb[2]
  if (!W) { const w = svg.match(/\bwidth="([\d.]+)"/i), h = svg.match(/\bheight="([\d.]+)"/i); if (w && h) { W = w[1]; H = h[1] } }

  // 1) <rect> full canvas (100% or exact dims at origin)
  svg = svg.replace(/<rect\b[^>]*\b(?:width="100%"[^>]*height="100%"|height="100%"[^>]*width="100%")[^>]*\/?>/gi, '')
  if (W && H) {
    svg = svg.replace(new RegExp(`<rect\\b[^>]*\\bwidth="${esc(W)}"[^>]*\\bheight="${esc(H)}"[^>]*\\/?>`, 'gi'), '')
    // 2) <path> tracing the full canvas rectangle: M0 0h{W}v{H}... / M0 0H{W}V{H}...
    svg = svg.replace(new RegExp(`<path\\b[^>]*\\bd="M0[ ,]?0\\s*[hH]\\s*-?${esc(W)}\\s*[vV]\\s*-?${esc(H)}[^"]*"[^>]*\\/?>`, 'gi'), '')
    svg = svg.replace(new RegExp(`<path\\b[^>]*\\bd="M0[ ,]?0\\s*[vV]\\s*-?${esc(H)}\\s*[hH]\\s*-?${esc(W)}[^"]*"[^>]*\\/?>`, 'gi'), '')
    // 3) <path> as four explicit corners: M0 0 L{W} 0 L{W} {H} L0 {H} Z
    svg = svg.replace(new RegExp(`<path\\b[^>]*\\bd="M0[ ,]0[ ,L]+${esc(W)}[ ,]0[ ,L]+${esc(W)}[ ,]${esc(H)}[^"]*"[^>]*\\/?>`, 'gi'), '')
  }

  if (svg !== orig) { writeFileSync(p, svg, 'utf8'); fixed.push(f) }
}
console.log(`sanitized ${fixed.length} svg(s): ${fixed.join(', ') || '(none)'}`)
