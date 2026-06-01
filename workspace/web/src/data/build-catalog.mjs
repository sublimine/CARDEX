// Script: merge .gen/*.json → catalog.ts
import { readFileSync, writeFileSync, readdirSync } from 'fs'
import { join } from 'path'

const GEN = new URL('.gen/', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')
const OUT = new URL('catalog.ts', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')

const G = 'https://www.google.com/s2/favicons?domain='
const SI = 'https://cdn.simpleicons.org/'
const WK = 'https://upload.wikimedia.org/wikipedia/commons/thumb/'
const gz = '&sz=128'

const LOGO_MAP = {
  // ── German ──────────────────────────────────────────────────────────────
  'Volkswagen':    { color: '#1b4ca3', logo: SI+'volkswagen/ffffff' },
  'BMW':           { color: '#1c69d4', logo: SI+'bmw/ffffff' },
  'Mercedes':      { color: '#8a8a8a', logo: WK+'9/90/Mercedes-Logo.svg/100px-Mercedes-Logo.svg.png' },
  'Mercedes-Benz': { color: '#8a8a8a', logo: WK+'9/90/Mercedes-Logo.svg/100px-Mercedes-Logo.svg.png' },
  'Audi':          { color: '#bb0a21', logo: SI+'audi/ffffff' },
  'Porsche':       { color: '#c9002b', logo: SI+'porsche/ffffff' },
  'Opel':          { color: '#f0be00', logo: SI+'opel/ffffff' },
  'Smart':         { color: '#1cb5e0', logo: G+'smart.com'+gz },
  'Alpina':        { color: '#00408a', logo: G+'alpina-automobiles.com'+gz },
  'Brabus':        { color: '#1a1a1a', logo: G+'brabus.com'+gz },
  'Wiesmann':      { color: '#c9002b', logo: G+'wiesmann.com'+gz },
  // ── French ──────────────────────────────────────────────────────────────
  'Peugeot':       { color: '#0099d6', logo: SI+'peugeot/ffffff' },
  'Renault':       { color: '#efdf00', logo: SI+'renault/ffffff' },
  'Citroën':       { color: '#ed1d24', logo: SI+'citroen/ffffff' },
  'Citroen':       { color: '#ed1d24', logo: SI+'citroen/ffffff' },
  'DS Automobiles':{ color: '#2a2a5a', logo: G+'dsautomobiles.com'+gz },
  'DS':            { color: '#2a2a5a', logo: G+'dsautomobiles.com'+gz },
  'Alpine':        { color: '#0055a4', logo: G+'alpinecar.com'+gz },
  'Dacia':         { color: '#1d5fa8', logo: SI+'dacia/ffffff' },
  'Bugatti':       { color: '#9b0000', logo: G+'bugatti.com'+gz },
  // ── Italian ─────────────────────────────────────────────────────────────
  'Fiat':          { color: '#8b1e3f', logo: SI+'fiat/ffffff' },
  'Alfa Romeo':    { color: '#a50024', logo: SI+'alfaromeo/ffffff' },
  'Abarth':        { color: '#cc0000', logo: G+'abarth.com'+gz },
  'Ferrari':       { color: '#cc0000', logo: SI+'ferrari/ffffff' },
  'Lamborghini':   { color: '#d4a017', logo: SI+'lamborghini/ffffff' },
  'Maserati':      { color: '#1e3a8a', logo: SI+'maserati/ffffff' },
  'Lancia':        { color: '#002f6c', logo: G+'lancia.com'+gz },
  'Pagani':        { color: '#1a1a1a', logo: G+'pagani.com'+gz },
  // ── Japanese ────────────────────────────────────────────────────────────
  'Toyota':        { color: '#eb0a1e', logo: SI+'toyota/ffffff' },
  'Honda':         { color: '#cc0000', logo: SI+'honda/ffffff' },
  'Nissan':        { color: '#c71444', logo: SI+'nissan/ffffff' },
  'Mazda':         { color: '#910a2a', logo: SI+'mazda/ffffff' },
  'Subaru':        { color: '#1a4aa6', logo: SI+'subaru/ffffff' },
  'Mitsubishi':    { color: '#cc0000', logo: SI+'mitsubishi/ffffff' },
  'Suzuki':        { color: '#1a1a6e', logo: SI+'suzuki/ffffff' },
  'Lexus':         { color: '#1a1a1a', logo: SI+'lexus/ffffff' },
  // ── Korean ──────────────────────────────────────────────────────────────
  'Hyundai':       { color: '#002c5f', logo: SI+'hyundai/ffffff' },
  'Kia':           { color: '#05141f', logo: SI+'kia/ffffff' },
  'Genesis':       { color: '#1a1a1a', logo: G+'genesis.com'+gz },
  // ── British ─────────────────────────────────────────────────────────────
  'Land Rover':    { color: '#005a2b', logo: G+'landrover.com'+gz },
  'Jaguar':        { color: '#1a1a1a', logo: G+'jaguar.com'+gz },
  'Aston Martin':  { color: '#004f2d', logo: G+'astonmartin.com'+gz },
  'Bentley':       { color: '#4b5320', logo: SI+'bentley/ffffff' },
  'McLaren':       { color: '#ff8000', logo: G+'mclaren.com'+gz },
  'Rolls-Royce':   { color: '#1a1a2e', logo: G+'rolls-roycemotorcars.com'+gz },
  'Lotus':         { color: '#005c2b', logo: G+'lotuscars.com'+gz },
  'INEOS':         { color: '#1a1a1a', logo: G+'ineosgrenadier.com'+gz },
  'Caterham':      { color: '#cc0000', logo: G+'caterham.com'+gz },
  'Morgan':        { color: '#1a4040', logo: G+'morgan-motor.co.uk'+gz },
  'TVR':           { color: '#1a1a8c', logo: G+'tvr.com'+gz },
  // ── Nordic ──────────────────────────────────────────────────────────────
  'Volvo':         { color: '#003057', logo: SI+'volvo/ffffff' },
  'Polestar':      { color: '#0a0a0a', logo: SI+'polestar/ffffff' },
  'Saab':          { color: '#1a3a6c', logo: G+'saab.com'+gz },
  'Koenigsegg':    { color: '#1a1a1a', logo: G+'koenigsegg.com'+gz },
  // ── Spanish ─────────────────────────────────────────────────────────────
  'SEAT':          { color: '#cc1729', logo: SI+'seat/ffffff' },
  'Seat':          { color: '#cc1729', logo: SI+'seat/ffffff' },
  'Cupra':         { color: '#c8aa61', logo: G+'cupraofficial.com'+gz },
  // ── Czech ───────────────────────────────────────────────────────────────
  'Skoda':         { color: '#4ba82e', logo: SI+'skoda/ffffff' },
  'Škoda':         { color: '#4ba82e', logo: SI+'skoda/ffffff' },
  // ── American ────────────────────────────────────────────────────────────
  'Ford':          { color: '#003476', logo: SI+'ford/ffffff' },
  'Jeep':          { color: '#1a3a1a', logo: SI+'jeep/ffffff' },
  'Dodge':         { color: '#1a1a6e', logo: G+'dodge.com'+gz },
  'Chrysler':      { color: '#003366', logo: G+'chrysler.com'+gz },
  'Cadillac':      { color: '#1a1a2e', logo: G+'cadillac.com'+gz },
  'Chevrolet':     { color: '#cc9900', logo: SI+'chevrolet/ffffff' },
  // ── EV / Chinese ────────────────────────────────────────────────────────
  'Tesla':         { color: '#cc0000', logo: SI+'tesla/ffffff' },
  'BYD':           { color: '#e60012', logo: G+'byd.com'+gz },
  'NIO':           { color: '#00c0ff', logo: G+'nio.com'+gz },
  'MG':            { color: '#b22222', logo: G+'mgmotor.co.uk'+gz },
  'Xpeng':         { color: '#1dc0e6', logo: G+'xpeng.com'+gz },
  'Lynk & Co':     { color: '#009944', logo: G+'lynkco.com'+gz },
  'Lynk&Co':       { color: '#009944', logo: G+'lynkco.com'+gz },
  'GWM / Ora':     { color: '#1a1a6e', logo: G+'gwm.com'+gz },
  'GWM':           { color: '#1a1a6e', logo: G+'gwm.com'+gz },
  'Ora':           { color: '#1a1a6e', logo: G+'gwm.com'+gz },
  'KG Mobility':   { color: '#1a5276', logo: G+'kg-mobility.com'+gz },
  'SsangYong':     { color: '#1a5276', logo: G+'kg-mobility.com'+gz },
  'Maxus':         { color: '#c0392b', logo: G+'maxus.global'+gz },
  'Omoda':         { color: '#e74c3c', logo: G+'omoda.com'+gz },
  'Leapmotor':     { color: '#2ecc71', logo: G+'leapmotor.com'+gz },
  'Zeekr':         { color: '#1a1aff', logo: G+'zeekrlife.com'+gz },
  'Aiways':        { color: '#0099cc', logo: G+'aiways.com'+gz },
  'JAECOO':        { color: '#1a3a6e', logo: G+'jaecoo.com'+gz },
  'Voyah':         { color: '#1a1a4a', logo: G+'voyah.com'+gz },
  'Hongqi':        { color: '#cc0000', logo: G+'hongqi.com'+gz },
  'Deepal':        { color: '#0055cc', logo: G+'deepal.com'+gz },
  'Neta':          { color: '#00aacc', logo: G+'neta.auto'+gz },
  // ── Other ───────────────────────────────────────────────────────────────
  'MINI':          { color: '#1f1f1f', logo: SI+'mini/ffffff' },
  'Mini':          { color: '#1f1f1f', logo: SI+'mini/ffffff' },
  'Infiniti':      { color: '#2a2a2a', logo: G+'infiniti.com'+gz },
  'Isuzu':         { color: '#1a1a8c', logo: G+'isuzu.com'+gz },
  'Rimac':         { color: '#cc0000', logo: G+'rimac-automobili.com'+gz },
  'Microlino':     { color: '#ff6600', logo: G+'microlino-car.com'+gz },
  'Brabus':        { color: '#1a1a1a', logo: G+'brabus.com'+gz },
  'Wiesmann':      { color: '#c9002b', logo: G+'wiesmann.com'+gz },
  'Caterham':      { color: '#cc0000', logo: G+'caterham.com'+gz },
  'Morgan':        { color: '#1a4040', logo: G+'morgan-motor.co.uk'+gz },
  'Pagani':        { color: '#1a1a1a', logo: G+'pagani.com'+gz },
  'Bugatti':       { color: '#9b0000', logo: G+'bugatti.com'+gz },
  'Koenigsegg':    { color: '#1a1a1a', logo: G+'koenigsegg.com'+gz },
}

const ORDER = [
  // German
  'Volkswagen','BMW','Mercedes','Audi','Porsche','Opel','Smart','MINI','Alpina','Brabus','Wiesmann',
  // French
  'Peugeot','Renault','Citroën','DS Automobiles','Alpine','Dacia','Bugatti',
  // Italian
  'Fiat','Alfa Romeo','Abarth','Ferrari','Lamborghini','Maserati','Lancia','Pagani',
  // Japanese
  'Toyota','Honda','Nissan','Mazda','Subaru','Mitsubishi','Suzuki','Lexus',
  // Korean
  'Hyundai','Kia','Genesis',
  // British
  'Land Rover','Jaguar','Aston Martin','Bentley','McLaren','Rolls-Royce','Lotus','INEOS','Caterham','Morgan','TVR',
  // Nordic
  'Volvo','Polestar','Saab','Koenigsegg',
  // Spanish
  'SEAT','Cupra',
  // Czech
  'Skoda',
  // American
  'Ford','Jeep','Dodge','Chrysler','Cadillac','Chevrolet',
  // EV/Chinese
  'Tesla','BYD','NIO','MG','Xpeng','Lynk & Co','GWM / Ora','KG Mobility','Zeekr','Aiways','JAECOO','Voyah','Hongqi','Deepal','Neta','Maxus','Omoda','Leapmotor',
  // Croatian/Other EV
  'Rimac','Microlino',
  // Others
  'Infiniti','Isuzu',
]

// Read + parse all JSON files
const files = readdirSync(GEN).filter(f => f.endsWith('.json'))
const allBrands = []
const seen = new Set()

for (const file of files) {
  const raw = readFileSync(join(GEN, file), 'utf8')
  let data
  try {
    data = JSON.parse(raw)
  } catch(e) {
    console.error(`Parse error in ${file}:`, e.message)
    continue
  }
  const brands = data.brands || []
  for (const b of brands) {
    // Normalize Mercedes-Benz → Mercedes
    if (b.name === 'Mercedes-Benz') b.name = 'Mercedes'
    if (b.name === 'Citroën' || b.name === 'Citroen') b.name = 'Citroën'
    if (b.name === 'Škoda') b.name = 'Skoda'
    if (b.name === 'Lynk&Co' || b.name === 'Lynk & Co') b.name = 'Lynk & Co'

    if (seen.has(b.name)) {
      // Merge models instead of duplicate
      const existing = allBrands.find(x => x.name === b.name)
      if (existing) {
        const existingNames = new Set(existing.models.map(m => m.name))
        for (const m of (b.models || [])) {
          if (!existingNames.has(m.name)) {
            existing.models.push(m)
            existingNames.add(m.name)
          }
        }
      }
      continue
    }
    seen.add(b.name)
    allBrands.push(b)
  }
}

// Sort by ORDER array
allBrands.sort((a, b) => {
  const ia = ORDER.indexOf(a.name)
  const ib = ORDER.indexOf(b.name)
  if (ia === -1 && ib === -1) return a.name.localeCompare(b.name)
  if (ia === -1) return 1
  if (ib === -1) return -1
  return ia - ib
})

// Generate TypeScript
function esc(s) { return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'") }

let ts = `// Auto-generated — exhaustive EU car catalog — do not edit manually
export interface Model { name: string; submodels: string[] }
export interface Brand { name: string; logo: string; color: string; models: Model[] }

export const BRANDS: Brand[] = [\n`

for (const b of allBrands) {
  const meta = LOGO_MAP[b.name] || { color: '#1a1a1a', logo: '' }
  ts += `  {\n`
  ts += `    name: '${esc(b.name)}',\n`
  ts += `    color: '${meta.color}',\n`
  ts += `    logo: '${esc(meta.logo)}',\n`
  ts += `    models: [\n`
  for (const m of (b.models || [])) {
    const subs = (m.submodels || []).map(s => `'${esc(s)}'`).join(', ')
    ts += `      { name: '${esc(m.name)}', submodels: [${subs}] },\n`
  }
  ts += `    ],\n`
  ts += `  },\n`
}

ts += `]\n`

writeFileSync(OUT, ts, 'utf8')

const totalModels = allBrands.reduce((acc, b) => acc + (b.models||[]).length, 0)
const totalSubs = allBrands.reduce((acc, b) => acc + (b.models||[]).reduce((a, m) => a + (m.submodels||[]).length, 0), 0)
console.log(`✓ catalog.ts written`)
console.log(`  Brands: ${allBrands.length}`)
console.log(`  Models: ${totalModels}`)
console.log(`  Submodels: ${totalSubs}`)
console.log(`  Lines: ~${ts.split('\n').length}`)
