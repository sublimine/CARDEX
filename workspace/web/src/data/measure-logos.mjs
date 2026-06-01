// Measures the intrinsic aspect ratio (width/height) of every local logo file
// so BrandLogo can normalize all marks to the same OPTICAL size.
// Output: logo-ar.json  { "mercedes.png": 1.333, "lucid.svg": 15.875, ... }
import { readdirSync, readFileSync, writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const HERE = dirname(fileURLToPath(import.meta.url))
const DIR = join(HERE, '..', '..', 'public', 'logos')
const OUT = join(HERE, 'logo-ar.json')

function svgAR(txt) {
  const vb = txt.match(/viewBox\s*=\s*["']\s*[\d.+-]+\s+[\d.+-]+\s+([\d.+-]+)\s+([\d.+-]+)/i)
  if (vb) { const w = +vb[1], h = +vb[2]; if (w > 0 && h > 0) return w / h }
  const w = txt.match(/\bwidth\s*=\s*["']?([\d.]+)/i), h = txt.match(/\bheight\s*=\s*["']?([\d.]+)/i)
  if (w && h && +h[1] > 0) return +w[1] / +h[1]
  return null
}
function pngAR(buf) {
  if (buf.length < 24 || buf[0] !== 0x89) return null
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20)
  return h > 0 ? w / h : null
}
function webpAR(buf) {
  // VP8X / VP8 / VP8L minimal parse
  const tag = buf.slice(12, 16).toString('ascii')
  try {
    if (tag === 'VP8X') { const w = 1 + buf.readUIntLE(24, 3), h = 1 + buf.readUIntLE(27, 3); return w / h }
    if (tag === 'VP8 ') { const w = buf.readUInt16LE(26) & 0x3fff, h = buf.readUInt16LE(28) & 0x3fff; return h ? w / h : null }
  } catch {}
  return null
}

const out = {}
for (const f of readdirSync(DIR)) {
  const p = join(DIR, f)
  try {
    let ar = null
    if (f.endsWith('.svg')) ar = svgAR(readFileSync(p, 'utf8'))
    else if (f.endsWith('.png')) ar = pngAR(readFileSync(p))
    else if (f.endsWith('.webp')) ar = webpAR(readFileSync(p))
    if (ar && isFinite(ar)) out[f] = Math.round(ar * 1000) / 1000
  } catch {}
}
writeFileSync(OUT, JSON.stringify(out), 'utf8')
const vals = Object.values(out).sort((a, b) => a - b)
console.log(`logo-ar.json — ${vals.length} files, AR min ${vals[0]} / median ${vals[Math.floor(vals.length / 2)]} / max ${vals[vals.length - 1]}`)
