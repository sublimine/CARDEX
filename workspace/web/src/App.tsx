import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Shell from './layout/Shell'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './auth/LoginPage'
import Dashboard from './pages/Dashboard'
import Vehicles from './pages/Vehicles'
import Kanban from './pages/Kanban'
import Contacts from './pages/Contacts'
import Deals from './pages/Deals'
import Inbox from './pages/Inbox'
import Calendar from './pages/Calendar'
import Finance from './pages/Finance'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <ProtectedRoute>
            <Shell />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="vehicles"  element={<Vehicles />} />
        <Route path="kanban"    element={<Kanban />} />
        <Route path="contacts"  element={<Contacts />} />
        <Route path="deals"     element={<Deals />} />
        <Route path="inbox"     element={<Inbox />} />
        <Route path="calendar"  element={<Calendar />} />
        <Route path="finance"   element={<Finance />} />
        <Route path="settings"  element={<Settings />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
