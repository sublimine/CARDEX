/**
 * CARDEX Landing — Awwwards-tier adaptation of the SmartHome "Modern UI Flow" reference.
 * Vibe: Ethereal Glass × Asymmetric Bento (high-end-visual-design skill)
 * Double-Bezel architecture on every card. Custom cubic-bezier physics throughout.
 * Reference: https://es.pinterest.com/pin/777574691956038286/
 */
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'

/* ─── Springs ──────────────────────────────────────────────────────────────── */
const SP  = { type: 'spring', stiffness: 420, damping: 30 } as const
const SM  = { type: 'spring', stiffness: 280, damping: 24 } as const
const EX  = [0.16, 1, 0.3, 1] as const  /* ease-out-expo */
const REV = [0.32, 0.72, 0, 1] as const /* heavy decel */

/* ─── Fonts (Google Fonts loaded in index.html) ────────────────────────────── */
const F = '"Plus Jakarta Sans", system-ui, sans-serif'

/* ─── Photo ────────────────────────────────────────────────────────────────── */
const PHOTO = 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1000&q=95&auto=format&fit=crop'

/* ─── Card shell: outer bezel ──────────────────────────────────────────────── */
const SHELL: React.CSSProperties = {
  borderRadius: 20,
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.08)',
  padding: 4,
  backdropFilter: 'blur(32px) saturate(180%)',
  WebkitBackdropFilter: 'blur(32px) saturate(180%)',
  boxShadow: '0 2px 0 rgba(255,255,255,0.07) inset, 0 16px 48px rgba(0,0,0,0.4)',
}

/* ─── Card core: inner surface ─────────────────────────────────────────────── */
const CORE: React.CSSProperties = {
  borderRadius: 17,
  background: 'rgba(22, 20, 36, 0.88)',
  padding: '16px 18px',
  height: '100%',
  boxShadow: '0 1px 0 rgba(255,255,255,0.07) inset',
  overflow: 'hidden',
  position: 'relative',
}

/* ─── Toggle ────────────────────────────────────────────────────────────────── */
function Toggle({ on, col = '#06b6d4', onToggle }: { on: boolean; col?: string; onToggle: () => void }) {
  return (
    <motion.div onClick={onToggle}
      style={{
        width: 46, height: 26, borderRadius: 99, position: 'relative', cursor: 'pointer', flexShrink: 0,
        background: on ? col : 'rgba(255,255,255,0.10)',
        border: `1.5px solid ${on ? col : 'rgba(255,255,255,0.14)'}`,
        boxShadow: on ? `0 0 14px ${col}55` : 'none',
      }}
      animate={{ background: on ? col : 'rgba(255,255,255,0.10)' }}
      transition={{ duration: 0.25, ease: EX }}
    >
      <motion.div
        animate={{ x: on ? 22 : 3 }}
        transition={SP}
        style={{ position: 'absolute', top: 3, width: 18, height: 18, borderRadius: '50%', background: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.35)' }}
      />
    </motion.div>
  )
}

/* ─── SDI gauge ─────────────────────────────────────────────────────────────── */
function Gauge({ v }: { v: number }) {
  const R = 48, cx = 56, cy = 58, arc = Math.PI * R
  const pct = v / 10
  const col = v >= 7 ? '#f43f5e' : v >= 5 ? '#f59e0b' : '#10b981'
  return (
    <svg width={112} height={68} viewBox="0 0 112 68" style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>
      </defs>
      <path d={`M 8,${cy} A ${R},${R} 0 0 1 ${2*cx-8},${cy}`}
        fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={7} strokeLinecap="round" />
      <motion.path
        d={`M 8,${cy} A ${R},${R} 0 0 1 ${2*cx-8},${cy}`}
        fill="none" stroke="url(#gaugeGrad)" strokeWidth={7} strokeLinecap="round"
        strokeDasharray={`${arc}`} strokeDashoffset={arc * (1 - pct)}
        initial={{ strokeDashoffset: arc }} animate={{ strokeDashoffset: arc * (1 - pct) }}
        transition={{ duration: 1.4, ease: EX, delay: 0.5 }}
      />
      {/* needle */}
      <motion.line
        x1={cx} y1={cy}
        x2={cx + Math.cos(Math.PI * (1 - pct)) * (R - 14)}
        y2={cy + Math.sin(Math.PI * (1 - pct)) * (R - 14)}
        stroke={col} strokeWidth={2.5} strokeLinecap="round"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        transition={{ delay: 1.3, duration: 0.4 }}
      />
      <circle cx={cx} cy={cy} r={4.5} fill={col} />
    </svg>
  )
}

/* ─── Mini sparkline ────────────────────────────────────────────────────────── */
function Spark({ data, col }: { data: number[]; col: string }) {
  const W = 90, H = 36
  const mn = Math.min(...data), mx = Math.max(...data)
  const pts = data.map((v, i) => `${(i / (data.length-1)) * W},${H - ((v-mn)/(mx-mn||1)) * (H-6) - 3}`)
  const area = `M0,${H} L${pts.join(' L')} L${W},${H} Z`
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sg${col.slice(1)}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={col} stopOpacity={0.4} />
          <stop offset="100%" stopColor={col} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#sg${col.slice(1)})`} />
      <motion.polyline points={pts.join(' ')} fill="none" stroke={col} strokeWidth={2} strokeLinecap="round"
        initial={{ strokeDasharray: 300, strokeDashoffset: 300 }}
        animate={{ strokeDashoffset: 0 }}
        transition={{ duration: 1.2, ease: EX, delay: 0.6 }} />
    </svg>
  )
}

/* ─── NLC chart ─────────────────────────────────────────────────────────────── */
function NLCChart() {
  const data = [38, 44, 36, 50, 42, 56, 48]
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
  const W = 100, H = 48, mn = 30, mx = 60
  const pts: [number, number][] = data.map((v, i) => [
    4 + (i / (data.length-1)) * (W-8),
    H - ((v-mn)/(mx-mn)) * (H-8) - 4,
  ])
  const area = `M${pts[0][0]},${H} ` + pts.map(([x,y]) => `L${x},${y}`).join(' ') + ` L${pts[pts.length-1][0]},${H} Z`
  const last = pts[pts.length-1]
  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <svg width="100%" height={H+16} viewBox={`0 0 ${W} ${H+16}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="nlcA" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.38} />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#nlcA)" />
        <motion.polyline points={pts.map(([x,y])=>`${x},${y}`).join(' ')} fill="none"
          stroke="#06b6d4" strokeWidth={1.8} strokeLinecap="round"
          initial={{ strokeDasharray: 400, strokeDashoffset: 400 }}
          animate={{ strokeDashoffset: 0 }}
          transition={{ duration: 1.4, ease: EX, delay: 0.6 }} />
        {/* peak bubble */}
        <rect x={pts[5][0]-8} y={pts[5][1]-12} width={22} height={11} rx={5.5} fill="rgba(255,255,255,0.92)" />
        <text x={pts[5][0]+3} y={pts[5][1]-4} textAnchor="middle" fontSize={6} fontWeight={700} fill="#0a0a1a">4.8%</text>
        {/* day labels */}
        {days.map((d,i) => (
          <text key={d} x={pts[i][0]} y={H+13} textAnchor="middle" fontSize={5.5} fill="rgba(255,255,255,0.22)">{d}</text>
        ))}
      </svg>
    </div>
  )
}

/* ─── MAIN ───────────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const [tab,  setTab]  = useState(0)
  const [iva,  setIva]  = useState(true)
  const [rebu, setRebu] = useState(true)

  return (
    /* Outer: lavender-to-periwinkle — matches reference exactly */
    <div style={{
      minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #ede9fe 0%, #e0e7ff 38%, #dbeafe 68%, #e0f2fe 100%)',
      fontFamily: F, padding: 'clamp(12px,2vw,28px)',
    }}>

      {/* ── DEVICE MOCKUP — outer bezel ──────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 36, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.85, ease: EX }}
        style={{
          width: '100%', maxWidth: 1060,
          borderRadius: 28,
          padding: 6,
          background: 'linear-gradient(160deg, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0.10) 100%)',
          border: '1px solid rgba(255,255,255,0.55)',
          boxShadow: '0 48px 140px rgba(99,102,241,0.22), 0 12px 40px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.6)',
        }}
      >
        {/* Inner device surface */}
        <div style={{
          borderRadius: 23,
          background: '#0e0e22',
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
          aspectRatio: '16/11',
        }}>

          {/* ── TOP BAR ─────────────────────────────────────────────────── */}
          <div style={{
            height: 50, flexShrink: 0, display: 'flex', alignItems: 'center',
            padding: '0 14px', gap: 10,
            background: 'rgba(14,14,34,0.96)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}>
            {/* Logo */}
            <div style={{ display:'flex', alignItems:'center', gap:7, marginRight:6 }}>
              <div style={{ width:28, height:28, borderRadius:9, background:'rgba(99,102,241,0.22)', border:'1px solid rgba(99,102,241,0.45)', display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 0 16px rgba(99,102,241,0.3)' }}>
                <div style={{ width:11, height:11, borderRadius:3.5, background:'linear-gradient(135deg,#a5b4fc,#6366f1)', boxShadow:'0 0 8px rgba(99,102,241,0.7)' }} />
              </div>
              <span style={{ fontSize:12, fontWeight:800, letterSpacing:'0.16em', background:'linear-gradient(120deg,#a5b4fc 0%,#c4b5fd 50%,#67e8f9 100%)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>CARDEX</span>
            </div>

            {/* Pill nav */}
            <div style={{ display:'flex', background:'rgba(255,255,255,0.05)', borderRadius:999, padding:3, border:'1px solid rgba(255,255,255,0.07)' }}>
              {['Dashboard','Coverage','Listings','Reports'].map((t,i) => (
                <motion.button key={t} onClick={() => setTab(i)}
                  style={{ padding:'4px 13px', borderRadius:999, fontSize:11, fontWeight:600, border:'none', cursor:'pointer', fontFamily:F,
                    background: tab===i ? 'rgba(255,255,255,0.13)' : 'transparent',
                    color: tab===i ? '#f1f5f9' : '#64748b',
                    boxShadow: tab===i ? 'inset 0 1px 0 rgba(255,255,255,0.12)' : 'none',
                    position: 'relative',
                  }}
                  whileTap={{ scale: 0.96 }}
                >
                  {t}
                  {i===3 && <span style={{ marginLeft:4, fontSize:8, fontWeight:800, background:'#6366f1', color:'#fff', padding:'1px 4px', borderRadius:99 }}>12</span>}
                </motion.button>
              ))}
            </div>

            <div style={{ flex:1 }} />

            {/* Right controls */}
            <div style={{ display:'flex', alignItems:'center', gap:5 }}>
              {/* Mail + Bell */}
              {['M','B'].map((k) => (
                <motion.button key={k} whileHover={{ background:'rgba(255,255,255,0.10)' }} whileTap={{ scale:0.95 }}
                  style={{ width:30, height:30, borderRadius:9, background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.09)', display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer' }}>
                  <div style={{ width:10, height:10, borderRadius:k==='B'?'50%':2, border:'1.5px solid #475569', position:'relative' }}>
                    {k==='B' && <div style={{ position:'absolute', top:-3, right:-2, width:5, height:5, borderRadius:'50%', background:'#6366f1', border:'1px solid #0e0e22' }} />}
                  </div>
                </motion.button>
              ))}
              {/* Avatar pill */}
              <motion.div whileHover={{ background:'rgba(255,255,255,0.10)' }}
                style={{ display:'flex', alignItems:'center', gap:7, padding:'3px 10px 3px 3px', borderRadius:999, background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.09)', cursor:'pointer' }}>
                <div style={{ width:24, height:24, borderRadius:'50%', background:'linear-gradient(135deg,#6366f1,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:9, fontWeight:800, color:'#fff' }}>E</div>
                <span style={{ fontSize:11, fontWeight:600, color:'#cbd5e1' }}>Elias K.</span>
                <svg width={8} height={8} viewBox="0 0 8 8"><path d="M1 2.5L4 5.5L7 2.5" stroke="#475569" strokeWidth={1.5} strokeLinecap="round" fill="none"/></svg>
              </motion.div>
            </div>
          </div>

          {/* ── BODY ────────────────────────────────────────────────────── */}
          <div style={{ flex:1, display:'flex', overflow:'hidden', minHeight:0 }}>

            {/* LEFT SIDEBAR — icon strip */}
            <div style={{ width:46, flexShrink:0, display:'flex', flexDirection:'column', alignItems:'center', paddingTop:14, gap:3, background:'rgba(10,10,26,0.9)', borderRight:'1px solid rgba(255,255,255,0.05)' }}>
              {[
                <path key="d" d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round"/>,
                <><circle key="ca" cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth={1.5}/><path d="M8 12h8M12 8v8" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round"/></>,
                <><rect key="ba" x="3" y="3" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5}/><rect x="14" y="3" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5}/><rect x="14" y="14" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5}/><rect x="3" y="14" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth={1.5}/></>,
                <><path key="sa" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round"/></>,
                <><circle key="ga" cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth={1.5}/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round"/></>,
              ].map((icon, i) => (
                <motion.button key={i}
                  whileHover={{ background: 'rgba(255,255,255,0.08)', borderColor:'rgba(255,255,255,0.14)' }}
                  whileTap={{ scale: 0.92 }}
                  style={{ width:32, height:32, borderRadius:10, display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', background: i===0 ? 'rgba(255,255,255,0.10)':'transparent', border: i===0 ? '1px solid rgba(255,255,255,0.16)':'1px solid transparent' }}
                >
                  <svg width={15} height={15} viewBox="0 0 24 24" style={{ color: i===0 ? '#e2e8f0':'#334155' }}>{icon}</svg>
                </motion.button>
              ))}
              <div style={{ flex:1 }} />
              <motion.div whileHover={{ scale:1.08 }}
                style={{ width:28, height:28, borderRadius:'50%', background:'linear-gradient(135deg,#6366f1,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, fontWeight:800, color:'#fff', marginBottom:14, cursor:'pointer', boxShadow:'0 0 14px rgba(99,102,241,0.4)' }}>E</motion.div>
            </div>

            {/* LEFT PHOTO PANEL */}
            <div style={{ flex:'0 0 41%', position:'relative', overflow:'hidden' }}>
              <img src={PHOTO} alt="" style={{ width:'100%', height:'100%', objectFit:'cover', objectPosition:'center 55%' }} />
              {/* Warm amber overlay — simulates golden sunset */}
              <div style={{ position:'absolute', inset:0, background:'radial-gradient(ellipse at 70% 40%, rgba(251,146,60,0.22) 0%, transparent 55%)' }} />
              <div style={{ position:'absolute', inset:0, background:'radial-gradient(ellipse at 30% 60%, rgba(234,88,12,0.12) 0%, transparent 50%)' }} />
              {/* Edge fades */}
              <div style={{ position:'absolute', inset:0, background:'linear-gradient(to right, rgba(10,10,26,0.05) 0%, rgba(10,10,26,0.6) 100%)' }} />
              <div style={{ position:'absolute', inset:0, background:'linear-gradient(to top, rgba(10,10,26,0.95) 0%, transparent 58%)' }} />

              {/* Greeting top-left */}
              <motion.div initial={{ opacity:0, y:-10 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.45, duration:0.6, ease:EX }}
                style={{ position:'absolute', top:18, left:16 }}>
                <div style={{ fontSize:15, fontWeight:800, color:'#f8fafc', letterSpacing:'-0.02em', textShadow:'0 2px 20px rgba(0,0,0,0.5)' }}>Hello, trader.</div>
                <div style={{ fontSize:11, color:'rgba(255,255,255,0.48)', marginTop:2, fontWeight:500 }}>How's your arbitrage going?</div>
              </motion.div>

              {/* CTA button */}
              <motion.div initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.65, duration:0.5, ease:EX }}
                style={{ position:'absolute', bottom:52, left:16 }}>
                <motion.button onClick={() => nav('/login')}
                  whileHover={{ scale:1.04, boxShadow:'0 0 32px rgba(99,102,241,0.65)' }}
                  whileTap={{ scale:0.97 }}
                  transition={SP}
                  style={{ display:'flex', alignItems:'center', gap:8, padding:'9px 18px', borderRadius:999, fontSize:12, fontWeight:700, color:'#fff', background:'linear-gradient(135deg,#6366f1,#7c3aed)', border:'none', cursor:'pointer', fontFamily:F, boxShadow:'0 0 22px rgba(99,102,241,0.4)' }}>
                  Enter platform
                  <div style={{ width:20, height:20, borderRadius:'50%', background:'rgba(255,255,255,0.18)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                    <svg width={9} height={9} viewBox="0 0 10 10"><path d="M1 9L9 1M9 1H3M9 1V7" stroke="#fff" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </div>
                </motion.button>
              </motion.div>

              {/* Bottom bar */}
              <div style={{ position:'absolute', bottom:0, left:0, right:0, padding:'10px 14px', display:'flex', alignItems:'center', justifyContent:'space-between', background:'rgba(10,10,26,0.78)', backdropFilter:'blur(16px)', borderTop:'1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ display:'flex', gap:5 }}>
                  {['⌕','+','−','×'].map((s,i) => (
                    <motion.button key={i} whileHover={{ background:'rgba(255,255,255,0.12)' }} whileTap={{ scale:0.9 }}
                      style={{ width:26, height:26, borderRadius:7, background:'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.1)', display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', fontSize:11, color:'#94a3b8' }}>{s}</motion.button>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize:9, fontWeight:700, color:'#e2e8f0' }}>CARDEX Intelligence Hub</div>
                  <div style={{ fontSize:8, color:'#334155', marginTop:1 }}>Monitor EU markets with your team</div>
                </div>
                <div style={{ display:'flex', alignItems:'center' }}>
                  {['#6366f1','#7c3aed','#0891b2'].map((c,i) => (
                    <div key={i} style={{ width:22, height:22, borderRadius:'50%', background:c, border:'2px solid #0e0e22', marginLeft:i>0?-7:0, display:'flex', alignItems:'center', justifyContent:'center', fontSize:8, fontWeight:800, color:'#fff' }}>{['A','B','C'][i]}</div>
                  ))}
                  <motion.div whileHover={{ background:'rgba(255,255,255,0.14)' }}
                    style={{ width:22, height:22, borderRadius:'50%', background:'rgba(255,255,255,0.09)', border:'2px solid rgba(255,255,255,0.18)', marginLeft:-7, display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', fontSize:13, color:'#94a3b8' }}>+</motion.div>
                </div>
              </div>
            </div>

            {/* ── RIGHT BENTO ──────────────────────────────────────────── */}
            <div style={{
              flex:1, padding:'12px 12px 0 8px',
              display:'grid',
              gridTemplateColumns:'1fr 1fr',
              gridTemplateRows:'auto auto auto auto',
              gap:8,
              background:'rgba(8,8,22,0.55)',
              overflowY:'auto',
            }}>

              {/* CARD 1 — New Listings (= Energy Usage) */}
              <motion.div initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.3, duration:0.55, ease:EX }} style={SHELL}>
                <div style={CORE}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:'#64748b', letterSpacing:'0.04em' }}>New Listings Today</span>
                    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="#334155" strokeWidth={1.8} strokeLinecap="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
                  </div>
                  <div style={{ display:'flex', alignItems:'baseline', gap:8, marginBottom:12 }}>
                    <span style={{ fontSize:30, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.05em' }}>2.847</span>
                    <span style={{ fontSize:10, fontWeight:700, color:'#06b6d4' }}>Medium</span>
                  </div>
                  {[{l:'🇩🇪 Germany',v:0.72,c:'#6366f1'},{l:'🇪🇸 Spain',v:0.58,c:'#7c3aed'},{l:'🇫🇷 France',v:0.44,c:'#0891b2'}].map(({l,v,c})=>(
                    <div key={l} style={{ marginBottom:7 }}>
                      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                        <span style={{ fontSize:9, color:'#475569', fontWeight:500 }}>{l}</span>
                        <span style={{ fontSize:9, color:'#334155' }}>{Math.round(v*100)}%</span>
                      </div>
                      <div style={{ height:4, background:'rgba(255,255,255,0.06)', borderRadius:99, overflow:'hidden' }}>
                        <motion.div initial={{ width:0 }} animate={{ width:`${v*100}%` }} transition={{ delay:0.7, duration:0.9, ease:EX }}
                          style={{ height:'100%', background:`linear-gradient(90deg,${c}60,${c})`, borderRadius:99 }} />
                      </div>
                    </div>
                  ))}
                  <div style={{ marginTop:10, display:'flex', alignItems:'center', gap:5 }}>
                    <div style={{ width:5, height:5, borderRadius:'50%', background:'#06b6d4', boxShadow:'0 0 8px #06b6d4', animation:'cxPulse 2s infinite' }} />
                    <span style={{ fontSize:9, color:'#334155', fontWeight:500 }}>Auto-indexing active</span>
                  </div>
                </div>
              </motion.div>

              {/* CARD 2 — Top Opportunity (= Living room / temperature) */}
              <motion.div initial={{ opacity:0, y:14 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.35, duration:0.55, ease:EX }}
                style={{ ...SHELL, background:'rgba(99,102,241,0.10)', border:'1px solid rgba(99,102,241,0.22)' }}>
                <div style={{ ...CORE, background:'rgba(18,16,40,0.88)', border:'1px solid rgba(99,102,241,0.15)', display:'flex', flexDirection:'column' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:'#818cf8' }}>Top Opportunity</span>
                    <Toggle on={true} col="#818cf8" onToggle={() => {}} />
                  </div>
                  <div style={{ fontSize:28, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.05em', lineHeight:1.1, marginBottom:3 }}>€ 58.900</div>
                  <div style={{ fontSize:10, color:'#6366f1', marginBottom:12, fontWeight:600 }}>BMW M3 Competition · Munich</div>
                  <div style={{ display:'flex', gap:3, marginBottom:10 }}>
                    {['IVA','REBU','Both'].map((t,i)=>(
                      <div key={t} style={{ flex:1, padding:'4px 0', textAlign:'center', borderRadius:6, fontSize:9, fontWeight:700, cursor:'pointer', background:i===0?'rgba(99,102,241,0.3)':'rgba(255,255,255,0.04)', color:i===0?'#a5b4fc':'#475569', border:i===0?'1px solid rgba(99,102,241,0.4)':'1px solid transparent' }}>{t}</div>
                    ))}
                  </div>
                  {/* bar chart */}
                  <div style={{ display:'flex', alignItems:'flex-end', gap:3, flex:1, paddingBottom:2 }}>
                    {[42,55,48,64,58,72,66].map((v,i)=>(
                      <motion.div key={i}
                        initial={{ scaleY:0 }} animate={{ scaleY:1 }} transition={{ delay:0.7+i*0.05, duration:0.5, ease:EX }}
                        style={{ flex:1, background:i===6?'#6366f1':'rgba(99,102,241,0.18)', borderRadius:'3px 3px 0 0', height:`${v}%`, transformOrigin:'bottom' }} />
                    ))}
                  </div>
                  <div style={{ display:'flex', justifyContent:'space-around', marginTop:3 }}>
                    {['M','T','W','T','F','S','S'].map((d,i)=><span key={i} style={{ fontSize:6.5, color:'rgba(255,255,255,0.2)', textAlign:'center', flex:1 }}>{d}</span>)}
                  </div>
                </div>
              </motion.div>

              {/* CARD 3 — IVA toggle (= Wi-Fi, full width flat) */}
              <motion.div initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.4, duration:0.5, ease:EX }}
                style={{ ...SHELL, gridColumn:'1 / -1' }}>
                <div style={{ ...CORE, padding:'12px 16px', display:'flex', alignItems:'center', justifyContent:'space-between' }}
                  onClick={() => setIva(v=>!v)}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:32, height:32, borderRadius:10, background:'rgba(6,182,212,0.14)', border:'1px solid rgba(6,182,212,0.28)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#06b6d4" strokeWidth={1.7} strokeLinecap="round"><rect x="2" y="2" width="20" height="20" rx="5"/><path d="M16 12H8M12 8v8"/></svg>
                    </div>
                    <div>
                      <div style={{ fontSize:12, fontWeight:700, color:'#f1f5f9' }}>IVA Deductible</div>
                      <div style={{ fontSize:9, color:'#475569', marginTop:1 }}>Auto-classification · 62% of fleet</div>
                    </div>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:iva?'#06b6d4':'#475569' }}>{iva?'Active':'Paused'}</span>
                    <Toggle on={iva} col="#06b6d4" onToggle={() => setIva(v=>!v)} />
                  </div>
                </div>
              </motion.div>

              {/* CARD 4 — SDI gauge (= Lighting Brightness) */}
              <motion.div initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.45, duration:0.5, ease:EX }} style={SHELL}>
                <div style={CORE}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:2 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:'#64748b' }}>Seller Desperation</span>
                    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="#334155" strokeWidth={1.8} strokeLinecap="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
                  </div>
                  <div style={{ fontSize:10, color:'#f43f5e', fontWeight:700, marginBottom:4 }}>8.2 · High urgency</div>
                  <div style={{ display:'flex', justifyContent:'center' }}>
                    <Gauge v={8.2} />
                  </div>
                  <div style={{ textAlign:'center', fontSize:8, color:'#334155', marginTop:2 }}>Updated 22:00</div>
                </div>
              </motion.div>

              {/* CARD 5 — REBU toggle (= Kitchen) */}
              <motion.div initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.5, duration:0.5, ease:EX }} style={SHELL}>
                <div style={{ ...CORE, display:'flex', flexDirection:'column' }} onClick={() => setRebu(v=>!v)}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:'#64748b' }}>REBU</span>
                    <Toggle on={rebu} col="#f59e0b" onToggle={() => setRebu(v=>!v)} />
                  </div>
                  <div style={{ fontSize:28, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.04em' }}>38%</div>
                  <div style={{ fontSize:9, color:'#475569', marginTop:2, marginBottom:10 }}>of fleet classified</div>
                  <div style={{ flex:1, display:'flex', alignItems:'flex-end' }}>
                    <Spark data={[30,35,28,42,38,45,38]} col="#f59e0b" />
                  </div>
                </div>
              </motion.div>

              {/* CARD 6 — NLC chart (= Solar Charge, full width) */}
              <motion.div initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.55, duration:0.55, ease:EX }}
                style={{ ...SHELL, gridColumn:'1 / -1', marginBottom:12 }}>
                <div style={CORE}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
                    <div>
                      <div style={{ fontSize:10, fontWeight:700, color:'#64748b', marginBottom:4 }}>NLC Activity — this week</div>
                      <div style={{ display:'flex', alignItems:'baseline', gap:7 }}>
                        <span style={{ fontSize:22, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.04em' }}>4.8%</span>
                        <span style={{ fontSize:10, color:'#06b6d4', fontWeight:600 }}>avg margin EU6</span>
                      </div>
                    </div>
                    <div style={{ padding:'5px 12px', borderRadius:999, background:'rgba(255,255,255,0.88)', backdropFilter:'blur(8px)' }}>
                      <span style={{ fontSize:10, fontWeight:800, color:'#0a0a1a' }}>4.8%</span>
                    </div>
                  </div>
                  <NLCChart />
                </div>
              </motion.div>

            </div>
          </div>
        </div>
      </motion.div>

      <style>{`
        @keyframes cxPulse { 0%,100%{opacity:1}50%{opacity:.3} }
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
      `}</style>
    </div>
  )
}
