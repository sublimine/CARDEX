// CARDEX Intelligence — Content Script
// Extrae datos del listing actual y muestra el overlay de inteligencia

(function () {
  'use strict';

  // Evitar inyección doble
  if (window.__cardexInjected) return;
  window.__cardexInjected = true;

  // ── Detectores de datos por sitio ────────────────────────────────────────────

  const SITE_EXTRACTORS = {
    // AutoScout24 (todas las variantes)
    'autoscout24': {
      test: () => document.querySelector('[data-testid="listing-price"], .Price_price__APlgs, .cldt-price'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('[data-testid="listing-price"] .sc-font-bold, .Price_price__APlgs, .cldt-price');
        const price = parsePrice(priceEl?.textContent);
        const kmEl = document.querySelector('[data-testid="Kilometres"], .cldt-stage-mileage');
        const mileage = parseNumber(kmEl?.textContent);
        const yearEl = document.querySelector('[data-testid="FirstRegistration"], .cldt-stage-regdate');
        const year = parseYear(yearEl?.textContent);
        const { make, model } = parseTitleAutoScout(title);
        const country = detectCountry();
        return { make, model, year, price_eur: price, mileage_km: mileage, country };
      }
    },

    // mobile.de
    'mobile.de': {
      test: () => document.querySelector('.cBox-body--resultitem, .g-col-12.u-text-left'),
      extract: () => {
        const title = document.querySelector('h1.h2, h1.title, .listing-title')?.textContent?.trim() || '';
        const priceEl = document.querySelector('.seller-price, .price-block__price, [class*="price"]');
        const price = parsePrice(priceEl?.textContent);
        const kmEl = document.querySelector('[data-testid="mileage"], .listing-attribute-mileage');
        const mileage = parseNumber(kmEl?.textContent);
        const yearEl = document.querySelector('[data-testid="registration"], .listing-attribute-registration');
        const year = parseYear(yearEl?.textContent);
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'DE' };
      }
    },

    // Wallapop
    'wallapop.com': {
      test: () => document.querySelector('[class*="ItemDetail"], [data-testid="item-detail"]'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('[class*="Price"], .price, [data-testid="item-price"]');
        const price = parsePrice(priceEl?.textContent);
        const descEl = document.querySelector('[data-testid="item-description"], [class*="description"]');
        const desc = descEl?.textContent || '';
        const mileage = extractMileageFromText(desc);
        const year = extractYearFromText(title + ' ' + desc);
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'ES' };
      }
    },

    // LeBonCoin
    'leboncoin.fr': {
      test: () => document.querySelector('[data-qa-id="adview_price"]'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('[data-qa-id="adview_price"] span');
        const price = parsePrice(priceEl?.textContent);
        const attrs = document.querySelectorAll('[data-qa-id*="attribute"]');
        let mileage = 0, year = 0;
        attrs.forEach(el => {
          const t = el.textContent.toLowerCase();
          if (t.includes('km')) mileage = parseNumber(el.textContent);
          if (t.match(/\b20\d{2}\b/)) year = parseYear(el.textContent);
        });
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'FR' };
      }
    },

    // Coches.net
    'coches.net': {
      test: () => document.querySelector('.ad-price, [class*="precio"], .mt-DetailedPrice'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('.ad-price span, .mt-DetailedPrice-module_price');
        const price = parsePrice(priceEl?.textContent);
        const kmEl = document.querySelector('[class*="km"], [class*="kilometraje"], .mt-DetailedMedia-module_attribute');
        const mileage = parseNumber(kmEl?.textContent);
        const yearEl = document.querySelector('[class*="year"], [class*="año"]');
        const year = parseYear(yearEl?.textContent || title);
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'ES' };
      }
    },

    // Marktplaats
    'marktplaats.nl': {
      test: () => document.querySelector('[class*="Price"], .price-info'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('[class*="Price"] span, .price-info strong');
        const price = parsePrice(priceEl?.textContent);
        const mileage = extractMileageFromText(document.body.textContent);
        const year = extractYearFromText(title);
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'NL' };
      }
    },

    // La Centrale
    'lacentrale.fr': {
      test: () => document.querySelector('.classified-price, [class*="price"]'),
      extract: () => {
        const title = document.querySelector('h1')?.textContent?.trim() || '';
        const priceEl = document.querySelector('.classified-price, [class*="priceTotal"]');
        const price = parsePrice(priceEl?.textContent);
        const mileage = extractMileageFromText(document.body.textContent);
        const year = extractYearFromText(title);
        const { make, model } = parseTitleGeneric(title);
        return { make, model, year, price_eur: price, mileage_km: mileage, country: 'FR' };
      }
    },
  };

  // ── Utilidades de parsing ─────────────────────────────────────────────────────

  function parsePrice(text) {
    if (!text) return 0;
    const cleaned = text.replace(/[^\d.,]/g, '').replace(/\.(?=\d{3})/g, '').replace(',', '.');
    return Math.round(parseFloat(cleaned) || 0);
  }

  function parseNumber(text) {
    if (!text) return 0;
    return parseInt(text.replace(/[^\d]/g, ''), 10) || 0;
  }

  function parseYear(text) {
    if (!text) return 0;
    const m = text.match(/\b(19|20)\d{2}\b/);
    return m ? parseInt(m[0], 10) : 0;
  }

  function extractMileageFromText(text) {
    const m = text.match(/(\d[\d\s.]*)\s*km/i);
    if (m) return parseNumber(m[1]);
    return 0;
  }

  function extractYearFromText(text) {
    const m = text.match(/\b(20\d{2}|19\d{2})\b/);
    return m ? parseInt(m[0], 10) : 0;
  }

  function detectCountry() {
    const host = window.location.hostname;
    if (host.includes('.es')) return 'ES';
    if (host.includes('.de') || host.includes('mobile.de')) return 'DE';
    if (host.includes('.fr') || host.includes('leboncoin') || host.includes('lacentrale')) return 'FR';
    if (host.includes('.nl') || host.includes('marktplaats') || host.includes('gaspedaal')) return 'NL';
    if (host.includes('.be') || host.includes('tweedehands')) return 'BE';
    if (host.includes('.ch') || host.includes('comparis')) return 'CH';
    return 'EU';
  }

  function parseTitleAutoScout(title) {
    // AutoScout24 titles: "BMW 320d xDrive Touring" or "Volkswagen Golf 1.6 TDI"
    const parts = title.trim().split(/\s+/);
    const make = parts[0] || '';
    const model = parts[1] || '';
    return { make, model };
  }

  function parseTitleGeneric(title) {
    const parts = title.trim().split(/[\s\-|:]+/);
    const make = parts[0] || '';
    const model = parts.slice(1, 3).join(' ') || '';
    return { make, model };
  }

  // ── Seleccionar extractor ─────────────────────────────────────────────────────

  function getCurrentExtractor() {
    const host = window.location.hostname;
    for (const [key, extractor] of Object.entries(SITE_EXTRACTORS)) {
      if (host.includes(key)) return extractor;
    }
    return null;
  }

  // ── Overlay UI ────────────────────────────────────────────────────────────────

  function createOverlay() {
    const panel = document.createElement('div');
    panel.id = 'cardex-overlay';
    panel.innerHTML = `
      <div id="cardex-header">
        <span id="cardex-logo">⬡ CARDEX</span>
        <span id="cardex-status">Analizando…</span>
        <button id="cardex-close" title="Cerrar">×</button>
      </div>
      <div id="cardex-body">
        <div class="cardex-skeleton"></div>
        <div class="cardex-skeleton"></div>
        <div class="cardex-skeleton"></div>
      </div>
    `;
    document.body.appendChild(panel);

    document.getElementById('cardex-close').addEventListener('click', () => {
      panel.style.display = 'none';
    });

    // Drag support
    let isDragging = false, startX, startY, initRight, initTop;
    const header = document.getElementById('cardex-header');
    header.addEventListener('mousedown', e => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = panel.getBoundingClientRect();
      initRight = window.innerWidth - rect.right;
      initTop = rect.top;
      e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      panel.style.right = (initRight - dx) + 'px';
      panel.style.top = (initTop + dy) + 'px';
    });
    document.addEventListener('mouseup', () => { isDragging = false; });

    return panel;
  }

  // Safe HTML escape — prevents XSS when rendering API strings into innerHTML
  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Safe number formatter — validates numeric type before rendering
  function fmt(n) {
    const num = typeof n === 'number' ? n : parseFloat(n);
    if (!isFinite(num)) return '—';
    return `€${Math.round(num).toLocaleString('es-ES')}`;
  }

  function updateOverlay(panel, data) {
    const body = document.getElementById('cardex-body');
    const status = document.getElementById('cardex-status');

    if (data.error) {
      status.textContent = 'Sin datos';
      status.className = 'cardex-status-error';
      // Use textContent for error — never put API strings in innerHTML
      const errDiv = document.createElement('div');
      errDiv.className = 'cardex-error';
      errDiv.textContent = '⚠ ' + data.error;
      body.replaceChildren(errDiv);
      return;
    }

    if (data.disabled) {
      panel.style.display = 'none';
      return;
    }

    status.textContent = data.cached ? 'Caché' : 'En vivo';
    status.className = 'cardex-status-live';

    // Validate and normalize numeric fields from API
    const mdsRaw = typeof data.mds_days === 'number' ? data.mds_days : parseFloat(data.mds_days) || 0;
    const turnRaw = typeof data.predicted_turn_days === 'number' ? data.predicted_turn_days : parseFloat(data.predicted_turn_days) || 0;
    const medianRaw = typeof data.median_price_eur === 'number' ? data.median_price_eur : parseFloat(data.median_price_eur) || 0;
    const p25Raw = typeof data.p25_price_eur === 'number' ? data.p25_price_eur : parseFloat(data.p25_price_eur) || 0;
    const p75Raw = typeof data.p75_price_eur === 'number' ? data.p75_price_eur : parseFloat(data.p75_price_eur) || 0;
    const deltaRaw = typeof data.price_delta_eur === 'number' ? data.price_delta_eur : parseFloat(data.price_delta_eur) || 0;

    // Position — only accept known whitelist values, never raw API string
    const POSITION_MAP = {
      CHEAP:     { label: '▼ Precio bajo',  color: '#10b981' },
      FAIR:      { label: '● Precio justo', color: '#f59e0b' },
      EXPENSIVE: { label: '▲ Precio alto',  color: '#ef4444' },
    };
    const position = POSITION_MAP[data.market_position] ?? POSITION_MAP.FAIR;

    const mdsColor = mdsRaw <= 20 ? '#10b981' : mdsRaw <= 45 ? '#f59e0b' : '#6b7280';
    const mdsLabel = mdsRaw <= 20 ? `Alta (${mdsRaw}d)` : mdsRaw <= 45 ? `Media (${mdsRaw}d)` : `Baja (${mdsRaw}d)`;

    const turnColor = turnRaw <= 20 ? '#10b981' : turnRaw <= 45 ? '#f59e0b' : '#ef4444';
    const turnLabel = `~${turnRaw} días`;

    // esc() all API strings before interpolation into innerHTML
    const cheapestCountry = data.cheapest_country ? esc(data.cheapest_country) : '?';
    const arbitrageSection = data.arbitrage_flag ? `
      <div class="cardex-divider"></div>
      <div class="cardex-arbitrage">
        <strong>Arbitraje detectado</strong><br>
        En ${cheapestCountry}: ${fmt(medianRaw - deltaRaw)}<br>
        <span class="cardex-arb-delta">-${fmt(deltaRaw)} vs este país</span>
      </div>` : '';

    body.innerHTML = `
      <div class="cardex-row">
        <span class="cardex-label">Posición precio</span>
        <span class="cardex-value" style="color:${position.color}">${position.label}</span>
      </div>
      <div class="cardex-row cardex-row-sub">
        <span class="cardex-label">Mediana mercado</span>
        <span class="cardex-value">${fmt(medianRaw)}</span>
      </div>
      <div class="cardex-row cardex-row-sub">
        <span class="cardex-label">Rango (P25–P75)</span>
        <span class="cardex-value">${fmt(p25Raw)} – ${fmt(p75Raw)}</span>
      </div>
      <div class="cardex-divider"></div>
      <div class="cardex-row">
        <span class="cardex-label">Demanda</span>
        <span class="cardex-value" style="color:${mdsColor}">${mdsLabel}</span>
      </div>
      <div class="cardex-row">
        <span class="cardex-label">Venta estimada</span>
        <span class="cardex-value" style="color:${turnColor}">${turnLabel}</span>
      </div>
      ${arbitrageSection}
      <div class="cardex-footer">
        <a href="https://cardex.eu/analytics" target="_blank" rel="noopener noreferrer">Ver análisis completo →</a>
      </div>
    `;
  }

  // ── Main ──────────────────────────────────────────────────────────────────────

  async function init() {
    // Pequeño delay para que la página cargue
    await new Promise(r => setTimeout(r, 1200));

    const extractor = getCurrentExtractor();
    if (!extractor || !extractor.test()) return;

    let data;
    try {
      data = extractor.extract();
    } catch (e) {
      return;
    }

    // Solo continuar si tenemos datos mínimos
    if (!data.make || !data.price_eur) return;

    const panel = createOverlay();

    // Llamar al background para obtener datos de mercado
    chrome.runtime.sendMessage(
      { type: 'MARKET_CHECK', payload: data },
      (response) => {
        if (chrome.runtime.lastError) {
          updateOverlay(panel, { error: 'Extensión no disponible' });
          return;
        }
        updateOverlay(panel, response || { error: 'Sin respuesta' });
      }
    );
  }

  // Esperar a que el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init en navegación SPA (AutoScout24 y otros usan SPA routing)
  let lastUrl = location.href;
  new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      const existing = document.getElementById('cardex-overlay');
      if (existing) existing.remove();
      window.__cardexInjected = false;
      setTimeout(init, 500);
    }
  }).observe(document, { subtree: true, childList: true });

})();
