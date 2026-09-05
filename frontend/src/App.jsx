import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Store, Calendar, Database, RefreshCw,
  KeyRound, LogOut, ChevronDown, User, ShieldCheck,
  Zap, Volume2, VolumeX,
} from 'lucide-react'
import VoiceRecorder from './components/VoiceRecorder'
import DraftTransaction from './components/DraftTransaction'
import KPIGrid from './components/KPIGrid'
import RecoveryFeed from './components/RecoveryFeed'
import AuthModal from './components/AuthModal'
import ChangePasswordModal from './components/ChangePasswordModal'

/**
 * Main application shell for Voice Ledger (Kirana Khata).
 *
 * Enforces:
 * - Route guarding (Login/Register required to access dashboard)
 * - Automatic session persistence with JWT tokens
 * - Logged-in state lock (prevents navigating back to login unless logged out)
 * - Password change modal
 * - Multi-tenant data isolation per shopkeeper
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

// Format today's date in Hindi-friendly format
function formatDate() {
  const now = new Date()
  const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }
  return now.toLocaleDateString('hi-IN', options)
}

export default function App() {
  // ── Authentication State ──
  const [token, setToken] = useState(() => localStorage.getItem('kirana_token'))
  const [currentUser, setCurrentUser] = useState(null)
  const [isAuthChecking, setIsAuthChecking] = useState(true)
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false)
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false)

  // ── App State ──
  const [apiStatus, setApiStatus] = useState('checking') // 'online', 'offline', 'checking'
  const [draftData, setDraftData] = useState(null)
  const [kpiData, setKpiData] = useState(null)
  const [ledgerEntries, setLedgerEntries] = useState([])
  const [customerDues, setCustomerDues] = useState([])
  const [isSeeding, setIsSeeding] = useState(false)
  const [notification, setNotification] = useState(null)
  const [activeTab, setActiveTab] = useState('dashboard') // 'dashboard', 'ledger'

  const userMenuRef = useRef(null)

  // Close user menu on outside click
  useEffect(() => {
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setIsUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // ── Notification Helper ──
  const showNotification = useCallback((message, type = 'success') => {
    setNotification({ message, type })
    setTimeout(() => setNotification(null), 4000)
  }, [])

  // ── Razorpay Kirana Soundbox Alert ──
  const [soundboxEnabled, setSoundboxEnabled] = useState(true)

  const playSoundboxAlert = useCallback((amount, mode = 'ONLINE') => {
    if (!soundboxEnabled) return

    try {
      // 1. Play dual-tone POS audio chime using Web Audio API
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (AudioContext) {
        const audioCtx = new AudioContext()
        const osc = audioCtx.createOscillator()
        const gain = audioCtx.createGain()
        osc.connect(gain)
        gain.connect(audioCtx.destination)

        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime) // D5
        osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.12) // A5
        gain.gain.setValueAtTime(0.25, audioCtx.currentTime)
        gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.45)

        osc.start()
        osc.stop(audioCtx.currentTime + 0.45)
      }

      // 2. Hindi Kirana Soundbox voice announcement
      if ('speechSynthesis' in window) {
        setTimeout(() => {
          const rounded = Math.round(Number(amount || 0))
          const text = mode === 'CASH'
            ? `Nokad bhugtan prapt hua: ${rounded} rupaye cash khate me darj!`
            : `Razorpay par ${rounded} rupaye prapt hue!`
          const utterance = new SpeechSynthesisUtterance(text)
          utterance.lang = 'hi-IN'
          utterance.rate = 1.05
          utterance.pitch = 1.05
          window.speechSynthesis.speak(utterance)
        }, 250)
      }
    } catch (err) {
      console.warn('Soundbox audio play failed:', err)
    }
  }, [soundboxEnabled])

  // ── Verify Stored Session on Boot ──
  useEffect(() => {
    const verifySession = async () => {
      const savedToken = localStorage.getItem('kirana_token')
      if (!savedToken) {
        setIsAuthChecking(false)
        return
      }

      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${savedToken}` },
        })

        if (res.ok) {
          const userData = await res.json()
          setCurrentUser(userData)
          setToken(savedToken)
        } else {
          localStorage.removeItem('kirana_token')
          setToken(null)
          setCurrentUser(null)
        }
      } catch (e) {
        console.error('Session check failed:', e)
      } finally {
        setIsAuthChecking(false)
      }
    }

    verifySession()
  }, [])

  // ── Auth Action Handlers ──
  const handleAuthSuccess = (authData) => {
    localStorage.setItem('kirana_token', authData.access_token)
    setToken(authData.access_token)
    setCurrentUser(authData.user)
    showNotification(`Welcome, ${authData.user.name}! 🏪`)
  }

  const handleLogout = () => {
    localStorage.removeItem('kirana_token')
    setToken(null)
    setCurrentUser(null)
    setDraftData(null)
    setKpiData(null)
    setLedgerEntries([])
    setCustomerDues([])
    setIsUserMenuOpen(false)
    showNotification('Logged out successfully.')
  }

  // ── Authenticated API Fetch Helper ──
  const authFetch = useCallback(
    async (endpoint, options = {}) => {
      if (!token) return null

      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      }

      try {
        const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers })
        if (res.status === 401) {
          handleLogout()
          showNotification('Session expired. Please sign in again.', 'error')
          return null
        }
        return res
      } catch (err) {
        console.error(`API call ${endpoint} failed:`, err)
        throw err
      }
    },
    [token, showNotification]
  )

  // ── Health Check ──
  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
      if (res.ok) {
        setApiStatus('online')
      } else {
        setApiStatus('offline')
      }
    } catch {
      setApiStatus('offline')
    }
  }, [])

  // ── Dashboard Data Fetchers (Strictly Scoped) ──
  const fetchSummary = useCallback(async () => {
    if (!token) return
    try {
      const res = await authFetch('/ledger/summary')
      if (res && res.ok) {
        const data = await res.json()
        setKpiData(data)
      }
    } catch (e) {
      console.error('Failed to fetch summary:', e)
    }
  }, [authFetch, token])

  const fetchLedger = useCallback(async () => {
    if (!token) return
    try {
      const res = await authFetch('/ledger/entries?per_page=50')
      if (res && res.ok) {
        const data = await res.json()
        setLedgerEntries(data.entries || [])
      }
    } catch (e) {
      console.error('Failed to fetch ledger:', e)
    }
  }, [authFetch, token])

  const fetchDues = useCallback(async () => {
    if (!token) return
    try {
      const res = await authFetch('/customers/dues')
      if (res && res.ok) {
        const data = await res.json()
        setCustomerDues(data || [])
      }
    } catch (e) {
      console.error('Failed to fetch dues:', e)
    }
  }, [authFetch, token])

  const refreshAll = useCallback(async () => {
    if (!token) return
    await Promise.all([fetchSummary(), fetchLedger(), fetchDues()])
  }, [fetchSummary, fetchLedger, fetchDues, token])

  // Load data whenever authenticated user is active
  useEffect(() => {
    checkHealth()
    if (currentUser && token) {
      refreshAll()
    }
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [checkHealth, refreshAll, currentUser, token])

  // ── Seed Demo Data ──
  const handleSeedData = async () => {
    setIsSeeding(true)
    try {
      const res = await fetch(`${API_BASE}/demo/seed`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        showNotification('Demo data ready! Refreshing...')
        await refreshAll()
      } else {
        showNotification(data.error?.message || 'Seed failed', 'error')
      }
    } catch {
      showNotification('Failed to load demo data', 'error')
    } finally {
      setIsSeeding(false)
    }
  }

  // ── Transaction Draft Events ──
  const handleDraftReady = (data) => {
    setDraftData(data)
    showNotification('Voice processed! Review the draft below.', 'info')
  }

  const handleCommitSuccess = async () => {
    setDraftData(null)
    showNotification('✅ Transaction recorded successfully!')
    await refreshAll()
  }

  const handleDismissDraft = () => {
    setDraftData(null)
  }

  const handleReminderSent = () => {
    showNotification('WhatsApp reminder link generated! 📱')
    fetchDues()
  }

  const handlePaymentSuccess = (paymentResult) => {
    const mode = paymentResult.payment_mode || 'ONLINE'
    playSoundboxAlert(paymentResult.amount_paid, mode)
    const modeLabel = mode === 'CASH' ? 'Cash (रोकड़)' : 'Razorpay / Online'
    showNotification(`₹${paymentResult.amount_paid} received via ${modeLabel} for ${paymentResult.customer_name}! 🚀`, 'success')
    fetchSummary()
    fetchEntries()
    fetchDues()
  }

  // ── Initial Loading Screen ──
  if (isAuthChecking) {
    return (
      <div className="min-h-screen bg-fintech-bg flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-fintech-accent to-indigo-700 flex items-center justify-center mx-auto mb-4 animate-pulse">
            <Store className="w-6 h-6 text-white" />
          </div>
          <p className="text-sm font-medium text-gray-400">Loading secure Kirana session...</p>
        </div>
      </div>
    )
  }

  // ── Unauthenticated: Guard Route (Cannot access Home Page) ──
  if (!currentUser) {
    return <AuthModal onAuthSuccess={handleAuthSuccess} />
  }

  // ── Authenticated: Home Page (Cannot access Login Page without logging out) ──
  return (
    <div className="min-h-screen bg-fintech-bg text-gray-100">
      {/* ── Notification Toast ── */}
      {notification && (
        <div
          className={`fixed top-4 right-4 z-50 animate-slide-up max-w-sm
          ${notification.type === 'error' ? 'bg-red-500/90' :
            notification.type === 'info' ? 'bg-blue-500/90' :
            'bg-emerald-500/90'}
          text-white px-5 py-3 rounded-xl shadow-2xl backdrop-blur-sm
          border border-white/10 text-sm font-medium`}
        >
          {notification.message}
        </div>
      )}

      {/* ── Change Password Modal ── */}
      {isChangePasswordOpen && (
        <ChangePasswordModal
          token={token}
          onClose={() => setIsChangePasswordOpen(false)}
          onSuccess={(msg) => showNotification(msg, 'success')}
        />
      )}

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-fintech-bg/85 border-b border-fintech-border/50">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            {/* Store & Shopkeeper Info */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fintech-accent to-indigo-700
                            flex items-center justify-center shadow-lg shadow-fintech-accent/20 border border-white/10">
                <Store className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base sm:text-lg font-bold text-white leading-tight truncate max-w-[200px] sm:max-w-xs">
                  {currentUser.shop_name}
                </h1>
                <p className="text-xs text-gray-400 flex items-center gap-1.5">
                  <Calendar className="w-3 h-3" />
                  {formatDate()}
                </p>
              </div>
            </div>

            {/* Right Controls: API Status, Demo Seed, User Menu */}
            <div className="flex items-center gap-3">
              {/* API Status */}
              <div className="hidden sm:flex items-center gap-1.5 text-xs">
                {apiStatus === 'online' ? (
                  <>
                    <span className="status-dot-online" />
                    <span className="text-emerald-400">Online</span>
                  </>
                ) : apiStatus === 'offline' ? (
                  <>
                    <span className="status-dot-offline" />
                    <span className="text-red-400">Offline</span>
                  </>
                ) : (
                  <span className="text-gray-500">Checking...</span>
                )}
              </div>

              {/* Razorpay Rails Badge */}
              <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/25 text-[#3894ff] text-[11px] font-semibold">
                <Zap className="w-3 h-3 text-yellow-300 fill-yellow-300" />
                <span>Razorpay Rails</span>
              </div>

              {/* Soundbox Voice Alert Toggle */}
              <button
                id="btn-toggle-soundbox"
                onClick={() => setSoundboxEnabled(!soundboxEnabled)}
                className={`flex items-center gap-1.5 py-1.5 px-2.5 rounded-xl border text-xs font-medium transition-all ${
                  soundboxEnabled
                    ? 'bg-blue-500/15 border-blue-500/40 text-[#3894ff]'
                    : 'bg-fintech-surface/60 border-fintech-border text-gray-500'
                }`}
                title={soundboxEnabled ? 'Soundbox Voice Alert Active (Click to mute)' : 'Soundbox Muted (Click to enable)'}
              >
                {soundboxEnabled ? <Volume2 className="w-3.5 h-3.5 text-[#3894ff]" /> : <VolumeX className="w-3.5 h-3.5 text-gray-500" />}
                <span className="hidden sm:inline">Soundbox: {soundboxEnabled ? 'ON' : 'OFF'}</span>
              </button>

              {/* Seed Demo Button */}
              <button
                id="btn-seed-data"
                onClick={handleSeedData}
                disabled={isSeeding}
                className="btn-ghost text-xs hidden sm:flex items-center gap-1.5 py-2 px-3"
                title="Load sample transactions for demonstration"
              >
                <Database className="w-3.5 h-3.5 text-fintech-warning" />
                <span>{isSeeding ? 'Loading...' : 'Demo Data'}</span>
              </button>

              {/* User Settings Dropdown */}
              <div className="relative" ref={userMenuRef}>
                <button
                  id="btn-user-menu"
                  onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                  className="flex items-center gap-2 py-1.5 px-3 rounded-xl bg-fintech-surface/80 hover:bg-fintech-surface border border-fintech-border text-xs transition-all duration-200"
                >
                  <div className="w-6 h-6 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-xs">
                    {currentUser.name?.[0] || 'U'}
                  </div>
                  <span className="font-medium text-white hidden sm:inline">
                    {currentUser.name} {currentUser.surname}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                </button>

                {/* Dropdown Menu */}
                {isUserMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-fintech-card/95 border border-fintech-border shadow-2xl backdrop-blur-xl py-2 z-50 animate-slide-up">
                    <div className="px-4 py-2 border-b border-fintech-border/50">
                      <p className="text-xs font-semibold text-white truncate">
                        {currentUser.name} {currentUser.surname}
                      </p>
                      <p className="text-[11px] text-gray-400 truncate">{currentUser.email}</p>
                      <p className="text-[11px] text-emerald-400 truncate mt-0.5">{currentUser.phone}</p>
                    </div>

                    <div className="py-1">
                      {/* Change Password Option */}
                      <button
                        id="btn-open-change-password"
                        onClick={() => {
                          setIsUserMenuOpen(false)
                          setIsChangePasswordOpen(true)
                        }}
                        className="w-full px-4 py-2 text-left text-xs text-gray-300 hover:text-white hover:bg-fintech-surface/80 flex items-center gap-2.5 transition-colors"
                      >
                        <KeyRound className="w-4 h-4 text-fintech-accent" />
                        <span>Change Password</span>
                      </button>

                      {/* Log Out Option */}
                      <button
                        id="btn-logout"
                        onClick={handleLogout}
                        className="w-full px-4 py-2 text-left text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 flex items-center gap-2.5 transition-colors"
                      >
                        <LogOut className="w-4 h-4" />
                        <span>Log Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main Content ── */}
      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* ── Shop Banner / Tagline ── */}
        <div className="text-center py-1">
          <p className="text-gray-400 text-xs sm:text-sm font-medium tracking-wide">
            <span className="text-fintech-accent">Bolkar</span> hisaab rakho •{' '}
            <span className="text-fintech-warning">Udhaar</span> bhoolo mat •{' '}
            <span className="text-fintech-success">Payment</span> jaldi pao
          </p>
        </div>

        {/* ── KPI Dashboard ── */}
        <KPIGrid data={kpiData} />

        {/* ── Voice Recorder ── */}
        <VoiceRecorder
          onDraftReady={handleDraftReady}
          apiStatus={apiStatus}
          token={token}
        />

        {/* ── Draft Transaction Review ── */}
        {draftData && (
          <div className="animate-slide-up">
            <DraftTransaction
              data={draftData}
              onCommitSuccess={handleCommitSuccess}
              onDismiss={handleDismissDraft}
              token={token}
              merchantId={currentUser.merchant_id}
            />
          </div>
        )}

        {/* ── Tab Navigation ── */}
        <div className="flex gap-2 border-b border-fintech-border/50 pb-0">
          <button
            id="tab-dues-recovery"
            onClick={() => setActiveTab('dashboard')}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-all duration-200
              ${activeTab === 'dashboard'
                ? 'text-fintech-accent border-b-2 border-fintech-accent bg-fintech-accent/5'
                : 'text-gray-400 hover:text-gray-200'
              }`}
          >
            Udhaar & Recovery
          </button>
          <button
            id="tab-ledger-history"
            onClick={() => setActiveTab('ledger')}
            className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-all duration-200
              ${activeTab === 'ledger'
                ? 'text-fintech-accent border-b-2 border-fintech-accent bg-fintech-accent/5'
                : 'text-gray-400 hover:text-gray-200'
              }`}
          >
            Ledger History
          </button>
          <button
            id="btn-refresh-all"
            onClick={refreshAll}
            className="ml-auto text-gray-500 hover:text-gray-300 transition-colors p-2"
            title="Refresh Khata Data"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* ── Tab Content ── */}
        {activeTab === 'dashboard' ? (
          <RecoveryFeed
            customerDues={customerDues}
            onReminderSent={handleReminderSent}
            onPaymentSuccess={handlePaymentSuccess}
            token={token}
            merchantId={currentUser.merchant_id}
          />
        ) : (
          <div className="space-y-3 animate-fade-in">
            <h2 className="text-lg font-semibold text-white">Recent Transactions</h2>
            {ledgerEntries.length === 0 ? (
              <div className="glass-card p-8 text-center">
                <p className="text-gray-400">No transactions recorded yet for this shop. Speak or record your first sale!</p>
              </div>
            ) : (
              <div className="space-y-2">
                {ledgerEntries.map((entry) => (
                  <div key={entry.id} className="glass-card-hover p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`badge ${
                              entry.transaction_type === 'SALE'
                                ? 'badge-info'
                                : entry.transaction_type === 'PAYMENT_RECEIVED'
                                ? 'badge-success'
                                : 'badge-warning'
                            }`}
                          >
                            {entry.transaction_type === 'SALE'
                              ? '🛒 Sale'
                              : entry.transaction_type === 'PAYMENT_RECEIVED'
                              ? '💰 Payment'
                              : entry.transaction_type}
                          </span>
                          {entry.customer_name && (
                            <span className="text-sm text-gray-300 font-medium truncate">
                              {entry.customer_name}
                            </span>
                          )}
                        </div>
                        {entry.raw_transcript && (
                          <p className="text-xs text-gray-500 italic truncate mt-1">
                            "{entry.raw_transcript}"
                          </p>
                        )}
                        <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-400">
                          {parseFloat(entry.cash_paid) > 0 && (
                            <span className="text-fintech-cash">
                              💵 Cash: ₹{Number(entry.cash_paid).toLocaleString('en-IN')}
                            </span>
                          )}
                          {parseFloat(entry.upi_paid) > 0 && (
                            <span className="text-fintech-upi">
                              📱 UPI: ₹{Number(entry.upi_paid).toLocaleString('en-IN')}
                            </span>
                          )}
                          {parseFloat(entry.credit_amount) > 0 && (
                            <span className="text-fintech-udhar">
                              📝 Udhar: ₹{Number(entry.credit_amount).toLocaleString('en-IN')}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="amount-display text-lg text-white">
                          ₹{Number(entry.total_amount).toLocaleString('en-IN')}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {entry.created_at
                            ? new Date(entry.created_at).toLocaleTimeString('en-IN', {
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : ''}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="max-w-5xl mx-auto px-4 py-8 text-center border-t border-fintech-border/30 mt-12">
        <p className="text-xs text-gray-500 flex items-center justify-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          <span>Kirana Khata AI • Bcrypt Secured • Isolated Shop Data</span>
        </p>
      </footer>
    </div>
  )
}
