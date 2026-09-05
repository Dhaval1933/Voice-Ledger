import React, { useState, useEffect } from 'react'
import {
  Banknote, Smartphone, Zap, CheckCircle2, AlertCircle,
  Loader2, ArrowRight, User, Calendar
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export default function SettleDueModal({
  isOpen,
  onClose,
  customer,
  onPaymentSuccess,
  token,
}) {
  if (!isOpen || !customer) return null

  const totalDue = Number(customer.total_outstanding || 0)
  const [amount, setAmount] = useState(totalDue.toString())
  const [paymentMode, setPaymentMode] = useState('CASH') // 'CASH', 'UPI', 'RAZORPAY'
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (customer) {
      setAmount(Number(customer.total_outstanding || 0).toString())
      setPaymentMode('CASH')
      setNotes('')
      setError(null)
    }
  }, [customer])

  const parsedAmount = Number(amount || 0)

  const handleQuickAmount = (val) => {
    setAmount(val.toString())
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)

    if (parsedAmount <= 0) {
      setError('Please enter an amount greater than 0.')
      return
    }

    if (parsedAmount > totalDue) {
      setError(`Payment cannot exceed total due balance of ₹${totalDue.toLocaleString('en-IN')}.`)
      return
    }

    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/recovery/settle-payment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          customer_id: customer.id,
          recovery_id: customer.recovery_id,
          amount: parsedAmount,
          payment_mode: paymentMode,
          notes: notes.trim() || `Customer ${customer.name} paid ₹${parsedAmount} via ${paymentMode}`,
        }),
      })

      const data = await res.json()
      if (!res.ok || !data.success) {
        throw new Error(data.error?.message || data.message || 'Failed to record payment.')
      }

      onPaymentSuccess(data)
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md bg-fintech-surface border border-fintech-border rounded-2xl shadow-2xl p-6 relative overflow-hidden">
        {/* Glow accent */}
        <div className={`absolute top-0 right-0 w-44 h-44 rounded-full blur-3xl pointer-events-none ${
          paymentMode === 'CASH' ? 'bg-emerald-500/15' : paymentMode === 'UPI' ? 'bg-purple-500/15' : 'bg-blue-500/15'
        }`} />

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white shadow-lg ${
              paymentMode === 'CASH'
                ? 'bg-gradient-to-br from-emerald-500 to-teal-700 shadow-emerald-500/20'
                : paymentMode === 'UPI'
                ? 'bg-gradient-to-br from-purple-500 to-indigo-700 shadow-purple-500/20'
                : 'bg-gradient-to-br from-blue-500 to-indigo-700 shadow-blue-500/20'
            }`}>
              {paymentMode === 'CASH' ? (
                <Banknote className="w-5 h-5" />
              ) : paymentMode === 'UPI' ? (
                <Smartphone className="w-5 h-5" />
              ) : (
                <Zap className="w-5 h-5 text-yellow-300" />
              )}
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Record Udhar Repayment</h3>
              <p className="text-xs text-gray-400">
                Settling dues for <strong className="text-gray-200">{customer.name}</strong>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Customer Balance Summary Banner */}
        <div className="p-3 rounded-xl bg-fintech-bg/70 border border-fintech-border/60 flex items-center justify-between mb-4">
          <div>
            <span className="text-[11px] text-gray-400 font-medium block">Total Pending Udhar</span>
            <span className="text-xl font-extrabold text-fintech-udhar">
              ₹{totalDue.toLocaleString('en-IN')}
            </span>
          </div>
          {parsedAmount > 0 && (
            <div className="text-right">
              <span className="text-[11px] text-gray-400 font-medium block">Remaining After Payment</span>
              <span className={`text-sm font-bold ${totalDue - parsedAmount === 0 ? 'text-emerald-400' : 'text-gray-200'}`}>
                ₹{Math.max(0, totalDue - parsedAmount).toLocaleString('en-IN')}
              </span>
            </div>
          )}
        </div>

        {/* Error notification */}
        {error && (
          <div className="mb-3 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Mode Selector */}
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-2">
              Payment Received via:
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                id="btn-mode-cash"
                onClick={() => setPaymentMode('CASH')}
                className={`p-3 rounded-xl border flex flex-col items-center gap-1.5 transition-all text-xs font-semibold ${
                  paymentMode === 'CASH'
                    ? 'bg-emerald-500/20 border-emerald-500/60 text-emerald-300 shadow-lg shadow-emerald-500/10'
                    : 'bg-fintech-bg/50 border-fintech-border/50 text-gray-400 hover:text-gray-200'
                }`}
              >
                <Banknote className="w-4 h-4" />
                <span>Cash (रोकड़)</span>
              </button>

              <button
                type="button"
                id="btn-mode-upi"
                onClick={() => setPaymentMode('UPI')}
                className={`p-3 rounded-xl border flex flex-col items-center gap-1.5 transition-all text-xs font-semibold ${
                  paymentMode === 'UPI'
                    ? 'bg-purple-500/20 border-purple-500/60 text-purple-300 shadow-lg shadow-purple-500/10'
                    : 'bg-fintech-bg/50 border-fintech-border/50 text-gray-400 hover:text-gray-200'
                }`}
              >
                <Smartphone className="w-4 h-4" />
                <span>Direct UPI</span>
              </button>

              <button
                type="button"
                id="btn-mode-razorpay"
                onClick={() => setPaymentMode('RAZORPAY')}
                className={`p-3 rounded-xl border flex flex-col items-center gap-1.5 transition-all text-xs font-semibold ${
                  paymentMode === 'RAZORPAY'
                    ? 'bg-blue-500/20 border-blue-500/60 text-blue-300 shadow-lg shadow-blue-500/10'
                    : 'bg-fintech-bg/50 border-fintech-border/50 text-gray-400 hover:text-gray-200'
                }`}
              >
                <Zap className="w-4 h-4" />
                <span>Razorpay Link</span>
              </button>
            </div>
          </div>

          {/* Amount Input */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-medium text-gray-300">
                Amount Received (₹)
              </label>
              <span className="text-[11px] text-gray-400">Supports Partial Payment</span>
            </div>
            <div className="relative">
              <span className="absolute left-3.5 top-2.5 text-gray-400 font-bold text-sm">₹</span>
              <input
                id="input-settle-amount"
                type="number"
                step="0.01"
                min="1"
                max={totalDue}
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="input-field pl-8 font-mono text-base font-bold py-2"
                placeholder="0.00"
              />
            </div>

            {/* Quick Amount Chips */}
            <div className="flex flex-wrap gap-1.5 mt-2">
              <button
                type="button"
                onClick={() => handleQuickAmount(totalDue)}
                className="px-2.5 py-1 rounded-lg bg-fintech-bg hover:bg-fintech-bg/80 border border-fintech-border text-[11px] font-medium text-gray-300 hover:text-white transition-colors"
              >
                Full Due (₹{totalDue})
              </button>
              {totalDue > 100 && (
                <button
                  type="button"
                  onClick={() => handleQuickAmount(Math.round(totalDue / 2))}
                  className="px-2.5 py-1 rounded-lg bg-fintech-bg hover:bg-fintech-bg/80 border border-fintech-border text-[11px] font-medium text-gray-300 hover:text-white transition-colors"
                >
                  Half (₹{Math.round(totalDue / 2)})
                </button>
              )}
              {[100, 200, 500].filter((val) => val < totalDue).map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => handleQuickAmount(val)}
                  className="px-2.5 py-1 rounded-lg bg-fintech-bg hover:bg-fintech-bg/80 border border-fintech-border text-[11px] font-medium text-gray-300 hover:text-white transition-colors"
                >
                  ₹{val}
                </button>
              ))}
            </div>
          </div>

          {/* Notes (Optional) */}
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1">
              Note (Optional)
            </label>
            <input
              id="input-settle-note"
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Paid cash at counter"
              className="input-field text-xs py-2"
            />
          </div>

          {/* Submit button */}
          <button
            type="submit"
            id="btn-confirm-settle-payment"
            disabled={loading || parsedAmount <= 0}
            className={`w-full py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 shadow-lg transition-all active:scale-95 disabled:opacity-50 ${
              paymentMode === 'CASH'
                ? 'bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white shadow-emerald-500/20'
                : paymentMode === 'UPI'
                ? 'bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-400 hover:to-indigo-500 text-white shadow-purple-500/20'
                : 'bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-400 hover:to-indigo-500 text-white shadow-blue-500/20'
            }`}
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                <span>
                  Confirm ₹{parsedAmount ? parsedAmount.toLocaleString('en-IN') : 0}{' '}
                  {paymentMode === 'CASH' ? 'Cash Settlement' : `${paymentMode} Payment`}
                </span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
