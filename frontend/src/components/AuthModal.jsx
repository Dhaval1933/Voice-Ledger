import React, { useState } from 'react'
import {
  Store, Mail, Lock, User, Phone, Eye, EyeOff,
  ArrowRight, ShieldCheck, Sparkles, CheckCircle2, AlertCircle, KeyRound,
} from 'lucide-react'
import ForgotPasswordModal from './ForgotPasswordModal'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export default function AuthModal({ onAuthSuccess }) {
  const [isLogin, setIsLogin] = useState(true)
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  // Login form state
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')

  // Sign up form state
  const [signupForm, setSignupForm] = useState({
    email: '',
    name: '',
    surname: '',
    shop_name: '',
    phone: '',
    password: '',
    confirm_password: '',
  })

  const handleSignupChange = (e) => {
    const { name, value } = e.target
    setSignupForm((prev) => ({ ...prev, [name]: value }))
  }

  // Quick 1-click login for preloaded demo store
  const handleQuickDemo = async () => {
    setLoginEmail('demo@kirana.store')
    setLoginPassword('sharma123')
    setError(null)
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'demo@kirana.store',
          password: 'sharma123',
        }),
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error?.message || data.detail || 'Demo login failed.')
      }

      onAuthSuccess(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }


  // Handle Login Submit
  const handleLoginSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    if (!loginEmail.trim() || !loginPassword.trim()) {
      setError('Please enter both email and password.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: loginEmail.trim(),
          password: loginPassword,
        }),
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error?.message || data.detail || 'Login failed. Check your credentials.')
      }

      onAuthSuccess(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Handle Sign Up Submit
  const handleSignupSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    const { email, name, surname, shop_name, phone, password, confirm_password } = signupForm

    // Validation
    if (!email.trim() || !name.trim() || !surname.trim() || !shop_name.trim() || !phone.trim() || !password) {
      setError('Please fill in all required fields.')
      return
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Please provide a valid email address.')
      return
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters long.')
      return
    }

    if (password !== confirm_password) {
      setError('Passwords do not match. Please re-enter.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          name: name.trim(),
          surname: surname.trim(),
          shop_name: shop_name.trim(),
          phone: phone.trim(),
          password,
        }),
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error?.message || data.detail || 'Sign up failed. Please try again.')
      }

      setSuccessMsg('Account created successfully! Logging you in...')
      setTimeout(() => {
        onAuthSuccess(data)
      }, 700)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-fintech-bg flex flex-col justify-center items-center p-4 relative overflow-hidden">
      {/* Background Decorative Glows */}
      <div className="absolute top-1/4 -left-20 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-emerald-600/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md z-10">
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-fintech-accent to-indigo-700 shadow-xl shadow-fintech-accent/25 mb-3 border border-white/10">
            <Store className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Kirana Khata</h1>
          <p className="text-xs text-gray-400 mt-1">
            Voice-First AI Ledger & Smart Udhar Controller for Shopkeepers
          </p>
        </div>

        {/* Auth Card */}
        <div className="glass-card p-6 sm:p-8 border border-fintech-border/80 shadow-2xl relative">
          {/* Tab Selector */}
          <div className="flex bg-fintech-bg/80 p-1 rounded-xl border border-fintech-border/50 mb-6">
            <button
              type="button"
              id="tab-login"
              onClick={() => { setIsLogin(true); setError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200 ${
                isLogin
                  ? 'bg-fintech-accent text-white shadow-md shadow-fintech-accent/30'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              id="tab-signup"
              onClick={() => { setIsLogin(false); setError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all duration-200 ${
                !isLogin
                  ? 'bg-fintech-accent text-white shadow-md shadow-fintech-accent/30'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              Register Shop
            </button>
          </div>

          {/* Alert / Notification Messages */}
          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-start gap-2 animate-fade-in">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {successMsg && (
            <div className="mb-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2 animate-fade-in">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* ── Login Form ── */}
          {isLogin ? (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-gray-400 absolute left-3.5 top-3.5" />
                  <input
                    id="input-login-email"
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="sharma@kirana.com"
                    className="input-field pl-10 text-sm"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-medium text-gray-300">
                    Password
                  </label>
                  <button
                    type="button"
                    id="btn-forgot-password-link"
                    onClick={() => {
                      setError(null)
                      setIsForgotPasswordOpen(true)
                    }}
                    className="text-xs text-fintech-accent hover:text-indigo-400 font-medium transition-colors"
                  >
                    Forgot Password?
                  </button>
                </div>
                <div className="relative">
                  <Lock className="w-4 h-4 text-gray-400 absolute left-3.5 top-3.5" />
                  <input
                    id="input-login-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="••••••••"
                    className="input-field pl-10 pr-10 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-3.5 text-gray-400 hover:text-gray-200"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                id="btn-submit-login"
                disabled={loading}
                className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
              >
                {loading ? (
                  <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Sign In to Store</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>

              {/* Demo Account Quick-Fill Helper */}
              <div className="pt-3 border-t border-fintech-border/40">
                <button
                  type="button"
                  id="btn-quick-demo-login"
                  onClick={handleQuickDemo}
                  className="w-full py-2 px-3 rounded-lg bg-fintech-surface/60 hover:bg-fintech-surface text-gray-400 hover:text-gray-200 border border-fintech-border/40 text-xs flex items-center justify-center gap-2 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5 text-fintech-warning" />
                  <span>Use Preloaded Demo Store (1-Click)</span>
                </button>
              </div>
            </form>
          ) : (
            /* ── Sign Up Form ── */
            <form onSubmit={handleSignupSubmit} className="space-y-3">
              {/* Name and Surname */}
              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    First Name
                  </label>
                  <div className="relative">
                    <User className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                    <input
                      id="input-signup-name"
                      name="name"
                      type="text"
                      required
                      value={signupForm.name}
                      onChange={handleSignupChange}
                      placeholder="Ramesh"
                      className="input-field pl-9 text-xs py-2.5"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    Surname
                  </label>
                  <input
                    id="input-signup-surname"
                    name="surname"
                    type="text"
                    required
                    value={signupForm.surname}
                    onChange={handleSignupChange}
                    placeholder="Sharma"
                    className="input-field text-xs py-2.5"
                  />
                </div>
              </div>

              {/* Shop Name */}
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Name of Shop (Dukan Name)
                </label>
                <div className="relative">
                  <Store className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                  <input
                    id="input-signup-shop-name"
                    name="shop_name"
                    type="text"
                    required
                    value={signupForm.shop_name}
                    onChange={handleSignupChange}
                    placeholder="Sharma Kirana & General Store"
                    className="input-field pl-9 text-xs py-2.5"
                  />
                </div>
              </div>

              {/* Email Address */}
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Email Address (Unique)
                </label>
                <div className="relative">
                  <Mail className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                  <input
                    id="input-signup-email"
                    name="email"
                    type="email"
                    required
                    value={signupForm.email}
                    onChange={handleSignupChange}
                    placeholder="sharma@kirana.com"
                    className="input-field pl-9 text-xs py-2.5"
                  />
                </div>
              </div>

              {/* Phone Number */}
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Phone Number (Mobile)
                </label>
                <div className="relative">
                  <Phone className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                  <input
                    id="input-signup-phone"
                    name="phone"
                    type="tel"
                    required
                    value={signupForm.phone}
                    onChange={handleSignupChange}
                    placeholder="9876543210"
                    className="input-field pl-9 text-xs py-2.5"
                  />
                </div>
              </div>

              {/* Password & Confirm */}
              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                    <input
                      id="input-signup-password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={signupForm.password}
                      onChange={handleSignupChange}
                      placeholder="Min 6 chars"
                      className="input-field pl-9 pr-8 text-xs py-2.5"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-2 top-3 text-gray-400 hover:text-gray-200"
                    >
                      {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-3.5" />
                    <input
                      id="input-signup-confirm-password"
                      name="confirm_password"
                      type={showConfirmPassword ? 'text' : 'password'}
                      required
                      value={signupForm.confirm_password}
                      onChange={handleSignupChange}
                      placeholder="Repeat password"
                      className="input-field pl-9 pr-8 text-xs py-2.5"
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      className="absolute right-2 top-3 text-gray-400 hover:text-gray-200"
                    >
                      {showConfirmPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  id="btn-submit-signup"
                  disabled={loading}
                  className="btn-success w-full flex items-center justify-center gap-2 py-2.5 text-xs"
                >
                  {loading ? (
                    <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      <ShieldCheck className="w-4 h-4" />
                      <span>Register & Create Shop Khata</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Security / Privacy Trust Badge */}
        <div className="text-center mt-4">
          <p className="text-xs text-gray-500 flex items-center justify-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            <span>Encrypted with bcrypt • Isolated Shopkeeper Data</span>
          </p>
        </div>
      </div>

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordOpen}
        onClose={() => setIsForgotPasswordOpen(false)}
        defaultEmail={loginEmail}
        onResetSuccess={(resetEmail) => {
          setLoginEmail(resetEmail)
          setIsForgotPasswordOpen(false)
          setIsLogin(true)
          setSuccessMsg('Password reset successfully! Please sign in with your new password.')
        }}
      />
    </div>
  )
}
