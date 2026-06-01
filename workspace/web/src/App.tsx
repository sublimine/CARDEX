import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Shell from './layout/Shell'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './auth/LoginPage'
import Landing from './pages/Landing'
import CheckPage from './pages/Check'
import Dashboard from './pages/Dashboard'
import Vehicles from './pages/Vehicles'
import Kanban from './pages/Kanban'
import Contacts from './pages/Contacts'
import Deals from './pages/Deals'
import Inbox from './pages/Inbox'
import Calendar from './pages/Calendar'
import Finance from './pages/Finance'
import Settings from './pages/Settings'
import Market from './pages/Market'
import Terminal from './pages/Terminal'
import { useAuthContext } from './auth/AuthContext'

function RootRedirect() {
  const { isAuthenticated, isLoading } = useAuthContext()
  if (isLoading) return null
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <Landing />
}

/**
 * Global colored mesh — fixed behind every page.
 * Two orbs come from .cx-mesh ::before/::after (violet + blue).
 * Two extra orbs (teal + fuchsia) are mounted as inline divs since CSS only
 * grants two pseudo-elements per node.
 */
function GlobalMesh() {
  return (
    <div className="cx-mesh" aria-hidden>
      {/* Orb 3 — teal, bottom-center */}
      <div
        className="cx-orb"
        style={{
          position: 'absolute',
          bottom: '6%',
          left: '32%',
          width: 560,
          height: 560,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(8,145,178,0.48) 0%, rgba(8,145,178,0) 70%)',
          filter: 'blur(80px)',
          animation: 'cxFloat3 12s ease-in-out infinite',
        }}
      />
      {/* Orb 4 — fuchsia, mid-left */}
      <div
        className="cx-orb"
        style={{
          position: 'absolute',
          top: '55%',
          left: '-4%',
          width: 480,
          height: 480,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(192,38,211,0.42) 0%, rgba(192,38,211,0) 70%)',
          filter: 'blur(70px)',
          animation: 'cxFloat4 18s ease-in-out infinite',
        }}
      />
      {/* Grain overlay — adds texture to break the gradient banding */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          opacity: 0.18,
          mixBlendMode: 'overlay',
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.35 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
        }}
      />
    </div>
  )
}

export default function App() {
  return (
    <>
      <GlobalMesh />
      <Routes>
        {/* Public routes */}
        <Route path="/"         element={<RootRedirect />} />
        <Route path="/landing"  element={<Landing />} />
        <Route path="/login"    element={<LoginPage />} />
        <Route path="/check"    element={<CheckPage />} />
        <Route path="/check/:vin" element={<CheckPage />} />

        {/* Protected app shell */}
        <Route
          element={
            <ProtectedRoute>
              <Shell />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard"  element={<Dashboard />} />
          <Route path="vehicles"   element={<Vehicles />} />
          <Route path="kanban"     element={<Kanban />} />
          <Route path="contacts"   element={<Contacts />} />
          <Route path="deals"      element={<Deals />} />
          <Route path="inbox"      element={<Inbox />} />
          <Route path="calendar"   element={<Calendar />} />
          <Route path="finance"    element={<Finance />} />
          <Route path="market"    element={<Market />} />
          <Route path="terminal"  element={<Terminal />} />
          <Route path="settings"   element={<Settings />} />
          <Route path="*"          element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </>
  )
}
