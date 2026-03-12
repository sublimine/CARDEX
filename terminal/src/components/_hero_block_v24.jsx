import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── HELPER ──────────────────────────────────────────────────────────────────
const fmt = (n) => new Intl.NumberFormat("de-DE").format(n);

// ─── 3D ILLUMINATED CHART ─────────────────────────────────────────────────────
// Redesigned from standard candlesticks to a highly professional, modern "density map" / area chart look
function AdvancedChartWidget() {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#06070a", borderRadius: 16, border: "1px solid rgba(255,255,255,0.05)", overflow: "hidden", position: "relative", boxShadow: "inset 0 10px 30px rgba(0,0,0,0.8)" }}>
      {/* Background Grid */}
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)", backgroundSize: "40px 40px", zIndex: 1 }}/>
      
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)", zIndex: 2 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <span style={{ fontSize: 16, fontWeight: 900, color: "#fff", letterSpacing: "-0.02em" }}>BMW 330i</span>
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", fontWeight: 600 }}>DE ➔ ES Model</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {["1H", "1D", "1W", "1M"].map((t, i) => (
            <div key={t} style={{ fontSize: 11, fontWeight: 700, padding: "4px 8px", borderRadius: 6, background: i === 1 ? "rgba(41, 98, 255, 0.2)" : "transparent", color: i === 1 ? "#fff" : "rgba(255,255,255,0.5)", cursor: "pointer" }}>{t}</div>
          ))}
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div style={{ flex: 1, position: "relative", zIndex: 2 }}>
         {/* Y-Axis Labels */}
         <div style={{ position: "absolute", right: 12, top: 12, bottom: 12, display: "flex", flexDirection: "column", justifyContent: "space-between", fontSize: 10, color: "rgba(255,255,255,0.3)", fontFamily: "monospace", zIndex: 10 }}>
            <span>€35.2k</span>
            <span>€34.8k</span>
            <span>€34.4k</span>
            <span>€34.0k</span>
         </div>
         
         {/* The "Area" Volume (SVG) */}
         <div style={{ position: "absolute", left: 0, right: 60, bottom: 0, height: "80%" }}>
            <svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 100 100">
              <defs>
                <linearGradient id="chartGlow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2962ff" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#2962ff" stopOpacity="0.0" />
                </linearGradient>
                <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#2962ff" />
                  <stop offset="50%" stopColor="#4ade80" />
                  <stop offset="100%" stopColor="#2962ff" />
                </linearGradient>
              </defs>
              {/* Animated Path */}
              <path d="M0,80 Q10,75 20,60 T40,50 T60,20 T80,30 T100,10 L100,100 L0,100 Z" fill="url(#chartGlow)" />
              <path d="M0,80 Q10,75 20,60 T40,50 T60,20 T80,30 T100,10" fill="none" stroke="url(#lineGrad)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" style={{ filter: "drop-shadow(0 0 8px rgba(41, 98, 255, 0.8))" }} />
              
              {/* Highlight Pulse Point */}
              <circle cx="100" cy="10" r="3" fill="#fff" style={{ filter: "drop-shadow(0 0 10px #fff)" }} />
            </svg>
         </div>

         {/* Volume Bars (Bottom) */}
         <div style={{ position: "absolute", left: 0, right: 60, bottom: 0, height: "20%", display: "flex", alignItems: "flex-end", gap: "2%", padding: "0 2%" }}>
            {[30, 45, 20, 60, 80, 40, 50, 90, 30, 55, 75, 100].map((h, i) => (
              <div key={i} style={{ flex: 1, height: `${h}%`, background: "rgba(255,255,255,0.08)", borderRadius: "2px 2px 0 0" }} />
            ))}
         </div>
      </div>
    </div>
  );
}

// ─── HERO BLOCK V24 ───────────────────────────────────────────────────────────

export default function HeroBlockV24() {
  return (
    <section style={{ position: "relative", marginBottom: 0, height: 950, overflow: "visible", fontFamily: "Inter, sans-serif" }}>
      
      {/* ── AMBIENT STUDIO ── */}
      <div style={{ position: "absolute", inset: -200, background: "radial-gradient(ellipse at 50% 30%, #302b63 0%, #0f0b20 50%, #05040a 100%)", zIndex: 0 }} />
      
      <style>
        {`
          @keyframes floatStructural { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
          @keyframes swipeInertiaMvq {
            0%, 15%   { transform: translateY(0); animation-timing-function: cubic-bezier(0.1, 0.9, 0.2, 1); }
            20%, 45%  { transform: translateY(-25%); animation-timing-function: cubic-bezier(0.1, 0.9, 0.2, 1); }
            50%, 80%  { transform: translateY(-50%); animation-timing-function: cubic-bezier(0.1, 0.9, 0.2, 1); }
            85%, 100% { transform: translateY(0); animation-timing-function: ease-in-out; }
          }
          @keyframes pulseLive { 0%, 100%{ opacity: 1; box-shadow: 0 0 15px #ef4444; } 50%{ opacity: 0.4; box-shadow: 0 0 5px #ef4444; } }
          
          /* The floating maquetas with drop shadow instead of a box */
          .maqueta-toy {
             filter: drop-shadow(0 20px 20px rgba(0,0,0,0.6)) brightness(1.1) contrast(1.2);
             transition: transform 0.3s;
          }
        `}
      </style>

      <div style={{ position: "relative", zIndex: 10, height: "100%", display: "flex", alignItems: "center", paddingLeft: 80, paddingRight: 40, maxWidth: 1800, margin: "0 auto" }}>
        
        {/* ═══════════════ LEFT CONTENT ═══════════════ */}
        <div style={{ flexShrink: 0, width: 440, zIndex: 50, position: "relative", transform: "translateY(-40px)" }}>
          <h1 style={{ fontSize: 90, fontWeight: 900, color: "#fff", lineHeight: 0.95, margin: "0 0 24px 0", letterSpacing: "-0.04em" }}>
            Market<br/>
            <span style={{ color: "rgba(255,255,255,0.95)" }}>Intelligence</span>
          </h1>
          <p style={{ fontSize: 20, color: "rgba(255,255,255,0.6)", lineHeight: 1.5, margin: 0, fontWeight: 400 }}>
            Cross-border vehicle arbitrage,<br/>
            automated DNA verification,<br/>
            and execution feeds.
          </p>
          <div style={{ display: "flex", gap: 16, marginTop: 40 }}>
            <button style={{ background: "#fff", color: "#000", padding: "16px 32px", borderRadius: 12, fontWeight: 700, fontSize: 16 }}>Explore Platform</button>
          </div>
        </div>

        {/* ═══════════════ 3D THE PHYSICS ENGINE - V24 FLIPPED & STRUCTURED ═══════════════ */}
        <div style={{ flex: 1, position: "relative", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
          
          <div style={{ 
            perspective: 4000, 
            perspectiveOrigin: "50% 50%", 
            position: "absolute", 
            width: 1400, height: 900, 
            right: -300, 
            top: -40, 
            display: "flex", alignItems: "center", justifyContent: "center" 
          }}>
            
            {/* Master Wrapper: FLIPPED Y-ROTATION (+22deg instead of -22deg) */}
            <div style={{ 
              transformStyle: "preserve-3d", 
              transform: "scale(0.85) rotateX(10deg) rotateY(22deg) rotateZ(0deg)", /* FLIPPED */
              position: "relative",
              width: "100%", height: "100%"
            }}>

              {/* ───────────────────────────────────────────────────────── */}
              {/* 1. THE HARDWARE ANCHOR (Screen + Keyboard Base)             */}
              {/* ───────────────────────────────────────────────────────── */}
              
              <div style={{
                position: "absolute", top: "10%", left: "10%",
                width: 1050, height: 650,
                transformStyle: "preserve-3d",
                background: "linear-gradient(145deg, #05050a 0%, #000 100%)",
                borderRadius: 24,
                borderTop: "2px solid rgba(255,255,255,0.25)",
                borderRight: "2px solid rgba(255,255,255,0.15)", /* Flipped highlight */
                boxShadow: "40px 60px 100px rgba(0,0,0,0.8)", /* Flipped shadow */
                zIndex: 1
              }}>
                {/* Screen Content Glow */}
                <div style={{ position: "absolute", inset: 16, background: "#06070a", borderRadius: 12, overflow: "hidden" }}>
                   <div style={{ position: "absolute", bottom: "10%", left: "20%", width: 600, height: 600, background: "rgba(41, 98, 255, 0.15)", filter: "blur(140px)", borderRadius: "50%" }} />
                </div>

                {/* --- THE KEYBOARD BASE --- */}
                <div style={{
                  position: "absolute", bottom: 0, left: 0,
                  width: "100%", height: 800, 
                  transformOrigin: "bottom",
                  transform: "rotateX(90deg) translateY(2px)", 
                  background: "linear-gradient(180deg, #1b1c23 0%, #0e0e13 30%, #050508 100%)",
                  borderRadius: "0 0 40px 40px",
                  borderRight: "2px solid rgba(255,255,255,0.1)", /* Flipped */
                  boxShadow: "0 100px 150px rgba(0,0,0,0.9)",
                  display: "flex", justifyContent: "center"
                }}>
                  {/* Keyboard Well */}
                  <div style={{ width: 850, height: 350, background: "#050508", marginTop: 50, borderRadius: 16, border: "1px solid rgba(255,255,255,0.05)", boxShadow: "inset 0 10px 40px rgba(0,0,0,0.9)" }}>
                     <div style={{ width: "100%", height: "100%", backgroundImage: "linear-gradient(90deg, rgba(255,255,255,0.03) 2px, transparent 2px), linear-gradient(0deg, rgba(255,255,255,0.03) 2px, transparent 2px)", backgroundSize: "32px 32px", opacity: 0.8 }} />
                  </div>
                  {/* Trackpad */}
                  <div style={{ position: "absolute", bottom: 140, left: "50%", transform: "translateX(-50%)", width: 380, height: 180, background: "#18181f", borderRadius: 12, border: "1px solid rgba(255,255,255,0.02)", boxShadow: "inset 0 2px 10px rgba(0,0,0,0.5)" }} />
                </div>

                {/* ───────────────────────────────────────────────────────── */}
                {/* 2. THE STRUCTURED UI LAYERS (Embedded INSIDE the screen)  */}
                {/* Nested here so they share the exact 1050x650 coordinate   */}
                {/* system of the screen, guaranteeing perfect alignment.     */}
                {/* ───────────────────────────────────────────────────────── */}
                
                <div style={{ position: "absolute", inset: 16, zIndex: 10, transformStyle: "preserve-3d" }}>

                  {/* LAYER 1: Base Application Chrome (Z = 40) */}
                  <div style={{
                    position: "absolute", inset: 0,
                    transform: "translateZ(40px)",
                    background: "rgba(10, 12, 18, 0.4)",
                    backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
                    borderRadius: 12,
                    border: "1px solid rgba(255,255,255,0.05)",
                    padding: 24,
                    display: "flex", flexDirection: "column", gap: 24
                  }}>
                    {/* Header Bar */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontSize: 24, fontWeight: 800, color: "#fff", marginBottom: 4 }}>Terminal <span style={{ color: "#2962ff" }}>Pro</span></div>
                        <div style={{ fontSize: 13, color: "rgba(255,255,255,0.5)" }}>Live European Arbitrage</div>
                      </div>
                      <div style={{ background: "rgba(255,255,255,0.05)", padding: "12px 20px", borderRadius: 12, border: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: 24 }}>
                        <div>
                          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", fontWeight: 700, marginBottom: 2 }}>Gross Margin</div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: "#fff", fontFamily: "monospace" }}>€34,600</div>
                        </div>
                        <div style={{ width: 1, background: "rgba(255,255,255,0.1)" }} />
                        <div>
                          <div style={{ fontSize: 10, color: "#4ade80", textTransform: "uppercase", fontWeight: 700, marginBottom: 2 }}>Active Spread</div>
                          <div style={{ fontSize: 18, fontWeight: 800, color: "#4ade80", fontFamily: "monospace" }}>+€4,405</div>
                        </div>
                      </div>
                    </div>

                    {/* Main Grid */}
                    <div style={{ flex: 1, display: "flex", gap: 24 }}>
                      
                      {/* Left Column (Chart + Watchlist) */}
                      <div style={{ flex: 7, display: "flex", flexDirection: "column", gap: 24 }}>
                         
                         <div style={{ flex: 1, display: "flex", gap: 16 }}>
                            {/* Watchlist */}
                            <div style={{ width: 180, display: "flex", flexDirection: "column", gap: 8 }}>
                               <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", fontWeight: 800, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Priority Targets</div>
                               {[
                                  { tk: "BMW/M3", d: "+2.4%", a: true },
                                  { tk: "AUD/RS6", d: "+1.1%" },
                                  { tk: "POR/911", d: "-0.4%" },
                                  { tk: "MER/G63", d: "+3.8%" }
                                ].map(w => (
                                   <div key={w.tk} style={{ padding: "12px", background: w.a ? "rgba(41, 98, 255, 0.15)" : "rgba(255,255,255,0.03)", borderRadius: 10, border: "1px solid", borderColor: w.a ? "rgba(41, 98, 255, 0.4)" : "rgba(255,255,255,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                     <span style={{ fontSize: 13, fontWeight: w.a ? 800 : 600, color: w.a ? "#fff" : "rgba(255,255,255,0.6)" }}>{w.tk}</span>
                                     <span style={{ fontSize: 12, fontWeight: 700, color: w.d.includes('+') ? "#4ade80" : "#f87171", fontFamily: "monospace" }}>{w.d}</span>
                                   </div>
                                ))}
                            </div>
                            
                            {/* The Redesigned Chart */}
                            <AdvancedChartWidget />
                         </div>

                      </div>

                    </div>
                  </div>

                  {/* LAYER 2: Protruding Modules (Z = 120, structured rigidly to the grid) */}
                  {/* Right Column: Toy Maquetas Feed - Pops out of the screen layout */}
                  <div style={{
                    position: "absolute", right: 24, top: 120, bottom: 24, width: 340,
                    transform: "translateZ(120px)",
                    background: "rgba(18, 15, 30, 0.65)",
                    backdropFilter: "blur(40px) saturate(120%)", WebkitBackdropFilter: "blur(40px) saturate(120%)",
                    borderRadius: 16,
                    border: "1px solid rgba(255,255,255,0.15)",
                    boxShadow: "20px 30px 60px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.2)",
                    padding: 20, display: "flex", flexDirection: "column",
                    animation: "floatStructural 6s ease-in-out infinite"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                      <h3 style={{ fontSize: 12, fontWeight: 800, color: "#fff", margin: 0, textTransform: "uppercase", letterSpacing: 1 }}>Live Maqueta Feed</h3>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#ef4444", animation: "pulseLive 1.5s infinite" }}/>
                    </div>

                    <div style={{ flex: 1, overflow: "hidden", position: "relative", maskImage: "linear-gradient(to bottom, black 70%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 70%, transparent 100%)" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: 16, animation: "swipeInertiaMvq 12s infinite" }}>
                        {[
                          // TOY PNGs (Transparent Background Models)
                          { img: "https://purepng.com/public/uploads/large/purepng.com-porscheporscheporsche-automobilegerman-automobile-manufacturer-17015275899264ptc9.png", name: "Porsche 911 GT3", spec: "Arbitrage Execution • ES", price: "€185k", margin: "+€8.2k", hl: true },
                          { img: "https://purepng.com/public/uploads/large/purepng.com-audi-rs6audi-rs6audi-cars-1701527413554ypsl8.png", name: "Audi RS6 Avant", spec: "Market Match • CH", price: "€112k", margin: "+€6.5k" },
                          { img: "https://purepng.com/public/uploads/large/purepng.com-mercedes-amg-gtmercedes-amg-gtmercedes-amg-mercedes-benzmercedes-cars-17015275213197lixd.png", name: "Mercedes AMG GT", spec: "Cross Border • BE", price: "€210k", margin: "+€4.1k" },
                          { img: "https://purepng.com/public/uploads/large/purepng.com-bmw-m3-white-carbmwbmw-carbmw-carsauto-automobile-170152740618063wpx.png", name: "BMW M3 Comp", spec: "Direct Route • NL", price: "€95k", margin: "+€3.8k" },
                        ].map((car, i) => (
                          <div key={i} style={{ background: car.hl ? "rgba(41, 98, 255, 0.15)" : "rgba(255,255,255,0.03)", border: "1px solid " + (car.hl ? "rgba(41, 98, 255, 0.4)" : "rgba(255,255,255,0.05)"), borderRadius: 12, padding: "16px 12px", display: "flex", flexDirection: "column", gap: 8, alignItems: "center", position: "relative" }}>
                            
                            {/* "MAQUETA" TRANSPARENT RENDERING */}
                            {/* Instead of a constrained image box, the transparent 3D car floats freely over the glass card */}
                            <div style={{ width: "100%", height: 80, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", zIndex: 2 }}>
                               {/* Ground Reflection/Shadow */}
                               <div style={{ position: "absolute", bottom: -5, width: "60%", height: 10, background: "rgba(0,0,0,0.6)", borderRadius: "50%", filter: "blur(6px)", transform: "scaleY(0.4)" }} />
                               {/* The Transparent Toy Car */}
                               <img src={car.img} alt={car.name} className="maqueta-toy" style={{ width: "90%", objectFit: "contain", maxHeight: "100%" }} />
                            </div>

                            <div style={{ width: "100%", textAlign: "center", zIndex: 2 }}>
                              <div style={{ fontSize: 14, fontWeight: 900, color: "#fff", marginBottom: 2 }}>{car.name}</div>
                              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", marginBottom: 8, fontWeight: 600 }}>{car.spec}</div>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(0,0,0,0.3)", padding: "6px 10px", borderRadius: 8, border: "1px solid rgba(255,255,255,0.05)" }}>
                                <div style={{ fontSize: 12, color: "rgba(255,255,255,0.8)", fontWeight: 700 }}>{car.price}</div>
                                <div style={{ fontSize: 12, color: "#4ade80", fontWeight: 800 }}>{car.margin}</div>
                              </div>
                            </div>

                            {/* Decorative lighting on the card itself */}
                            {car.hl && <div style={{ position: "absolute", top: 0, left: "20%", right: "20%", height: 1, background: "linear-gradient(90deg, transparent, #2962ff, transparent)" }}/>}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* LAYER 3: Yield Routes (Z = 180, bottom-left intersection) */}
                  <div style={{
                    position: "absolute", left: 160 + 24 + 24, bottom: -40, /* Structurally aligned with the chart */
                    width: 320, height: 140,
                    transform: "translateZ(180px)",
                    background: "rgba(18, 15, 30, 0.8)",
                    backdropFilter: "blur(40px)", WebkitBackdropFilter: "blur(40px)",
                    borderRadius: 16,
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderTop: "1px solid rgba(41, 98, 255, 0.6)",
                    boxShadow: "20px 40px 80px rgba(0,0,0,0.7), inset 0 2px 2px rgba(255,255,255,0.1)",
                    padding: "16px 20px", display: "flex", flexDirection: "column",
                    animation: "floatStructural 7s ease-in-out infinite reverse",
                    zIndex: 20
                  }}>
                    <h4 style={{ fontSize: 10, fontWeight: 800, color: "#2962ff", textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>Active Yield Routes</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {[
                        { time: "DE➔ES", sub: "BMW 330i xDrive", v: "+€4,405" },
                        { time: "FR➔CH", sub: "Audi RS6 Avant", v: "+€6,500" },
                      ].map((r, i) => (
                        <div key={i} style={{ display: "flex", gap: 12, alignItems: "center" }}>
                          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4ade80", animation: i === 0 ? "pulseLive 2s infinite" : "none" }}/>
                          <div style={{ flex: 1, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                            <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>{r.sub}</div>
                            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.4)", fontFamily: "monospace" }}>{r.time}</div>
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 800, color: "#4ade80", fontFamily: "monospace", width: 65, textAlign: "right" }}>{r.v}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                </div>
              </div>

            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
