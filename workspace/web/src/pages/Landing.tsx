/**
 * Landing — pixel-faithful CARDEX adaptation of the SmartHome "Modern UI Flow" reference.
 * https://es.pinterest.com/pin/777574691956038286/
 *
 * Structure:
 *  - Lavender/light outer background
 *  - App floats as device-mockup card
 *  - Left 40%: warm car photo + greeting overlay + toolbar
 *  - Thin left icon sidebar
 *  - Right 60%: dark bento grid (Energy→NewListings, Temp→TopOpportunity,
 *                                 WiFi→IVA toggle, Lighting→SDI gauge,
 *                                 Kitchen→REBU toggle, Solar→NLC chart)
 */
import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search, Plus, Minus, X, MoreHorizontal,
  Mail, Bell, ChevronLeft, ChevronDown,
  LayoutDashboard, Car, FileSearch, Users,
  BarChart3, Settings, Shield, ArrowUpRight,
  Maximize2, ToggleRight,
} from 'lucide-react'

const F = '"Inter", system-ui, -apple-system, sans-serif'
const E = [0.22, 1, 0.36, 1] as const

const HERO_PHOTO = 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=900&q=92&auto=format&fit=crop'

/* ─── Toggle switch ──────────────────────────────────────────────────────── */
function Toggle({ on, color = '#06b6d4' }: { on: boolean; color?: string }) {
  return (
    <div style={{
      width: 44, height: 24, borderRadius: 99, position: 'relative', flexShrink: 0,
      background: on ? color : 'rgba(255,255,255,0.12)',
      border: `1px solid ${on ? color : 'rgba(255,255,255,0.15)'}`,
      boxShadow: on ? `0 0 12px ${color}60` : 'none',
      transition: 'all 0.3s',
      cursor: 'pointer',
    }}>
      <motion.div
        animate={{ x: on ? 22 : 2 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        style={{ position: 'absolute', top: 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
      />
    </div>
  )
}

/* ─── SDI semicircle gauge ───────────────────────────────────────────────── */
function SDIGauge({ value }: { value: number }) {
  const pct = value / 10
  const R = 52, cx = 60, cy = 60
  const arc = Math.PI * R
  const dash = arc * pct
  const col = value >= 7 ? '#f43f5e' : value >= 5 ? '#f59e0b' : '#06b6d4'
  return (
    <div style={{ position: 'relative', width: 120, height: 70, margin: '0 auto' }}>
      <svg width={120} height={70} viewBox="0 0 120 70">
        <path d={`M 8,60 A ${R},${R} 0 0 1 112,60`} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={8} strokeLinecap="round" />
        <motion.path
          d={`M 8,60 A ${R},${R} 0 0 1 112,60`}
          fill="none" stroke={col} strokeWidth={8} strokeLinecap="round"
          strokeDasharray={`${arc}`} strokeDashoffset={arc - dash}
          initial={{ strokeDashoffset: arc }}
          animate={{ strokeDashoffset: arc - dash }}
          transition={{ duration: 1.4, ease: E, delay: 0.5 }}
        />
        {/* needle */}
        <motion.line
          x1={cx} y1={cy}
          x2={cx + Math.cos(Math.PI + pct * Math.PI) * (R - 12)}
          y2={cy + Math.sin(Math.PI + pct * Math.PI) * (R - 12)}
          stroke={col} strokeWidth={2.5} strokeLinecap="round"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 0.3 }}
        />
        <circle cx={cx} cy={cy} r={4} fill={col} />
        <text x={cx} y={cy + 16} textAnchor="middle" fill={col} fontSize={22} fontWeight={900}>{value}</text>
      </svg>
    </div>
  )
}

/* ─── Mini area chart ────────────────────────────────────────────────────── */
function MiniChart({ data, color }: { data: number[]; color: string }) {
  const w = 100, h = 40
  const max = Math.max(...data), min = Math.min(...data)
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / (max - min + 1)) * (h - 4) - 2
    return `${x},${y}`
  })
  const area = `M0,${h} L${pts.join(' L')} L${w},${h} Z`
  const line = pts.join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`cg${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#cg${color.replace('#','')})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {/* highlight dot at last point */}
      <circle cx={w} cy={pts[pts.length-1].split(',')[1]} r={3} fill={color} />
      <circle cx={w} cy={pts[pts.length-1].split(',')[1]} r={6} fill={color} fillOpacity={0.2} />
    </svg>
  )
}

/* ─── NLC area chart (wide) ──────────────────────────────────────────────── */
function NLCChart() {
  const data = [38, 42, 36, 44, 40, 52, 48]
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
  const w = 280, h = 60
  const max = Math.max(...data), min = 30
  const pts = data.map((v, i) => {
    const x = 8 + (i / (data.length - 1)) * (w - 16)
    const y = h - ((v - min) / (max - min + 2)) * (h - 8) - 4
    return [x, y] as [number, number]
  })
  const area = `M${pts[0][0]},${h} ` + pts.map(([x,y]) => `L${x},${y}`).join(' ') + ` L${pts[pts.length-1][0]},${h} Z`
  const line = pts.map(([x,y]) => `${x},${y}`).join(' ')
  return (
    <div style={{ position: 'relative' }}>
      <svg width={w} height={h+20} viewBox={`0 0 ${w} ${h+20}`}>
        <defs>
          <linearGradient id="nlcGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#nlcGrad)" />
        <polyline points={line} fill="none" stroke="#06b6d4" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {/* peak label */}
        <rect x={pts[5][0]-20} y={pts[5][1]-18} width={40} height={16} rx={8} fill="rgba(255,255,255,0.9)" />
        <text x={pts[5][0]} y={pts[5][1]-7} textAnchor="middle" fontSize={9} fontWeight={700} fill="#0a0a1a">4.8%</text>
        {/* day labels */}
        {days.map((d, i) => (
          <text key={d} x={pts[i][0]} y={h+16} textAnchor="middle" fontSize={8} fill="rgba(255,255,255,0.25)">{d}</text>
        ))}
      </svg>
    </div>
  )
}

/* ─── MAIN ───────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const [ivaOn,  setIvaOn]  = useState(true)
  const [rebuOn, setRebuOn] = useState(true)
  const [tab, setTab] = useState(0)

  const cardBase: React.CSSProperties = {
    borderRadius: 16,
    background: 'rgba(255,255,255,0.07)',
    backdropFilter: 'blur(20px) saturate(180%)',
    WebkitBackdropFilter: 'blur(20px) saturate(180%)',
    border: '1px solid rgba(255,255,255,0.10)',
    boxShadow: '0 4px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.10)',
    padding: 16,
    overflow: 'hidden',
    position: 'relative',
  }

  return (
    /* Outer lavender background */
    <div style={{
      minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #ede9fe 0%, #e0e7ff 40%, #dbeafe 70%, #e0f2fe 100%)',
      fontFamily: F, padding: '24px',
    }}>

      {/* ── APP FRAME (device mockup) ──────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.7, ease: E }}
        style={{
          width: '100%', maxWidth: 1020, aspectRatio: '4/3',
          borderRadius: 24,
          background: '#0e0e22',
          boxShadow: '0 40px 120px rgba(99,102,241,0.25), 0 8px 32px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          border: '1px solid rgba(255,255,255,0.12)',
        }}
      >

        {/* ── TOP NAVBAR ──────────────────────────────────────────────── */}
        <div style={{
          height: 52, flexShrink: 0, display: 'flex', alignItems: 'center',
          padding: '0 16px',
          background: 'rgba(14,14,34,0.95)',
          borderBottom: '1px solid rgba(255,255,255,0.07)',
          backdropFilter: 'blur(20px)',
          gap: 12,
        }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginRight: 8 }}>
            <div style={{ width: 26, height: 26, borderRadius: 8, background: 'rgba(99,102,241,0.25)', border: '1px solid rgba(99,102,241,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 14px rgba(99,102,241,0.3)' }}>
              <div style={{ width: 10, height: 10, borderRadius: 3, background: 'linear-gradient(135deg,#818cf8,#6366f1)' }} />
            </div>
            <span style={{ fontSize: 12, fontWeight: 900, letterSpacing: '0.16em', background: 'linear-gradient(120deg,#a5b4fc,#c4b5fd,#67e8f9)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>CARDEX</span>
          </div>

          {/* Pill tabs */}
          <div style={{ display: 'flex', gap: 2, background: 'rgba(255,255,255,0.05)', borderRadius: 999, padding: '3px', border: '1px solid rgba(255,255,255,0.07)' }}>
            {['Dashboard','Coverage','Listings','Reports'].map((t, i) => (
              <button key={t} onClick={() => setTab(i)} style={{
                padding: '4px 14px', borderRadius: 999, fontSize: 11, fontWeight: 600, border: 'none', cursor: 'pointer', fontFamily: F, transition: 'all 0.2s',
                background: tab === i ? 'rgba(255,255,255,0.12)' : 'transparent',
                color: tab === i ? '#f1f5f9' : '#64748b',
                boxShadow: tab === i ? 'inset 0 1px 0 rgba(255,255,255,0.1)' : 'none',
              }}>
                {t}{i === 3 && <span style={{ marginLeft: 4, fontSize: 9, fontWeight: 800, background: '#6366f1', color: '#fff', padding: '1px 5px', borderRadius: 99 }}>12</span>}
              </button>
            ))}
          </div>

          <div style={{ flex: 1 }} />

          {/* Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {[Mail, Bell].map((Icon, i) => (
              <button key={i} style={{ width: 30, height: 30, borderRadius: 9, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', transition: 'all 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}>
                <Icon style={{ width: 12, height: 12, color: '#64748b' }} />
              </button>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 10px 4px 4px', borderRadius: 999, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' }}>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'linear-gradient(135deg,#6366f1,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 800, color: '#fff' }}>E</div>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#e2e8f0' }}>Elias K.</span>
              <ChevronDown style={{ width: 10, height: 10, color: '#64748b' }} />
            </div>
          </div>
        </div>

        {/* ── BODY ──────────────────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

          {/* ── LEFT ICON SIDEBAR ──────────────────────────────────────── */}
          <div style={{
            width: 48, flexShrink: 0,
            background: 'rgba(14,14,34,0.8)',
            borderRight: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            paddingTop: 16, gap: 4,
          }}>
            {[
              { Icon: LayoutDashboard, active: true  },
              { Icon: Car,             active: false },
              { Icon: BarChart3,       active: false },
              { Icon: FileSearch,      active: false },
              { Icon: Shield,          active: false },
              { Icon: Settings,        active: false },
            ].map(({ Icon, active }, i) => (
              <div key={i} style={{
                width: 32, height: 32, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
                background: active ? 'rgba(255,255,255,0.12)' : 'transparent',
                border: active ? '1px solid rgba(255,255,255,0.18)' : '1px solid transparent',
                transition: 'all 0.2s',
              }}
                onMouseEnter={e => { if(!active)(e.currentTarget as HTMLDivElement).style.background='rgba(255,255,255,0.07)' }}
                onMouseLeave={e => { if(!active)(e.currentTarget as HTMLDivElement).style.background='transparent' }}
              >
                <Icon style={{ width: 14, height: 14, color: active ? '#f1f5f9' : '#334155' }} strokeWidth={active ? 2.2 : 1.8} />
              </div>
            ))}
          </div>

          {/* ── LEFT PHOTO PANEL ───────────────────────────────────────── */}
          <div style={{ flex: '0 0 42%', position: 'relative', overflow: 'hidden' }}>
            <img src={HERO_PHOTO} alt="Luxury vehicle" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center 55%' }} />
            {/* warm amber tint overlay to match reference */}
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(160deg, rgba(14,14,34,0.05) 0%, rgba(251,146,60,0.08) 50%, rgba(14,14,34,0.7) 100%)' }} />
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(14,14,34,0.92) 0%, transparent 55%)' }} />
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to right, transparent 60%, rgba(14,14,34,0.5) 100%)' }} />

            {/* Greeting top-left */}
            <motion.div
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.5, ease: E }}
              style={{ position: 'absolute', top: 18, left: 16 }}
            >
              <div style={{ fontSize: 16, fontWeight: 900, color: '#f8fafc', letterSpacing: '-0.02em', textShadow: '0 2px 20px rgba(0,0,0,0.5)' }}>Hello, trader.</div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', marginTop: 2 }}>How's your arbitrage going?</div>
            </motion.div>

            {/* Bottom CTA + toolbar */}
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0 }}>
              <motion.div
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.5, ease: E }}
                style={{ padding: '0 16px 12px' }}
              >
                <motion.button
                  onClick={() => nav('/login')}
                  whileHover={{ scale: 1.04, boxShadow: '0 0 30px rgba(99,102,241,0.6)' }}
                  whileTap={{ scale: 0.97 }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 20px', borderRadius: 10, fontSize: 12, fontWeight: 700, color: '#fff', background: 'linear-gradient(135deg,#6366f1,#7c3aed)', border: 'none', cursor: 'pointer', fontFamily: F, boxShadow: '0 0 20px rgba(99,102,241,0.4)' }}
                >
                  Enter platform <ArrowUpRight style={{ width: 12, height: 12 }} strokeWidth={2.5} />
                </motion.button>
              </motion.div>

              {/* Bottom bar */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 14px',
                background: 'rgba(14,14,34,0.75)',
                backdropFilter: 'blur(16px)',
                borderTop: '1px solid rgba(255,255,255,0.07)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {[Search, Plus, Minus, X].map((Icon, i) => (
                    <button key={i} style={{ width: 26, height: 26, borderRadius: 7, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                      <Icon style={{ width: 10, height: 10, color: '#94a3b8' }} />
                    </button>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: '#f1f5f9' }}>CARDEX Intelligence Hub</div>
                  <div style={{ fontSize: 8, color: '#475569' }}>Monitor all EU markets with your team</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  {['#6366f1','#7c3aed','#0891b2'].map((c, i) => (
                    <div key={i} style={{ width: 22, height: 22, borderRadius: '50%', background: c, border: '2px solid #0e0e22', marginLeft: i === 0 ? 0 : -7, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontWeight: 800, color: '#fff' }}>{String.fromCharCode(65+i)}</div>
                  ))}
                  <div style={{ width: 22, height: 22, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', border: '2px solid rgba(255,255,255,0.2)', marginLeft: -7, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                    <Plus style={{ width: 8, height: 8, color: '#94a3b8' }} />
                  </div>
                  <button style={{ marginLeft: 10, width: 22, height: 22, borderRadius: 6, background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                    <ChevronLeft style={{ width: 10, height: 10, color: '#94a3b8' }} />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* ── RIGHT BENTO GRID ───────────────────────────────────────── */}
          <div style={{
            flex: 1, padding: '14px 14px 0 10px',
            background: 'rgba(10,10,24,0.6)',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gridTemplateRows: 'auto auto auto auto',
            gap: 10,
            overflowY: 'auto',
          }}>

            {/* Card 1 — New Listings (= Energy Usage, left, tall) */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.3, duration:0.45, ease:E }}
              style={{ ...cardBase }}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 }}>
                <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8' }}>New Listings Today</span>
                <Maximize2 style={{ width:12, height:12, color:'#334155', cursor:'pointer' }} />
              </div>
              <div style={{ marginBottom:8 }}>
                <span style={{ fontSize:28, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.04em' }}>2.847</span>
                <span style={{ fontSize:11, color:'#06b6d4', marginLeft:8, fontWeight:600 }}>Medium</span>
              </div>
              {/* progress bars by country */}
              {[
                { l:'🇩🇪 Germany', v:0.72, c:'#6366f1' },
                { l:'🇪🇸 Spain',   v:0.58, c:'#7c3aed' },
                { l:'🇫🇷 France',  v:0.44, c:'#0891b2' },
              ].map(item => (
                <div key={item.l} style={{ marginBottom:7 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
                    <span style={{ fontSize:9, color:'#475569', fontWeight:600 }}>{item.l}</span>
                    <span style={{ fontSize:9, color:'#475569' }}>{Math.round(item.v*100)}%</span>
                  </div>
                  <div style={{ height:4, background:'rgba(255,255,255,0.07)', borderRadius:2, overflow:'hidden' }}>
                    <motion.div
                      initial={{ width:0 }} animate={{ width:`${item.v*100}%` }}
                      transition={{ delay:0.6+Math.random()*0.2, duration:0.9, ease:E }}
                      style={{ height:'100%', background:`linear-gradient(90deg,${item.c}70,${item.c})`, borderRadius:2 }}
                    />
                  </div>
                </div>
              ))}
              <div style={{ marginTop:10, display:'flex', alignItems:'center', gap:6 }}>
                <div style={{ width:6, height:6, borderRadius:'50%', background:'#06b6d4', boxShadow:'0 0 8px #06b6d4', animation:'cxPulse 2s infinite' }} />
                <span style={{ fontSize:9, color:'#334155', fontWeight:600 }}>Auto-indexing active</span>
              </div>
            </motion.div>

            {/* Card 2 — Top Opportunity (= Living room 23°, right, tall) */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.35, duration:0.45, ease:E }}
              style={{ ...cardBase, background:'rgba(99,102,241,0.12)', border:'1px solid rgba(99,102,241,0.25)', display:'flex', flexDirection:'column' }}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                <span style={{ fontSize:11, fontWeight:700, color:'#a5b4fc' }}>Top Opportunity</span>
                <Toggle on={true} color="#818cf8" />
              </div>
              <div style={{ fontSize:28, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.04em', lineHeight:1 }}>€ 58.900</div>
              <div style={{ fontSize:10, color:'#6366f1', marginTop:4, marginBottom:12 }}>BMW M3 Competition · Munich</div>

              {/* Period selector */}
              <div style={{ display:'flex', gap:4, marginBottom:12 }}>
                {['IVA','REBU','Both'].map((t,i) => (
                  <div key={t} style={{ flex:1, padding:'4px 0', textAlign:'center', borderRadius:6, fontSize:9, fontWeight:700, cursor:'pointer', background:i===0?'rgba(99,102,241,0.3)':'rgba(255,255,255,0.05)', color:i===0?'#a5b4fc':'#475569', border:i===0?'1px solid rgba(99,102,241,0.4)':'1px solid transparent' }}>{t}</div>
                ))}
              </div>

              {/* Mini bar chart */}
              <div style={{ display:'flex', alignItems:'flex-end', gap:3, flex:1 }}>
                {[40,55,48,62,58,70,65].map((v,i) => (
                  <motion.div key={i}
                    initial={{ height:0 }} animate={{ height:`${v}%` }}
                    transition={{ delay:0.7+i*0.05, duration:0.5, ease:E }}
                    style={{ flex:1, background:i===6?'#6366f1':'rgba(99,102,241,0.2)', borderRadius:'3px 3px 0 0', minHeight:4 }}
                  />
                ))}
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', marginTop:4 }}>
                {['M','T','W','T','F','S','S'].map((d,i) => (
                  <span key={i} style={{ fontSize:7, color:'rgba(255,255,255,0.2)', flex:1, textAlign:'center' }}>{d}</span>
                ))}
              </div>
            </motion.div>

            {/* Card 3 — IVA Active (= Wi-Fi toggle, full width, flat) */}
            <motion.div
              initial={{ opacity:0, y:8 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.4, duration:0.4, ease:E }}
              style={{ ...cardBase, padding:'12px 16px', display:'flex', alignItems:'center', justifyContent:'space-between', gridColumn:'1 / -1' }}
              onClick={() => setIvaOn(v => !v)}
            >
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:32, height:32, borderRadius:10, background:'rgba(6,182,212,0.15)', border:'1px solid rgba(6,182,212,0.3)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <ToggleRight style={{ width:14, height:14, color:'#06b6d4' }} />
                </div>
                <div>
                  <div style={{ fontSize:12, fontWeight:700, color:'#f1f5f9' }}>IVA Deductible</div>
                  <div style={{ fontSize:9, color:'#475569' }}>Auto-classification active · 62% of fleet</div>
                </div>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ fontSize:10, color: ivaOn?'#06b6d4':'#475569', fontWeight:600 }}>{ivaOn?'Active':'Paused'}</span>
                <Toggle on={ivaOn} color="#06b6d4" />
              </div>
            </motion.div>

            {/* Card 4 — SDI Score (= Lighting Brightness with dial) */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.45, duration:0.45, ease:E }}
              style={{ ...cardBase }}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:4 }}>
                <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8' }}>Seller Desperation</span>
                <Maximize2 style={{ width:12, height:12, color:'#334155', cursor:'pointer' }} />
              </div>
              <div style={{ fontSize:9, color:'#f43f5e', fontWeight:600, marginBottom:4 }}>8.2 · High</div>
              <SDIGauge value={8.2} />
              <div style={{ textAlign:'center', marginTop:4 }}>
                <span style={{ fontSize:9, color:'#334155' }}>Updated 22:00</span>
              </div>
            </motion.div>

            {/* Card 5 — REBU toggle (= Kitchen) */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.5, duration:0.4, ease:E }}
              style={{ ...cardBase, display:'flex', flexDirection:'column', justifyContent:'space-between' }}
              onClick={() => setRebuOn(v => !v)}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span style={{ fontSize:11, fontWeight:700, color:'#94a3b8' }}>REBU</span>
                <Toggle on={rebuOn} color="#f59e0b" />
              </div>
              <div style={{ marginTop:12 }}>
                <div style={{ fontSize:22, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.03em' }}>38%</div>
                <div style={{ fontSize:9, color:'#475569', marginTop:3 }}>of fleet classified</div>
              </div>
              <div style={{ marginTop:8 }}>
                <MiniChart data={[30,35,28,42,38,45,38]} color="#f59e0b" />
              </div>
            </motion.div>

            {/* Card 6 — NLC Activity (= Solar Charge chart, full width) */}
            <motion.div
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:0.55, duration:0.5, ease:E }}
              style={{ ...cardBase, gridColumn:'1 / -1', marginBottom:14 }}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
                <div>
                  <div style={{ fontSize:11, fontWeight:700, color:'#94a3b8' }}>NLC Activity — this week</div>
                  <div style={{ display:'flex', alignItems:'baseline', gap:6, marginTop:4 }}>
                    <span style={{ fontSize:22, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.03em' }}>4.8%</span>
                    <span style={{ fontSize:10, color:'#06b6d4', fontWeight:600 }}>avg margin EU6</span>
                  </div>
                </div>
                <div style={{ padding:'5px 12px', borderRadius:999, background:'rgba(255,255,255,0.85)', backdropFilter:'blur(8px)' }}>
                  <span style={{ fontSize:10, fontWeight:700, color:'#0a0a1a' }}>4.8%</span>
                </div>
              </div>
              <NLCChart />
            </motion.div>

          </div>
        </div>
      </motion.div>

      <style>{`@keyframes cxPulse{0%,100%{opacity:1}50%{opacity:.3}}`}</style>
    </div>
  )
}
