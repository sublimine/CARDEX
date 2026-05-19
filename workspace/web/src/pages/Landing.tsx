import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion'
import {
  ArrowUpRight, Shield, Zap, Globe, TrendingUp,
  ChevronRight, MapPin, Activity, Check, Car,
  BarChart3, Sparkles, Star,
} from 'lucide-react'

const EASE = [0.22, 1, 0.36, 1] as const
const FONT = '"Inter", system-ui, -apple-system, sans-serif'

/* ─── Hero photos ─────────────────────────────────────────────────────────── */
const HERO_BG   = 'https://images.unsplash.com/photo-1617814076367-b759c7d7e738?w=1800&q=90&auto=format&fit=crop'
const BMW_PHOTO = 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&q=90&auto=format&fit=crop'
const CAR_PHOTOS = [
  { src: 'https://images.unsplash.com/photo-1555215695-3004980ad54e?w=700&q=85&auto=format&fit=crop', make:'BMW',     model:'M3 Competition',    year:2022, city:'Munich',    flag:'🇩🇪', price:'€ 58.900', km:'24.500', regime:'IVA Deductible', regColor:'#10b981', nlc:'€ 62.340', dest:'🇪🇸', sdi:8.2, sdiC:'#f43f5e' },
  { src: 'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?w=700&q=85&auto=format&fit=crop', make:'Mercedes', model:'C 220d AMG',         year:2021, city:'Paris',    flag:'🇫🇷', price:'€ 28.400', km:'41.200', regime:'REBU',          regColor:'#f59e0b', nlc:'€ 31.200', dest:'🇳🇱', sdi:5.1, sdiC:'#06b6d4' },
  { src: 'https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?w=700&q=85&auto=format&fit=crop', make:'Audi',    model:'A4 2.0 TDI S-Line', year:2023, city:'Amsterdam',flag:'🇳🇱', price:'€ 34.500', km:'18.900', regime:'IVA Deductible', regColor:'#10b981', nlc:'€ 36.800', dest:'🇧🇪', sdi:6.7, sdiC:'#3b82f6' },
  { src: 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=700&q=85&auto=format&fit=crop', make:'Porsche',  model:'911 Carrera S',      year:2020, city:'Zurich',   flag:'🇨🇭', price:'€ 89.900', km:'31.600', regime:'IVA Deductible', regColor:'#10b981', nlc:'€ 94.100', dest:'🇩🇪', sdi:9.1, sdiC:'#f43f5e' },
]

const FEATURES = [
  { icon: TrendingUp, color: '#3b82f6', title: 'Fiscal intelligence',       desc: 'IVA / REBU auto-classification with full traceability to the prompt and model that produced each decision.' },
  { icon: Globe,      color: '#a855f7', title: 'Pan-European coverage',     desc: 'DE · ES · FR · NL · BE · CH — sitemap-first indexing from every dealer. Nothing abandoned mid-pagination.' },
  { icon: Zap,        color: '#06b6d4', title: 'Real-time pipeline',        desc: 'Redis Streams at-least-once delivery. Scraped → normalized → classified in under 2 seconds per listing.' },
  { icon: Shield,     color: '#10b981', title: 'Net Landed Cost',           desc: 'Total cost of importing any vehicle to any destination country — duties, transport, registration — computed automatically.' },
  { icon: BarChart3,  color: '#f59e0b', title: 'Price delta tracking',      desc: 'Instant alerts when a dealer drops price. Know before competitors. Historical timeline per listing.' },
  { icon: Activity,   color: '#f43f5e', title: 'Seller Desperation Index',  desc: 'SDI scores quantify seller urgency. MATRABA flags, EuroNCAP, EU RAPEX — every risk surfaced automatically.' },
]

const COUNTRIES = [
  { flag:'🇩🇪', name:'Germany',     n:'890K+' },
  { flag:'🇫🇷', name:'France',      n:'640K+' },
  { flag:'🇪🇸', name:'Spain',       n:'720K+' },
  { flag:'🇳🇱', name:'Netherlands', n:'380K+' },
  { flag:'🇧🇪', name:'Belgium',     n:'290K+' },
  { flag:'🇨🇭', name:'Switzerland', n:'180K+' },
]

/* ─── SDI bar ─────────────────────────────────────────────────────────────── */
function SDIBar({ v, c }: { v: number; c: string }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{ flex:1, height:3, background:'rgba(255,255,255,0.1)', borderRadius:2, overflow:'hidden' }}>
        <motion.div
          initial={{ width:0 }}
          whileInView={{ width:`${v*10}%` }}
          viewport={{ once:true }}
          transition={{ duration:0.9, ease:EASE, delay:0.1 }}
          style={{ height:'100%', background:`linear-gradient(90deg, ${c}80, ${c})`, borderRadius:2 }}
        />
      </div>
      <span style={{ fontSize:12, fontWeight:800, color:c, minWidth:24 }}>{v}</span>
    </div>
  )
}

/* ─── Vehicle card ────────────────────────────────────────────────────────── */
function VehicleCard({ d, i }: { d: typeof CAR_PHOTOS[0]; i: number }) {
  const [hov, setHov] = useState(false)
  return (
    <motion.div
      initial={{ opacity:0, y:32 }}
      whileInView={{ opacity:1, y:0 }}
      viewport={{ once:true, margin:'-40px' }}
      transition={{ delay:i*0.08, duration:0.6, ease:EASE }}
      onHoverStart={() => setHov(true)}
      onHoverEnd={() => setHov(false)}
      style={{
        borderRadius:20, overflow:'hidden', cursor:'pointer',
        background: hov ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)',
        border: `1px solid ${hov ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.09)'}`,
        backdropFilter:'blur(20px)', WebkitBackdropFilter:'blur(20px)',
        boxShadow: hov
          ? '0 24px 60px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.12) inset'
          : '0 8px 30px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.07) inset',
        transform: hov ? 'translateY(-6px)' : 'none',
        transition: 'all 0.35s cubic-bezier(0.22,1,0.36,1)',
      }}
    >
      {/* Photo */}
      <div style={{ position:'relative', height:190, overflow:'hidden' }}>
        <img src={d.src} alt={d.make} style={{ width:'100%', height:'100%', objectFit:'cover', transform: hov ? 'scale(1.07)' : 'scale(1)', transition:'transform 0.5s cubic-bezier(0.22,1,0.36,1)' }} />
        <div style={{ position:'absolute', inset:0, background:'linear-gradient(to top, rgba(5,5,20,0.95) 0%, rgba(5,5,20,0.3) 55%, transparent 100%)' }} />
        <div style={{ position:'absolute', top:12, left:12, display:'flex', alignItems:'center', gap:5, padding:'4px 10px', borderRadius:999, background:'rgba(5,5,20,0.65)', backdropFilter:'blur(14px)', border:'1px solid rgba(255,255,255,0.12)', fontSize:11, color:'rgba(255,255,255,0.7)', fontWeight:600 }}>
          {d.flag} {d.city}
        </div>
        {d.sdi >= 8 && (
          <div style={{ position:'absolute', top:12, right:12, padding:'4px 10px', borderRadius:999, background:`${d.sdiC}22`, backdropFilter:'blur(14px)', border:`1px solid ${d.sdiC}55`, fontSize:10, color:d.sdiC, fontWeight:800, letterSpacing:'0.07em' }}>HOT</div>
        )}
        <div style={{ position:'absolute', bottom:14, left:14 }}>
          <div style={{ fontSize:17, fontWeight:900, color:'#f1f5f9', letterSpacing:'-0.02em' }}>{d.make} <span style={{ fontWeight:500, color:'#94a3b8' }}>{d.model}</span></div>
          <div style={{ fontSize:11, color:'#64748b', marginTop:2 }}>{d.year}</div>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding:'16px 18px 18px' }}>
        <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', marginBottom:12 }}>
          <span style={{ fontSize:22, fontWeight:900, color:'#f1f5f9', letterSpacing:'-0.03em' }}>{d.price}</span>
          <span style={{ fontSize:12, color:'#475569' }}>{d.km} km</span>
        </div>
        <div style={{ display:'inline-flex', alignItems:'center', gap:5, padding:'3px 10px', borderRadius:999, background:`${d.regColor}15`, border:`1px solid ${d.regColor}35`, fontSize:10, fontWeight:700, color:d.regColor, letterSpacing:'0.05em', textTransform:'uppercase', marginBottom:14 }}>
          <span style={{ width:5, height:5, borderRadius:'50%', background:d.regColor, display:'block' }} />
          {d.regime}
        </div>
        <div style={{ height:1, background:'rgba(255,255,255,0.06)', marginBottom:12 }} />
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
          <span style={{ fontSize:10, color:'#475569', textTransform:'uppercase', letterSpacing:'0.07em', fontWeight:600 }}>NLC → {d.dest}</span>
          <span style={{ fontSize:13, fontWeight:800, color:'#f1f5f9' }}>{d.nlc}</span>
        </div>
        <SDIBar v={d.sdi} c={d.sdiC} />
      </div>
    </motion.div>
  )
}

/* ─── Landing ─────────────────────────────────────────────────────────────── */
export default function Landing() {
  const nav = useNavigate()
  const { scrollY } = useScroll()
  const navBlur = useTransform(scrollY, [0,60], [0,1])

  return (
    <div style={{ background:'#020209', minHeight:'100dvh', fontFamily:FONT, overflowX:'hidden', color:'#f1f5f9' }}>

      {/* ── NAVBAR ────────────────────────────────────────────────────────── */}
      <motion.nav style={{
        position:'fixed', top:0, left:0, right:0, zIndex:100,
        height:64, display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'0 clamp(20px,4vw,56px)',
        backgroundColor: useTransform(scrollY,[0,60],['rgba(2,2,9,0)','rgba(2,2,9,0.88)']),
        backdropFilter:'blur(24px)', WebkitBackdropFilter:'blur(24px)',
        borderBottom:'1px solid',
        borderColor: useTransform(scrollY,[0,60],['rgba(255,255,255,0)','rgba(255,255,255,0.07)']),
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ width:34, height:34, borderRadius:11, background:'linear-gradient(135deg,rgba(59,130,246,0.18),rgba(99,102,241,0.18))', border:'1px solid rgba(59,130,246,0.35)', display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 0 24px rgba(59,130,246,0.2)' }}>
            <div style={{ width:12, height:12, borderRadius:4, background:'linear-gradient(135deg,#3b82f6,#6366f1)', boxShadow:'0 0 14px rgba(59,130,246,0.7)' }} />
          </div>
          <span style={{ fontSize:15, fontWeight:900, letterSpacing:'0.2em', background:'linear-gradient(120deg,#e2e8f0,#94a3b8)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>CARDEX</span>
        </div>

        <div style={{ display:'flex', gap:2 }}>
          {['Platform','Coverage','Pricing'].map(l => (
            <button key={l} style={{ padding:'7px 16px', borderRadius:9, fontSize:13, fontWeight:500, color:'#64748b', background:'transparent', border:'none', cursor:'pointer', fontFamily:FONT, transition:'color 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.color='#f1f5f9')}
              onMouseLeave={e => (e.currentTarget.style.color='#64748b')}
            >{l}</button>
          ))}
        </div>

        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <button onClick={() => nav('/login')} style={{ padding:'8px 18px', borderRadius:10, fontSize:13, fontWeight:600, color:'#64748b', background:'transparent', border:'1px solid rgba(255,255,255,0.08)', cursor:'pointer', fontFamily:FONT, transition:'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.color='#f1f5f9'; e.currentTarget.style.borderColor='rgba(255,255,255,0.16)' }}
            onMouseLeave={e => { e.currentTarget.style.color='#64748b'; e.currentTarget.style.borderColor='rgba(255,255,255,0.08)' }}>
            Sign in
          </button>
          <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.03 }} whileTap={{ scale:0.97 }} transition={{ type:'spring', stiffness:400, damping:20 }}
            style={{ display:'flex', alignItems:'center', gap:7, padding:'8px 20px', borderRadius:10, fontSize:13, fontWeight:700, color:'#fff', background:'linear-gradient(135deg,#3b82f6,#6366f1)', border:'none', cursor:'pointer', fontFamily:FONT, boxShadow:'0 0 24px rgba(59,130,246,0.35)' }}>
            Get access <ArrowUpRight style={{ width:13, height:13 }} strokeWidth={2.5} />
          </motion.button>
        </div>
      </motion.nav>

      {/* ── HERO ──────────────────────────────────────────────────────────── */}
      <section style={{ position:'relative', minHeight:'100dvh', display:'flex', alignItems:'center', overflow:'hidden' }}>

        {/* FULL BLEED background image */}
        <div style={{ position:'absolute', inset:0, zIndex:0 }}>
          <img src={HERO_BG} alt="" style={{ width:'100%', height:'100%', objectFit:'cover', objectPosition:'center 40%' }} />
          {/* Left dark gradient — keeps text readable */}
          <div style={{ position:'absolute', inset:0, background:'linear-gradient(100deg, rgba(2,2,9,0.97) 0%, rgba(2,2,9,0.88) 40%, rgba(2,2,9,0.55) 65%, rgba(2,2,9,0.15) 100%)' }} />
          {/* Top/bottom fades */}
          <div style={{ position:'absolute', inset:0, background:'linear-gradient(to bottom, rgba(2,2,9,0.5) 0%, transparent 20%, transparent 80%, rgba(2,2,9,0.9) 100%)' }} />
        </div>

        {/* Colored mesh behind glass elements */}
        <div aria-hidden style={{ position:'absolute', inset:0, zIndex:1, pointerEvents:'none' }}>
          <div style={{ position:'absolute', top:'10%', right:'18%', width:400, height:400, borderRadius:'50%', background:'radial-gradient(circle, rgba(99,102,241,0.5) 0%, transparent 70%)', filter:'blur(60px)' }} />
          <div style={{ position:'absolute', bottom:'15%', right:'8%', width:300, height:300, borderRadius:'50%', background:'radial-gradient(circle, rgba(59,130,246,0.45) 0%, transparent 70%)', filter:'blur(50px)' }} />
          <div style={{ position:'absolute', top:'40%', right:'38%', width:200, height:200, borderRadius:'50%', background:'radial-gradient(circle, rgba(168,85,247,0.35) 0%, transparent 70%)', filter:'blur(40px)' }} />
        </div>

        {/* Content grid */}
        <div style={{ position:'relative', zIndex:2, display:'grid', gridTemplateColumns:'1fr 1fr', gap:48, alignItems:'center', maxWidth:1200, margin:'0 auto', width:'100%', padding:'100px clamp(20px,4vw,56px) 80px' }}>

          {/* LEFT — copy */}
          <div>
            <motion.div initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.5, ease:EASE }}>
              <div style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 14px', borderRadius:999, background:'rgba(59,130,246,0.12)', border:'1px solid rgba(59,130,246,0.3)', marginBottom:24, backdropFilter:'blur(10px)' }}>
                <div style={{ width:6, height:6, borderRadius:'50%', background:'#3b82f6', animation:'cxPulse 2s infinite' }} />
                <span style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#93c5fd' }}>B2B Vehicle Intelligence</span>
              </div>
            </motion.div>

            <motion.h1
              initial={{ opacity:0, y:28, filter:'blur(12px)' }}
              animate={{ opacity:1, y:0, filter:'blur(0px)' }}
              transition={{ delay:0.08, duration:0.75, ease:EASE }}
              style={{ fontSize:'clamp(40px,5vw,72px)', fontWeight:900, lineHeight:1.04, letterSpacing:'-0.04em', marginBottom:22, color:'#f8fafc' }}
            >
              The fiscal edge{' '}
              <br />
              <span style={{ background:'linear-gradient(120deg, #60a5fa 0%, #a78bfa 50%, #67e8f9 100%)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>
                for EU arbitrage
              </span>
            </motion.h1>

            <motion.p
              initial={{ opacity:0, y:16 }}
              animate={{ opacity:1, y:0 }}
              transition={{ delay:0.18, duration:0.6, ease:EASE }}
              style={{ fontSize:17, color:'#94a3b8', lineHeight:1.72, maxWidth:460, marginBottom:36 }}
            >
              3.5M listings across 6 EU countries. IVA/REBU auto-classification with full traceability.
              Net Landed Cost and Seller Desperation Index on every vehicle — before you call.
            </motion.p>

            <motion.div initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.26, duration:0.5, ease:EASE }} style={{ display:'flex', gap:12, marginBottom:44, flexWrap:'wrap' }}>
              <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.04, boxShadow:'0 0 60px rgba(59,130,246,0.5)' }} whileTap={{ scale:0.97 }} transition={{ type:'spring', stiffness:380, damping:18 }}
                style={{ display:'flex', alignItems:'center', gap:10, padding:'14px 30px', borderRadius:14, fontSize:15, fontWeight:800, color:'#fff', background:'linear-gradient(135deg,#3b82f6,#6366f1)', border:'none', cursor:'pointer', fontFamily:FONT, boxShadow:'0 0 35px rgba(59,130,246,0.3)' }}>
                Open platform
                <div style={{ width:26, height:26, borderRadius:'50%', background:'rgba(255,255,255,0.2)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <ArrowUpRight style={{ width:13, height:13 }} strokeWidth={2.5} />
                </div>
              </motion.button>
              <button onClick={() => document.getElementById('vehicles')?.scrollIntoView({ behavior:'smooth' })}
                style={{ display:'flex', alignItems:'center', gap:8, padding:'14px 24px', borderRadius:14, fontSize:15, fontWeight:600, color:'#94a3b8', background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.12)', cursor:'pointer', fontFamily:FONT, backdropFilter:'blur(12px)', transition:'all 0.2s' }}
                onMouseEnter={e => { e.currentTarget.style.color='#f1f5f9'; e.currentTarget.style.background='rgba(255,255,255,0.1)' }}
                onMouseLeave={e => { e.currentTarget.style.color='#94a3b8'; e.currentTarget.style.background='rgba(255,255,255,0.06)' }}>
                See live data <ChevronRight style={{ width:14, height:14 }} />
              </button>
            </motion.div>

            <motion.div initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ delay:0.5 }} style={{ display:'flex', gap:22 }}>
              {[{ icon:Check, t:'No setup fee' }, { icon:Shield, t:'GDPR compliant' }, { icon:Sparkles, t:'AI-classified' }].map(({ icon:Icon, t }) => (
                <div key={t} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, color:'#475569' }}>
                  <Icon style={{ width:12, height:12, color:'#06b6d4' }} strokeWidth={2.5} />
                  {t}
                </div>
              ))}
            </motion.div>
          </div>

          {/* RIGHT — glass intelligence panel floating over car photo */}
          <motion.div
            initial={{ opacity:0, x:40, rotateY:6 }}
            animate={{ opacity:1, x:0, rotateY:0 }}
            transition={{ delay:0.35, duration:0.9, ease:EASE }}
            style={{ position:'relative', display:'flex', justifyContent:'center' }}
          >
            {/* Main glass card */}
            <div style={{
              width:'100%', maxWidth:460, borderRadius:24, overflow:'hidden',
              background:'rgba(255,255,255,0.07)',
              backdropFilter:'blur(40px) saturate(180%)',
              WebkitBackdropFilter:'blur(40px) saturate(180%)',
              border:'1px solid rgba(255,255,255,0.15)',
              boxShadow:'0 32px 80px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.15) inset',
            }}>
              {/* Header bar */}
              <div style={{ padding:'13px 18px', borderBottom:'1px solid rgba(255,255,255,0.08)', display:'flex', alignItems:'center', justifyContent:'space-between', background:'rgba(255,255,255,0.03)' }}>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <div style={{ width:8, height:8, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 12px #10b981' }} />
                  <span style={{ fontSize:10, fontWeight:700, color:'rgba(255,255,255,0.6)', letterSpacing:'0.1em', textTransform:'uppercase' }}>Live Intelligence</span>
                </div>
                <span style={{ fontSize:10, color:'rgba(255,255,255,0.3)', fontWeight:500 }}>2s ago</span>
              </div>

              {/* Car photo inside card */}
              <div style={{ position:'relative', height:195, overflow:'hidden' }}>
                <img src={BMW_PHOTO} alt="BMW M3" style={{ width:'100%', height:'100%', objectFit:'cover' }} />
                <div style={{ position:'absolute', inset:0, background:'linear-gradient(to top, rgba(10,10,30,0.92) 0%, transparent 55%)' }} />
                <div style={{ position:'absolute', bottom:14, left:16 }}>
                  <div style={{ fontSize:20, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.02em' }}>BMW M3 Competition</div>
                  <div style={{ fontSize:12, color:'rgba(255,255,255,0.5)', display:'flex', alignItems:'center', gap:4, marginTop:2 }}>
                    <MapPin style={{ width:10, height:10 }} /> 🇩🇪 Munich · 2022
                  </div>
                </div>
              </div>

              {/* Data grid */}
              <div style={{ padding:'16px 18px' }}>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:14 }}>
                  {[
                    { l:'Asking price',   v:'€ 58.900', c:'#f8fafc' },
                    { l:'Mileage',        v:'24.500 km', c:'#94a3b8' },
                    { l:'Fiscal regime',  v:'IVA Ded.', c:'#10b981' },
                    { l:'Classification', v:'< 2s',      c:'#3b82f6' },
                  ].map(item => (
                    <div key={item.l} style={{ background:'rgba(255,255,255,0.05)', borderRadius:11, padding:'10px 13px', border:'1px solid rgba(255,255,255,0.08)' }}>
                      <div style={{ fontSize:9, color:'rgba(255,255,255,0.35)', textTransform:'uppercase', letterSpacing:'0.09em', fontWeight:600, marginBottom:4 }}>{item.l}</div>
                      <div style={{ fontSize:15, fontWeight:800, color:item.c }}>{item.v}</div>
                    </div>
                  ))}
                </div>

                {/* NLC row */}
                <div style={{ background:'rgba(99,102,241,0.15)', border:'1px solid rgba(99,102,241,0.3)', borderRadius:13, padding:'12px 16px', display:'flex', justifyContent:'space-between', alignItems:'center', backdropFilter:'blur(10px)' }}>
                  <div>
                    <div style={{ fontSize:9, color:'rgba(255,255,255,0.4)', textTransform:'uppercase', letterSpacing:'0.09em', fontWeight:600, marginBottom:3 }}>Net Landed Cost → 🇪🇸 Spain</div>
                    <div style={{ fontSize:22, fontWeight:900, color:'#f8fafc', letterSpacing:'-0.03em' }}>€ 62.340</div>
                  </div>
                  <div style={{ textAlign:'right' }}>
                    <div style={{ fontSize:9, color:'rgba(255,255,255,0.4)', textTransform:'uppercase', letterSpacing:'0.09em', fontWeight:600, marginBottom:3 }}>SDI Score</div>
                    <div style={{ fontSize:22, fontWeight:900, color:'#f43f5e', letterSpacing:'-0.03em' }}>8.2</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Float 1 — bottom left */}
            <motion.div
              initial={{ opacity:0, x:-20, y:10 }} animate={{ opacity:1, x:0, y:0 }} transition={{ delay:1.2, duration:0.7, ease:EASE }}
              style={{ position:'absolute', bottom:-18, left:-28, background:'rgba(16,185,129,0.1)', backdropFilter:'blur(24px)', WebkitBackdropFilter:'blur(24px)', border:'1px solid rgba(16,185,129,0.3)', borderRadius:14, padding:'10px 14px', display:'flex', alignItems:'center', gap:10, boxShadow:'0 8px 30px rgba(0,0,0,0.4), 0 0 0 1px rgba(16,185,129,0.1)' }}
            >
              <div style={{ width:30, height:30, borderRadius:9, background:'rgba(16,185,129,0.18)', border:'1px solid rgba(16,185,129,0.35)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                <Car style={{ width:14, height:14, color:'#10b981' }} />
              </div>
              <div>
                <div style={{ fontSize:12, fontWeight:700, color:'#f1f5f9' }}>+847 new listings</div>
                <div style={{ fontSize:10, color:'#475569' }}>indexed this hour</div>
              </div>
            </motion.div>

            {/* Float 2 — top right */}
            <motion.div
              initial={{ opacity:0, x:20 }} animate={{ opacity:1, x:0 }} transition={{ delay:1.6, duration:0.7, ease:EASE }}
              style={{ position:'absolute', top:-18, right:-20, background:'rgba(59,130,246,0.1)', backdropFilter:'blur(24px)', WebkitBackdropFilter:'blur(24px)', border:'1px solid rgba(59,130,246,0.28)', borderRadius:14, padding:'10px 14px', display:'flex', alignItems:'center', gap:8, boxShadow:'0 8px 24px rgba(0,0,0,0.35)' }}
            >
              <Check style={{ width:14, height:14, color:'#3b82f6' }} strokeWidth={2.5} />
              <div>
                <div style={{ fontSize:12, fontWeight:700, color:'#f1f5f9' }}>99.2% accuracy</div>
                <div style={{ fontSize:10, color:'#475569' }}>REBU classification</div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── STATS ─────────────────────────────────────────────────────────── */}
      <section style={{ padding:'0 clamp(20px,4vw,56px) 100px' }}>
        <div style={{ maxWidth:1100, margin:'0 auto', display:'grid', gridTemplateColumns:'repeat(4,1fr)', background:'rgba(255,255,255,0.04)', backdropFilter:'blur(20px)', border:'1px solid rgba(255,255,255,0.08)', borderRadius:22, overflow:'hidden', boxShadow:'0 8px 40px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.07) inset' }}>
          {[
            { v:'3.5M+', l:'Vehicles indexed', c:'#3b82f6' },
            { v:'6',     l:'EU countries',     c:'#a855f7' },
            { v:'2.5K+', l:'Dealer sources',   c:'#06b6d4' },
            { v:'< 2s',  l:'Classification',   c:'#10b981' },
          ].map((s,i) => (
            <motion.div key={s.l} initial={{ opacity:0, y:16 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ delay:i*0.07, duration:0.5, ease:EASE }}
              style={{ padding:'32px 28px', textAlign:'center', borderRight: i<3 ? '1px solid rgba(255,255,255,0.06)' : 'none', position:'relative', overflow:'hidden' }}>
              <div aria-hidden style={{ position:'absolute', top:-20, left:'50%', transform:'translateX(-50%)', width:120, height:80, background:s.c, opacity:0.07, filter:'blur(30px)', borderRadius:'50%' }} />
              <div style={{ fontSize:38, fontWeight:900, letterSpacing:'-0.04em', color:s.c, marginBottom:7, textShadow:`0 0 30px ${s.c}50` }}>{s.v}</div>
              <div style={{ fontSize:11, color:'#475569', fontWeight:600, letterSpacing:'0.08em', textTransform:'uppercase' }}>{s.l}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── VEHICLE CARDS ─────────────────────────────────────────────────── */}
      <section id="vehicles" style={{ padding:'0 clamp(20px,4vw,56px) 120px' }}>
        <div style={{ maxWidth:1200, margin:'0 auto' }}>
          <motion.div initial={{ opacity:0, y:16 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ duration:0.5, ease:EASE }} style={{ marginBottom:52 }}>
            <div style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 14px', borderRadius:999, background:'rgba(168,85,247,0.1)', border:'1px solid rgba(168,85,247,0.28)', marginBottom:18, backdropFilter:'blur(10px)' }}>
              <div style={{ width:5, height:5, borderRadius:'50%', background:'#a855f7', animation:'cxPulse 2s infinite' }} />
              <span style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#c084fc' }}>Live intelligence</span>
            </div>
            <h2 style={{ fontSize:'clamp(30px,3.5vw,50px)', fontWeight:900, letterSpacing:'-0.04em', color:'#f8fafc', marginBottom:14 }}>Real listings. Real intelligence.</h2>
            <p style={{ fontSize:16, color:'#64748b', maxWidth:520, lineHeight:1.65 }}>Every vehicle auto-classified with fiscal regime, NLC and SDI — in under 2 seconds.</p>
          </motion.div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16 }}>
            {CAR_PHOTOS.map((d,i) => <VehicleCard key={i} d={d} i={i} />)}
          </div>
          <motion.div initial={{ opacity:0, y:12 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ delay:0.3, duration:0.5, ease:EASE }} style={{ textAlign:'center', marginTop:40 }}>
            <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.02 }} whileTap={{ scale:0.97 }} style={{ display:'inline-flex', alignItems:'center', gap:8, padding:'12px 28px', borderRadius:12, fontSize:14, fontWeight:700, color:'#f1f5f9', background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.12)', cursor:'pointer', fontFamily:FONT, backdropFilter:'blur(16px)' }}>
              Browse all 3.5M listings <ArrowUpRight style={{ width:14, height:14 }} strokeWidth={2.5} />
            </motion.button>
          </motion.div>
        </div>
      </section>

      {/* ── FEATURES ──────────────────────────────────────────────────────── */}
      <section style={{ padding:'0 clamp(20px,4vw,56px) 120px' }}>
        <div style={{ maxWidth:1200, margin:'0 auto' }}>
          <motion.div initial={{ opacity:0, y:16 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ duration:0.5, ease:EASE }} style={{ textAlign:'center', marginBottom:56 }}>
            <div style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 14px', borderRadius:999, background:'rgba(6,182,212,0.1)', border:'1px solid rgba(6,182,212,0.28)', marginBottom:18, backdropFilter:'blur(10px)' }}>
              <div style={{ width:5, height:5, borderRadius:'50%', background:'#06b6d4', animation:'cxPulse 2s infinite' }} />
              <span style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#67e8f9' }}>Platform capabilities</span>
            </div>
            <h2 style={{ fontSize:'clamp(30px,3.5vw,50px)', fontWeight:900, letterSpacing:'-0.04em', color:'#f8fafc', marginBottom:14 }}>Built for professional traders</h2>
            <p style={{ fontSize:16, color:'#64748b', maxWidth:480, margin:'0 auto' }}>Every feature designed around real friction in cross-border vehicle arbitrage.</p>
          </motion.div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:16 }}>
            {FEATURES.map((f,i) => (
              <motion.div key={f.title}
                initial={{ opacity:0, y:22 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ delay:i*0.07, duration:0.55, ease:EASE }}
                style={{
                  padding:'28px', borderRadius:20, position:'relative', overflow:'hidden', cursor:'default',
                  background:'rgba(255,255,255,0.04)',
                  backdropFilter:'blur(20px)', WebkitBackdropFilter:'blur(20px)',
                  border:'1px solid rgba(255,255,255,0.08)',
                  boxShadow:'0 4px 20px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.07) inset',
                  transition:'all 0.3s cubic-bezier(0.22,1,0.36,1)',
                }}
                whileHover={{ y:-5, transition:{ duration:0.25 } }}
                onMouseEnter={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = `${f.color}40`
                  el.style.boxShadow = `0 16px 50px rgba(0,0,0,0.45), 0 0 0 1px ${f.color}20, 0 1px 0 rgba(255,255,255,0.09) inset`
                  el.style.background = `rgba(255,255,255,0.07)`
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget as HTMLDivElement
                  el.style.borderColor = 'rgba(255,255,255,0.08)'
                  el.style.boxShadow = '0 4px 20px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.07) inset'
                  el.style.background = 'rgba(255,255,255,0.04)'
                }}
              >
                <div aria-hidden style={{ position:'absolute', top:-30, right:-20, width:130, height:130, borderRadius:'50%', background:f.color, opacity:0.1, filter:'blur(35px)', pointerEvents:'none' }} />
                <div style={{ width:46, height:46, borderRadius:14, background:`${f.color}15`, border:`1px solid ${f.color}30`, display:'flex', alignItems:'center', justifyContent:'center', marginBottom:18 }}>
                  <f.icon style={{ width:21, height:21, color:f.color }} strokeWidth={1.8} />
                </div>
                <h3 style={{ fontSize:16, fontWeight:800, color:'#f1f5f9', marginBottom:10, letterSpacing:'-0.01em' }}>{f.title}</h3>
                <p style={{ fontSize:13, color:'#64748b', lineHeight:1.7 }}>{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── COUNTRIES ─────────────────────────────────────────────────────── */}
      <section style={{ padding:'0 clamp(20px,4vw,56px) 120px' }}>
        <div style={{ maxWidth:1000, margin:'0 auto' }}>
          <motion.div initial={{ opacity:0, y:16 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ duration:0.5, ease:EASE }} style={{ textAlign:'center', marginBottom:52 }}>
            <div style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 14px', borderRadius:999, background:'rgba(16,185,129,0.1)', border:'1px solid rgba(16,185,129,0.28)', marginBottom:18, backdropFilter:'blur(10px)' }}>
              <div style={{ width:5, height:5, borderRadius:'50%', background:'#10b981', animation:'cxPulse 2s infinite' }} />
              <span style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#6ee7b7' }}>Coverage</span>
            </div>
            <h2 style={{ fontSize:'clamp(30px,3.5vw,50px)', fontWeight:900, letterSpacing:'-0.04em', color:'#f8fafc', marginBottom:14 }}>6 countries. Every dealer.</h2>
            <p style={{ fontSize:16, color:'#64748b', maxWidth:480, margin:'0 auto' }}>From AutoScout24 to the unknown dealer in rural France with a 3-car website.</p>
          </motion.div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(6,1fr)', gap:12 }}>
            {COUNTRIES.map((c,i) => (
              <motion.div key={c.name}
                initial={{ opacity:0, scale:0.88 }} whileInView={{ opacity:1, scale:1 }} viewport={{ once:true }} transition={{ delay:i*0.06, duration:0.45, ease:EASE }}
                whileHover={{ y:-5, scale:1.05, transition:{ duration:0.2 } }}
                style={{
                  padding:'22px 12px', borderRadius:18, textAlign:'center', cursor:'default',
                  background:'rgba(255,255,255,0.04)',
                  backdropFilter:'blur(20px)', WebkitBackdropFilter:'blur(20px)',
                  border:'1px solid rgba(255,255,255,0.08)',
                  boxShadow:'0 4px 16px rgba(0,0,0,0.25), 0 1px 0 rgba(255,255,255,0.07) inset',
                  transition:'all 0.25s cubic-bezier(0.22,1,0.36,1)',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderColor='rgba(255,255,255,0.16)'; (e.currentTarget as HTMLDivElement).style.background='rgba(255,255,255,0.07)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor='rgba(255,255,255,0.08)'; (e.currentTarget as HTMLDivElement).style.background='rgba(255,255,255,0.04)' }}
              >
                <div style={{ fontSize:34, marginBottom:9 }}>{c.flag}</div>
                <div style={{ fontSize:12, fontWeight:700, color:'#e2e8f0', marginBottom:4 }}>{c.name}</div>
                <div style={{ fontSize:10, color:'#334155', fontWeight:600 }}>{c.n}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────────────────── */}
      <section style={{ padding:'0 clamp(20px,4vw,56px) 140px' }}>
        <motion.div initial={{ opacity:0, y:24 }} whileInView={{ opacity:1, y:0 }} viewport={{ once:true }} transition={{ duration:0.6, ease:EASE }} style={{ maxWidth:760, margin:'0 auto', position:'relative' }}>
          {/* Gradient border glow */}
          <div aria-hidden style={{ position:'absolute', inset:-1, borderRadius:29, background:'linear-gradient(135deg,rgba(59,130,246,0.6),rgba(168,85,247,0.5),rgba(6,182,212,0.4))', filter:'blur(1px)', zIndex:0 }} />
          <div style={{ position:'relative', zIndex:1, background:'rgba(2,2,9,0.9)', backdropFilter:'blur(40px)', borderRadius:28, padding:'clamp(40px,5vw,64px)', textAlign:'center', overflow:'hidden' }}>
            {/* Mesh inside */}
            <div aria-hidden style={{ position:'absolute', top:'20%', left:'15%', width:200, height:200, borderRadius:'50%', background:'radial-gradient(circle,rgba(59,130,246,0.25) 0%, transparent 70%)', filter:'blur(40px)', pointerEvents:'none' }} />
            <div aria-hidden style={{ position:'absolute', bottom:'10%', right:'15%', width:180, height:180, borderRadius:'50%', background:'radial-gradient(circle,rgba(168,85,247,0.2) 0%, transparent 70%)', filter:'blur(35px)', pointerEvents:'none' }} />
            <div style={{ position:'relative', zIndex:1 }}>
              <div style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 14px', borderRadius:999, background:'rgba(6,182,212,0.1)', border:'1px solid rgba(6,182,212,0.28)', marginBottom:20, backdropFilter:'blur(10px)' }}>
                <div style={{ width:5, height:5, borderRadius:'50%', background:'#06b6d4', animation:'cxPulse 2s infinite' }} />
                <span style={{ fontSize:10, fontWeight:700, letterSpacing:'0.12em', textTransform:'uppercase', color:'#67e8f9' }}>Get started</span>
              </div>
              <h2 style={{ fontSize:'clamp(28px,3.5vw,46px)', fontWeight:900, letterSpacing:'-0.04em', color:'#f8fafc', marginBottom:16 }}>Ready to trade smarter?</h2>
              <p style={{ fontSize:16, color:'#64748b', marginBottom:36, lineHeight:1.65, maxWidth:480, margin:'0 auto 36px' }}>
                Access 3.5M classified vehicle listings across 6 EU markets. No guesswork on fiscal regimes.
              </p>
              <div style={{ display:'flex', gap:12, justifyContent:'center', flexWrap:'wrap' }}>
                <motion.button onClick={() => nav('/login')} whileHover={{ scale:1.04, boxShadow:'0 0 70px rgba(59,130,246,0.5)' }} whileTap={{ scale:0.97 }} transition={{ type:'spring', stiffness:380, damping:18 }}
                  style={{ display:'inline-flex', alignItems:'center', gap:10, padding:'15px 36px', borderRadius:14, fontSize:16, fontWeight:800, color:'#fff', background:'linear-gradient(135deg,#3b82f6,#6366f1)', border:'none', cursor:'pointer', fontFamily:FONT, boxShadow:'0 0 35px rgba(59,130,246,0.35)' }}>
                  Enter workspace
                  <div style={{ width:28, height:28, borderRadius:'50%', background:'rgba(255,255,255,0.2)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                    <ArrowUpRight style={{ width:14, height:14 }} strokeWidth={2.5} />
                  </div>
                </motion.button>
                <button onClick={() => nav('/check')}
                  style={{ display:'inline-flex', alignItems:'center', gap:8, padding:'15px 28px', borderRadius:14, fontSize:16, fontWeight:700, color:'#94a3b8', background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.1)', cursor:'pointer', fontFamily:FONT, backdropFilter:'blur(16px)', transition:'all 0.2s' }}
                  onMouseEnter={e => { e.currentTarget.style.color='#f1f5f9'; e.currentTarget.style.borderColor='rgba(255,255,255,0.18)' }}
                  onMouseLeave={e => { e.currentTarget.style.color='#94a3b8'; e.currentTarget.style.borderColor='rgba(255,255,255,0.1)' }}>
                  Try VIN Check <ChevronRight style={{ width:14, height:14 }} />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── FOOTER ────────────────────────────────────────────────────────── */}
      <footer style={{ borderTop:'1px solid rgba(255,255,255,0.06)', padding:'28px clamp(20px,4vw,56px)', display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:16 }}>
        <div style={{ display:'flex', alignItems:'center', gap:9 }}>
          <div style={{ width:26, height:26, borderRadius:8, background:'rgba(59,130,246,0.12)', border:'1px solid rgba(59,130,246,0.25)', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <div style={{ width:9, height:9, borderRadius:3, background:'linear-gradient(135deg,#3b82f6,#6366f1)' }} />
          </div>
          <span style={{ fontSize:13, fontWeight:900, letterSpacing:'0.2em', color:'#475569' }}>CARDEX</span>
        </div>
        <div style={{ display:'flex', gap:24 }}>
          {['Privacy','Terms','Contact'].map(l => (
            <button key={l} style={{ fontSize:12, color:'#334155', background:'none', border:'none', cursor:'pointer', fontFamily:FONT, transition:'color 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.color='#94a3b8')} onMouseLeave={e => (e.currentTarget.style.color='#334155')}>
              {l}
            </button>
          ))}
        </div>
        <span style={{ fontSize:12, color:'#1e293b' }}>© 2026 CARDEX · B2B Vehicle Intelligence</span>
      </footer>

      <style>{`
        @keyframes cxPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.8)} }
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
      `}</style>
    </div>
  )
}
