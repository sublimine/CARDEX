// CARDEX Intelligence — Background Service Worker
// Gestiona caché de respuestas API y comunicación entre content scripts y popup

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutos de caché
const cache = new Map(); // En-memory cache (se limpia al reiniciar el SW)

// Escucha mensajes de content scripts y popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'MARKET_CHECK') {
    handleMarketCheck(message.payload).then(sendResponse).catch(err => {
      sendResponse({ error: err.message });
    });
    return true; // Keep channel open for async response
  }

  if (message.type === 'GET_SETTINGS') {
    chrome.storage.sync.get(['apiUrl', 'apiToken', 'enabled'], (settings) => {
      sendResponse({
        apiUrl: settings.apiUrl || 'http://localhost:8080',
        apiToken: settings.apiToken || '',
        enabled: settings.enabled !== false,
      });
    });
    return true;
  }

  if (message.type === 'SAVE_SETTINGS') {
    chrome.storage.sync.set(message.payload, () => sendResponse({ ok: true }));
    return true;
  }
});

async function handleMarketCheck(params) {
  // Build cache key
  const cacheKey = JSON.stringify(params);
  const cached = cache.get(cacheKey);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return { ...cached.data, cached: true };
  }

  // Get settings
  const settings = await new Promise(resolve => {
    chrome.storage.sync.get(['apiUrl', 'enabled'], resolve);
  });

  if (settings.enabled === false) {
    return { disabled: true };
  }

  const apiUrl = (settings.apiUrl || 'http://localhost:8080').replace(/\/$/, '');

  // Build query string
  const qs = new URLSearchParams({
    make: params.make || '',
    model: params.model || '',
    year: params.year || '',
    price_eur: params.price_eur || '',
    mileage_km: params.mileage_km || '',
    country: params.country || '',
  }).toString();

  try {
    const res = await fetch(`${apiUrl}/api/v1/ext/market-check?${qs}`, {
      headers: { 'Accept': 'application/json' },
      signal: AbortSignal.timeout(8000),
    });

    if (!res.ok) {
      throw new Error(`API error ${res.status}`);
    }

    const data = await res.json();

    // Store in cache
    cache.set(cacheKey, { data, ts: Date.now() });

    // Limit cache size
    if (cache.size > 200) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }

    return data;
  } catch (err) {
    throw new Error(`CARDEX API no disponible: ${err.message}`);
  }
}
