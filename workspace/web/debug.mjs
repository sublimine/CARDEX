import puppeteer from 'puppeteer'
import { writeFileSync } from 'fs'

const BASE = 'http://localhost:5173'
const EMAIL = 'salmankarrouch777@gmail.com'
const PASS  = 'Cardex2026!'

const logs    = []
const errors  = []
const netFail = []
const netReqs = []

function ts() { return new Date().toISOString() }

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
})
const page = await browser.newPage()

// ── Capture everything ────────────────────────────────────────────────────────
page.on('console', msg => {
  const entry = { time: ts(), type: msg.type(), text: msg.text() }
  logs.push(entry)
  if (msg.type() === 'error') errors.push(entry)
})

page.on('pageerror', err => {
  const entry = { time: ts(), type: 'pageerror', text: err.message, stack: err.stack }
  errors.push(entry)
  logs.push(entry)
})

page.on('requestfailed', req => {
  netFail.push({ time: ts(), url: req.url(), reason: req.failure()?.errorText })
})

page.on('request', req => {
  if (req.url().includes('localhost')) {
    netReqs.push({ time: ts(), method: req.method(), url: req.url() })
  }
})

page.on('response', async res => {
  if (res.url().includes('/api/') && !res.ok()) {
    let body = ''
    try { body = await res.text() } catch {}
    netFail.push({ time: ts(), url: res.url(), status: res.status(), body })
  }
})

// ── Step 1: Load login page ───────────────────────────────────────────────────
console.log('\n=== STEP 1: loading login page ===')
await page.goto(BASE, { waitUntil: 'networkidle0', timeout: 30000 })
await new Promise(r => setTimeout(r, 2000))

const ss1 = 'debug-login.png'
await page.screenshot({ path: ss1, fullPage: true })
console.log(`Screenshot saved: ${ss1}`)

const title1 = await page.title()
const url1   = page.url()
console.log(`URL: ${url1}  Title: ${title1}`)

const html1 = await page.evaluate(() => document.documentElement.outerHTML)
writeFileSync('debug-login.html', html1)

// ── Step 2: Fill login form ───────────────────────────────────────────────────
console.log('\n=== STEP 2: filling login form ===')

const emailSel = 'input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="correo" i]'
const passSel  = 'input[type="password"]'
const btnSel   = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Ingresar"), button:has-text("Login")'

const emailEl = await page.$(emailSel)
const passEl  = await page.$(passSel)
console.log(`Email field found: ${!!emailEl}`)
console.log(`Password field found: ${!!passEl}`)

// Dump all inputs on page
const inputs = await page.evaluate(() =>
  [...document.querySelectorAll('input')].map(i => ({
    type: i.type, name: i.name, placeholder: i.placeholder, id: i.id,
  }))
)
console.log('All inputs on page:', JSON.stringify(inputs, null, 2))

const buttons = await page.evaluate(() =>
  [...document.querySelectorAll('button')].map(b => ({
    type: b.type, text: b.textContent?.trim(), id: b.id,
  }))
)
console.log('All buttons on page:', JSON.stringify(buttons, null, 2))

if (!emailEl || !passEl) {
  console.error('ERROR: Could not find login form fields. Dumping body HTML.')
  const body = await page.evaluate(() => document.body.innerHTML)
  console.log('Body HTML (first 3000):', body.slice(0, 3000))
} else {
  await emailEl.click({ clickCount: 3 })
  await emailEl.type(EMAIL)
  await passEl.click({ clickCount: 3 })
  await passEl.type(PASS)
  console.log('Form filled.')

  // Click the submit button
  const btn = await page.$('button[type="submit"]')
           || await page.$x('//button[contains(text(),"Sign") or contains(text(),"Ingresar") or contains(text(),"Login") or contains(text(),"Entrar")]').then(r => r[0])

  if (btn) {
    console.log('Clicking submit button...')
    await btn.click()
  } else {
    console.log('No submit button found — pressing Enter')
    await passEl.press('Enter')
  }
}

// ── Step 3: Wait and observe ──────────────────────────────────────────────────
console.log('\n=== STEP 3: waiting 6s after login ===')
await new Promise(r => setTimeout(r, 6000))

const url2 = page.url()
console.log(`URL after login: ${url2}`)

const ss2 = 'debug-after-login.png'
await page.screenshot({ path: ss2, fullPage: true })
console.log(`Screenshot saved: ${ss2}`)

const html2 = await page.evaluate(() => document.documentElement.outerHTML)
writeFileSync('debug-after-login.html', html2)

// Check what's actually rendered
const bodyText = await page.evaluate(() => document.body.innerText)
const bodyBg   = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
const rootBg   = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--bg-primary'))
console.log(`Body background-color: ${bodyBg}`)
console.log(`CSS --bg-primary: ${rootBg}`)
console.log(`Body text (first 500): ${bodyText.slice(0, 500)}`)

// Check React root
const reactRoot = await page.evaluate(() => {
  const root = document.getElementById('root')
  return {
    children: root?.children.length,
    innerHTML: root?.innerHTML?.slice(0, 500),
  }
})
console.log('React root:', JSON.stringify(reactRoot, null, 2))

// ── Summary ───────────────────────────────────────────────────────────────────
console.log('\n=== CONSOLE LOGS (all) ===')
logs.forEach(l => console.log(`  [${l.type}] ${l.text}`))

console.log('\n=== JS ERRORS ===')
if (errors.length === 0) {
  console.log('  (none)')
} else {
  errors.forEach(e => {
    console.log(`  [${e.type}] ${e.text}`)
    if (e.stack) console.log('    stack:', e.stack.split('\n').slice(0, 5).join('\n    '))
  })
}

console.log('\n=== NETWORK FAILURES ===')
if (netFail.length === 0) {
  console.log('  (none)')
} else {
  netFail.forEach(f => console.log(`  ${f.method || ''} ${f.url} → ${f.status || f.reason} ${f.body || ''}`))
}

console.log('\n=== LOCAL NETWORK REQUESTS ===')
netReqs.slice(-30).forEach(r => console.log(`  ${r.method} ${r.url}`))

await browser.close()
console.log('\nDone.')
