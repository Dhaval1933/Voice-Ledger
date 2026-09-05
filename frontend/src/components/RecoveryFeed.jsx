import React, { useState } from 'react'
import {
  User, Phone, Clock, AlertTriangle, MessageCircle,
  ExternalLink, CheckCircle2, Send, Loader2, Smartphone,
  Zap, Copy, Check, ShieldCheck, Banknote,
} from 'lucide-react'
import RazorpayCheckoutModal from './RazorpayCheckoutModal'
import SettleDueModal from './SettleDueModal'

/**
 * RecoveryFeed — Customer dues with WhatsApp reminder dispatch & Razorpay Rails.
 *
 * Shows customers with outstanding balances.
 * Each card: name, phone, ₹ outstanding, due date, overdue badge, recovery status.
 * Actions:
 * - "Pay via Razorpay" triggers Razorpay checkout modal / 1-click simulation.
 * - "Send WhatsApp Link" triggers POST /api/recovery/send-reminder.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

function formatIndianCurrency(amount) {
  const num = Number(amount || 0)
  if (num === 0) return '₹0'
  const str = Math.round(num).toString()
  if (str.length <= 3) return `₹${str}`
  const lastThree = str.slice(-3)
  const remaining = str.slice(0, -3)
  const formatted = remaining.replace(/\B(?=(\d{2})+(?!\d))/g, ',')
  return `₹${formatted},${lastThree}`
}

function CustomerDueCard({ customer, onReminderSent, onOpenRazorpay, onOpenSettle, token, merchantId }) {
  const [isSending, setIsSending] = useState(false)
  const [whatsappResult, setWhatsappResult] = useState(null)
  const [error, setError] = useState(null)
  const [copiedLink, setCopiedLink] = useState(false)

  const handleSendReminder = async () => {
    if (!customer.recovery_id) return
    setIsSending(true)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/recovery/send-reminder`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          recovery_id: customer.recovery_id,
          merchant_id: merchantId || 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        }),
      })

      const data = await res.json()

      if (data.success) {
        setWhatsappResult(data)
        onReminderSent(data)
      } else {
        setError(data.error?.message || 'Failed to send reminder')
      }
    } catch (err) {
      setError('Network error')
    } finally {
      setIsSending(false)
    }
  }

  const handleCopyLink = () => {
    if (customer.razorpay_short_url) {
      navigator.clipboard.writeText(customer.razorpay_short_url)
      setCopiedLink(true)
      setTimeout(() => setCopiedLink(false), 2000)
    }
  }

  const statusConfig = {
    PENDING: { label: 'Pending', class: 'badge-warning' },
    LINK_SENT: { label: 'Link Sent', class: 'badge-info' },
    COLLECTED: { label: 'Collected', class: 'badge-success' },
  }
  const status = statusConfig[customer.recovery_status] || statusConfig.PENDING

  return (
    <div className={`glass-card-hover p-4 ${customer.is_overdue ? 'border-l-4 border-l-red-500' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        {/* Customer Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-fintech-accent/20 to-indigo-800/30
                          flex items-center justify-center border border-fintech-border/30">
              <User className="w-4 h-4 text-fintech-accent" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">{customer.name}</p>
              {customer.phone && (
                <p className="text-xs text-gray-500 flex items-center gap-1">
                  <Phone className="w-3 h-3" /> {customer.phone}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mt-2">
            <span className={status.class}>{status.label}</span>
            {customer.is_overdue && (
              <span className="badge-danger">
                <AlertTriangle className="w-3 h-3" /> Overdue
              </span>
            )}
            {customer.razorpay_short_url && (
              <button
                type="button"
                onClick={handleCopyLink}
                className="text-[10px] bg-blue-500/10 text-[#3894ff] border border-blue-500/30 px-2 py-0.5 rounded-full flex items-center gap-1 hover:bg-blue-500/20 transition-colors"
                title="Copy Razorpay Link"
              >
                {copiedLink ? <Check className="w-2.5 h-2.5 text-emerald-400" /> : <Copy className="w-2.5 h-2.5" />}
                <span>Razorpay Link</span>
              </button>
            )}
          </div>

          {customer.latest_due_date && (
            <p className="text-xs text-gray-500 mt-1.5 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Due: {new Date(customer.latest_due_date).toLocaleDateString('hi-IN', {
                day: 'numeric', month: 'short', year: 'numeric'
              })}
            </p>
          )}
        </div>

        {/* Amount */}
        <div className="text-right">
          <p className={`amount-display text-xl ${customer.is_overdue ? 'text-red-400' : 'text-fintech-udhar'}`}>
            {formatIndianCurrency(customer.total_outstanding)}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">Baaki</p>
        </div>
      </div>

      {/* ── Action Buttons (Cash Settlement, Razorpay & WhatsApp) ── */}
      <div className="mt-3 pt-3 border-t border-fintech-border/30 space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {/* Settle Cash button */}
          <button
            id={`btn-settle-cash-${customer.id}`}
            onClick={() => onOpenSettle(customer)}
            className="flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-xl
                     bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-600/30
                     text-xs font-semibold shadow-sm transition-all active:scale-95"
            title="Customer paid in Cash (Nokad)"
          >
            <Banknote className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span className="truncate">Settle Cash</span>
          </button>

          {/* Pay via Razorpay button */}
          <button
            id={`btn-razorpay-${customer.id}`}
            onClick={() => onOpenRazorpay(customer)}
            className="flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-xl
                     bg-gradient-to-r from-[#0B72E7] to-[#0A58CA] text-white hover:from-[#0960c5] hover:to-[#0848a6]
                     text-xs font-semibold shadow-md shadow-blue-500/20 transition-all active:scale-95"
            title="Generate UPI QR or Razorpay Payment Link"
          >
            <Zap className="w-3.5 h-3.5 text-yellow-300 fill-yellow-300 shrink-0" />
            <span className="truncate">Online / QR</span>
          </button>
        </div>

        {/* WhatsApp Reminder button */}
        <button
          id={`btn-whatsapp-${customer.id}`}
          onClick={handleSendReminder}
          disabled={isSending || !customer.recovery_id}
          className="w-full flex items-center justify-center gap-1.5 py-1.5 px-2.5 rounded-lg
                   bg-green-600/10 text-green-400 border border-green-500/20
                   hover:bg-green-600/20 transition-all text-xs font-medium disabled:opacity-50"
        >
          {isSending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          ) : (
            <MessageCircle className="w-3.5 h-3.5 shrink-0" />
          )}
          <span className="truncate">Send WhatsApp Due Reminder</span>
        </button>
      </div>

      {/* ── WhatsApp Result ── */}
      {whatsappResult && (
        <div className="mt-3 pt-3 border-t border-fintech-border/30 space-y-2 animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">WhatsApp link generated!</span>
          </div>

          <div className="p-2.5 rounded-lg bg-fintech-bg/50 border border-fintech-border/30">
            <p className="text-xs text-gray-400 whitespace-pre-line">{whatsappResult.message}</p>
          </div>

          <a
            href={whatsappResult.whatsapp_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 py-2 rounded-lg
                     bg-green-600/20 text-green-400 border border-green-500/20
                     hover:bg-green-600/30 transition-all text-xs font-medium"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open WhatsApp
          </a>

          {/* UPI Link */}
          {customer.upi_deep_link && (
            <a
              href={customer.upi_deep_link}
              className="flex items-center justify-center gap-2 py-2 rounded-lg
                       bg-purple-600/20 text-purple-400 border border-purple-500/20
                       hover:bg-purple-600/30 transition-all text-xs font-medium"
            >
              <Smartphone className="w-3.5 h-3.5" />
              Open UPI Payment
            </a>
          )}
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="mt-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300">
          {error}
        </div>
      )}
    </div>
  )
}

export default function RecoveryFeed({ customerDues, onReminderSent, onPaymentSuccess, token, merchantId }) {
  const [selectedCustomerForRazorpay, setSelectedCustomerForRazorpay] = useState(null)
  const [selectedCustomerForSettle, setSelectedCustomerForSettle] = useState(null)

  if (!customerDues || customerDues.length === 0) {
    return (
      <div className="glass-card p-8 text-center animate-fade-in">
        <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-fintech-surface/50
                      flex items-center justify-center">
          <CheckCircle2 className="w-6 h-6 text-emerald-400" />
        </div>
        <p className="text-gray-400 text-sm">No outstanding Udhaar! 🎉</p>
        <p className="text-gray-500 text-xs mt-1">All customers are fully paid up.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-fintech-udhar" />
          Active Dues & Recovery
          <span className="text-sm font-normal text-gray-400 ml-1">
            ({customerDues.length} customer{customerDues.length > 1 ? 's' : ''})
          </span>
        </h2>
        <span className="text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full font-medium flex items-center gap-1">
          <Banknote className="w-3 h-3 text-emerald-400" />
          <span>Cash & Digital Ready</span>
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {customerDues.map((customer) => (
          <CustomerDueCard
            key={customer.id}
            customer={customer}
            onReminderSent={onReminderSent}
            onOpenRazorpay={(cust) => setSelectedCustomerForRazorpay(cust)}
            onOpenSettle={(cust) => setSelectedCustomerForSettle(cust)}
            token={token}
            merchantId={merchantId}
          />
        ))}
      </div>

      {/* Settle Due (Cash / UPI) Modal */}
      <SettleDueModal
        isOpen={!!selectedCustomerForSettle}
        onClose={() => setSelectedCustomerForSettle(null)}
        customer={selectedCustomerForSettle}
        onPaymentSuccess={onPaymentSuccess}
        token={token}
      />

      {/* Razorpay Checkout Modal */}
      <RazorpayCheckoutModal
        isOpen={!!selectedCustomerForRazorpay}
        onClose={() => setSelectedCustomerForRazorpay(null)}
        customer={selectedCustomerForRazorpay}
        onPaymentSuccess={onPaymentSuccess}
        token={token}
      />
    </div>
  )
}
