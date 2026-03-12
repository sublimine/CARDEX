import { useState, useEffect, useCallback } from "react";

// ─── MOCK DATA (matches real PG schema from e2e test) ───────────────────────
const MOCK_VEHICLES = [
  {
    vehicle_ulid: "01KJK5GNWR9ZKXZWHPJ0EKDM1F",
    vin: "WBA11111111111111",
    make: "BMW",
    model: "330i",
    year: 2023,
    mileage_km: 15000,
    color: "Schwarz",
    co2_gkm: 150,
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 190,
    price_raw: 25000,
    currency_raw: "EUR",
    gross_physical_cost_eur: 25000,
    origin_country: "DE",
    target_country: "DE",
    net_landed_cost_eur: 25800,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    tax_method: "VIES",
    lifecycle_status: "QUOTED",
    current_quote_id: "4278d9e6",
    quote_expires_at: new Date(Date.now() + 240000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 12,
    source_platform: "BCA",
    h3_index_res4: "841f91dffffffff",
    logistics_cost_eur: 800,
    tax_amount_eur: 0,
    seller_type: "DEALER",
  },
  {
    vehicle_ulid: "01KJK5H2XR8YKXZWHPJ0EKDM2G",
    vin: "WVWZZZ3CZWE123456",
    make: "Volkswagen",
    model: "Golf GTI",
    year: 2022,
    mileage_km: 32000,
    color: "Tornado Red",
    co2_gkm: 168,
    fuel_type: "Petrol",
    transmission: "Manual",
    power_kw: 180,
    price_raw: 89000,
    currency_raw: "PLN",
    gross_physical_cost_eur: 20648,
    origin_country: "PL",
    target_country: "ES",
    net_landed_cost_eur: 23537.18,
    tax_status: "REBU",
    tax_confidence: 1.0,
    tax_method: "AHO_CORASICK:margeregling",
    lifecycle_status: "QUOTED",
    current_quote_id: "a91bc3f2",
    quote_expires_at: new Date(Date.now() + 180000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 28,
    source_platform: "ARVAL",
    h3_index_res4: "841e59dffffffff",
    logistics_cost_eur: 950,
    tax_amount_eur: 1939.18,
    seller_type: "FLEET",
  },
  {
    vehicle_ulid: "01KJK5J4YS7XKXZWHPJ0EKDM3H",
    vin: "WF0XXXGCDX1234567",
    make: "Ford",
    model: "Focus ST",
    year: 2021,
    mileage_km: 48000,
    color: "Frozen White",
    co2_gkm: 179,
    fuel_type: "Petrol",
    transmission: "Manual",
    power_kw: 206,
    price_raw: 18500,
    currency_raw: "GBP",
    gross_physical_cost_eur: 21645,
    origin_country: "GB",
    target_country: "FR",
    net_landed_cost_eur: 25885.40,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    tax_method: "VIES",
    lifecycle_status: "QUOTED",
    current_quote_id: "c44de7a1",
    quote_expires_at: new Date(Date.now() + 120000).toISOString(),
    sdi_zone: "FLOORPLAN_60D_CLIFF",
    sdi_alert: true,
    days_on_market: 61,
    source_platform: "LEASEPLAN",
    h3_index_res4: "841fa59ffffffff",
    logistics_cost_eur: 1200,
    tax_amount_eur: 3040.40,
    seller_type: "DEALER",
  },
  {
    vehicle_ulid: "01KJK5K6ZT6WKXZWHPJ0EKDM4I",
    vin: "WAUZZZ4G6KN012345",
    make: "Audi",
    model: "A4 Avant",
    year: 2024,
    mileage_km: 8000,
    color: "Nardo Grey",
    co2_gkm: 132,
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 150,
    price_raw: 32000,
    currency_raw: "EUR",
    gross_physical_cost_eur: 32000,
    origin_country: "DE",
    target_country: "NL",
    net_landed_cost_eur: 49960,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    tax_method: "VIES",
    lifecycle_status: "QUOTED",
    current_quote_id: "f88ac2d5",
    quote_expires_at: new Date(Date.now() + 290000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 5,
    source_platform: "BCA",
    h3_index_res4: "841f91dffffffff",
    logistics_cost_eur: 700,
    tax_amount_eur: 17260,
    seller_type: "DEALER",
  },
  {
    vehicle_ulid: "01KJK5L8AU5VKXZWHPJ0EKDM5J",
    vin: "WDB2120001A123456",
    make: "Mercedes-Benz",
    model: "E 220 d",
    year: 2022,
    mileage_km: 55000,
    color: "Obsidian Black",
    co2_gkm: 142,
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 143,
    price_raw: 28500,
    currency_raw: "EUR",
    gross_physical_cost_eur: 28500,
    origin_country: "DE",
    target_country: "ES",
    net_landed_cost_eur: 30692.13,
    tax_status: "PENDING_VIES_OPTIMISTIC",
    tax_confidence: 0.7,
    tax_method: "VIES_TIMEOUT",
    lifecycle_status: "QUOTED",
    current_quote_id: "d55ba4e9",
    quote_expires_at: new Date(Date.now() + 60000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 34,
    source_platform: "BCA",
    h3_index_res4: "841f91dffffffff",
    logistics_cost_eur: 800,
    tax_amount_eur: 1392.13,
    seller_type: "DEALER",
  },
  {
    vehicle_ulid: "01KJK5M9BV4UKXZWHPJ0EKDM6K",
    vin: "TMBJB9NE3L0123456",
    make: "Škoda",
    model: "Octavia RS",
    year: 2020,
    mileage_km: 72000,
    color: "Race Blue",
    co2_gkm: 155,
    fuel_type: "Petrol",
    transmission: "Automatic",
    power_kw: 180,
    price_raw: 520000,
    currency_raw: "CZK",
    gross_physical_cost_eur: 21320,
    origin_country: "CZ",
    target_country: "DE",
    net_landed_cost_eur: 22470,
    tax_status: "REBU",
    tax_confidence: 0.95,
    tax_method: "VIES_INVALID",
    lifecycle_status: "QUOTED",
    current_quote_id: "e66cb5fa",
    quote_expires_at: new Date(Date.now() + 210000).toISOString(),
    sdi_zone: "FLOORPLAN_90D_CLIFF",
    sdi_alert: true,
    days_on_market: 91,
    source_platform: "ARVAL",
    h3_index_res4: "841e39dffffffff",
    logistics_cost_eur: 1150,
    tax_amount_eur: 0,
    seller_type: "INDIVIDUAL",
  },
  {
    vehicle_ulid: "01KJK5NABW3TKXZWHPJ0EKDM7L",
    vin: "ZFA31200001234567",
    make: "Fiat",
    model: "500e",
    year: 2023,
    mileage_km: 12000,
    color: "Glacier White",
    co2_gkm: 0,
    fuel_type: "Electric",
    transmission: "Automatic",
    power_kw: 87,
    price_raw: 19800,
    currency_raw: "EUR",
    gross_physical_cost_eur: 19800,
    origin_country: "IT",
    target_country: "DE",
    net_landed_cost_eur: 20750,
    tax_status: "REBU",
    tax_confidence: 1.0,
    tax_method: "AHO_CORASICK:regime del margine",
    lifecycle_status: "QUOTED",
    current_quote_id: "b77dc6eb",
    quote_expires_at: new Date(Date.now() + 270000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 18,
    source_platform: "LEASEPLAN",
    h3_index_res4: "841e19dffffffff",
    logistics_cost_eur: 950,
    tax_amount_eur: 0,
    seller_type: "FLEET",
  },
  {
    vehicle_ulid: "01KJK5PBCX2SKXZWHPJ0EKDM8M",
    vin: "SALVA2AE9LH012345",
    make: "Land Rover",
    model: "Discovery Sport",
    year: 2021,
    mileage_km: 41000,
    color: "Eiger Grey",
    co2_gkm: 198,
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 150,
    price_raw: 27500,
    currency_raw: "GBP",
    gross_physical_cost_eur: 32175,
    origin_country: "GB",
    target_country: "ES",
    net_landed_cost_eur: 36377.31,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    tax_method: "VIES",
    lifecycle_status: "QUOTED",
    current_quote_id: "a88ed7fc",
    quote_expires_at: new Date(Date.now() + 150000).toISOString(),
    sdi_zone: null,
    sdi_alert: false,
    days_on_market: 22,
    source_platform: "BCA",
    h3_index_res4: "841fa59ffffffff",
    logistics_cost_eur: 1400,
    tax_amount_eur: 2802.31,
    seller_type: "DEALER",
  },
];

// ─── HELPERS ────────────────────────────────────────────────────────────────
const fmt = (n) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
const fmtInt = (n) => new Intl.NumberFormat("de-DE").format(n);

const countryFlags = { DE: "🇩🇪", PL: "🇵🇱", FR: "🇫🇷", ES: "🇪🇸", NL: "🇳🇱", GB: "🇬🇧", IT: "🇮🇹", CZ: "🇨🇿", BE: "🇧🇪", AT: "🇦🇹" };
const flag = (c) => countryFlags[c] || c;

function timeLeft(expiresAt) {
  const diff = new Date(expiresAt) - Date.now();
  if (diff <= 0) return { text: "EXPIRED", urgent: true };
  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return { text: `${m}:${String(s).padStart(2, "0")}`, urgent: diff < 60000 };
}

const taxBadge = (status) => {
  const map = {
    DEDUCTIBLE: { bg: "#0d5c2e", fg: "#34d399", label: "DEDUCTIBLE" },
    REBU: { bg: "#7c2d12", fg: "#fb923c", label: "REBU §25a" },
    PENDING_VIES_OPTIMISTIC: { bg: "#713f12", fg: "#fbbf24", label: "PENDING" },
    REQUIRES_HUMAN_AUDIT: { bg: "#4c1d1d", fg: "#f87171", label: "AUDIT" },
  };
  return map[status] || { bg: "#333", fg: "#999", label: status };
};

const sdiBadge = (zone) => {
  if (!zone) return null;
  if (zone.includes("60D")) return { bg: "#713f12", fg: "#fbbf24", label: "60D CLIFF" };
  if (zone.includes("90D")) return { bg: "#4c1d1d", fg: "#f87171", label: "90D CLIFF" };
  return { bg: "#333", fg: "#999", label: zone };
};

// ─── STYLES ─────────────────────────────────────────────────────────────────
const S = {
  root: { background: "#0a0a0c", color: "#c8ccd0", fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace", minHeight: "100vh", fontSize: "12.5px", lineHeight: 1.5 },
  header: { background: "#111114", borderBottom: "1px solid #1e1e24", padding: "12px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 100 },
  logo: { display: "flex", alignItems: "center", gap: 10 },
  logoMark: { width: 28, height: 28, background: "linear-gradient(135deg, #f59e0b, #d97706)", borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 800, color: "#0a0a0c" },
  logoText: { fontSize: 16, fontWeight: 700, color: "#f0f0f0", letterSpacing: 3 },
  headerRight: { display: "flex", alignItems: "center", gap: 16, fontSize: 11, color: "#666" },
  pulse: { width: 7, height: 7, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 6px #22c55e80", animation: "pulse 2s infinite" },
  body: { display: "flex", height: "calc(100vh - 53px)" },
  sidebar: { width: 240, background: "#0f0f12", borderRight: "1px solid #1e1e24", padding: "16px 12px", display: "flex", flexDirection: "column", gap: 16, overflowY: "auto", flexShrink: 0 },
  sideLabel: { fontSize: 9, fontWeight: 700, letterSpacing: 2, color: "#555", textTransform: "uppercase", marginBottom: 6 },
  filterGroup: { display: "flex", flexDirection: "column", gap: 4 },
  filterBtn: (active) => ({ padding: "6px 10px", borderRadius: 4, border: "1px solid " + (active ? "#d97706" : "#1e1e24"), background: active ? "#d9770615" : "transparent", color: active ? "#f59e0b" : "#888", cursor: "pointer", fontSize: 11, textAlign: "left", transition: "all .15s" }),
  main: { flex: 1, overflowY: "auto", padding: 0 },
  toolbar: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 20px", borderBottom: "1px solid #1e1e24", background: "#0d0d10", position: "sticky", top: 0, zIndex: 50 },
  searchBox: { background: "#111114", border: "1px solid #1e1e24", borderRadius: 4, padding: "6px 10px", color: "#c8ccd0", fontSize: 12, fontFamily: "inherit", width: 260, outline: "none" },
  statsBar: { display: "flex", gap: 20, fontSize: 11, color: "#666" },
  statVal: { color: "#f59e0b", fontWeight: 600 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { padding: "8px 12px", textAlign: "left", fontSize: 9, fontWeight: 700, letterSpacing: 1.5, color: "#555", textTransform: "uppercase", borderBottom: "1px solid #1e1e24", position: "sticky", top: 41, background: "#0d0d10", zIndex: 40 },
  thR: { textAlign: "right" },
  tr: (selected, sdi) => ({ background: selected ? "#1a1a20" : "transparent", borderBottom: "1px solid #111114", cursor: "pointer", transition: "background .1s", ...(sdi ? { borderLeft: "2px solid #f59e0b" } : {}) }),
  td: { padding: "8px 12px", whiteSpace: "nowrap", fontSize: 12 },
  tdR: { textAlign: "right", fontVariantNumeric: "tabular-nums" },
  badge: (bg, fg) => ({ display: "inline-block", padding: "2px 6px", borderRadius: 3, background: bg, color: fg, fontSize: 10, fontWeight: 600, letterSpacing: 0.5 }),
  detail: { width: 380, background: "#0f0f12", borderLeft: "1px solid #1e1e24", overflowY: "auto", flexShrink: 0 },
  detailHeader: { padding: "16px", borderBottom: "1px solid #1e1e24" },
  detailTitle: { fontSize: 15, fontWeight: 700, color: "#f0f0f0", marginBottom: 4 },
  detailSub: { fontSize: 11, color: "#666" },
  detailSection: { padding: "12px 16px", borderBottom: "1px solid #1a1a1e" },
  detailLabel: { fontSize: 9, fontWeight: 700, letterSpacing: 1.5, color: "#555", textTransform: "uppercase", marginBottom: 8 },
  row: { display: "flex", justifyContent: "space-between", padding: "3px 0" },
  rowLabel: { color: "#777" },
  rowVal: { color: "#e0e0e0", fontWeight: 500, fontVariantNumeric: "tabular-nums" },
  rowValHighlight: { color: "#f59e0b", fontWeight: 700, fontVariantNumeric: "tabular-nums" },
  nlcBar: { height: 6, borderRadius: 3, background: "#1e1e24", marginTop: 8, overflow: "hidden" },
  nlcSegment: (color, width) => ({ height: "100%", width: width + "%", float: "left", background: color }),
  reserveBtn: (disabled) => ({ width: "100%", padding: "10px", borderRadius: 4, border: "none", background: disabled ? "#333" : "linear-gradient(135deg, #d97706, #b45309)", color: disabled ? "#666" : "#0a0a0c", fontWeight: 700, fontSize: 12, fontFamily: "inherit", cursor: disabled ? "not-allowed" : "pointer", letterSpacing: 1, marginTop: 8, transition: "all .2s" }),
  timer: (urgent) => ({ fontSize: 20, fontWeight: 800, color: urgent ? "#f87171" : "#f59e0b", fontVariantNumeric: "tabular-nums", letterSpacing: 1 }),
  empty: { padding: 40, textAlign: "center", color: "#444", fontSize: 13 },
};

// ─── MAIN COMPONENT ─────────────────────────────────────────────────────────
export default function CARDEXTerminal() {
  const [vehicles] = useState(MOCK_VEHICLES);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ tax: null, origin: null, target: null, sdi: false });
  const [, setTick] = useState(0);
  const [reserved, setReserved] = useState({});

  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(iv);
  }, []);

  const toggleFilter = useCallback((key, val) => {
    setFilters((f) => ({ ...f, [key]: f[key] === val ? null : val }));
  }, []);

  const filtered = vehicles.filter((v) => {
    if (search) {
      const q = search.toLowerCase();
      if (!(v.make.toLowerCase().includes(q) || v.model.toLowerCase().includes(q) || v.vin.toLowerCase().includes(q))) return false;
    }
    if (filters.tax && v.tax_status !== filters.tax) return false;
    if (filters.origin && v.origin_country !== filters.origin) return false;
    if (filters.target && v.target_country !== filters.target) return false;
    if (filters.sdi && !v.sdi_alert) return false;
    return true;
  });

  const sel = selected ? vehicles.find((v) => v.vehicle_ulid === selected) : null;

  const origins = [...new Set(vehicles.map((v) => v.origin_country))].sort();
  const targets = [...new Set(vehicles.map((v) => v.target_country))].sort();

  const totalNLC = filtered.reduce((s, v) => s + v.net_landed_cost_eur, 0);
  const avgMargin = filtered.length ? filtered.reduce((s, v) => s + ((v.gross_physical_cost_eur / v.net_landed_cost_eur) * 100 - 100) * -1, 0) / filtered.length : 0;

  return (
    <div style={S.root}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&display=swap');
        @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.4 } }
        @keyframes fadeIn { from { opacity:0; transform:translateY(4px) } to { opacity:1; transform:translateY(0) } }
        *::-webkit-scrollbar { width: 6px }
        *::-webkit-scrollbar-track { background: #0a0a0c }
        *::-webkit-scrollbar-thumb { background: #222; border-radius: 3px }
        tr:hover { background: #14141a !important }
      `}</style>

      {/* HEADER */}
      <div style={S.header}>
        <div style={S.logo}>
          <div style={S.logoMark}>CX</div>
          <div style={S.logoText}>CARDEX</div>
          <span style={{ fontSize: 10, color: "#555", marginLeft: 8, letterSpacing: 1 }}>TERMINAL v1.0</span>
        </div>
        <div style={S.headerRight}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={S.pulse} />
            <span style={{ color: "#22c55e" }}>LIVE</span>
          </div>
          <span>{new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
          <span>|</span>
          <span>{filtered.length} vehicles</span>
        </div>
      </div>

      <div style={S.body}>
        {/* SIDEBAR */}
        <div style={S.sidebar}>
          <div>
            <div style={S.sideLabel}>Tax Status</div>
            <div style={S.filterGroup}>
              {["DEDUCTIBLE", "REBU", "PENDING_VIES_OPTIMISTIC"].map((t) => (
                <button key={t} style={S.filterBtn(filters.tax === t)} onClick={() => toggleFilter("tax", t)}>
                  <span style={{ ...S.badge(...Object.values(taxBadge(t)).slice(0, 2)), marginRight: 6 }}>{taxBadge(t).label}</span>
                  <span style={{ color: "#555" }}>({vehicles.filter((v) => v.tax_status === t).length})</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div style={S.sideLabel}>Origin</div>
            <div style={S.filterGroup}>
              {origins.map((c) => (
                <button key={c} style={S.filterBtn(filters.origin === c)} onClick={() => toggleFilter("origin", c)}>
                  {flag(c)} {c} <span style={{ color: "#555" }}>({vehicles.filter((v) => v.origin_country === c).length})</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div style={S.sideLabel}>Target</div>
            <div style={S.filterGroup}>
              {targets.map((c) => (
                <button key={c} style={S.filterBtn(filters.target === c)} onClick={() => toggleFilter("target", c)}>
                  {flag(c)} {c} <span style={{ color: "#555" }}>({vehicles.filter((v) => v.target_country === c).length})</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <div style={S.sideLabel}>Alerts</div>
            <button style={S.filterBtn(filters.sdi)} onClick={() => setFilters((f) => ({ ...f, sdi: !f.sdi }))}>
              ⚠ SDI Cliff <span style={{ color: "#555" }}>({vehicles.filter((v) => v.sdi_alert).length})</span>
            </button>
          </div>

          <div style={{ marginTop: "auto", padding: "12px 0", borderTop: "1px solid #1e1e24", fontSize: 10, color: "#444" }}>
            <div>PostgreSQL ● ClickHouse</div>
            <div>Redis Streams ● RedisBloom</div>
            <div style={{ marginTop: 4, color: "#333" }}>CARDEX © 2026</div>
          </div>
        </div>

        {/* TABLE */}
        <div style={S.main}>
          <div style={S.toolbar}>
            <input style={S.searchBox} placeholder="Search make, model or VIN..." value={search} onChange={(e) => setSearch(e.target.value)} />
            <div style={S.statsBar}>
              <span>Σ NLC: <span style={S.statVal}>€{fmt(totalNLC)}</span></span>
              <span>Avg Δ: <span style={S.statVal}>{avgMargin.toFixed(1)}%</span></span>
            </div>
          </div>

          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Vehicle</th>
                <th style={S.th}>Route</th>
                <th style={S.th}>Source</th>
                <th style={S.th}>Tax</th>
                <th style={{ ...S.th, ...S.thR }}>GPC €</th>
                <th style={{ ...S.th, ...S.thR }}>NLC €</th>
                <th style={{ ...S.th, ...S.thR }}>Δ %</th>
                <th style={{ ...S.th, ...S.thR }}>Quote ⏱</th>
                <th style={S.th}>SDI</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((v) => {
                const tl = timeLeft(v.quote_expires_at);
                const delta = ((v.net_landed_cost_eur - v.gross_physical_cost_eur) / v.gross_physical_cost_eur) * 100;
                const tb = taxBadge(v.tax_status);
                const sb = sdiBadge(v.sdi_zone);
                return (
                  <tr key={v.vehicle_ulid} style={S.tr(selected === v.vehicle_ulid, v.sdi_alert)} onClick={() => setSelected(v.vehicle_ulid)}>
                    <td style={S.td}>
                      <div style={{ color: "#e0e0e0", fontWeight: 600 }}>{v.make} {v.model}</div>
                      <div style={{ fontSize: 10, color: "#555" }}>{v.year} · {fmtInt(v.mileage_km)} km · {v.fuel_type}</div>
                    </td>
                    <td style={S.td}>
                      <span>{flag(v.origin_country)}</span>
                      <span style={{ color: "#333", margin: "0 4px" }}>→</span>
                      <span>{flag(v.target_country)}</span>
                    </td>
                    <td style={{ ...S.td, color: "#666" }}>{v.source_platform}</td>
                    <td style={S.td}><span style={S.badge(tb.bg, tb.fg)}>{tb.label}</span></td>
                    <td style={{ ...S.td, ...S.tdR, color: "#999" }}>€{fmt(v.gross_physical_cost_eur)}</td>
                    <td style={{ ...S.td, ...S.tdR, color: "#f0f0f0", fontWeight: 700 }}>€{fmt(v.net_landed_cost_eur)}</td>
                    <td style={{ ...S.td, ...S.tdR, color: delta > 15 ? "#f87171" : delta > 8 ? "#fbbf24" : "#34d399" }}>+{delta.toFixed(1)}%</td>
                    <td style={{ ...S.td, ...S.tdR }}>
                      <span style={{ color: tl.urgent ? "#f87171" : "#888", fontWeight: tl.urgent ? 700 : 400 }}>{tl.text}</span>
                    </td>
                    <td style={S.td}>{sb && <span style={S.badge(sb.bg, sb.fg)}>{sb.label}</span>}</td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr><td colSpan={9} style={S.empty}>No vehicles match filters</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* DETAIL PANEL */}
        {sel && (
          <div style={S.detail}>
            <div style={S.detailHeader}>
              <div style={S.detailTitle}>{sel.make} {sel.model}</div>
              <div style={S.detailSub}>{sel.vin}</div>
              <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                <span style={S.badge(...Object.values(taxBadge(sel.tax_status)).slice(0, 2))}>{taxBadge(sel.tax_status).label}</span>
                {sel.sdi_zone && <span style={S.badge(...Object.values(sdiBadge(sel.sdi_zone)).slice(0, 2))}>{sdiBadge(sel.sdi_zone).label}</span>}
              </div>
            </div>

            {/* Timer */}
            <div style={{ ...S.detailSection, textAlign: "center", padding: "16px" }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 2, color: "#555", marginBottom: 4 }}>QUOTE EXPIRES IN</div>
              <div style={S.timer(timeLeft(sel.quote_expires_at).urgent)}>{timeLeft(sel.quote_expires_at).text}</div>
              <div style={{ fontSize: 10, color: "#444", marginTop: 4 }}>ID: {sel.current_quote_id}...</div>
            </div>

            {/* Vehicle Specs */}
            <div style={S.detailSection}>
              <div style={S.detailLabel}>Specifications</div>
              <div style={S.row}><span style={S.rowLabel}>Year</span><span style={S.rowVal}>{sel.year}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Mileage</span><span style={S.rowVal}>{fmtInt(sel.mileage_km)} km</span></div>
              <div style={S.row}><span style={S.rowLabel}>Color</span><span style={S.rowVal}>{sel.color}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Fuel</span><span style={S.rowVal}>{sel.fuel_type}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Transmission</span><span style={S.rowVal}>{sel.transmission}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Power</span><span style={S.rowVal}>{sel.power_kw} kW</span></div>
              <div style={S.row}><span style={S.rowLabel}>CO₂</span><span style={S.rowVal}>{sel.co2_gkm} g/km</span></div>
              <div style={S.row}><span style={S.rowLabel}>Days on Market</span><span style={{ ...S.rowVal, color: sel.sdi_alert ? "#f87171" : undefined }}>{sel.days_on_market}d</span></div>
            </div>

            {/* NLC Breakdown */}
            <div style={S.detailSection}>
              <div style={S.detailLabel}>Net Landed Cost Breakdown</div>
              <div style={S.row}><span style={S.rowLabel}>Gross Physical Cost</span><span style={S.rowVal}>€{fmt(sel.gross_physical_cost_eur)}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Logistics ({flag(sel.origin_country)}→{flag(sel.target_country)})</span><span style={S.rowVal}>€{fmt(sel.logistics_cost_eur)}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Tax ({sel.target_country})</span><span style={S.rowVal}>€{fmt(sel.tax_amount_eur)}</span></div>
              <div style={{ ...S.row, borderTop: "1px solid #1e1e24", paddingTop: 6, marginTop: 4 }}>
                <span style={{ ...S.rowLabel, fontWeight: 700, color: "#e0e0e0" }}>NET LANDED COST</span>
                <span style={S.rowValHighlight}>€{fmt(sel.net_landed_cost_eur)}</span>
              </div>
              <div style={S.nlcBar}>
                <div style={S.nlcSegment("#22c55e", (sel.gross_physical_cost_eur / sel.net_landed_cost_eur) * 100)} title="GPC" />
                <div style={S.nlcSegment("#3b82f6", (sel.logistics_cost_eur / sel.net_landed_cost_eur) * 100)} title="Logistics" />
                <div style={S.nlcSegment("#f59e0b", (sel.tax_amount_eur / sel.net_landed_cost_eur) * 100)} title="Tax" />
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10 }}>
                <span><span style={{ color: "#22c55e" }}>■</span> GPC</span>
                <span><span style={{ color: "#3b82f6" }}>■</span> Logistics</span>
                <span><span style={{ color: "#f59e0b" }}>■</span> Tax</span>
              </div>
            </div>

            {/* Tax Classification */}
            <div style={S.detailSection}>
              <div style={S.detailLabel}>Tax Classification</div>
              <div style={S.row}><span style={S.rowLabel}>Status</span><span style={S.rowVal}>{sel.tax_status}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Confidence</span><span style={S.rowVal}>{(sel.tax_confidence * 100).toFixed(0)}%</span></div>
              <div style={S.row}><span style={S.rowLabel}>Method</span><span style={{ ...S.rowVal, fontSize: 10 }}>{sel.tax_method}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Seller</span><span style={S.rowVal}>{sel.seller_type}</span></div>
            </div>

            {/* Provenance */}
            <div style={S.detailSection}>
              <div style={S.detailLabel}>Provenance</div>
              <div style={S.row}><span style={S.rowLabel}>Source</span><span style={S.rowVal}>{sel.source_platform}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Origin</span><span style={S.rowVal}>{flag(sel.origin_country)} {sel.origin_country}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Target</span><span style={S.rowVal}>{flag(sel.target_country)} {sel.target_country}</span></div>
              <div style={S.row}><span style={S.rowLabel}>Raw Price</span><span style={S.rowVal}>{fmt(sel.price_raw)} {sel.currency_raw}</span></div>
            </div>

            {/* Reserve */}
            <div style={{ padding: "12px 16px" }}>
              {reserved[sel.vehicle_ulid] ? (
                <div style={{ textAlign: "center", padding: 10, border: "1px solid #0d5c2e", borderRadius: 4, background: "#0d5c2e20" }}>
                  <span style={{ color: "#34d399", fontWeight: 700 }}>✓ RESERVED</span>
                </div>
              ) : (
                <button
                  style={S.reserveBtn(timeLeft(sel.quote_expires_at).text === "EXPIRED")}
                  disabled={timeLeft(sel.quote_expires_at).text === "EXPIRED"}
                  onClick={() => setReserved((r) => ({ ...r, [sel.vehicle_ulid]: true }))}
                >
                  RESERVE AT €{fmt(sel.net_landed_cost_eur)}
                </button>
              )}
              <div style={{ fontSize: 9, color: "#444", textAlign: "center", marginTop: 6 }}>
                Quote secured by HMAC-SHA256 · Stripe Connect settlement
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
