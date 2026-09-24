// Captures the in-product guide screenshots from the real UI.
//
//   npm run docs:screenshots                  # every shot
//   npm run docs:screenshots -- --only tasks-list,calendar-month
//   npm run docs:screenshots -- --discover    # log API calls, write nothing
//
// The Vite dev server renders the actual application while every /api request
// is answered from ./guide-screenshots/fixtures.mjs: a fictional firm with
// synthetic people, clients, and matters. No backend, database, or customer
// data is involved, and the browser clock is frozen so dates are stable.
// Images are written as WebP to public/guide-assets/ for the guides to use.
import { chromium } from '@playwright/test'
import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { FIXED_NOW, TIMEZONE, createFixtureRouter } from './guide-screenshots/fixtures.mjs'
import { SHOTS } from './guide-screenshots/shots.mjs'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outputDir = path.join(frontendDir, 'public', 'guide-assets')
const args = process.argv.slice(2)
const discover = args.includes('--discover')
const onlyArg = args.find((arg) => arg.startsWith('--only'))
const only = onlyArg
  ? new Set((onlyArg.includes('=') ? onlyArg.split('=')[1] : args[args.indexOf(onlyArg) + 1] || '').split(',').filter(Boolean))
  : null
const WEBP_QUALITY = Number(process.env.GUIDE_SCREENSHOT_QUALITY || 0.86)

function chromiumExecutable() {
  if (process.env.GUIDE_SCREENSHOT_CHROMIUM) return process.env.GUIDE_SCREENSHOT_CHROMIUM
  if (existsSync(chromium.executablePath())) return undefined
  // Sandboxes that pre-install a browser for a different Playwright release.
  return existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined
}

async function encodeWebp(encoder, png) {
  const dataUrl = await encoder.evaluate(async ({ source, quality }) => {
    const image = new Image()
    image.src = source
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = image.naturalWidth
    canvas.height = image.naturalHeight
    canvas.getContext('2d').drawImage(image, 0, 0)
    return canvas.toDataURL('image/webp', quality)
  }, { source: `data:image/png;base64,${png.toString('base64')}`, quality: WEBP_QUALITY })
  if (!dataUrl.startsWith('data:image/webp')) throw new Error('This Chromium build cannot encode WebP')
  return Buffer.from(dataUrl.split(',')[1], 'base64')
}

// Outlines the controls a guide step refers to and, when labelled, pins a
// numbered marker to each so the text can say "select (1), then (2)".
async function annotate(page, marks = []) {
  if (!marks.length) return
  const boxes = []
  for (const mark of marks) {
    const locator = typeof mark.target === 'function' ? mark.target(page) : page.locator(mark.target)
    const box = await locator.first().boundingBox({ timeout: 8_000 }).catch(() => null)
    if (!box) throw new Error(`Annotation target not found or not visible: ${mark.target}`)
    boxes.push({ ...box, label: mark.label || '', pad: mark.pad ?? 4, placement: mark.placement || 'top-left' })
  }
  await page.evaluate((items) => {
    for (const item of items) {
      const ring = document.createElement('div')
      ring.setAttribute('data-guide-annotation', '')
      Object.assign(ring.style, {
        position: 'fixed', left: `${item.x - item.pad}px`, top: `${item.y - item.pad}px`,
        width: `${item.width + item.pad * 2}px`, height: `${item.height + item.pad * 2}px`,
        border: '3px solid #3157D5', borderRadius: '10px', boxShadow: '0 0 0 4px rgba(49, 87, 213, 0.18)',
        pointerEvents: 'none', zIndex: 2147483646,
      })
      document.body.appendChild(ring)
      if (!item.label) continue
      const badge = document.createElement('div')
      badge.setAttribute('data-guide-annotation', '')
      badge.textContent = item.label
      Object.assign(badge.style, {
        // Badges sit on the ring's top-left corner unless that would cover text
        // the reader needs, in which case a shot can move them below the ring.
        position: 'fixed',
        left: `${Math.max(2, item.x - item.pad - 13)}px`,
        top: `${Math.max(2, item.placement === 'bottom-left' ? item.y + item.height + item.pad - 13 : item.y - item.pad - 13)}px`,
        width: '26px', height: '26px', borderRadius: '999px', background: '#3157D5', color: '#fff',
        font: '700 13px/26px Manrope, Inter, sans-serif', textAlign: 'center', boxShadow: '0 2px 6px rgba(22, 24, 23, 0.35)',
        pointerEvents: 'none', zIndex: 2147483647,
      })
      document.body.appendChild(badge)
    }
  }, boxes)
}

async function capture(browser, encoder, baseURL, shot, unhandled) {
  const context = await browser.newContext({
    baseURL,
    viewport: shot.viewport || { width: 1440, height: 900 },
    deviceScaleFactor: shot.scale || 2,
    locale: 'en-US',
    timezoneId: TIMEZONE,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  })
  await context.clock.setFixedTime(FIXED_NOW)
  await context.addInitScript((storage) => {
    for (const [key, value] of Object.entries(storage)) window.localStorage.setItem(key, value)
  }, shot.localStorage || {})

  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })

  // Later registrations win: external hosts are blocked, the web font is
  // fetched on the Node side (so sandbox proxies and TLS verification keep
  // working), and the API is answered from fixtures.
  await page.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort())
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, async (route) => {
    try {
      await route.fulfill({ response: await route.fetch() })
    } catch {
      await route.abort()
    }
  })
  await page.route('**/api/**', createFixtureRouter({
    user: shot.user,
    overrides: shot.fixtures,
    onUnhandled: (key) => unhandled.add(`${shot.name}: ${key}`),
    onRequest: discover ? (key) => console.log(`  ${shot.name} → ${key}`) : undefined,
  }))

  await page.goto(shot.path, { waitUntil: 'domcontentloaded' })
  // Responsive pages render a hidden mobile copy too, so wait for a visible match.
  if (shot.waitFor) await page.getByText(shot.waitFor, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 20_000 })
  await page.waitForLoadState('networkidle').catch(() => {})
  if (shot.setup) await shot.setup(page)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(shot.settle ?? 400)

  if (discover) {
    await context.close()
    return { errors }
  }

  // Development-only chrome (the build badge) is not part of any workflow.
  await page.addStyleTag({ content: '.fixed.bottom-2.right-2.font-mono { display: none !important; }' })
  const clip = typeof shot.clip === 'function' ? await shot.clip(page) : shot.clip
  await annotate(page, shot.annotate)
  const target = typeof shot.target === 'function' ? shot.target(page) : shot.target ? page.locator(shot.target).first() : null
  const png = target
    ? await target.screenshot({ animations: 'disabled', caret: 'hide' })
    : await page.screenshot({ animations: 'disabled', caret: 'hide', clip, fullPage: Boolean(shot.fullPage) })
  const webp = await encodeWebp(encoder, png)
  await writeFile(path.join(outputDir, `${shot.name}.webp`), webp)
  await context.close()
  return { errors, bytes: webp.length }
}

const shots = SHOTS.filter((shot) => !only || only.has(shot.name))
if (!shots.length) {
  console.error(`No shots selected${only ? ` for ${[...only].join(', ')}` : ''}.`)
  process.exit(1)
}

const server = await createServer({
  root: frontendDir,
  configFile: path.join(frontendDir, 'vite.config.js'),
  logLevel: 'warn',
  server: { host: '127.0.0.1', port: Number(process.env.GUIDE_SCREENSHOT_PORT || 4319), strictPort: false, hmr: false },
})
await server.listen()
const baseURL = server.resolvedUrls.local[0].replace(/\/$/, '')

const browser = await chromium.launch({
  executablePath: chromiumExecutable(),
  // Only the web-font fetch leaves the machine; the app itself is local.
  proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: '127.0.0.1,localhost' } : undefined,
})
const encoder = await browser.newPage()
await mkdir(outputDir, { recursive: true })

const unhandled = new Set()
let failures = 0
try {
  for (const shot of shots) {
    const started = Date.now()
    try {
      const { errors, bytes } = await capture(browser, encoder, baseURL, shot, unhandled)
      const size = bytes ? ` ${(bytes / 1024).toFixed(0)} KB` : ''
      console.log(`${discover ? 'visited' : 'captured'} ${shot.name}${size} (${Date.now() - started} ms)`)
      for (const error of errors) console.log(`  page error: ${error.slice(0, 240)}`)
    } catch (error) {
      failures += 1
      console.error(`FAILED ${shot.name}: ${error.message.split('\n')[0]}`)
    }
  }
} finally {
  await browser.close()
  await server.close()
}

if (unhandled.size) {
  console.log('\nAPI requests answered with the generic fallback (add fixtures if a screen looks empty):')
  for (const key of [...unhandled].sort()) console.log(`  ${key}`)
}
if (failures) process.exit(1)
