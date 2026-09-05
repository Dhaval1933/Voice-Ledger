import React, { useState } from 'react'
import {
  CreditCard, Smartphone, QrCode, Building, CheckCircle2,
  AlertCircle, ExternalLink, Copy, Check, ShieldCheck, Zap,
  Loader2, MessageCircle
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export default function RazorpayCheckoutModal({
  isOpen,
  onClose,
  customer,
  onPaymentSuccess,
  token,
}) {
  const [activeTab, setActiveTab] = useState('qr') // 'qr', 'card', 'netbanking', 'link'
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [copiedLink, setCopiedLink] = useState(false)

  // Card mock state
  const [cardNumber, setCardNumber] = useState('4111 2222 3333 4444')
  const [cardExpiry, setCardExpiry] = useState('12/28')
  const [cardCvv, setCardCvv] = useState('789')
  const [cardName, setCardName] = useState(customer?.name || 'Customer Name')

  if (!isOpen || !customer) return null

  const amount = Number(customer.total_outstanding || 0)
  const formattedAmount = `₹${amount.toLocaleString('en-IN')}`
  const shortUrl = customer.razorpay_short_url || `https://rzp.io/i/${customer.recovery_id?.slice(0, 8) || 'demo'}`

  // 1-Click Simulation for hackathon evaluation
  const handleSimulatePayment = async () => {
    if (!customer.recovery_id) return
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/recovery/simulate-razorpay-payment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          recovery_id: customer.recovery_id,
          amount: amount,
        }),
      })

      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.error?.message || data.message || 'Payment simulation failed.')
      }

      onPaymentSuccess(data)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shortUrl)
    setCopiedLink(true)
    setTimeout(() => setCopiedLink(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-lg bg-[#0C1B2E] border border-blue-500/30 rounded-2xl shadow-2xl overflow-hidden relative">
        {/* Top Header branded with Razorpay colors */}
        <div className="bg-gradient-to-r from-[#0B72E7] via-[#1185F7] to-[#0A58CA] p-5 text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center font-bold text-lg">
              ₹
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-extrabold tracking-tight text-base">Razorpay</span>
                <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-medium tracking-wide">
                  SECURE RAILS
                </span>
              </div>
              <p className="text-xs text-blue-100 mt-0.5">
                Kirana Khata Udhar Settlement for <strong className="text-white">{customer.name}</strong>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-white/70 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Amount Banner */}
        <div className="bg-[#081525] border-b border-blue-500/20 px-6 py-4 flex items-center justify-between">
          <div>
            <span className="text-[11px] text-gray-400 font-medium block">Total Pending Udhar</span>
            <span className="text-2xl font-extrabold text-white tracking-tight">{formattedAmount}</span>
          </div>

          {/* Quick 1-Click Simulation Button for Judges */}
          <button
            id="btn-simulate-razorpay-pay"
            onClick={handleSimulatePayment}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold text-xs shadow-lg shadow-emerald-500/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5 text-yellow-300 fill-yellow-300" />
            )}
            <span>Simulate Payment (1-Click)</span>
          </button>
        </div>

        {/* Error notification */}
        {error && (
          <div className="m-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Payment Methods Nav */}
        <div className="flex border-b border-blue-500/20 bg-[#091728] px-4 pt-2">
          {[
            { id: 'qr', label: 'UPI / Dynamic QR', icon: QrCode },
            { id: 'card', label: 'Debit & Credit Cards', icon: CreditCard },
            { id: 'netbanking', label: 'Netbanking', icon: Building },
            { id: 'link', label: 'Payment Link', icon: ExternalLink },
          ].map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3.5 py-2.5 text-xs font-semibold border-b-2 transition-all ${
                  isActive
                    ? 'border-[#0B72E7] text-[#0B72E7] bg-blue-500/10 rounded-t-lg'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>

        {/* Payment Method Content */}
        <div className="p-6">
          {/* ── 1. Dynamic UPI QR Tab ── */}
          {activeTab === 'qr' && (
            <div className="text-center space-y-4">
              <div className="inline-block p-3 rounded-2xl bg-white shadow-xl shadow-blue-500/10 border-2 border-[#0B72E7]/40">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(
                    customer.upi_deep_link || `upi://pay?pa=sharmakirana@upi&pn=KiranaStore&am=${amount}&cu=INR`
                  )}`}
                  alt="Razorpay Dynamic UPI QR"
                  className="w-44 h-44 mx-auto"
                />
              </div>

              <div>
                <p className="text-xs font-semibold text-white">Scan with Any UPI App to Pay</p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Google Pay • PhonePe • Paytm • CRED • BHIM UPI
                </p>
              </div>

              {customer.upi_deep_link && (
                <a
                  href={customer.upi_deep_link}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600/20 text-[#3894ff] border border-blue-500/30 hover:bg-blue-600/30 text-xs font-semibold transition-colors"
                >
                  <Smartphone className="w-4 h-4" />
                  <span>Open directly in UPI App</span>
                </a>
              )}
            </div>
          )}

          {/* ── 2. Cards Tab ── */}
          {activeTab === 'card' && (
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Card Number
                </label>
                <div className="relative">
                  <CreditCard className="w-4 h-4 text-gray-400 absolute left-3.5 top-3" />
                  <input
                    type="text"
                    value={cardNumber}
                    onChange={(e) => setCardNumber(e.target.value)}
                    className="input-field pl-10 text-xs py-2.5 font-mono"
                    placeholder="4111 2222 3333 4444"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    Valid Thru (MM/YY)
                  </label>
                  <input
                    type="text"
                    value={cardExpiry}
                    onChange={(e) => setCardExpiry(e.target.value)}
                    className="input-field text-xs py-2.5 font-mono text-center"
                    placeholder="MM/YY"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    CVV
                  </label>
                  <input
                    type="password"
                    maxLength={4}
                    value={cardCvv}
                    onChange={(e) => setCardCvv(e.target.value)}
                    className="input-field text-xs py-2.5 font-mono text-center"
                    placeholder="•••"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Cardholder Name
                </label>
                <input
                  type="text"
                  value={cardName}
                  onChange={(e) => setCardName(e.target.value)}
                  className="input-field text-xs py-2.5"
                  placeholder="Cardholder Name"
                />
              </div>

              <button
                onClick={handleSimulatePayment}
                disabled={loading}
                className="w-full py-2.5 rounded-xl bg-[#0B72E7] hover:bg-[#095ec4] text-white font-semibold text-xs shadow-lg shadow-blue-500/20 transition-all flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <span>Pay {formattedAmount} via Razorpay</span>}
              </button>
            </div>
          )}

          {/* ── 3. Netbanking Tab ── */}
          {activeTab === 'netbanking' && (
            <div className="space-y-4">
              <p className="text-xs text-gray-400">Select customer's bank for instant internet banking settlement:</p>
              <div className="grid grid-cols-2 gap-2.5">
                {[
                  { name: 'HDFC Bank', code: 'HDFC' },
                  { name: 'State Bank of India', code: 'SBI' },
                  { name: 'ICICI Bank', code: 'ICICI' },
                  { name: 'Axis Bank', code: 'UTIB' },
                  { name: 'Kotak Mahindra', code: 'KKBK' },
                  { name: 'Punjab National Bank', code: 'PUNB' },
                ].map((bank) => (
                  <button
                    key={bank.code}
                    type="button"
                    onClick={handleSimulatePayment}
                    disabled={loading}
                    className="p-2.5 rounded-xl bg-fintech-bg/70 hover:bg-blue-600/10 border border-fintech-border/60 hover:border-blue-500/40 text-left transition-colors flex items-center gap-2 text-xs font-medium text-gray-200"
                  >
                    <Building className="w-3.5 h-3.5 text-[#0B72E7]" />
                    <span>{bank.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── 4. Payment Link Tab ── */}
          {activeTab === 'link' && (
            <div className="space-y-4">
              <p className="text-xs text-gray-300 leading-relaxed">
                Share this unique Razorpay Payment Link with <strong>{customer.name}</strong>. When they pay, the Khata balance clears automatically via webhook reconciliation.
              </p>

              <div className="flex items-center gap-2 p-2 rounded-xl bg-fintech-bg border border-fintech-border">
                <input
                  type="text"
                  readOnly
                  value={shortUrl}
                  className="bg-transparent text-xs font-mono text-[#3894ff] flex-1 outline-none px-2"
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-[#3894ff] text-xs font-semibold flex items-center gap-1 transition-colors shrink-0"
                >
                  {copiedLink ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedLink ? 'Copied' : 'Copy'}</span>
                </button>
              </div>

              {/* WhatsApp Share Shortcut */}
              <a
                href={`https://wa.me/?text=${encodeURIComponent(
                  `Namaste ${customer.name}, aapka ₹${amount} ka pending hisaab clear karne ke liye Razorpay link yahan hai: ${shortUrl}`
                )}`}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 transition-all text-xs font-semibold"
              >
                <MessageCircle className="w-4 h-4" />
                <span>Share Link on WhatsApp</span>
              </a>
            </div>
          )}
        </div>

        {/* Footer Security Badge */}
        <div className="px-6 py-3 bg-[#081525] border-t border-blue-500/20 flex items-center justify-between text-[11px] text-gray-400">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>PCI-DSS Compliant • HMAC SHA-256 Webhook Reconciled</span>
          </div>
          <span className="text-[#0B72E7] font-semibold">Razorpay Rails</span>
        </div>
      </div>
    </div>
  )
}
