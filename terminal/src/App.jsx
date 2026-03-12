import React, { useState, useEffect, useCallback, useMemo, memo } from "react";
import MesaDeDecisiones from "./components/MesaDeDecisiones";
import HomepageInstitucional from "./components/HomepageInstitucional";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  ComposedChart,
  Line,
} from "recharts";

// ─── CONSTANTS ─────────────────────────────────────────────────────────────
const CARDEX_LOGO = "/logo.png";
const CARDEX_COLORS = { primary: "#00b4d8", accent: "#0096c7", gradient: "linear-gradient(135deg, #00e0ff, #0096c7)" };

const ALL_COUNTRIES = [
  { code: "ES", name: "España" },
  { code: "FR", name: "Francia" },
  { code: "DE", name: "Alemania" },
  { code: "CH", name: "Suiza" },
  { code: "NL", name: "Holanda" },
  { code: "BE", name: "Bélgica" },
];

const FLAG_COLORS = {
  DE: ["#000", "#DD0000", "#FFCE00"],
  ES: ["#C60B1E", "#FFC400", "#C60B1E"],
  FR: ["#002395", "#FFF", "#ED2939"],
  NL: ["#AE1C28", "#FFF", "#21468B"],
  BE: ["#000", "#FDDA24", "#FD0E35"],
  CH: ["#FF0000"], // cruz blanca sobre rojo
};

// ─── MOCK DATA ──────────────────────────────────────────────────────────────
const MOCK_VEHICLES = [
  {
    vehicle_ulid: "01KJK5GNWR9ZKXZWHPJ0EKDM1F",
    make: "BMW",
    model: "330i",
    year: 2023,
    mileage_km: 15000,
    color: "Schwarz",
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 190,
    net_landed_cost_eur: 25800,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    days_on_market: 12,
    origin_country: "DE",
    image: "https://loremflickr.com/320/240/car,sedan?lock=1",
    tags: ["HIGH DEMAND"],
  },
  {
    vehicle_ulid: "01KJK5H2XR8YKXZWHPJ0EKDM2G",
    make: "Volkswagen",
    model: "Golf GTI",
    year: 2022,
    mileage_km: 32000,
    color: "Tornado Red",
    fuel_type: "Petrol",
    transmission: "Manual",
    power_kw: 180,
    net_landed_cost_eur: 23537,
    tax_status: "REBU",
    tax_confidence: 1.0,
    days_on_market: 28,
    origin_country: "FR",
    image: "https://loremflickr.com/320/240/car,hatchback?lock=2",
    tags: [],
  },
  {
    vehicle_ulid: "01KJK5J4YS7XKXZWHPJ0EKDM3H",
    make: "Ford",
    model: "Focus ST",
    year: 2021,
    mileage_km: 48000,
    color: "Frozen White",
    fuel_type: "Petrol",
    transmission: "Manual",
    power_kw: 206,
    net_landed_cost_eur: 25885,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    days_on_market: 61,
    origin_country: "DE",
    sdi_alert: true,
    image: "https://loremflickr.com/320/240/car,parking?lock=3",
    tags: ["LOW KM"],
  },
  {
    vehicle_ulid: "01KJK5K6ZT6WKXZWHPJ0EKDM4I",
    make: "Audi",
    model: "A4 Avant",
    year: 2024,
    mileage_km: 8000,
    color: "Nardo Grey",
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 150,
    net_landed_cost_eur: 49960,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    days_on_market: 5,
    origin_country: "CH",
    image: "https://loremflickr.com/320/240/car,wagon?lock=4",
    tags: ["ELECTRIC"],
  },
  {
    vehicle_ulid: "01KJK5L8AU5VKXZWHPJ0EKDM5J",
    make: "Mercedes-Benz",
    model: "E 220 d",
    year: 2022,
    mileage_km: 55000,
    color: "Obsidian Black",
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 143,
    net_landed_cost_eur: 30692,
    tax_status: "PENDING_VIES_OPTIMISTIC",
    tax_confidence: 0.7,
    days_on_market: 34,
    origin_country: "NL",
    image: "https://loremflickr.com/320/240/car,sedan?lock=5",
    tags: [],
  },
  {
    vehicle_ulid: "01KJK5M9BV4UKXZWHPJ0EKDM6K",
    make: "Škoda",
    model: "Octavia RS",
    year: 2020,
    mileage_km: 72000,
    color: "Race Blue",
    fuel_type: "Petrol",
    transmission: "Manual",
    power_kw: 180,
    net_landed_cost_eur: 22470,
    tax_status: "REBU",
    tax_confidence: 0.95,
    days_on_market: 91,
    origin_country: "BE",
    sdi_alert: true,
    image: "https://loremflickr.com/320/240/car,parking?lock=6",
    tags: [],
  },
  {
    vehicle_ulid: "01KJK5NABW3TKXZWHPJ0EKDM7L",
    make: "Fiat",
    model: "500e",
    year: 2023,
    mileage_km: 12000,
    color: "Glacier White",
    fuel_type: "Electric",
    transmission: "Automatic",
    power_kw: 87,
    net_landed_cost_eur: 20750,
    tax_status: "REBU",
    tax_confidence: 1.0,
    days_on_market: 18,
    origin_country: "ES",
    image: "https://loremflickr.com/320/240/compact,car?lock=7",
    tags: ["ELECTRIC"],
  },
  {
    vehicle_ulid: "01KJK5PBCX2SKXZWHPJ0EKDM8M",
    make: "Land Rover",
    model: "Discovery Sport",
    year: 2021,
    mileage_km: 41000,
    color: "Eiger Grey",
    fuel_type: "Diesel",
    transmission: "Automatic",
    power_kw: 150,
    net_landed_cost_eur: 36377,
    tax_status: "DEDUCTIBLE",
    tax_confidence: 0.98,
    days_on_market: 22,
    origin_country: "FR",
    image: "https://loremflickr.com/320/240/suv,car?lock=8",
    tags: ["HIGH DEMAND"],
  },
];

// ─── HELPERS ────────────────────────────────────────────────────────────────
const fmt = (n) =>
  new Intl.NumberFormat("de-DE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
const fmtK = (n) =>
  new Intl.NumberFormat("de-DE").format(n);
const kwToCv = (kw) => Math.round(kw * 1.36);

function levenshtein(a, b) {
  const m = a.length,
    n = b.length;
  const dp = Array(m + 1)
    .fill(null)
    .map(() => Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
  return dp[m][n];
}

const COLOR_SYNONYMS = {
  red: ["rojo", "rouge", "rot", "rosso", "rjo", "rge"],
  blue: ["azul", "bleu", "blau", "blu", "azl"],
  white: ["blanco", "blanc", "weiß", "weiss", "bianco", "whit"],
  black: ["negro", "noir", "schwarz", "nero", "blak", "blck"],
  grey: ["gris", "grau", "grigio", "gray", "grey"],
};
const MAKE_ALIASES = {
  bmw: ["bwm", "bmv"],
  vw: ["volkswagen", "volks"],
  audi: [],
  mercedes: ["mercedes-benz", "benz"],
  ford: [],
  fiat: [],
  skoda: ["škoda"],
  "land rover": ["landrover"],
};
const MODEL_ALIASES = {
  m4: ["m440i", "m 4"],
  a4: ["a4 avant", "a 4"],
  golf: ["golf gti", "gti"],
  "t-roc": ["troc", "t roc"],
};

const DASHBOARD_MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const GLOBAL_SALES_BY_YEAR = {
  "2022": DASHBOARD_MONTHS.map((m, i) => ({ month: m, actual: [38, 42, 48, 52, 58, 62, 68, 55, 48, 42, 38, 32][i], bp: [50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72][i] })),
  "2023": DASHBOARD_MONTHS.map((m, i) => ({ month: m, actual: [42, 45, 52, 55, 62, 65, 72, 58, 50, 45, 40, 35][i], bp: [52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74][i] })),
  "2024": DASHBOARD_MONTHS.map((m, i) => ({ month: m, actual: [45, 48, 55, 58, 65, 68, 75, 60, 52, 46, 40, 36][i], bp: [55, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78][i] })),
};
const YTD_BY_PERIOD = { ytd: { value: "195k", bp: "300k", change: 25.3, range: "Ene 2024 - Ago 2024" }, monthly: { value: "72k", bp: "68k", change: 5.9, range: "Ago 2024" }, daily: { value: "2.4k", bp: "2.2k", change: 9.1, range: "Hoy" } };
const TOP_MODELS = [
  { name: "BMW 330i", sales: "10.2k", img: "https://loremflickr.com/200/140/car,sedan?lock=1" },
  { name: "Audi A4 Avant", sales: "9.8k", img: "https://loremflickr.com/200/140/car,wagon?lock=4" },
  { name: "VW Golf GTI", sales: "6.2k", img: "https://loremflickr.com/200/140/car,hatchback?lock=2" },
  { name: "Mercedes E 220 d", sales: "5.6k", img: "https://loremflickr.com/200/140/car,sedan?lock=5" },
];

function getTrafficLightScore(v) {
  const conf = v.tax_confidence ?? 0;
  const status = v.tax_status ?? "";
  if (conf >= 0.95 && status === "DEDUCTIBLE") return "green";
  if (conf >= 0.7 || status === "REBU") return "amber";
  return "red";
}

// ─── MiniFlag ───────────────────────────────────────────────────────────────
function MiniFlag({ code }) {
  const colors = FLAG_COLORS[code];
  if (!colors) return null;
  const isCH = code === "CH";
  const dir = ["FR", "BE"].includes(code) ? "row" : "column";
  return (
    <div
      style={{
        width: 16,
        height: 11,
        borderRadius: 2,
        overflow: "hidden",
        flexShrink: 0,
        display: "flex",
        flexDirection: dir,
        opacity: 0.55,
      }}
    >
      {isCH ? (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "#FF0000",
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              position: "absolute",
              width: "60%",
              height: "40%",
              background: "#FFF",
              clipPath:
                "polygon(20% 0%, 80% 0%, 80% 100%, 20% 100%, 20% 45%, 80% 45%, 80% 55%, 20% 55%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              width: "25%",
              height: "70%",
              background: "#FFF",
              clipPath:
                "polygon(0% 15%, 100% 15%, 100% 85%, 0% 85%, 0% 40%, 100% 40%, 100% 60%, 0% 60%)",
            }}
          />
        </div>
      ) : (
        colors.map((c, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: c,
              minHeight: dir === "row" ? "100%" : 0,
              minWidth: dir === "column" ? "100%" : 0,
            }}
          />
        ))
      )}
    </div>
  );
}

// ─── MCard ──────────────────────────────────────────────────────────────────
const MCard = memo(function MCard({ v, theme }) {
  const score = getTrafficLightScore(v);
  const fuelLabel =
    v.fuel_type === "Petrol"
      ? "Gas"
      : v.fuel_type === "Diesel"
      ? "Diesel"
      : "EV";
  const isDark = theme === "dark";
  const sepColor = isDark ? "rgba(255,255,255,.25)" : "rgba(0,0,0,.2)";

  return (
    <div
      style={{
        borderRadius: 16,
        overflow: "hidden",
        background: isDark ? "#1a1a20" : "#fff",
        boxShadow: isDark
          ? "0 8px 32px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.03)"
          : "0 8px 32px rgba(0,0,0,.04), 0 2px 12px rgba(0,0,0,.03)",
        transition: "box-shadow .2s, transform .2s",
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = isDark
          ? "0 12px 40px rgba(0,0,0,.45)"
          : "0 12px 40px rgba(0,0,0,.08)";
        e.currentTarget.style.transform = "translateY(-2px)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = isDark
          ? "0 8px 32px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.03)"
          : "0 8px 32px rgba(0,0,0,.04), 0 2px 12px rgba(0,0,0,.03)";
        e.currentTarget.style.transform = "translateY(0)";
      }}
    >
      <div
        style={{
          position: "relative",
          height: 220,
          background: `linear-gradient(180deg, transparent 0%, rgba(0,0,0,.15) 40%, rgba(0,0,0,.65) 100%)`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <img
          src={v.image}
          alt={`${v.make} ${v.model}`}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "brightness(1.04) contrast(0.96) saturate(0.9)",
            imageRendering: "crisp-edges",
          }}
          onError={(e) => {
            e.target.style.display = "none";
            e.target.nextSibling.style.display = "flex";
          }}
        />
        <div
          style={{
            display: "none",
            position: "absolute",
            inset: 0,
            background: isDark ? "#2a2a30" : "#e8e8ec",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            color: isDark ? "#888" : "#666",
          }}
        >
          🚗 {v.make} {v.model}
        </div>

        {/* Overlay gradient */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg, rgba(0,0,0,.5) 0%, transparent 35%, rgba(0,0,0,.6) 100%)",
            pointerEvents: "none",
          }}
        />

        {/* Title + badges */}
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            right: 12,
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            alignItems: "flex-start",
          }}
        >
          <span
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: "#fff",
              textShadow: "0 1px 3px rgba(0,0,0,.8)",
            }}
          >
            {v.make} {v.model}
          </span>
          {v.tags?.map((t) => (
            <span
              key={t}
              style={{
                fontSize: 9,
                fontWeight: 600,
                padding: "2px 6px",
                borderRadius: 4,
                background: "rgba(0,0,0,.55)",
                color: "#fff",
              }}
            >
              {t}
            </span>
          ))}
        </div>

        {/* Semáforo + días */}
        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 4,
          }}
        >
          <div style={{ display: "flex", gap: 3 }}>
            {["green", "amber", "red"].map((c) => (
              <div
                key={c}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: score === c ? (c === "green" ? "#22c55e" : c === "amber" ? "#f59e0b" : "#ef4444") : "rgba(255,255,255,.25)",
                  boxShadow: score === c ? `0 0 6px ${c === "green" ? "#22c55e" : c === "amber" ? "#f59e0b" : "#ef4444"}80` : "none",
                }}
              />
            ))}
          </div>
          <span
            style={{
              fontSize: 9,
              fontWeight: 500,
              color: "rgba(255,255,255,.7)",
            }}
          >
            {v.days_on_market}d
          </span>
        </div>

        {/* Precio dentro de la imagen */}
        <div
          style={{
            position: "absolute",
            bottom: 36,
            left: 12,
            fontSize: 22,
            fontWeight: 800,
            color: "#fff",
            textShadow: "0 1px 4px rgba(0,0,0,.8)",
          }}
        >
          €{fmt(v.net_landed_cost_eur)}
        </div>

        {/* Fila características */}
        <div
          style={{
            position: "absolute",
            bottom: 12,
            left: 12,
            right: 12,
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            fontSize: 10,
            fontWeight: 500,
            color: "rgba(255,255,255,.75)",
          }}
        >
          <span>{fuelLabel}</span>
          <span style={{ color: sepColor }}>·</span>
          <span>{kwToCv(v.power_kw)} CV</span>
          <span style={{ color: sepColor }}>·</span>
          <span>{fmtK(v.mileage_km)} km</span>
          <span style={{ color: sepColor }}>·</span>
          <span>{v.year}</span>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              marginLeft: "auto",
              height: 11,
            }}
          >
            <span
              style={{
                fontSize: 10,
                fontWeight: 500,
                color: "rgba(255,255,255,.8)",
                lineHeight: 1,
                display: "flex",
                alignItems: "center",
              }}
            >
              {v.origin_country}
            </span>
            <MiniFlag code={v.origin_country} />
          </div>
        </div>
      </div>
    </div>
  );
});

// ─── Search engine ───────────────────────────────────────────────────────────
function searchVehicles(vehicles, query) {
  if (!query.trim()) return vehicles;
  const q = query.toLowerCase().trim();
  const terms = q.split(/\s+/).filter(Boolean);

  const score = (v) => {
    let s = 0;
    const make = v.make.toLowerCase();
    const model = v.model.toLowerCase();
    const color = (v.color || "").toLowerCase();

    for (const t of terms) {
      if (make.includes(t) || MAKE_ALIASES[make]?.some((a) => a.includes(t)))
        s += 10;
      if (model.includes(t) || Object.entries(MODEL_ALIASES).some(([k, aliases]) => k.includes(t) && model.includes(k)))
        s += 8;
      for (const [en, syns] of Object.entries(COLOR_SYNONYMS)) {
        if (en.includes(t) || syns.some((syn) => syn.includes(t) || t.includes(syn))) {
          if (color.includes(en) || syns.some((syn) => color.includes(syn))) s += 6;
          break;
        }
      }
      if (v.fuel_type?.toLowerCase().includes(t)) s += 3;
    }

    if (s === 0) {
      const all = `${make} ${model} ${color}`;
      if (terms.some((t) => all.includes(t))) s = 2;
    }
    return s;
  };

  const scored = vehicles.map((v) => ({ v, s: score(v) })).filter((x) => x.s > 0);
  scored.sort((a, b) => b.s - a.s);
  return scored.map((x) => x.v);
}

// ─── App ────────────────────────────────────────────────────────────────────
export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("cardex-theme") || "dark");
  const [page, setPage] = useState("home");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortBy, setSortBy] = useState("nlc-asc");
  const [searchQuery, setSearchQuery] = useState("");
  const [marcaModelo, setMarcaModelo] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [kmFrom, setKmFrom] = useState("");
  const [kmTo, setKmTo] = useState("");
  const [precioFrom, setPrecioFrom] = useState("");
  const [precioTo, setPrecioTo] = useState("");
  const [transmision, setTransmision] = useState("");
  const [combustible, setCombustible] = useState("");
  const [originCountry, setOriginCountry] = useState("");
  const [advPotenciaMin, setAdvPotenciaMin] = useState("");
  const [advCarroceria, setAdvCarroceria] = useState("");
  const [advEmisiones, setAdvEmisiones] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [dashboardPeriod, setDashboardPeriod] = useState("ytd");
  const [dashboardYear, setDashboardYear] = useState("2024");
  const [billingYearly, setBillingYearly] = useState(false);

  useEffect(() => {
    localStorage.setItem("cardex-theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const vehicles = useMemo(() => {
    let list = [...MOCK_VEHICLES];
    list = searchVehicles(list, searchQuery);
    if (marcaModelo) {
      const [make, model] = marcaModelo.split("|");
      list = list.filter((v) => v.make === make && v.model === model);
    }
    if (yearFrom) list = list.filter((v) => v.year >= parseInt(yearFrom, 10));
    if (yearTo) list = list.filter((v) => v.year <= parseInt(yearTo, 10));
    if (kmFrom) list = list.filter((v) => v.mileage_km >= parseInt(kmFrom, 10));
    if (kmTo) list = list.filter((v) => v.mileage_km <= parseInt(kmTo, 10));
    if (precioFrom) list = list.filter((v) => v.net_landed_cost_eur >= parseInt(precioFrom, 10));
    if (precioTo) list = list.filter((v) => v.net_landed_cost_eur <= parseInt(precioTo, 10));
    if (transmision) {
      const t = transmision.toLowerCase() === "automático" ? "automatic" : transmision.toLowerCase();
      list = list.filter((v) => (v.transmission || "").toLowerCase() === t);
    }
    if (combustible) {
      const map = { gasolina: "petrol", petrol: "petrol", diesel: "diesel", eléctrico: "electric", electric: "electric", híbrido: "hybrid", hibrido: "hybrid" };
      const val = map[combustible.toLowerCase()] || combustible.toLowerCase();
      list = list.filter((v) => (v.fuel_type || "").toLowerCase().includes(val));
    }
    if (originCountry) list = list.filter((v) => (v.origin_country || "") === originCountry);
    if (advPotenciaMin) list = list.filter((v) => (v.power_kw || 0) >= parseInt(advPotenciaMin, 10));
    if (advCarroceria) {
      const m = (v) => `${(v.make || "").toLowerCase()} ${(v.model || "").toLowerCase()}`;
      const match = {
        sedan: (v) => /330i|e 220|a4/i.test(m(v)),
        suv: (v) => /discovery|sport/i.test(m(v)),
        compacto: (v) => /500|golf|focus/i.test(m(v)),
        wagon: (v) => /avant|octavia/i.test(m(v)),
        hatchback: (v) => /golf|focus/i.test(m(v)),
        berlina: (v) => /e 220|330i|a4/i.test(m(v)),
      };
      if (match[advCarroceria]) list = list.filter(match[advCarroceria]);
    }
    if (sortBy === "nlc-asc") list.sort((a, b) => a.net_landed_cost_eur - b.net_landed_cost_eur);
    else if (sortBy === "nlc-desc") list.sort((a, b) => b.net_landed_cost_eur - a.net_landed_cost_eur);
    else if (sortBy === "year-desc") list.sort((a, b) => b.year - a.year);
    else if (sortBy === "year-asc") list.sort((a, b) => a.year - b.year);
    else if (sortBy === "km-asc") list.sort((a, b) => a.mileage_km - b.mileage_km);
    else if (sortBy === "km-desc") list.sort((a, b) => b.mileage_km - a.mileage_km);
    else if (sortBy === "days-asc") list.sort((a, b) => a.days_on_market - b.days_on_market);
    return list;
  }, [sortBy, searchQuery, marcaModelo, yearFrom, yearTo, kmFrom, kmTo, precioFrom, precioTo, transmision, combustible, originCountry, advPotenciaMin, advCarroceria]);

  const isDark = theme === "dark";

  const resetFilters = () => {
    setSearchQuery("");
    setMarcaModelo("");
    setYearFrom("");
    setYearTo("");
    setKmFrom("");
    setKmTo("");
    setPrecioFrom("");
    setPrecioTo("");
    setTransmision("");
    setCombustible("");
    setOriginCountry("");
    setAdvPotenciaMin("");
    setAdvCarroceria("");
    setAdvEmisiones("");
  };
  const MAKES = [...new Set(MOCK_VEHICLES.map((v) => v.make))].sort();
  const YEARS = [...new Set(MOCK_VEHICLES.map((v) => v.year))].sort((a, b) => b - a);
  const MAKE_MODELS = [...new Set(MOCK_VEHICLES.map((v) => `${v.make}|${v.model}`))].sort().map((s) => {
    const [m, mod] = s.split("|");
    return { value: s, label: `${m} ${mod}` };
  });
  const KM_OPTIONS = [0, 10000, 20000, 30000, 50000, 75000, 100000, 150000, 200000, 300000, 500000, 999999];
  const PRICE_OPTIONS = [0, 5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000, 150000, 200000, 999999];
  const ORDER_OPTIONS = [
    { value: "nlc-asc", label: "Precio: menor a mayor" },
    { value: "nlc-desc", label: "Precio: mayor a menor" },
    { value: "year-desc", label: "Año: más reciente" },
    { value: "year-asc", label: "Año: más antiguo" },
    { value: "km-asc", label: "Km: menos a más" },
    { value: "km-desc", label: "Km: más a menos" },
    { value: "days-asc", label: "Días en mercado: menos" },
  ];

  const chartData = useMemo(() => {
    const byCountry = {};
    MOCK_VEHICLES.forEach((v) => {
      byCountry[v.origin_country] = (byCountry[v.origin_country] || 0) + 1;
    });
    return Object.entries(byCountry).map(([c, n]) => ({ name: c, count: n }));
  }, []);

  const taxData = useMemo(() => {
    const byTax = {};
    MOCK_VEHICLES.forEach((v) => {
      byTax[v.tax_status] = (byTax[v.tax_status] || 0) + 1;
    });
    return Object.entries(byTax).map(([name, value]) => ({ name, value }));
  }, []);

  const COLORS = ["#22c55e", "#f59e0b", "#ef4444", "#6366f1"];
  const globalSalesData = GLOBAL_SALES_BY_YEAR[dashboardYear] || GLOBAL_SALES_BY_YEAR["2024"];
  const ytdInfo = YTD_BY_PERIOD[dashboardPeriod] || YTD_BY_PERIOD.ytd;

  const NavIcon = ({ name, size = 20, color }) => {
    const s = size;
    const icons = {
      home: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
      marketplace: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>,
      dashboard: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>,
      calendar: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>,
      car: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 17h14v-5H5v5z"/><path d="M5 12l2-4h10l2 4"/><circle cx="7.5" cy="17" r="1.5"/><circle cx="16.5" cy="17" r="1.5"/></svg>,
      globe: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>,
      chart: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,
      money: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
      profit: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
      pricing: <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
    };
    return icons[name] || null;
  };

  const NAV_ITEMS = [
    { id: "home", label: "Home", icon: "home" },
    { id: "marketplace", label: "Marketplace", icon: "marketplace" },
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "pricing", label: "Pricing", icon: "pricing" },
    { id: "calendar", label: "Calendario", icon: "calendar" },
    { id: "models", label: "Modelos core", icon: "car" },
    { id: "markets", label: "Mercados", icon: "globe" },
    { id: "sales", label: "Ventas", icon: "chart" },
    { id: "revenue", label: "Ingresos", icon: "money" },
    { id: "profit", label: "Beneficio", icon: "profit" },
  ];

  const PRICING_PLANS = [
    {
      name: "Free Plan",
      price: "Free",
      priceMonthly: null,
      priceYearly: null,
      features: [
        "Send up to 2 transfers per month",
        "Basic transaction history",
        "Email support",
        "Limited currency support (USD, EUR, GBP)",
        "Basic security features",
      ],
      highlighted: false,
    },
    {
      name: "Standard Plan",
      price: billingYearly ? "€7.99/m" : "€9.99/m",
      priceMonthly: 9.99,
      priceYearly: 7.99,
      features: [
        "Unlimited transfers",
        "Transaction history with export options",
        "Priority email support",
        "Expanded currency support",
        "Advanced security features",
      ],
      highlighted: true,
    },
    {
      name: "Pro Plan",
      price: billingYearly ? "€15.99/m" : "€19.99/m",
      priceMonthly: 19.99,
      priceYearly: 15.99,
      features: [
        "Unlimited transfers with priority processing",
        "Comprehensive transaction analytics",
        "24/7 priority support",
        "Full currency support",
        "Enhanced security features",
      ],
      highlighted: false,
    },
  ];

  return (
    <div className="app-root" style={{ minHeight: "100vh", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      <style>{`
        .app-root { font-family: 'DM Sans', system-ui, -apple-system, sans-serif; }
        [data-theme="dark"] { color-scheme: dark; }
        [data-theme="light"] { color-scheme: light; }
      `}</style>

      {page === "home" ? (
        <HomepageInstitucional onNavigate={setPage} />
      ) : page === "dashboard" ? (
        <MesaDeDecisiones onNavigate={setPage} />
      ) : (
      <div style={{ display: "flex", minHeight: "100vh", background: page === "marketplace" ? (isDark ? "#0a0a0c" : "#f0f0f2") : (isDark ? "#0a0a0c" : "#f1f5f9") }}>
        {/* SIDEBAR - siempre visible, adapta al tema */}
        <aside style={{ width: 240, background: isDark ? "#111114" : "#fff", borderRight: `1px solid ${isDark ? "#1e1e24" : "#e2e8f0"}`, padding: "20px 16px", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 32 }}>
            <img src={CARDEX_LOGO} alt="CARDEX" style={{ width: 36, height: 36, objectFit: "contain" }} />
            <span style={{ fontSize: 18, fontWeight: 700, color: isDark ? "#e0e0e0" : "#1e293b" }}>CARDEX</span>
          </div>
          <nav style={{ flex: 1 }}>
            {NAV_ITEMS.map((item) => {
              const active = page === item.id;
              const iconColor = active ? (isDark ? "#a5b4fc" : "#6366f1") : (isDark ? "#6b7280" : "#64748b");
              return (
                <button
                  key={item.id}
                  onClick={() => setPage(item.id)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "10px 12px",
                    marginBottom: 4,
                    border: "none",
                    borderRadius: 8,
                    background: active ? (isDark ? "#1e1e24" : "#eef2ff") : "transparent",
                    color: active ? (isDark ? "#e0e0e0" : "#1e293b") : (isDark ? "#9ca3af" : "#64748b"),
                    fontWeight: active ? 600 : 500,
                    cursor: "pointer",
                    fontSize: 14,
                    textAlign: "left",
                  }}
                >
                  <NavIcon name={item.icon} color={iconColor} />
                  {item.label}
                </button>
              );
            })}
          </nav>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#2a2a30" : "#e2e8f0"}`, background: "transparent", color: isDark ? "#9ca3af" : "#64748b", cursor: "pointer", fontSize: 12, marginTop: 8, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
            aria-label={theme === "dark" ? "Modo claro" : "Modo oscuro"}
          >
            {theme === "dark" ? (
              <><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg> Claro</>
            ) : (
              <><svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg> Oscuro</>
            )}
          </button>
        </aside>

        {/* MAIN CONTENT */}
      {page === "marketplace" && (
        <main style={{ flex: 1, overflowY: "auto", padding: 24, maxWidth: 1400, margin: 0, color: isDark ? "#e0e0e0" : "#1a1a1e" }}>
          {/* Buscador + Filtros - todo en un desplegable */}
          <div style={{ marginBottom: 24, padding: 20, borderRadius: 16, background: isDark ? "#111114" : "#fff", border: `1px solid ${isDark ? "#1e1e24" : "#e5e7eb"}`, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,.2)" : "0 1px 3px rgba(0,0,0,.06)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <div style={{ position: "relative", flex: "1 1 280px", minWidth: 200 }}>
                <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke={CARDEX_COLORS.primary} strokeWidth="1.5" style={{ position: "absolute", left: 16, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", opacity: 0.8 }}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                <input
                  type="text"
                  placeholder="Buscar por marca, modelo, color..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "14px 20px 14px 48px",
                    borderRadius: 12,
                    border: `1px solid ${searchFocused ? CARDEX_COLORS.primary : (isDark ? "#374151" : "#e5e7eb")}`,
                    background: isDark ? "#1a1a20" : "#f8fafc",
                    color: "inherit",
                    fontSize: 15,
                    outline: "none",
                    transition: "border-color .2s, box-shadow .2s",
                    boxShadow: searchFocused ? `0 0 0 3px ${CARDEX_COLORS.primary}30` : "none",
                  }}
                  onFocus={() => setSearchFocused(true)}
                  onBlur={() => setSearchFocused(false)}
                />
              </div>
              <button
                onClick={() => setFiltersOpen(!filtersOpen)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "14px 20px",
                  borderRadius: 12,
                  border: `1px solid ${filtersOpen ? CARDEX_COLORS.primary : (isDark ? "#374151" : "#e5e7eb")}`,
                  background: filtersOpen ? `${CARDEX_COLORS.primary}20` : "transparent",
                  color: filtersOpen ? CARDEX_COLORS.primary : "inherit",
                  fontSize: 14,
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
                Filtros {vehicles.length > 0 && `(${vehicles.length})`}
              </button>
            </div>

            {filtersOpen && (
              <div style={{ marginTop: 20, padding: 20, borderRadius: 12, background: isDark ? "#0a0a0c" : "#f1f5f9", border: `1px solid ${isDark ? "#1e1e24" : "#e2e8f0"}` }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 16 }}>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Orden</label>
                    <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      {ORDER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Marca y Modelo</label>
                    <select value={marcaModelo} onChange={(e) => setMarcaModelo(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Todas</option>
                      {MAKE_MODELS.map((mm) => <option key={mm.value} value={mm.value}>{mm.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Registro desde</label>
                    <select value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Registro hasta</label>
                    <select value={yearTo} onChange={(e) => setYearTo(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Km desde</label>
                    <select value={kmFrom} onChange={(e) => setKmFrom(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {KM_OPTIONS.map((k) => <option key={k} value={k}>{k >= 999999 ? "Sin límite" : k.toLocaleString("de-DE")}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Km hasta</label>
                    <select value={kmTo} onChange={(e) => setKmTo(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {KM_OPTIONS.map((k) => <option key={k} value={k}>{k >= 999999 ? "Sin límite" : k.toLocaleString("de-DE")}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Precio desde (€)</label>
                    <select value={precioFrom} onChange={(e) => setPrecioFrom(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {PRICE_OPTIONS.map((p) => <option key={p} value={p}>{p >= 999999 ? "Sin límite" : p.toLocaleString("de-DE")}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Precio hasta (€)</label>
                    <select value={precioTo} onChange={(e) => setPrecioTo(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {PRICE_OPTIONS.map((p) => <option key={p} value={p}>{p >= 999999 ? "Sin límite" : p.toLocaleString("de-DE")}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Transmisión</label>
                    <select value={transmision} onChange={(e) => setTransmision(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Todas</option>
                      <option value="Manual">Manual</option>
                      <option value="Automático">Automático</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Combustible</label>
                    <select value={combustible} onChange={(e) => setCombustible(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Todos</option>
                      <option value="Gasolina">Gasolina</option>
                      <option value="Diesel">Diesel</option>
                      <option value="Eléctrico">Eléctrico</option>
                      <option value="Híbrido">Híbrido</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>País origen</label>
                    <select value={originCountry} onChange={(e) => setOriginCountry(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Todos</option>
                      {ALL_COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Potencia mín. (kW)</label>
                    <select value={advPotenciaMin} onChange={(e) => setAdvPotenciaMin(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      {[80, 100, 120, 150, 180, 200, 250, 300].map((kw) => <option key={kw} value={kw}>{kw} kW</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Carrocería</label>
                    <select value={advCarroceria} onChange={(e) => setAdvCarroceria(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Todas</option>
                      <option value="sedan">Sedán</option>
                      <option value="suv">SUV</option>
                      <option value="berlina">Berlina</option>
                      <option value="compacto">Compacto</option>
                      <option value="hatchback">Hatchback</option>
                      <option value="wagon">Berlina familiar</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: isDark ? "#9ca3af" : "#64748b", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Emisiones CO₂</label>
                    <select value={advEmisiones} onChange={(e) => setAdvEmisiones(e.target.value)} style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: isDark ? "#1a1a20" : "#fff", color: "inherit", fontSize: 13, cursor: "pointer" }}>
                      <option value="">Cualquier</option>
                      <option value="a">A (&lt;100 g/km)</option>
                      <option value="b">B (100-120)</option>
                      <option value="c">C (120-140)</option>
                      <option value="d">D (140-160)</option>
                      <option value="e">E (&gt;160)</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20, paddingTop: 16, borderTop: `1px solid ${isDark ? "#374151" : "#e2e8f0"}` }}>
                  <span style={{ fontSize: 13, color: isDark ? "#9ca3af" : "#64748b" }}>{vehicles.length} resultados</span>
                  <button onClick={resetFilters} style={{ padding: "8px 16px", borderRadius: 8, border: `1px solid ${isDark ? "#374151" : "#e2e8f0"}`, background: "transparent", color: "inherit", fontSize: 13, cursor: "pointer" }}>Reiniciar filtros</button>
                </div>
              </div>
            )}
          </div>

          {/* Feed */}
          {vehicles.length === 0 ? (
            <div
              style={{
                padding: 60,
                textAlign: "center",
                color: isDark ? "#555" : "#888",
                fontSize: 15,
              }}
            >
              No hay vehículos que coincidan. Prueba a ajustar la búsqueda o filtros.
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: 20,
              }}
            >
              {vehicles.map((v) => (
                <MCard key={v.vehicle_ulid} v={v} theme={theme} />
              ))}
            </div>
          )}
        </main>
      )}

      {page === "pricing" && (
        <main style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", alignItems: "center", background: "#000000", color: "#ffffff", position: "relative", minHeight: "100vh" }}>
          {/* Título grande de fondo */}
          <h1 style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", fontSize: "clamp(72px, 12vw, 140px)", fontWeight: 800, color: "rgba(255,255,255,0.04)", pointerEvents: "none", userSelect: "none", zIndex: 0 }}>
            Pricing
          </h1>

          <div style={{ width: "100%", maxWidth: 1100, padding: "24px 32px", position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 40 }}>
            {/* Nav bar - pill glassmorphism */}
            <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "8px 16px", borderRadius: 9999, background: "rgba(255,255,255,0.06)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <button style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(255,255,255,0.08)", border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {["Home", "Pricing", "FAQ", "Contact"].map((link) => (
                  <span key={link} style={{ padding: "8px 16px", borderRadius: 8, fontSize: 14, fontWeight: 500, background: link === "Pricing" ? "rgba(255,255,255,0.15)" : "transparent", color: "#fff" }}>{link}</span>
                ))}
              </div>
              <button style={{ marginLeft: "auto", padding: "10px 20px", borderRadius: 9999, background: "#ffffff", color: "#000000", border: "1px solid rgba(0,0,0,0.1)", fontSize: 14, fontWeight: 600, cursor: "pointer" }}>Download</button>
            </div>

            {/* 3 cards en fila - glassmorphism */}
            <div style={{ display: "flex", gap: 24, justifyContent: "center", width: "100%", flexWrap: "wrap" }}>
              {PRICING_PLANS.map((plan) => (
                <div
                  key={plan.name}
                  style={{
                    flex: "1 1 300px",
                    maxWidth: 340,
                    padding: 28,
                    borderRadius: 24,
                    background: "rgba(255,255,255,0.04)",
                    backdropFilter: "blur(24px)",
                    WebkitBackdropFilter: "blur(24px)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, color: "rgba(255,255,255,0.6)", marginBottom: 8 }}>{plan.name}</div>
                  <div style={{ fontSize: 36, fontWeight: 700, color: "#ffffff", marginBottom: 24, lineHeight: 1.1 }}>
                    {plan.price === "Free" ? "Free" : (
                      <><span style={{ fontSize: 36 }}>{plan.price.replace("/m", "").trim()}</span><span style={{ fontSize: 24, fontWeight: 500, opacity: 0.8 }}>/m</span></>
                    )}
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: 0, flex: 1 }}>
                    {plan.features.map((f, i) => (
                      <li key={i} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, fontSize: 14, color: "rgba(255,255,255,0.7)" }}>
                        <span style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                        </span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <button
                    style={{
                      marginTop: 28,
                      padding: "14px 28px",
                      borderRadius: 9999,
                      border: plan.highlighted ? "none" : "1px solid rgba(255,255,255,0.15)",
                      fontSize: 15,
                      fontWeight: 600,
                      cursor: "pointer",
                      background: plan.highlighted ? "#ffffff" : "rgba(255,255,255,0.06)",
                      color: plan.highlighted ? "#000000" : "#ffffff",
                    }}
                  >
                    Get Started
                  </button>
                </div>
              ))}
            </div>

            {/* Billed Yearly toggle */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, alignSelf: "flex-start" }}>
              <button
                onClick={() => setBillingYearly(!billingYearly)}
                style={{
                  width: 48,
                  height: 26,
                  borderRadius: 9999,
                  border: "none",
                  background: "rgba(255,255,255,0.1)",
                  cursor: "pointer",
                  position: "relative",
                }}
              >
                <span style={{ position: "absolute", top: 3, left: billingYearly ? 25 : 3, width: 20, height: 20, borderRadius: "50%", background: "#ffffff", transition: "left 0.2s" }} />
              </button>
              <span style={{ fontSize: 14, color: "rgba(255,255,255,0.8)" }}>Billed Yearly</span>
            </div>

            {/* Footer: Plans + bar */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, width: "100%" }}>
              <button style={{ padding: "10px 24px", borderRadius: 12, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.8)", fontSize: 14, fontWeight: 500, cursor: "pointer" }}>Plans</button>
              <div style={{ width: "100%", maxWidth: 900, height: 8, borderRadius: 9999, background: "rgba(255,255,255,0.06)" }} />
            </div>
          </div>
        </main>
      )}

      {(page === "dashboard" || ["calendar", "models", "markets", "sales", "revenue", "profit"].includes(page)) && (
        <main style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", background: "transparent" }}>
            {/* TOP BAR */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 24px", background: isDark ? "#111114" : "#fff", borderBottom: `1px solid ${isDark ? "#1e1e24" : "#e2e8f0"}`, flexWrap: "wrap", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {["ytd", "monthly", "daily"].map((p) => (
                  <button key={p} onClick={() => setDashboardPeriod(p)} style={{ padding: "8px 16px", border: "none", background: "transparent", color: dashboardPeriod === p ? "#6366f1" : (isDark ? "#9ca3af" : "#64748b"), fontWeight: dashboardPeriod === p ? 600 : 500, fontSize: 14, cursor: "pointer", borderBottom: dashboardPeriod === p ? "2px solid #6366f1" : "2px solid transparent" }}>
                    {p === "ytd" ? "YTD" : p === "monthly" ? "Mensual" : "Diario"}
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: isDark ? "#1a1a20" : "#fff", borderRadius: 8, border: `1px solid ${isDark ? "#2a2a30" : "#e2e8f0"}`, width: 200 }}>
                  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke={isDark ? "#6b7280" : "#94a3b8"} strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                  <input type="text" placeholder="Buscar..." style={{ border: "none", outline: "none", fontSize: 14, width: "100%", background: "transparent", color: "inherit" }} />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", background: isDark ? "#1a1a20" : "#fff", borderRadius: 8, border: `1px solid ${isDark ? "#2a2a30" : "#e2e8f0"}` }}>
                  <select value={dashboardYear} onChange={(e) => setDashboardYear(e.target.value)} style={{ border: "none", outline: "none", fontSize: 14, cursor: "pointer", background: "transparent" }}>
                    {["2022", "2023", "2024"].map((y) => <option key={y} value={y}>{y}</option>)}
                  </select>
                </div>
                <button style={{ background: "none", border: "none", cursor: "pointer", padding: 4, color: isDark ? "#9ca3af" : "#64748b" }} title="Configuración">
                  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                </button>
                <button style={{ background: "none", border: "none", cursor: "pointer", padding: 4, position: "relative", color: isDark ? "#9ca3af" : "#64748b" }} title="Notificaciones">
                  <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
                  <span style={{ position: "absolute", top: -2, right: -2, width: 8, height: 8, background: "#ef4444", borderRadius: "50%" }} />
                </button>
                <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700, color: "#fff" }}>E</div>
              </div>
            </div>
            {/* CONTENIDO */}
            <div style={{ flex: 1, padding: 24 }}>
              <div style={{ display: "grid", gap: 24, gridTemplateColumns: "1fr 1fr" }}>
                {/* Ventas globales */}
                <div style={{ background: isDark ? "#111114" : "#fff", borderRadius: 12, padding: 20, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,.3)" : "0 1px 3px rgba(0,0,0,.08)", border: `1px solid ${isDark ? "#1e1e24" : "#e2e8f0"}`, gridColumn: "1 / -1" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: isDark ? "#e0e0e0" : "#1e293b" }}>Ventas globales</h3>
                    <div style={{ display: "flex", gap: 16, fontSize: 12, color: isDark ? "#9ca3af" : "#64748b" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 12, height: 12, background: "#6366f1", borderRadius: 2 }} />Actual</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 12, height: 12, background: isDark ? "#374151" : "#e2e8f0", borderRadius: 2 }} />BP</span>
                      <select value={dashboardYear} onChange={(e) => setDashboardYear(e.target.value)} style={{ border: "none", background: "transparent", fontSize: 12, cursor: "pointer", color: "inherit" }}>
                        <option value="2022">2022</option><option value="2023">2023</option><option value="2024">2024</option>
                      </select>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={280}>
                    <ComposedChart data={globalSalesData}>
                      <XAxis dataKey="month" tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#64748b" }} stroke={isDark ? "#374151" : "#e2e8f0"} />
                      <YAxis domain={[0, 80]} tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#64748b" }} stroke={isDark ? "#374151" : "#e2e8f0"} tickFormatter={(v) => `${v}k`} />
                      <Tooltip formatter={(v) => [`${v}k`, ""]} />
                      <Bar dataKey="bp" fill={isDark ? "#374151" : "#e2e8f0"} radius={[4, 4, 0, 0]} name="BP" />
                      <Bar dataKey="actual" fill="#6366f1" radius={[4, 4, 0, 0]} name="Actual" />
                      <Line type="monotone" dataKey="actual" stroke="#6366f1" strokeWidth={2} dot={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                {/* YTD */}
                <div style={{ background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)", borderRadius: 12, padding: 24, boxShadow: "0 4px 14px rgba(99,102,241,.35)", color: "#fff" }}>
                  <div style={{ fontSize: 14, opacity: 0.9, marginBottom: 4 }}>{dashboardPeriod === "ytd" ? "YTD" : dashboardPeriod === "monthly" ? "Mensual" : "Diario"}</div>
                  <div style={{ fontSize: 14, opacity: 0.8, marginBottom: 12 }}>{ytdInfo.range}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <span style={{ fontSize: 36, fontWeight: 800 }}>{ytdInfo.value}</span>
                    <span style={{ fontSize: 14, color: "#86efac", fontWeight: 600 }}>↑ {ytdInfo.change}%</span>
                  </div>
                  <div style={{ fontSize: 13, opacity: 0.9, marginTop: 8 }}>BP {ytdInfo.bp}</div>
                </div>
                {/* Modelos más vendidos */}
                <div style={{ background: isDark ? "#111114" : "#fff", borderRadius: 12, padding: 20, boxShadow: isDark ? "0 1px 3px rgba(0,0,0,.3)" : "0 1px 3px rgba(0,0,0,.08)", border: `1px solid ${isDark ? "#1e1e24" : "#e2e8f0"}`, gridColumn: "1 / -1" }}>
                  <h3 style={{ margin: "0 0 16px", fontSize: 16, fontWeight: 600, color: isDark ? "#e0e0e0" : "#1e293b" }}>Modelos más vendidos</h3>
                  <div style={{ display: "flex", gap: 16, overflowX: "auto", paddingBottom: 8 }}>
                    {TOP_MODELS.map((m) => (
                      <div key={m.name} style={{ minWidth: 160, background: isDark ? "#1a1a20" : "#f8fafc", borderRadius: 12, overflow: "hidden", border: `1px solid ${isDark ? "#2a2a30" : "#e2e8f0"}` }}>
                        <div style={{ height: 100, background: isDark ? "#2a2a30" : "#e2e8f0" }}>
                          <img src={m.img} alt={m.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        </div>
                        <div style={{ padding: 12 }}>
                          <div style={{ fontWeight: 600, fontSize: 14, color: isDark ? "#e0e0e0" : "#1e293b" }}>{m.name}</div>
                          <div style={{ fontSize: 18, fontWeight: 700, color: "#6366f1" }}>{m.sales}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </main>
      )}
      </div>
      )}
    </div>
  );
}
