/**
 * Vercel Edge Function — Spanish plate lookup proxy.
 *
 * Each invocation routes through a different Vercel edge node,
 * providing automatic IP rotation so comprobarmatricula.com per-IP
 * rate limits are never hit from a single source address.
 *
 * Flow:
 *   1. GET comprobarmatricula.com/matricula/{PLATE}/ → CSRF token + cookies
 *   2. GET /api/vehiculo.php?m={PLATE}&_tk={TOKEN} → vehicle JSON
 *   3. Return JSON with CORS headers
 *
 * Environment variables:
 *   CM_PROXY_SECRET  — shared secret the Go caller sends in X-CM-Proxy-Secret
 */
export const config = { runtime: 'edge' };

const UA_POOL = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
];

function pickUA(): string {
  return UA_POOL[Math.floor(Math.random() * UA_POOL.length)];
}

function extractCookies(headers: Headers): string {
  const cookies: string[] = [];
  headers.forEach((value, key) => {
    if (key.toLowerCase() === 'set-cookie') {
      const pair = value.split(';')[0].trim();
      if (pair) cookies.push(pair);
    }
  });
  return cookies.join('; ');
}

function extractToken(html: string): string | null {
  const m = html.match(/id="_g_tk"\s+value="([^"]+)"/);
  return m ? m[1] : null;
}

export default async function handler(req: Request): Promise<Response> {
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Content-Type': 'application/json',
  };

  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });

  // Optional shared-secret auth (set CM_PROXY_SECRET in Vercel dashboard)
  const envSecret = (globalThis as unknown as Record<string, string>)['CM_PROXY_SECRET'];
  if (envSecret) {
    if (req.headers.get('x-cm-proxy-secret') !== envSecret) {
      return new Response(JSON.stringify({ error: 'unauthorized' }), { status: 401, headers: cors });
    }
  }

  const plate = new URL(req.url).searchParams.get('plate')?.toUpperCase().replace(/[\s-]/g, '');
  if (!plate || !/^[A-Z0-9]{4,10}$/.test(plate)) {
    return new Response(JSON.stringify({ error: 'invalid_plate' }), { status: 400, headers: cors });
  }

  const ua = pickUA();
  const pageURL = `https://comprobarmatricula.com/matricula/${encodeURIComponent(plate)}/`;

  // Step 1: page fetch → token + cookies
  let html: string, cookies: string;
  try {
    const r = await fetch(pageURL, {
      headers: { 'User-Agent': ua, 'Accept': 'text/html', 'Accept-Language': 'es-ES,es;q=0.9' },
      redirect: 'follow',
    });
    html = await r.text();
    cookies = extractCookies(r.headers);
  } catch (e) {
    return new Response(JSON.stringify({ error: 'cm_unreachable', detail: String(e) }), { status: 502, headers: cors });
  }

  const token = extractToken(html);
  if (!token) {
    const ratelimited = html.includes('limit') || html.toLowerCase().includes('demasiadas');
    const isCF = html.includes('cloudflare') || html.includes('cf-ray') || html.includes('challenge');
    const debug = new URL(req.url).searchParams.has('debug');
    return new Response(JSON.stringify({
      ok: 0,
      limit: ratelimited,
      cloudflare: isCF,
      preview: debug ? html.slice(0, 400) : undefined,
    }), {
      status: ratelimited ? 429 : 404,
      headers: cors,
    });
  }

  // Step 2: JSON API call with token + session cookies
  const apiURL = `https://comprobarmatricula.com/api/vehiculo.php?m=${encodeURIComponent(plate)}&_tk=${encodeURIComponent(token)}&_hp=`;
  try {
    const r2 = await fetch(apiURL, {
      headers: {
        'User-Agent': ua,
        'Referer': pageURL,
        'Accept': 'application/json, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Cookie': cookies,
      },
    });
    const data = await r2.json();
    return new Response(JSON.stringify(data), { status: 200, headers: { ...cors, 'Cache-Control': 'no-store' } });
  } catch (e) {
    return new Response(JSON.stringify({ error: 'cm_api_failed', detail: String(e) }), { status: 502, headers: cors });
  }
}
