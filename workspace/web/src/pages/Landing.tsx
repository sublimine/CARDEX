/**
 * Landing — "Modern UI Flow" layout adapted for CARDEX.
 *
 * Reference: https://es.pinterest.com/pin/777574691956038286/
 * Split: left = luxury car photo (warm lighting), right = dark glass data cards.
 * Sidebar: icon-only nav strip on the far left.
 * Top nav: pill-tab navigation spanning full width.
 */
import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Car, Search, Plus, Minus, X,
  ChevronRight, ArrowUpRight, TrendingUp, Shield,
  Globe, Zap, MapPin, Activity, Check, Bell,
  BarChart3, Star, Users, Settings,
} from 'lucide-react'

const EASE = [0.22, 1, 0.36, 1] as const
const F = '"Inter", system-ui, -apple-system, sans-serif'

/* Photos */
const HERO_CAR = 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1000&q=92&auto=format&fit=crop'

/* Live feed data */
const VEHICLES = [
  { make:'BMW',      model:'M3 Competition',  flag:'🇩🇪', city:'Munich',    price:'€ 58.900', regime:'IVA', nlc:'€ 62.340', dest:'🇪🇸', sdi:8.2, change:'-€ 1.200', hot:true  },
  { make:'Porsche',  model:'911 Carrera S',    flag:'🇨🇭', city:'Zurich',    price:'€ 89.900', regime:'IVA', nlc:'€ 94.100', dest:'🇩🇪', sdi:9.1, change:'-€ 3.500', hot:true  },
  { make:'Mercedes', model:'C 220d AMG',       flag:'🇫🇷', city:'Paris',     price:'€ 28.400', regime:'REBU',nlc:'€ 31.200', dest:'🇳🇱', sdi:5.1, change: '—',        hot:false },
  { make:'Audi',     model:'A4 2.0 TDI',       flag:'🇳🇱', city:'Amsterdam', price:'€ 34.500', regime:'IVA', nlc:'€ 36.800', dest:'🇧🇪', sdi:6.7, change:'-€ 800',   hot:false },
]

/* Nav tabs */
const TABS = ['Dashboard','Coverage','Pricing','Reports']

/* Icon nav (left sidebar) */
const SIDE_NAV = [
  { icon: LayoutDashboard, active: true  },
  { icon: Car,             active: false },
  { icon: BarChart3,       active: false },
  { icon: Globe,           active: false },
  { icon: Shield,          active: false },
  { icon: Settings,        active: false },
]

/* ── Ticker ─────────────────────────────────────────────────────────────────── */
function LiveTicker() {
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % VEHICLES.length), 3000)
    return () => clearInterval(t)
  }, [])
  const v = VEHICLES[idx]
  return (
    <AnimatePresence mode="wait">
      <motion.div key={idx}
        initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}
        transition={{ duration:0.4, ease:EASE }}
        style={{ display:'flex', alignItems:'center', gap:10 }}
      >
        <div style={{ fontSize:12, fontWeight:700, color:'#f1f5f9' }}>{v.flag} {v.make} {v.model}</div>
        <div style={{ fontSize:11, color:'#64748b' }}>{v.price}</div>
        {v.hot && <div style={{ fontSize:9, fontWeight:800, padding:'2px 7px', borderRadius:999, background:'rgba(244,63,94,0.18)', border:'1px solid rgba(244,63,94,0.35)', color:'#f43f5e', letterSpacing:'0.06em' }}>HOT</div>}
      </motion.div>
    </AnimatePresence>
  )
}

/* ── SDI arc ─────────────────────────────────────────────────────────────────── */
function SDIArc({ value, max=10 }: { value:number; max?:number }) {
  const pct = value / max
  const r = 28, cx = 32, cy = 32, stroke = 4
  const circumference = Math.PI * r  // half circle
  const offset = circumference * (1 - pct)
  const col = value >= 7 ? '#f43f5e' : value >= 5 ? '#f59e0b' : '#10b981'
  return (
    <svg width={64} height={40} viewBox="0 0 64 46">
      <path d={`M ${cx-r},${cy} A ${r},${r} 0 0 1 ${cx+r},${cy}`}
        fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} strokeLinecap="round" />
      <motion.path
        d={`M ${cx-r},${cy} A ${r},${r} 0 0 1 ${cx+r},${cy}`}
        fill="none" stroke={col} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration:1.2, ease:EASE, delay:0.3 }}
      />
      <text x={cx} y={cy+2} textAnchor="middle" fontSize={13} fontWeight={800} fill={col}>{value}</text>
      <text x={cx} y={cy+14} textAnchor="middle" fontSize={7} fill="rgba(255,255,255,0.3)" fontWeight={600}>SDI</text>
    </svg>
  )
}

/* ── Price change badge ──────────────────────────────────────────────────────── */
function PriceBadge({ change }: { change:string }) {
  if (change === '—') return <span style={{ fontSize:11, color:'#475569' }}>—</span>
  const down = change.startsWith('-')
  return (
    <div style={{ display:'inline-flex', alignItems:'center', gap:3, padding:'2px 8px', borderRadius:6, background:down ? 'rgba(16,185,129,0.12)' : 'rgba(244,63,94,0.12)', border:`1px solid ${down ? 'rgba(16,185,129,0.3)' : 'rgba(244,63,94,0.3)'}` }}>
      <span style={{ fontSize:10, fontWeight:700, color: down ? '#10b981' : '#f43f5e' }}>{change}</span>
    </div>
  )
}

/* ── Vehicle row ─────────────────────────────────────────────────────────────── */
function VehicleRow({ v, i }: { v:typeof VEHICLES[0]; i:number }) {
  return (
    <motion.div
      initial={{ opacity:0, x:12 }} animate={{ opacity:1, x:0 }}
      transition={{ delay: 0.6 + i*0.07, duration:0.4, ease:EASE }}
      style={{
        display:'flex', alignItems:'center', gap:12, padding:'10px 14px', borderRadius:12,
        background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.06)',
        cursor:'pointer', transition:'all 0.2s cubic-bezier(0.22,1,0.36,1)',
      }}
      whileHover={{ background:'rgba(255,255,255,0.07)', borderColor:'rgba(255,255,255,0.11)' }}
    >
      {/* SDI mini */}
      <SDIArc value={v.sdi} />

      {/* Vehicle info */}
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:3 }}>
          <span style={{ fontSize:12, fontWeight:800, color:'#f1f5f9', letterSpacing:'-0.01em' }}>{v.make} {v.model}</span>
          {v.hot && <div style={{ fontSize:8, fontWeight:800, padding:'1px 6px', borderRadius:999, background:'rgba(244,63,94,0.15)', border:'1px solid rgba(244,63,94,0.3)', color:'#f43f5e', letterSpacing:'0.07em' }}>HOT</div>}
        </div>
        <div style={{ fontSize:10, color:'#475569' }}>{v.flag} {v.city} · {v.regime}</div>
      </div>

      {/* Prices */}
      <div style={{ textAlign:'right', flexShrink:0 }}>
        <div style={{ fontSize:13, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.02em', marginBottom:3 }}>{v.price}</div>
        <PriceBadge change={v.change} />
      </div>

      {/* NLC */}
      <div style={{ textAlign:'right', flexShrink:0, minWidth:90 }}>
        <div style={{ fontSize:9, color:'#334155', textTransform:'uppercase', letterSpacing:'0.07em', fontWeight:600, marginBottom:2 }}>NLC {v.dest}</div>
        <div style={{ fontSize:12, fontWeight:800, color:'#a78bfa' }}>{v.nlc}</div>
      </div>
    </motion.div>
  )
}

/* ── Landing ─────────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const [activeTab, setActiveTab] = useState(0)

  return (
    <div style={{ background:'#09091e', minHeight:'100dvh', fontFamily:F, overflowX:'hidden', color:'#f1f5f9' }}>

      {/* ── TOP NAV ──────────────────────────────────────────────────────── */}
      <motion.header
        initial={{ opacity:0, y:-10 }} animate={{ opacity:1, y:0 }}
        transition={{ duration:0.5, ease:EASE }}
        style={{
          display:'flex', alignItems:'center', height:60, padding:'0 24px',
          background:'rgba(9,9,30,0.85)', backdropFilter:'blur(24px) saturate(180%)',
          WebkitBackdropFilter:'blur(24px) saturate(180%)',
          borderBottom:'1px solid rgba(255,255,255,0.07)',
          position:'sticky', top:0, zIndex:100,
        }}
      >
        {/* Logo */}
        <div style={{ display:'flex', alignItems:'center', gap:10, marginRight:40 }}>
          <div style={{ width:30, height:30, borderRadius:9, background:'rgba(99,102,241,0.2)', border:'1px solid rgba(99,102,241,0.4)', display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 0 20px rgba(99,102,241,0.25)' }}>
            <div style={{ width:11, height:11, borderRadius:3, background:'linear-gradient(135deg,#818cf8,#6366f1)', boxShadow:'0 0 10px rgba(99,102,241,0.6)' }} />
          </div>
          <span style={{ fontSize:14, fontWeight:900, letterSpacing:'0.18em', background:'linear-gradient(120deg,#a5b4fc,#c4b5fd,#67e8f9)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>CARDEX</span>
        </div>

        {/* Pill tabs */}
        <div style={{ display:'flex', alignItems:'center', gap:2, background:'rgba(255,255,255,0.04)', borderRadius:999, padding:3, border:'1px solid rgba(255,255,255,0.07)', flex:1, maxWidth:420 }}>
          {TABS.map((t,i) => (
            <button key={t} onClick={() => setActiveTab(i)}
              style={{
                flex:1, padding:'6px 0', borderRadius:999, fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:F, border:'none', transition:'all 0.2s',
                background: activeTab===i ? 'rgba(255,255,255,0.1)' : 'transparent',
                color: activeTab===i ? '#f1f5f9' : '#64748b',
                boxShadow: activeTab===i ? '0 1px 0 rgba(255,255,255,0.08) inset' : 'none',
                backdropFilter: activeTab===i ? 'blur(10px)' : 'none',
              }}
            >{t}</button>
          ))}
          {/* Reports badge */}
          <div style={{ position:'relative', flex:1 }}>
            <div style={{ position:'absolute', top:-2, right:-2, width:14, height:14, borderRadius:'50%', background:'#6366f1', border:'2px solid #09091e', display:'flex', alignItems:'center', justifyContent:'center', fontSize:7, fontWeight:800, color:'#fff' }}>12</div>
          </div>
        </div>

        {/* Right actions */}
        <div style={{ display:'flex', alignItems:'center', gap:8, marginLeft:'auto' }}>
          <button style={{ width:34, height:34, borderRadius:10, background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.08)', display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', color:'#64748b', transition:'all 0.15s' }}
            onMouseEnter={e=>{e.currentTarget.style.background='rgba(255,255,255,0.09)';e.currentTarget.style.color='#f1f5f9'}}
            onMouseLeave={e=>{e.currentTarget.style.background='rgba(255,255,255,0.05)';e.currentTarget.style.color='#64748b'}}>
            <Bell style={{ width:14, height:14 }} />
          </button>
          <button onClick={() => nav('/login')}
            style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 16px', borderRadius:999, fontSize:12, fontWeight:600, color:'#f1f5f9', background:'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.12)', cursor:'pointer', fontFamily:F, backdropFilter:'blur(10px)' }}>
            Sign in
          </button>
          <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.04 }} whileTap={{ scale:0.97 }}
            style={{ display:'flex', alignItems:'center', gap:8, padding:'7px 18px', borderRadius:999, fontSize:12, fontWeight:700, color:'#fff', background:'linear-gradient(135deg,#6366f1,#7c3aed)', border:'none', cursor:'pointer', fontFamily:F, boxShadow:'0 0 20px rgba(99,102,241,0.4)' }}>
            <div style={{ width:20, height:20, borderRadius:'50%', background:'rgba(255,255,255,0.15)', display:'flex', alignItems:'center', justifyContent:'center' }}>
              <span style={{ fontSize:10, fontWeight:800 }}>↗</span>
            </div>
            Tom Dawson
          </motion.button>
        </div>
      </motion.header>

      {/* ── MAIN LAYOUT ──────────────────────────────────────────────────── */}
      <div style={{ display:'flex', height:'calc(100dvh - 60px)', overflow:'hidden' }}>

        {/* ── LEFT ICON SIDEBAR ──────────────────────────────────────────── */}
        <motion.aside
          initial={{ opacity:0, x:-20 }} animate={{ opacity:1, x:0 }}
          transition={{ delay:0.1, duration:0.5, ease:EASE }}
          style={{
            width:56, flexShrink:0, display:'flex', flexDirection:'column', alignItems:'center',
            paddingTop:20, gap:6,
            background:'rgba(9,9,30,0.7)', backdropFilter:'blur(20px) saturate(160%)',
            WebkitBackdropFilter:'blur(20px) saturate(160%)',
            borderRight:'1px solid rgba(255,255,255,0.07)',
          }}
        >
          {SIDE_NAV.map(({ icon:Icon, active }, i) => (
            <button key={i}
              style={{
                width:36, height:36, borderRadius:11, display:'flex', alignItems:'center', justifyContent:'center',
                background: active ? 'rgba(99,102,241,0.22)' : 'transparent',
                border: active ? '1px solid rgba(99,102,241,0.4)' : '1px solid transparent',
                cursor:'pointer', transition:'all 0.2s',
                boxShadow: active ? '0 0 16px rgba(99,102,241,0.2)' : 'none',
              }}
              onMouseEnter={e=>{ if(!active) e.currentTarget.style.background='rgba(255,255,255,0.07)' }}
              onMouseLeave={e=>{ if(!active) e.currentTarget.style.background='transparent' }}
            >
              <Icon style={{ width:15, height:15, color: active ? '#a5b4fc' : '#475569', filter: active ? 'drop-shadow(0 0 5px rgba(165,180,252,0.5))':'none' }} strokeWidth={active?2.3:1.8} />
            </button>
          ))}

          <div style={{ flex:1 }} />

          {/* User avatar */}
          <div style={{ width:32, height:32, borderRadius:'50%', background:'linear-gradient(135deg,#6366f1,#7c3aed)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:800, color:'#fff', marginBottom:16, boxShadow:'0 0 14px rgba(99,102,241,0.3)' }}>T</div>
        </motion.aside>

        {/* ── LEFT PHOTO PANEL ───────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity:0 }} animate={{ opacity:1 }}
          transition={{ delay:0.15, duration:0.7, ease:EASE }}
          style={{ flex:'0 0 42%', position:'relative', overflow:'hidden' }}
        >
          {/* Car photo */}
          <img src={HERO_CAR} alt="Luxury vehicle" style={{ width:'100%', height:'100%', objectFit:'cover', objectPosition:'center 60%' }} />

          {/* Gradient overlays */}
          <div style={{ position:'absolute', inset:0, background:'linear-gradient(to right, rgba(9,9,30,0.15) 0%, rgba(9,9,30,0.08) 50%, rgba(9,9,30,0.65) 100%)' }} />
          <div style={{ position:'absolute', inset:0, background:'linear-gradient(to top, rgba(9,9,30,0.85) 0%, transparent 50%)' }} />

          {/* Hero copy */}
          <motion.div
            initial={{ opacity:0, y:20 }} animate={{ opacity:1, y:0 }}
            transition={{ delay:0.4, duration:0.6, ease:EASE }}
            style={{ position:'absolute', bottom:60, left:28, right:28, zIndex:2 }}
          >
            <div style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'4px 12px', borderRadius:999, background:'rgba(99,102,241,0.15)', backdropFilter:'blur(12px)', border:'1px solid rgba(99,102,241,0.3)', marginBottom:16 }}>
              <div style={{ width:5, height:5, borderRadius:'50%', background:'#818cf8', animation:'cxPulse 2s infinite' }} />
              <span style={{ fontSize:9, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#a5b4fc' }}>B2B Vehicle Intelligence</span>
            </div>
            <h1 style={{ fontSize:'clamp(26px,3.5vw,40px)', fontWeight:900, lineHeight:1.1, letterSpacing:'-0.04em', marginBottom:12, color:'#f8fafc' }}>
              Hello, trader.<br />
              <span style={{ background:'linear-gradient(120deg,#a5b4fc,#c4b5fd 50%,#67e8f9)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>
                Your fiscal edge<br />starts here.
              </span>
            </h1>
            <p style={{ fontSize:13, color:'rgba(255,255,255,0.5)', marginBottom:22, lineHeight:1.6, maxWidth:340 }}>
              3.5M listings across 6 EU countries. IVA/REBU auto-classification and NLC computed on every vehicle.
            </p>
            <div style={{ display:'flex', gap:10 }}>
              <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.04, boxShadow:'0 0 40px rgba(99,102,241,0.5)' }} whileTap={{ scale:0.97 }}
                style={{ display:'flex', alignItems:'center', gap:8, padding:'11px 22px', borderRadius:12, fontSize:13, fontWeight:700, color:'#fff', background:'linear-gradient(135deg,#6366f1,#7c3aed)', border:'none', cursor:'pointer', fontFamily:F, boxShadow:'0 0 24px rgba(99,102,241,0.35)' }}>
                Enter platform <ArrowUpRight style={{ width:13, height:13 }} strokeWidth={2.5} />
              </motion.button>
              <button onClick={() => nav('/check')}
                style={{ display:'flex', alignItems:'center', gap:7, padding:'11px 18px', borderRadius:12, fontSize:13, fontWeight:600, color:'rgba(255,255,255,0.6)', background:'rgba(255,255,255,0.08)', backdropFilter:'blur(12px)', border:'1px solid rgba(255,255,255,0.12)', cursor:'pointer', fontFamily:F, transition:'all 0.2s' }}
                onMouseEnter={e=>{e.currentTarget.style.color='#f1f5f9';e.currentTarget.style.background='rgba(255,255,255,0.12)'}}
                onMouseLeave={e=>{e.currentTarget.style.color='rgba(255,255,255,0.6)';e.currentTarget.style.background='rgba(255,255,255,0.08)'}}>
                VIN Check <ChevronRight style={{ width:12, height:12 }} />
              </button>
            </div>
          </motion.div>

          {/* Smart Family Hub card — bottom */}
          <motion.div
            initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }}
            transition={{ delay:0.75, duration:0.5, ease:EASE }}
            style={{
              position:'absolute', bottom:0, left:0, right:0, padding:'14px 24px',
              display:'flex', alignItems:'center', justifyContent:'space-between',
              background:'rgba(9,9,30,0.7)', backdropFilter:'blur(20px)', borderTop:'1px solid rgba(255,255,255,0.07)',
            }}
          >
            <div>
              <div style={{ fontSize:11, fontWeight:700, color:'#f1f5f9' }}>CARDEX Intelligence Hub</div>
              <div style={{ fontSize:9, color:'#475569', marginTop:1 }}>Monitor all EU markets with your team</div>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:-4 }}>
              {['#6366f1','#7c3aed','#0891b2'].map((c,i) => (
                <div key={i} style={{ width:24, height:24, borderRadius:'50%', background:c, border:'2px solid #09091e', marginLeft:i===0?0:-8, display:'flex', alignItems:'center', justifyContent:'center', fontSize:9, fontWeight:800, color:'#fff' }}>{String.fromCharCode(65+i)}</div>
              ))}
              <div style={{ width:24, height:24, borderRadius:'50%', background:'rgba(255,255,255,0.1)', border:'2px solid rgba(255,255,255,0.15)', marginLeft:-8, display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer' }}>
                <Plus style={{ width:10, height:10, color:'#94a3b8' }} />
              </div>
            </div>
          </motion.div>
        </motion.div>

        {/* ── RIGHT PANEL — glass cards ──────────────────────────────────── */}
        <div style={{ flex:1, display:'flex', flexDirection:'column', overflowY:'auto', padding:'20px 20px 20px 16px', gap:14, background:'rgba(9,9,30,0.6)', backdropFilter:'blur(8px)' }}>

          {/* Stats strip */}
          <motion.div
            initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
            transition={{ delay:0.3, duration:0.5, ease:EASE }}
            style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12 }}
          >
            {[
              { label:'Indexed today', value:'+2.847', color:'#10b981', sub:'vehicles classified' },
              { label:'Active alerts', value:'14',     color:'#f59e0b', sub:'price drops detected' },
              { label:'Avg NLC margin', value:'4.8%',  color:'#a78bfa', sub:'across EU6 countries' },
            ].map((s,i) => (
              <motion.div key={s.label}
                initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }}
                transition={{ delay:0.35+i*0.06, duration:0.4, ease:EASE }}
                style={{
                  padding:'14px 16px', borderRadius:14,
                  background:'rgba(255,255,255,0.06)',
                  backdropFilter:'blur(20px) saturate(180%)',
                  WebkitBackdropFilter:'blur(20px) saturate(180%)',
                  border:'1px solid rgba(255,255,255,0.09)',
                  boxShadow:'0 4px 16px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08)',
                }}
              >
                <div style={{ fontSize:9, color:'#475569', textTransform:'uppercase', letterSpacing:'0.08em', fontWeight:600, marginBottom:6 }}>{s.label}</div>
                <div style={{ fontSize:22, fontWeight:900, color:s.color, letterSpacing:'-0.03em', marginBottom:3, textShadow:`0 0 20px ${s.color}40` }}>{s.value}</div>
                <div style={{ fontSize:9, color:'#334155', fontWeight:500 }}>{s.sub}</div>
              </motion.div>
            ))}
          </motion.div>

          {/* Live feed header */}
          <motion.div
            initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ delay:0.5, duration:0.4 }}
            style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}
          >
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ width:6, height:6, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 10px #10b981', animation:'cxPulse 2s infinite' }} />
              <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8', letterSpacing:'0.08em', textTransform:'uppercase' }}>Live feed</span>
              <LiveTicker />
            </div>
            <button onClick={() => nav('/login')} style={{ fontSize:10, fontWeight:700, color:'#6366f1', background:'transparent', border:'none', cursor:'pointer', fontFamily:F, textDecoration:'none', display:'flex', alignItems:'center', gap:4 }}>
              View all <ArrowUpRight style={{ width:10, height:10 }} />
            </button>
          </motion.div>

          {/* Vehicle rows */}
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {VEHICLES.map((v,i) => <VehicleRow key={i} v={v} i={i} />)}
          </div>

          {/* Bottom cards row */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
            {/* NLC breakdown */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.85, duration:0.5, ease:EASE }}
              style={{
                padding:'16px', borderRadius:16,
                background:'rgba(255,255,255,0.06)',
                backdropFilter:'blur(20px) saturate(180%)',
                border:'1px solid rgba(255,255,255,0.09)',
                boxShadow:'0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08)',
              }}
            >
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
                <div style={{ fontSize:10, fontWeight:700, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'0.08em' }}>NLC by country</div>
                <div style={{ width:20, height:20, borderRadius:6, background:'rgba(99,102,241,0.18)', border:'1px solid rgba(99,102,241,0.3)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <BarChart3 style={{ width:10, height:10, color:'#818cf8' }} strokeWidth={2} />
                </div>
              </div>
              {[
                { c:'🇩🇪', n:'Germany',  v:34, col:'#6366f1' },
                { c:'🇪🇸', n:'Spain',    v:27, col:'#7c3aed' },
                { c:'🇫🇷', n:'France',   v:22, col:'#0891b2' },
                { c:'🇳🇱', n:'Netherlands', v:17, col:'#059669' },
              ].map(item => (
                <div key={item.n} style={{ marginBottom:8 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                    <span style={{ fontSize:10, color:'#64748b' }}>{item.c} {item.n}</span>
                    <span style={{ fontSize:10, fontWeight:700, color:'#94a3b8' }}>{item.v}%</span>
                  </div>
                  <div style={{ height:3, background:'rgba(255,255,255,0.06)', borderRadius:2, overflow:'hidden' }}>
                    <motion.div initial={{ width:0 }} animate={{ width:`${item.v}%` }} transition={{ delay:1+Math.random()*0.3, duration:0.8, ease:EASE }}
                      style={{ height:'100%', background:`linear-gradient(90deg, ${item.col}80, ${item.col})`, borderRadius:2 }} />
                  </div>
                </div>
              ))}
            </motion.div>

            {/* Classification widget */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.9, duration:0.5, ease:EASE }}
              style={{
                padding:'16px', borderRadius:16,
                background:'rgba(255,255,255,0.06)',
                backdropFilter:'blur(20px) saturate(180%)',
                border:'1px solid rgba(255,255,255,0.09)',
                boxShadow:'0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08)',
              }}
            >
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
                <div style={{ fontSize:10, fontWeight:700, color:'#94a3b8', textTransform:'uppercase', letterSpacing:'0.08em' }}>Fiscal regime today</div>
                <div style={{ width:6, height:6, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 8px #10b981', animation:'cxPulse 2s infinite' }} />
              </div>

              {/* Donut simplified */}
              <div style={{ display:'flex', justifyContent:'center', marginBottom:14 }}>
                <div style={{ position:'relative', width:80, height:80 }}>
                  <svg viewBox="0 0 80 80" width={80} height={80}>
                    <circle cx={40} cy={40} r={28} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={14} />
                    <motion.circle cx={40} cy={40} r={28} fill="none" stroke="#6366f1" strokeWidth={14}
                      strokeDasharray={`${176 * 0.62} ${176}`} strokeDashoffset={44} strokeLinecap="round"
                      initial={{ strokeDasharray:'0 176' }} animate={{ strokeDasharray:`${176*0.62} 176` }}
                      transition={{ delay:1, duration:1.2, ease:EASE }} />
                    <motion.circle cx={40} cy={40} r={28} fill="none" stroke="#0891b2" strokeWidth={14}
                      strokeDasharray={`${176 * 0.38} ${176}`} strokeDashoffset={`${44 - 176*0.62}`} strokeLinecap="round"
                      initial={{ strokeDasharray:'0 176' }} animate={{ strokeDasharray:`${176*0.38} 176` }}
                      transition={{ delay:1.3, duration:1, ease:EASE }} />
                  </svg>
                  <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
                    <div style={{ fontSize:16, fontWeight:900, color:'#f8fafc' }}>62%</div>
                    <div style={{ fontSize:7, color:'#475569', fontWeight:600 }}>IVA</div>
                  </div>
                </div>
              </div>

              {[{ c:'#6366f1', l:'IVA Deductible', v:'62%' }, { c:'#0891b2', l:'REBU', v:'38%' }].map(item => (
                <div key={item.l} style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
                  <div style={{ width:8, height:8, borderRadius:2, background:item.c, flexShrink:0 }} />
                  <span style={{ fontSize:10, color:'#64748b', flex:1 }}>{item.l}</span>
                  <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8' }}>{item.v}</span>
                </div>
              ))}

              <div style={{ marginTop:12, padding:'8px 10px', borderRadius:9, background:'rgba(99,102,241,0.1)', border:'1px solid rgba(99,102,241,0.2)', display:'flex', alignItems:'center', gap:6 }}>
                <Zap style={{ width:10, height:10, color:'#818cf8', flexShrink:0 }} strokeWidth={2.5} />
                <span style={{ fontSize:9, color:'#818cf8', fontWeight:600 }}>Auto-classified in &lt; 2s per listing</span>
              </div>
            </motion.div>
          </div>

          {/* Bottom search / mini toolbar */}
          <motion.div
            initial={{ opacity:0 }} animate={{ opacity:1 }}
            transition={{ delay:1, duration:0.4 }}
            style={{ display:'flex', alignItems:'center', gap:8, padding:'10px 14px', borderRadius:14, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.07)', backdropFilter:'blur(16px)' }}
          >
            <Search style={{ width:13, height:13, color:'#475569', flexShrink:0 }} />
            <span style={{ fontSize:12, color:'#334155', flex:1 }}>Search 3.5M vehicles, VINs, dealers...</span>
            <div style={{ display:'flex', gap:4 }}>
              {[
                { icon:Plus,  label:'Add' },
                { icon:Minus, label:'Remove' },
                { icon:X,     label:'Clear' },
              ].map(({ icon:Icon, label }) => (
                <button key={label} title={label}
                  style={{ width:26, height:26, borderRadius:7, background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.09)', display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', transition:'all 0.15s' }}
                  onMouseEnter={e=>{e.currentTarget.style.background='rgba(255,255,255,0.12)'}}
                  onMouseLeave={e=>{e.currentTarget.style.background='rgba(255,255,255,0.06)'}}>
                  <Icon style={{ width:10, height:10, color:'#64748b' }} />
                </button>
              ))}
            </div>
          </motion.div>
        </div>
      </div>

      <style>{`@keyframes cxPulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.8)}}`}</style>
    </div>
  )
}
