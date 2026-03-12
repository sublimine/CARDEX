import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  LayoutDashboard, BarChart3, Settings, Search, Bell, TrendingUp, TrendingDown,
  ArrowUpRight, ChevronRight, DollarSign, Activity, Shield, Zap, Globe, Target,
  AlertTriangle, X, Download, Info, ShoppingBag, CreditCard, Filter,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart as RePie, Pie, Cell, ComposedChart,
} from "recharts";
import {
  PRICE_HISTORY, MONTHLY_PNL, DEAL_PIPELINE, ROUTE_PERFORMANCE, TAX_BREAKDOWN,
  HEATMAP_DATA, RADAR_OPPORTUNITIES, ALERTS, PERFORMANCE_DAILY, NLC_WATERFALL,
} from "./dashboardData.js";

const fmt = (n) => new Intl.NumberFormat("de-DE").format(n);
const fmtK = (n) => n >= 1e6 ? `€${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `€${(n / 1e3).toFixed(0)}k` : `€${n}`;

// ═══ SUB-COMPONENTS ═══

function Glass({ children, style, ...p }) {
  return <div style={{ background: "rgba(255,255,255,0.025)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: 16, ...style }} {...p}>{children}</div>;
}

function SideIcon({ icon: Icon, active, label, onClick }) {
  const [h, setH] = useState(false);
  return (
    <button onClick={onClick} title={label} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{ width: 42, height: 42, borderRadius: 12, border: "none", background: active ? "rgba(59,130,246,0.2)" : h ? "rgba(255,255,255,0.06)" : "transparent", color: active ? "#3B82F6" : h ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.3)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", transition: "all 0.2s", position: "relative" }}>
      <Icon size={19} strokeWidth={1.5} />
      {active && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: "0 3px 3px 0", background: "#3B82F6" }} />}
      {h && !active && <div style={{ position: "absolute", left: 50, top: "50%", transform: "translateY(-50%)", padding: "3px 8px", borderRadius: 6, background: "rgba(0,0,0,0.9)", color: "#fff", fontSize: 10, fontWeight: 600, whiteSpace: "nowrap", zIndex: 100 }}>{label}</div>}
    </button>
  );
}

function MiniSparkline({ data, color = "#22C55E", w = 48, h = 16 }) {
  const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rng) * (h - 2) - 1}`).join(" ");
  return <svg width={w} height={h} style={{ display: "block" }}><polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" /></svg>;
}

function ScoreBadge({ score, size = 44 }) {
  const color = score >= 90 ? "#22C55E" : score >= 70 ? "#F59E0B" : "#EF4444";
  const r = (size - 6) / 2, circ = 2 * Math.PI * r;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={2.5} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={2.5} strokeDasharray={circ} strokeDashoffset={circ * (1 - score / 100)} strokeLinecap="round" />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.28, fontWeight: 800, color, fontFamily: "'JetBrains Mono',monospace" }}>{score}</div>
    </div>
  );
}

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ padding: "8px 12px", borderRadius: 10, background: "rgba(10,14,23,0.95)", border: "1px solid rgba(255,255,255,0.08)" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "#fff", marginBottom: 3 }}>{label}</div>
      {payload.map((p, i) => <div key={i} style={{ fontSize: 10, color: p.color, display: "flex", alignItems: "center", gap: 4 }}><div style={{ width: 5, height: 5, borderRadius: "50%", background: p.color }} />{p.name}: <b>€{fmt(p.value)}</b></div>)}
    </div>
  );
};

// Heatmap cell color
function heatColor(score) {
  if (score >= 90) return "rgba(34,197,94,0.5)";
  if (score >= 80) return "rgba(34,197,94,0.3)";
  if (score >= 70) return "rgba(59,130,246,0.3)";
  if (score >= 60) return "rgba(139,92,246,0.25)";
  if (score >= 50) return "rgba(245,158,11,0.25)";
  return "rgba(239,68,68,0.2)";
}

// ═══ MAIN COMPONENT ═══

export default function MesaDeDecisiones({ onNavigate }) {
  const [time, setTime] = useState(new Date());
  const [radarFilter, setRadarFilter] = useState("all");
  const [selectedOp, setSelectedOp] = useState(null);
  const [alertsDismissed, setAlertsDismissed] = useState([]);
  const [priceRange, setPriceRange] = useState("3M");
  const [nlcHover, setNlcHover] = useState(null);

  useEffect(() => { const i = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(i); }, []);

  const liveAlerts = ALERTS.filter((_, i) => !alertsDismissed.includes(i));
  const filteredOps = radarFilter === "all" ? RADAR_OPPORTUNITIES : radarFilter === "high" ? RADAR_OPPORTUNITIES.filter(o => o.score >= 90) : RADAR_OPPORTUNITIES.filter(o => o.marginPct >= 14);
  const priceData = priceRange === "1M" ? PRICE_HISTORY.slice(-30) : priceRange === "1W" ? PRICE_HISTORY.slice(-7) : PRICE_HISTORY;

  return (
    <div style={{ position: "relative", minHeight: "100vh", width: "100%", fontFamily: "'Inter',system-ui,sans-serif", overflow: "hidden" }}>
      <div style={{ position: "fixed", inset: 0, zIndex: 0, background: "#060910" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 15% 30%, rgba(59,130,246,0.035) 0%, transparent 55%)" }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 85% 70%, rgba(139,92,246,0.025) 0%, transparent 50%)" }} />
        {/* Subtle grid */}
        <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px)", backgroundSize: "60px 60px" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, display: "flex", minHeight: "100vh" }}>
        {/* SIDEBAR */}
        <aside style={{ width: 60, padding: "14px 9px", display: "flex", flexDirection: "column", alignItems: "center", gap: 3, borderRight: "1px solid rgba(255,255,255,0.04)", background: "rgba(6,9,16,0.7)", backdropFilter: "blur(30px)", flexShrink: 0 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: "linear-gradient(135deg,#3B82F6,#8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 900, color: "#fff", marginBottom: 14 }}>CX</div>
          <SideIcon icon={LayoutDashboard} label="Home" onClick={() => onNavigate?.("home")} />
          <SideIcon icon={ShoppingBag} label="Marketplace" onClick={() => onNavigate?.("marketplace")} />
          <SideIcon icon={BarChart3} active label="Dashboard" onClick={() => onNavigate?.("dashboard")} />
          <SideIcon icon={Globe} label="Markets" onClick={() => onNavigate?.("markets")} />
          <SideIcon icon={CreditCard} label="Pricing" onClick={() => onNavigate?.("pricing")} />
          <div style={{ flex: 1 }} />
          <SideIcon icon={Bell} label="Alerts" onClick={() => { }} />
          <SideIcon icon={Settings} label="Settings" onClick={() => { }} />
          <div style={{ width: 32, height: 32, borderRadius: 8, background: "linear-gradient(135deg,#22C55E,#06B6D4)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", marginTop: 4, cursor: "pointer" }}>EC</div>
        </aside>

        {/* MAIN */}
        <main style={{ flex: 1, padding: "14px 20px 36px", overflowY: "auto", overflowX: "hidden" }}>
          {/* TOP BAR */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, gap: 10 }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>Operations Dashboard</h1>
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.25)", marginTop: 1 }}>{time.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })} · {time.toLocaleTimeString("en-GB")}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <select style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8, padding: "6px 10px", color: "rgba(255,255,255,0.5)", fontSize: 11, outline: "none", cursor: "pointer", fontFamily: "inherit" }}>
                <option>Mandato: SUVs Premium</option><option>Sedans DE→ES</option><option>Electric Fleet</option>
              </select>
              <button style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 12px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#3B82F6,#6366F1)", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}><Download size={12} /> Export</button>
            </div>
          </div>

          {/* ALERTS */}
          {liveAlerts.length > 0 && <div style={{ marginBottom: 12, display: "flex", flexDirection: "column", gap: 4 }}>
            {liveAlerts.map((a, i) => {
              const c = { critical: { bg: "rgba(239,68,68,0.05)", border: "rgba(239,68,68,0.12)", text: "#EF4444", I: AlertTriangle }, opportunity: { bg: "rgba(34,197,94,0.05)", border: "rgba(34,197,94,0.1)", text: "#22C55E", I: TrendingUp }, info: { bg: "rgba(59,130,246,0.04)", border: "rgba(59,130,246,0.08)", text: "#3B82F6", I: Info } }[a.severity];
              return <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 10, background: c.bg, border: `1px solid ${c.border}` }}>
                <c.I size={13} style={{ color: c.text, flexShrink: 0 }} /><span style={{ flex: 1, fontSize: 11, color: "rgba(255,255,255,0.7)" }}>{a.msg}</span>
                <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)" }}>{a.time}</span>
                <button onClick={() => setAlertsDismissed(p => [...p, ALERTS.indexOf(a)])} style={{ background: "none", border: "none", cursor: "pointer", color: "rgba(255,255,255,0.15)", padding: 1 }}><X size={11} /></button>
              </div>;
            })}
          </div>}

          {/* ═══ KPI ROW ═══ */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10, marginBottom: 14 }}>
            {[
              { label: "Portfolio Value", value: "€2.4M", change: 12.3, icon: DollarSign, color: "#3B82F6", spark: MONTHLY_PNL.map(p => p.cumProfit) },
              { label: "Monthly P&L", value: "+€82.4k", change: 27.1, icon: TrendingUp, color: "#22C55E", spark: MONTHLY_PNL.map(p => p.profit) },
              { label: "Active Deals", value: "234", change: 12.4, icon: Activity, color: "#8B5CF6", spark: [18, 22, 19, 25, 28, 24, 30] },
              { label: "Win Rate", value: "87.3%", change: 3.2, icon: Target, color: "#06B6D4", spark: [78, 82, 80, 85, 84, 86, 87.3] },
              { label: "Avg Margin", value: "14.2%", change: 2.1, icon: Zap, color: "#F59E0B", spark: [10, 12, 11, 13, 14, 12, 14.2] },
              { label: "Tax Savings", value: "€34.8k", change: 31.2, icon: Shield, color: "#EF4444", spark: [8, 12, 15, 18, 22, 26, 34.8] },
            ].map((s, i) => (
              <Glass key={i} style={{ padding: "14px 14px 10px", position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", top: -15, right: -15, width: 60, height: 60, borderRadius: "50%", background: s.color, opacity: 0.04, filter: "blur(20px)" }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <span style={{ fontSize: 9, fontWeight: 600, color: "rgba(255,255,255,0.35)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{s.label}</span>
                  <s.icon size={13} strokeWidth={1.5} style={{ color: s.color, opacity: 0.6 }} />
                </div>
                <div style={{ fontSize: 22, fontWeight: 800, color: "#fff", fontFamily: "'JetBrains Mono',monospace", letterSpacing: "-0.03em", marginBottom: 4 }}>{s.value}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <MiniSparkline data={s.spark} color={s.change >= 0 ? "#22C55E" : "#EF4444"} w={40} h={14} />
                  <span style={{ fontSize: 10, fontWeight: 600, color: s.change >= 0 ? "#22C55E" : "#EF4444" }}>{s.change >= 0 ? "+" : ""}{s.change}%</span>
                </div>
              </Glass>
            ))}
          </div>

          {/* ═══ TRADINGVIEW CHART + EQUITY CURVE ═══ */}
          <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 12, marginBottom: 14 }}>
            {/* TradingView Price Chart */}
            <Glass style={{ padding: "16px 16px 8px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#fff" }}>BMW 330i · Price Intelligence</h3>
                    <span style={{ padding: "2px 6px", borderRadius: 4, background: "rgba(34,197,94,0.1)", color: "#22C55E", fontSize: 9, fontWeight: 700 }}>LIVE</span>
                  </div>
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>Market avg price · 6 EU markets</span>
                </div>
                <div style={{ display: "flex", gap: 3 }}>
                  {["1W", "1M", "3M"].map(r => (
                    <button key={r} onClick={() => setPriceRange(r)} style={{ padding: "3px 8px", borderRadius: 6, border: "none", fontSize: 10, fontWeight: 600, cursor: "pointer", background: priceRange === r ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.03)", color: priceRange === r ? "#3B82F6" : "rgba(255,255,255,0.3)" }}>{r}</button>
                  ))}
                </div>
              </div>
              {/* Price + MA chart */}
              <ResponsiveContainer width="100%" height={180}>
                <ComposedChart data={priceData}>
                  <defs>
                    <linearGradient id="gPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#3B82F6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.03)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9 }} axisLine={false} tickLine={false} interval={priceRange === "1W" ? 0 : priceRange === "1M" ? 4 : 14} />
                  <YAxis tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} width={30} domain={["dataMin-500", "dataMax+500"]} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="price" stroke="#3B82F6" strokeWidth={2} fill="url(#gPrice)" name="Price" />
                  <Line type="monotone" dataKey="ma20" stroke="#F59E0B" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="MA20" connectNulls={false} />
                </ComposedChart>
              </ResponsiveContainer>
              {/* Volume bars */}
              <ResponsiveContainer width="100%" height={40}>
                <BarChart data={priceData}>
                  <XAxis dataKey="date" hide />
                  <Bar dataKey="volume" fill="rgba(59,130,246,0.2)" radius={[1, 1, 0, 0]} maxBarSize={6} />
                </BarChart>
              </ResponsiveContainer>
            </Glass>

            {/* Equity Curve (Cumulative P&L) */}
            <Glass style={{ padding: "16px 16px 8px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#fff" }}>Portfolio Equity Curve</h3>
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>Cumulative P&L · target: €500k</span>
                </div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "#22C55E", fontFamily: "'JetBrains Mono',monospace" }}>€{fmt(417940)}</div>
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={MONTHLY_PNL}>
                  <defs>
                    <linearGradient id="gEquity" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22C55E" stopOpacity={0.2} />
                      <stop offset="100%" stopColor="#22C55E" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.03)" vertical={false} />
                  <XAxis dataKey="month" tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} width={30} />
                  <Tooltip content={<ChartTip />} />
                  <Area type="monotone" dataKey="cumProfit" stroke="#22C55E" strokeWidth={2} fill="url(#gEquity)" name="Cumulative P&L" />
                  {/* Target line at 500k */}
                  <Line type="monotone" dataKey={() => 500000} stroke="rgba(255,255,255,0.1)" strokeWidth={1} strokeDasharray="6 3" dot={false} name="Target" />
                </AreaChart>
              </ResponsiveContainer>
            </Glass>
          </div>

          {/* ═══ HEATMAP + NLC WATERFALL ═══ */}
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12, marginBottom: 14 }}>
            {/* Market Opportunity Heatmap */}
            <Glass style={{ padding: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#fff" }}>Market Opportunity Matrix</h3>
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>AI profitability score by model × destination</span>
                </div>
                <div style={{ display: "flex", gap: 8, fontSize: 9, color: "rgba(255,255,255,0.25)" }}>
                  {[{ c: "rgba(239,68,68,0.4)", l: "Low" }, { c: "rgba(245,158,11,0.4)", l: "Med" }, { c: "rgba(59,130,246,0.4)", l: "Good" }, { c: "rgba(34,197,94,0.5)", l: "High" }].map(x =>
                    <span key={x.l} style={{ display: "flex", alignItems: "center", gap: 3 }}><div style={{ width: 8, height: 8, borderRadius: 2, background: x.c }} />{x.l}</span>
                  )}
                </div>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 3 }}>
                  <thead><tr>
                    <th style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", fontWeight: 500, textAlign: "left", padding: "0 6px 6px" }}></th>
                    {HEATMAP_DATA.countries.map(c => <th key={c} style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", fontWeight: 600, textAlign: "center", padding: "0 4px 6px" }}>{c}</th>)}
                  </tr></thead>
                  <tbody>{HEATMAP_DATA.models.map((model, mi) => (
                    <tr key={model}>
                      <td style={{ fontSize: 10, color: "rgba(255,255,255,0.5)", fontWeight: 500, padding: "0 6px", whiteSpace: "nowrap" }}>{model}</td>
                      {HEATMAP_DATA.scores[mi].map((score, ci) => (
                        <td key={ci} style={{ padding: 2 }}>
                          <div style={{
                            textAlign: "center", padding: "6px 4px", borderRadius: 6,
                            background: heatColor(score), fontSize: 11, fontWeight: 700,
                            color: score >= 80 ? "#fff" : "rgba(255,255,255,0.6)",
                            fontFamily: "'JetBrains Mono',monospace", cursor: "pointer",
                            transition: "all 0.15s", border: "1px solid transparent",
                          }}
                            onMouseEnter={e => { e.currentTarget.style.border = "1px solid rgba(255,255,255,0.2)"; e.currentTarget.style.transform = "scale(1.05)"; }}
                            onMouseLeave={e => { e.currentTarget.style.border = "1px solid transparent"; e.currentTarget.style.transform = "none"; }}
                          >{score}</div>
                        </td>
                      ))}
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Glass>

            {/* NLC Waterfall */}
            <Glass style={{ padding: "16px" }}>
              <h3 style={{ margin: "0 0 4px 0", fontSize: 14, fontWeight: 700, color: "#fff" }}>Net Landed Cost Breakdown</h3>
              <span style={{ fontSize: 10, color: "rgba(255,255,255,0.25)" }}>BMW 330i · DE → ES</span>
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 4 }}>
                {NLC_WATERFALL.map((item, i) => {
                  const maxVal = 38200;
                  const barWidth = (item.value / maxVal) * 100;
                  const isNeg = !item.isTotal && i > 0;
                  return (
                    <div key={i} onMouseEnter={() => setNlcHover(i)} onMouseLeave={() => setNlcHover(null)}
                      style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", borderRadius: 6, transition: "all 0.15s", background: nlcHover === i ? "rgba(255,255,255,0.03)" : "transparent" }}>
                      <span style={{ width: 65, fontSize: 10, color: item.isTotal ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.4)", fontWeight: item.isTotal ? 600 : 400, flexShrink: 0 }}>{item.name}</span>
                      <div style={{ flex: 1, height: 18, borderRadius: 4, background: "rgba(255,255,255,0.03)", overflow: "hidden" }}>
                        <div style={{ width: `${barWidth}%`, height: "100%", borderRadius: 4, background: `${item.color}60`, transition: "width 0.5s" }} />
                      </div>
                      <span style={{ width: 55, fontSize: 11, fontWeight: 700, color: item.color, fontFamily: "'JetBrains Mono',monospace", textAlign: "right" }}>
                        {isNeg ? "+" : ""}€{fmt(item.value)}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 8, background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.1)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>Net Margin</span>
                <span style={{ fontSize: 16, fontWeight: 800, color: "#22C55E", fontFamily: "'JetBrains Mono',monospace" }}>+€4.405 (11.0%)</span>
              </div>
            </Glass>
          </div>

          {/* ═══ PIPELINE + ROUTES + TAX ═══ */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 0.8fr", gap: 12, marginBottom: 14 }}>
            {/* Pipeline */}
            <Glass style={{ padding: "14px 14px 10px" }}>
              <h3 style={{ margin: "0 0 10px 0", fontSize: 13, fontWeight: 700, color: "#fff" }}>Deal Pipeline</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {DEAL_PIPELINE.map(s => {
                  const mx = Math.max(...DEAL_PIPELINE.map(x => x.count));
                  return <div key={s.stage} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", width: 55, flexShrink: 0 }}>{s.stage}</span>
                    <div style={{ flex: 1, height: 20, borderRadius: 5, background: "rgba(255,255,255,0.03)", overflow: "hidden" }}>
                      <div style={{ width: `${(s.count / mx) * 100}%`, height: "100%", borderRadius: 5, background: `linear-gradient(90deg,${s.color}30,${s.color}70)`, display: "flex", alignItems: "center", paddingLeft: 6 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#fff", fontFamily: "'JetBrains Mono',monospace" }}>{s.count}</span>
                      </div>
                    </div>
                    <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono',monospace", width: 45, textAlign: "right" }}>{fmtK(s.value)}</span>
                  </div>;
                })}
              </div>
            </Glass>

            {/* Routes */}
            <Glass style={{ padding: "14px 14px 10px" }}>
              <h3 style={{ margin: "0 0 10px 0", fontSize: 13, fontWeight: 700, color: "#fff" }}>Route Performance</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {ROUTE_PERFORMANCE.map(r => (
                  <div key={r.route} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 6px", borderRadius: 8, cursor: "pointer", transition: "all 0.15s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <span style={{ fontSize: 14, width: 40 }}>{r.flag}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "#fff" }}>{r.route}</div>
                      <div style={{ fontSize: 9, color: "rgba(255,255,255,0.25)" }}>{r.volume} deals · {r.avgDays}d avg</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#fff", fontFamily: "'JetBrains Mono',monospace" }}>{r.margin}%</div>
                      <span style={{ fontSize: 10, fontWeight: 600, color: r.trend >= 0 ? "#22C55E" : "#EF4444" }}>{r.trend >= 0 ? "+" : ""}{r.trend}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </Glass>

            {/* Tax */}
            <Glass style={{ padding: "14px" }}>
              <h3 style={{ margin: "0 0 6px 0", fontSize: 13, fontWeight: 700, color: "#fff" }}>Tax Status</h3>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 120 }}>
                <ResponsiveContainer width={110} height={110}>
                  <RePie><Pie data={TAX_BREAKDOWN} innerRadius={36} outerRadius={50} paddingAngle={3} dataKey="value" startAngle={90} endAngle={-270}>
                    {TAX_BREAKDOWN.map((e, i) => <Cell key={i} fill={e.color} stroke="none" />)}
                  </Pie></RePie>
                </ResponsiveContainer>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                {TAX_BREAKDOWN.map(t => <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 6, height: 6, borderRadius: 1, background: t.color }} />
                  <span style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", flex: 1 }}>{t.name}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", fontFamily: "'JetBrains Mono',monospace" }}>{t.value}%</span>
                </div>)}
              </div>
            </Glass>
          </div>

          {/* ═══ DEAL RADAR ═══ */}
          <Glass style={{ padding: "16px 18px 12px", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#22C55E", boxShadow: "0 0 8px #22C55E60", animation: "glowPulse 2s ease-in-out infinite" }} />
                <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#fff" }}>Deal Radar</h3>
                <span style={{ padding: "2px 7px", borderRadius: 5, background: "rgba(34,197,94,0.08)", color: "#22C55E", fontSize: 10, fontWeight: 600 }}>{filteredOps.length} live</span>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                {[{ id: "all", l: "All" }, { id: "high", l: "Score 90+" }, { id: "margin", l: "Margin 14%+" }].map(f =>
                  <button key={f.id} onClick={() => setRadarFilter(f.id)} style={{ padding: "4px 10px", borderRadius: 6, border: "none", fontSize: 10, fontWeight: 600, cursor: "pointer", background: radarFilter === f.id ? "rgba(59,130,246,0.12)" : "rgba(255,255,255,0.03)", color: radarFilter === f.id ? "#3B82F6" : "rgba(255,255,255,0.3)" }}>{f.l}</button>
                )}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
              {filteredOps.map(op => (
                <div key={op.id} onClick={() => setSelectedOp(selectedOp === op.id ? null : op.id)} style={{
                  borderRadius: 14, overflow: "hidden", cursor: "pointer", transition: "all 0.25s",
                  background: selectedOp === op.id ? "rgba(59,130,246,0.06)" : "rgba(255,255,255,0.015)",
                  border: `1px solid ${selectedOp === op.id ? "rgba(59,130,246,0.15)" : "rgba(255,255,255,0.04)"}`,
                }}
                  onMouseEnter={e => { if (selectedOp !== op.id) e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
                  onMouseLeave={e => { if (selectedOp !== op.id) e.currentTarget.style.background = "rgba(255,255,255,0.015)"; }}
                >
                  <div style={{ display: "flex", height: 90 }}>
                    <div style={{ width: 110, height: "100%", overflow: "hidden", flexShrink: 0 }}>
                      <img src={op.image} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.65) contrast(1.1)" }} />
                    </div>
                    <div style={{ flex: 1, padding: "8px 12px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                          <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", fontFamily: "'JetBrains Mono',monospace" }}>{op.id}</span>
                          <span style={{ padding: "1px 5px", borderRadius: 3, background: op.taxStatus === "DEDUCTIBLE" ? "rgba(34,197,94,0.08)" : "rgba(59,130,246,0.08)", color: op.taxStatus === "DEDUCTIBLE" ? "#22C55E" : "#3B82F6", fontSize: 8, fontWeight: 700 }}>{op.taxStatus}</span>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>{op.vehicle}</div>
                        <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)" }}>{op.year} · {fmt(op.km)}km · {op.origin}→{op.dest}</div>
                      </div>
                      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
                        <div style={{ fontSize: 15, fontWeight: 800, color: "#22C55E", fontFamily: "'JetBrains Mono',monospace" }}>+€{fmt(op.margin)}</div>
                        <ScoreBadge score={op.score} size={38} />
                      </div>
                    </div>
                  </div>
                  {selectedOp === op.id && (
                    <div style={{ padding: "10px 12px", borderTop: "1px solid rgba(255,255,255,0.05)", display: "flex", gap: 16, animation: "slideDown 0.25s ease-out" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, flex: 1 }}>
                        {[["Buy", op.buyPrice, "#fff"], ["Sell", op.sellPrice, "#fff"], ["Margin %", `${op.marginPct}%`, "#22C55E"], ["Days", `${op.daysOnMarket}d`, "#fff"]].map(([l, v, c]) =>
                          <div key={l}><span style={{ fontSize: 9, color: "rgba(255,255,255,0.25)" }}>{l}</span><div style={{ fontSize: 13, fontWeight: 700, color: c, fontFamily: "'JetBrains Mono',monospace" }}>{typeof v === "number" ? `€${fmt(v)}` : v}</div></div>
                        )}
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <button style={{ padding: "7px 16px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#22C55E,#16A34A)", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>Execute</button>
                        <button style={{ padding: "7px 16px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.03)", color: "rgba(255,255,255,0.5)", fontSize: 11, fontWeight: 500, cursor: "pointer" }}>Analyze</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Glass>

          {/* ═══ DAILY PERFORMANCE ═══ */}
          <Glass style={{ padding: "14px 14px 6px" }}>
            <h3 style={{ margin: "0 0 10px 0", fontSize: 13, fontWeight: 700, color: "#fff" }}>Daily Profit · Last 30 Days</h3>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={PERFORMANCE_DAILY} barGap={1}>
                <CartesianGrid stroke="rgba(255,255,255,0.02)" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: "rgba(255,255,255,0.15)", fontSize: 8 }} axisLine={false} tickLine={false} interval={4} />
                <Tooltip content={<ChartTip />} />
                <Bar dataKey="profit" name="Profit" fill="#3B82F6" radius={[2, 2, 0, 0]} maxBarSize={12} opacity={0.6} />
              </BarChart>
            </ResponsiveContainer>
          </Glass>
        </main>
      </div>

      <style>{`
        @keyframes glowPulse { 0%,100%{box-shadow:0 0 8px rgba(34,197,94,0.3)} 50%{box-shadow:0 0 16px rgba(34,197,94,0.6)} }
        @keyframes slideDown { from{opacity:0;max-height:0} to{opacity:1;max-height:200px} }
        main::-webkit-scrollbar{width:3px} main::-webkit-scrollbar-track{background:transparent} main::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.05);border-radius:2px}
        select option{background:#0A0E17;color:#fff}
      `}</style>
    </div>
  );
}
