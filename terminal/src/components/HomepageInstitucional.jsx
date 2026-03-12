import React, { useState, useEffect, useRef } from "react";
import {
  Search, Bell, Settings, LayoutDashboard, ShoppingBag, BarChart3,
  CreditCard, Globe, ArrowRight, Activity, Car, Shield, Radar, Bot, LineChart
} from "lucide-react";

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const TRANSACTION_POOL = [
  { vehicle: "BMW 530e xDrive", route: "DE → ES", amount: 38420, margin: 4210, time: 0 },
  { vehicle: "Audi Q5 S-Line", route: "NL → FR", amount: 42100, margin: 3890, time: 0 },
  { vehicle: "Mercedes GLC 300", route: "BE → ES", amount: 51200, margin: 6100, time: 0 },
  { vehicle: "VW Tiguan R-Line", route: "DE → FR", amount: 34800, margin: 2740, time: 0 },
  { vehicle: "Porsche Cayenne S", route: "CH → DE", amount: 68900, margin: 9200, time: 0 },
  { vehicle: "BMW X3 M40i", route: "DE → NL", amount: 55300, margin: 5800, time: 0 },
];

const PLATFORM_CAPABILITIES = [
  {
    icon: Radar,
    title: "Net Landed Cost Engine",
    desc: "Real-time tax, logistics & FX computation across 6 EU markets. Know the true cost before you buy.",
    stat: "< 50ms",
    statLabel: "Computation",
    color: "#3B82F6",
  },
  {
    icon: Bot,
    title: "AI Scoring · 98% Accuracy",
    desc: "Machine learning model scores every vehicle on profitability, risk, and market liquidity in real time.",
    stat: "12.4M",
    statLabel: "Assets analyzed",
    color: "#8B5CF6",
  },
  {
    icon: LineChart,
    title: "Market Intelligence",
    desc: "Live pricing feeds, auction data, and demand signals from every major European wholesale market.",
    stat: "6",
    statLabel: "EU Markets",
    color: "#22C55E",
  },
];

const fmt = (n) => new Intl.NumberFormat("de-DE").format(n);

// ─── EFFECTS & COMPONENTS ────────────────────────────────────────────────────
function Glass({ children, style, hover = false, onClick, ...props }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => hover && setHovered(true)}
      onMouseLeave={() => hover && setHovered(false)}
      style={{
        background: hovered ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.035)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        border: `1px solid ${hovered ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.06)"}`,
        borderRadius: 20,
        transition: "all 0.35s cubic-bezier(0.4,0,0.2,1)",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
}

function SideIcon({ icon: Icon, active, label, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      title={label}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: 44, height: 44, borderRadius: 14, border: "none",
        background: active ? "rgba(59,130,246,0.2)" : hovered ? "rgba(255,255,255,0.06)" : "transparent",
        color: active ? "#3B82F6" : hovered ? "rgba(255,255,255,0.7)" : "rgba(255,255,255,0.35)",
        display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", transition: "all 0.2s", position: "relative",
      }}
    >
      <Icon size={20} strokeWidth={1.5} />
      {active && <div style={{ position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)", width: 3, height: 20, borderRadius: "0 3px 3px 0", background: "#3B82F6" }} />}
      {hovered && !active && <div style={{ position: "absolute", left: 52, top: "50%", transform: "translateY(-50%)", padding: "4px 10px", borderRadius: 8, background: "rgba(0,0,0,0.85)", color: "#fff", fontSize: 11, fontWeight: 600, whiteSpace: "nowrap", pointerEvents: "none", zIndex: 100 }}>{label}</div>}
    </button>
  );
}

function AnimatedCounter({ value, prefix = "", suffix = "" }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let start = null;
    const duration = 2000;
    const animate = (t) => {
      if (!start) start = t;
      const progress = Math.min((t - start) / duration, 1);
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      setCount(value * easeOutQuart);
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, [value]);
  return <span>{prefix}{count > 1000 ? fmt(Math.round(count)) : count.toFixed(1)}{suffix}</span>;
}

// ─── MAIN COMPONENT: CINEMATIC V6 ─────────────────────────────────────────────
export default function HomepageInstitucional({ onNavigate }) {
  const [time, setTime] = useState(new Date());
  const [searchFocused, setSearchFocused] = useState(false);
  const [transactions, setTransactions] = useState([]);
  const txIndexRef = useRef(0);

  useEffect(() => {
    const i = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(i);
  }, []);

  useEffect(() => {
    const initial = TRANSACTION_POOL.slice(0, 5).map((tx, i) => ({ ...tx, id: `TX-${8847 - i}`, key: Date.now() + i, entering: false }));
    setTransactions(initial);
    txIndexRef.current = 5;

    const interval = setInterval(() => {
      const idx = txIndexRef.current % TRANSACTION_POOL.length;
      txIndexRef.current++;
      const newTx = { ...TRANSACTION_POOL[idx], id: `TX-${8847 + txIndexRef.current}`, key: Date.now(), entering: true };
      
      setTransactions(prev => {
        const next = [newTx, ...prev.slice(0, 4)];
        return next.map((tx, i) => ({ ...tx, entering: i === 0 }));
      });

      setTimeout(() => {
        setTransactions(prev => prev.map(tx => ({ ...tx, entering: false })));
      }, 600);
    }, 3500);

    return () => clearInterval(interval);
  }, []);

  const greeting = (() => {
    const h = time.getHours();
    if (h < 12) return "Good morning";
    if (h < 18) return "Good afternoon";
    return "Good evening";
  })();

  return (
    <div style={{ position: "relative", minHeight: "100vh", width: "100%", fontFamily: "'Inter', system-ui, -apple-system, sans-serif", overflow: "hidden", background: "#0A0E17", color: "#fff" }}>
      
      {/* ═══ V6 CINEMATIC HERO BACKGROUND ═══ */}
      <div style={{ position: "fixed", inset: 0, zIndex: 0 }}>
        <img src="/hero-car.png" alt="" style={{
          width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 30%",
          filter: "brightness(0.3) saturate(0.8) contrast(1.1)", transform: "scale(1.02)",
        }} />
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 70% 50%, rgba(59,130,246,0.15) 0%, transparent 60%)" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, rgba(10,14,23,0.95) 0%, rgba(10,14,23,0.6) 40%, transparent 80%)" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(180deg, rgba(10,14,23,0.4) 0%, rgba(10,14,23,0.9) 100%)" }} />
      </div>

      <div style={{ position: "relative", zIndex: 1, display: "flex", minHeight: "100vh" }}>
        
        {/* ═══ SIDEBAR ═══ */}
        <aside style={{
          width: 64, padding: "16px 10px", display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
          borderRight: "1px solid rgba(255,255,255,0.04)", background: "rgba(10,14,23,0.4)", backdropFilter: "blur(20px)", flexShrink: 0
        }}>
          <div style={{ width: 38, height: 38, borderRadius: 11, background: "linear-gradient(135deg, #3B82F6, #8B5CF6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 900, color: "#fff", marginBottom: 16 }}>CX</div>
          <SideIcon icon={LayoutDashboard} active label="Home" onClick={() => onNavigate?.("home")} />
          <SideIcon icon={ShoppingBag} label="Marketplace" onClick={() => onNavigate?.("marketplace")} />
          <SideIcon icon={BarChart3} label="Dashboard" onClick={() => onNavigate?.("dashboard")} />
          <SideIcon icon={Globe} label="Markets" onClick={() => onNavigate?.("markets")} />
          <SideIcon icon={CreditCard} label="Pricing" onClick={() => onNavigate?.("pricing")} />
          <div style={{ flex: 1 }} />
          <SideIcon icon={Bell} label="Notifications" onClick={() => {}} />
          <SideIcon icon={Settings} label="Settings" onClick={() => {}} />
          <div style={{ width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg, #22C55E, #06B6D4)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#fff", marginTop: 6, cursor: "pointer" }}>EC</div>
        </aside>

        {/* ═══ MAIN SCREEN ═══ */}
        <main style={{ flex: 1, padding: "24px 40px", overflowY: "auto", overflowX: "hidden" }}>
          
          {/* TOP NAV HEADER */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 60 }}>
            <div>
              <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.02em" }}>
                {greeting}, <span style={{ background: "linear-gradient(135deg, #3B82F6, #8B5CF6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Trader</span>
              </div>
              <div style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", marginTop: 4 }}>
                {time.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })} · {time.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
            
            <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
               <div style={{
                 display: "flex", alignItems: "center", gap: 12,
                 background: searchFocused ? "rgba(255,255,255,0.08)" : "rgba(255,255,255,0.04)",
                 border: `1px solid ${searchFocused ? "rgba(59,130,246,0.4)" : "rgba(255,255,255,0.06)"}`,
                 borderRadius: 16, padding: "0 16px", height: 48, width: 360, transition: "all 0.3s",
                 boxShadow: searchFocused ? "0 0 20px rgba(59,130,246,0.2)" : "none"
               }}>
                 <Search size={18} color="rgba(255,255,255,0.4)" />
                 <input placeholder="Search vehicles, markets..." onFocus={() => setSearchFocused(true)} onBlur={() => setSearchFocused(false)} style={{ background: "none", border: "none", outline: "none", color: "#fff", fontSize: 14, width: "100%" }} />
                 <kbd style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: 5, border: "1px solid rgba(255,255,255,0.06)", fontFamily: "monospace" }}>⌘K</kbd>
               </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", borderRadius: 12, background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.2)" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#22C55E", boxShadow: "0 0 10px #22C55E" }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#22C55E", letterSpacing: 1 }}>LIVE NETWORK</span>
            </div>
          </div>

          {/* V6 HERO CONTENT (Split Layout) */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", minHeight: "calc(100vh - 240px)" }}>
            
            {/* LEFT: Cinematic Typography */}
            <div style={{ flex: 1, maxWidth: 640 }}>
              <div style={{ display: "inline-block", padding: "6px 12px", borderRadius: 8, background: "rgba(59, 130, 246, 0.15)", border: "1px solid rgba(59, 130, 246, 0.3)", color: "#3B82F6", fontSize: 12, fontWeight: 700, letterSpacing: 1, marginBottom: 24 }}>
                INSTITUTIONAL GRADE
              </div>
              <h1 style={{ fontSize: 88, fontWeight: 900, lineHeight: 1.05, letterSpacing: "-0.04em", margin: "0 0 24px 0" }}>
                Market<br />
                <span style={{ background: "linear-gradient(135deg, #fff 0%, rgba(255,255,255,0.4) 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Intelligence.</span>
              </h1>
              <p style={{ fontSize: 20, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginBottom: 48, maxWidth: 480 }}>
                Next-generation wholesale orchestration. Cross-border vehicle arbitrage, automated DNA verification, and execution feeds.
              </p>
              
              <div style={{ display: "flex", gap: 16 }}>
                <button style={{ background: "#fff", color: "#000", padding: "18px 36px", borderRadius: 12, fontWeight: 700, fontSize: 16, cursor: "pointer", border: "none", transition: "transform 0.2s", ":active": { transform: "scale(0.98)" } }}>
                  Enter Platform
                </button>
                <button style={{ background: "rgba(255,255,255,0.05)", color: "#fff", padding: "18px 36px", borderRadius: 12, fontWeight: 600, fontSize: 16, border: "1px solid rgba(255,255,255,0.1)", cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                  View Systems <ArrowRight size={18} />
                </button>
              </div>
            </div>

            {/* RIGHT: Floating Dashboard Panels (V6 Standard Mockup) */}
            <div style={{ width: 540, display: "flex", flexDirection: "column", gap: 24, paddingRight: 20 }}>
              
              {/* Daily Overview */}
              <Glass style={{ padding: 24, boxShadow: "0 20px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
                   <div>
                     <div style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Active Execution Yield</div>
                     <div style={{ fontSize: 42, fontWeight: 900, fontFamily: "monospace", letterSpacing: "-1px" }}>
                       €<AnimatedCounter value={4.2} suffix="M" />
                     </div>
                   </div>
                   <div style={{ padding: "8px 12px", background: "rgba(74,222,128,0.1)", borderRadius: 10, border: "1px solid rgba(74,222,128,0.2)", display: "flex", alignItems: "center", gap: 6 }}>
                     <Activity size={16} color="#4ade80" />
                     <span style={{ fontSize: 13, color: "#4ade80", fontWeight: 800 }}>+12.4%</span>
                   </div>
                </div>

                {/* CSS Area Chart Mockup */}
                <div style={{ height: 80, width: "100%", position: "relative" }}>
                   <svg viewBox="0 0 100 30" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
                     <defs>
                       <linearGradient id="gV6" x1="0" y1="0" x2="0" y2="1">
                         <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.4" />
                         <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
                       </linearGradient>
                     </defs>
                     <path d="M0,30 L0,20 Q10,15 20,25 T40,10 T60,18 T80,5 T100,15 L100,30 Z" fill="url(#gV6)" />
                     <path d="M0,20 Q10,15 20,25 T40,10 T60,18 T80,5 T100,15" fill="none" stroke="#3B82F6" strokeWidth="2" vectorEffect="non-scaling-stroke" />
                   </svg>
                </div>
              </Glass>

              {/* Live Execution Feed */}
              <Glass style={{ padding: 24, height: 360, display: "flex", flexDirection: "column", boxShadow: "0 20px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                   <div style={{ fontSize: 12, fontWeight: 800, color: "#fff", textTransform: "uppercase", letterSpacing: 1 }}>Arbitrage Execution Feed</div>
                   <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#ef4444", animation: "pulseLive 2s infinite" }} />
                </div>
                
                <div style={{ flex: 1, overflow: "hidden", position: "relative", maskImage: "linear-gradient(to bottom, black 70%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 70%, transparent 100%)" }}>
                   <div style={{ display: "flex", flexDirection: "column", gap: 12, position: "absolute", top: 0, left: 0, right: 0 }}>
                     {transactions.map((tx) => (
                        <div key={tx.key} style={{
                           padding: "16px", background: "rgba(255,255,255,0.03)", borderRadius: 16, border: "1px solid rgba(255,255,255,0.05)",
                           display: "flex", alignItems: "center", justifyContent: "space-between",
                           transition: "all 0.5s cubic-bezier(0.4, 0, 0.2, 1)",
                           transform: tx.entering ? "translateY(-20px) scale(0.98)" : "translateY(0) scale(1)",
                           opacity: tx.entering ? 0 : 1,
                        }}>
                           <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                             <div style={{ width: 40, height: 40, borderRadius: 10, background: "rgba(255,255,255,0.05)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                               <Car size={20} color="rgba(255,255,255,0.5)" />
                             </div>
                             <div>
                               <div style={{ fontSize: 14, fontWeight: 700, color: "#fff", marginBottom: 4 }}>{tx.vehicle}</div>
                               <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>{tx.id} • {tx.route}</div>
                             </div>
                           </div>
                           <div style={{ textAlign: "right" }}>
                             <div style={{ fontSize: 15, fontWeight: 800, color: "#fff", fontFamily: "monospace", letterSpacing: "-0.5px" }}>€{fmt(tx.amount)}</div>
                             <div style={{ padding: "4px 8px", background: "rgba(74,222,128,0.1)", borderRadius: 6, display: "inline-block", marginTop: 6 }}>
                               <div style={{ fontSize: 11, fontWeight: 800, color: "#4ade80", fontFamily: "monospace" }}>+€{fmt(tx.margin)}</div>
                             </div>
                           </div>
                        </div>
                     ))}
                   </div>
                </div>
              </Glass>

            </div>
          </div>
          
          {/* SECTION 2: PLATFORM CAPABILITIES */}
          <div style={{ marginTop: 100, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24 }}>
             {PLATFORM_CAPABILITIES.map((mod, i) => (
               <Glass key={i} hover style={{ padding: 32 }}>
                 <div style={{ width: 48, height: 48, borderRadius: 12, background: `${mod.color}15`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 24 }}>
                   <mod.icon size={24} color={mod.color} />
                 </div>
                 <h3 style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 12 }}>{mod.title}</h3>
                 <p style={{ fontSize: 14, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginBottom: 24 }}>{mod.desc}</p>
                 <div style={{ paddingTop: 20, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                   <div style={{ fontSize: 24, fontWeight: 800, color: mod.color, fontFamily: "monospace" }}>{mod.stat}</div>
                   <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", marginTop: 4, textTransform: "uppercase", letterSpacing: 1 }}>{mod.statLabel}</div>
                 </div>
               </Glass>
             ))}
          </div>

        </main>
      </div>

      <style>
        {`
          @keyframes pulseLive { 0%, 100% { opacity: 1; box-shadow: 0 0 12px #ef4444; } 50% { opacity: 0.4; box-shadow: 0 0 4px #ef4444; } }
          @keyframes glowPulse { 0%, 100% { box-shadow: 0 0 12px #22C55E80; } 50% { box-shadow: 0 0 24px #22C55E; } }
        `}
      </style>
    </div>
  );
}
