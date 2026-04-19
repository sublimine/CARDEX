import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import './index.css'

// Apply saved theme before first paint.
// CSS tokens: :root = dark (default), .light = light overrides.
// Tailwind darkMode:'class' requires the .dark class on <html>.
const saved = localStorage.getItem('theme')
if (saved === 'light') {
  document.documentElement.classList.add('light')
} else {
  document.documentElement.classList.add('dark')
}

// Register service worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(console.error)
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
