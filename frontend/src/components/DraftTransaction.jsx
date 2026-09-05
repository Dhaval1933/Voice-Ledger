import React, { useState } from 'react'
import {
  CheckCircle2, AlertTriangle, XCircle, User, ShoppingCart,
  CreditCard, Banknote, Smartphone, Calendar, FileText,
  Shield, Loader2, X
} from 'lucide-react'

/**
 * DraftTransaction — Review and confirm an extracted transaction.
 *
 * Displays:
 * - Raw transcript
 * - Transaction type & customer match
 * - Financial breakdown (editable)
 * - Validation badge (✓ Math Verified / ⚠ Discrepancy)
 * - Flags (injection, duplicate, ambiguous)
 * - Confirm & Record button
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export default function DraftTransaction({ data, onCommitSuccess, onDismiss, token, merchantId }) {
  const { transcript, draft, customer_match, validation, can_commit, idempotency_hash, flags } = data

  const [isCommitting, setIsCommitting] = useState(false)
  const [commitError, setCommitError] = useState(null)
  const [editedFields, setEditedFields] = useState({
    total_amount: draft.financials.total_amount,
    cash_paid: draft.financials.cash_paid,
    upi_paid: draft.financials.upi_paid,
    credit_amount: draft.financials.credit_amount,
  })

  // ── Commit Transaction ──
  const handleCommit = async () => {
    setIsCommitting(true)
    setCommitError(null)

    try {
      const body = {
        merchant_id: merchantId || 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        customer_id: customer_match?.matched_customer?.id || null,
        customer_name: customer_match?.is_new_customer ? draft.customer.name : null,
        customer_phone: draft.customer.phone,
        transaction_type: draft.transaction_type,
        total_amount: editedFields.total_amount.toString(),
        cash_paid: editedFields.cash_paid.toString(),
        upi_paid: editedFields.upi_paid.toString(),
        credit_amount: editedFields.credit_amount.toString(),
        due_date: draft.due_date,
        items: draft.items.map(item => ({
          item_name: item.item_name,
          quantity: item.quantity,
          unit_price: item.price ? item.price.toString() : null,
        })),
        raw_transcript: transcript,
        confidence_score: draft.confidence_score,
        idempotency_hash: idempotency_hash,
      }

      const res = await fetch(`${API_BASE}/ledger/commit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      })

      const result = await res.json()

      if (result.success) {
        onCommitSuccess(result)
      } else {
        setCommitError(result.error?.message || 'Commit failed')
      }
    } catch (err) {
      setCommitError(err.message || 'Network error')
    } finally {
      setIsCommitting(false)
    }
  }

  // Transaction type display
  const typeConfig = {
    SALE: { label: '🛒 Sale', color: 'badge-info' },
    PAYMENT_RECEIVED: { label: '💰 Payment Received', color: 'badge-success' },
    EXPENSE: { label: '📤 Expense', color: 'badge-warning' },
    PURCHASE: { label: '📦 Purchase', color: 'badge-warning' },
  }
  const txnDisplay = typeConfig[draft.transaction_type] || typeConfig.SALE

  // Check if math is valid with edited fields
  const computedTotal = parseFloat(editedFields.cash_paid || 0) +
    parseFloat(editedFields.upi_paid || 0) +
    parseFloat(editedFields.credit_amount || 0)
  const actualTotal = parseFloat(editedFields.total_amount || 0)
  const localDelta = Math.abs(actualTotal - computedTotal)
  const localValid = localDelta < 0.01

  return (
    <div className="glass-card p-5 space-y-4 border-l-4 border-l-fintech-accent">
      {/* ── Header ── */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-white flex items-center gap-2">
            <FileText className="w-4 h-4 text-fintech-accent" />
            Draft Review
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">Review and confirm the transaction</p>
        </div>
        <button
          onClick={onDismiss}
          className="text-gray-500 hover:text-gray-300 p-1 rounded-lg hover:bg-fintech-surface/50 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Raw Transcript ── */}
      <div className="p-3 rounded-xl bg-fintech-bg/50 border border-fintech-border/30">
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Voice Transcript</p>
        <p className="text-sm text-gray-200 italic">"{transcript}"</p>
      </div>

      {/* ── Transaction Type & Customer ── */}
      <div className="flex flex-wrap gap-3">
        <span className={txnDisplay.color}>{txnDisplay.label}</span>

        <div className="flex items-center gap-1.5">
          <User className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-sm text-white font-medium">{draft.customer.name}</span>
          {customer_match?.matched_customer && (
            <span className="text-xs text-emerald-400 ml-1">
              ✓ {Math.round((customer_match.match_score || 0) * 100)}% match
            </span>
          )}
          {customer_match?.is_new_customer && (
            <span className="text-xs text-amber-400 ml-1">🆕 New customer</span>
          )}
          {customer_match?.is_ambiguous && (
            <span className="text-xs text-red-400 ml-1">⚠ Ambiguous</span>
          )}
        </div>
      </div>

      {/* ── Financial Breakdown ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="space-y-1">
          <label className="text-xs text-gray-500 flex items-center gap-1">
            <ShoppingCart className="w-3 h-3" /> Total
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">₹</span>
            <input
              type="number"
              value={editedFields.total_amount}
              onChange={e => setEditedFields(prev => ({ ...prev, total_amount: e.target.value }))}
              className="input-field pl-7 text-sm font-semibold text-white"
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fintech-cash flex items-center gap-1">
            <Banknote className="w-3 h-3" /> Cash
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">₹</span>
            <input
              type="number"
              value={editedFields.cash_paid}
              onChange={e => setEditedFields(prev => ({ ...prev, cash_paid: e.target.value }))}
              className="input-field pl-7 text-sm text-fintech-cash"
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fintech-upi flex items-center gap-1">
            <Smartphone className="w-3 h-3" /> UPI
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">₹</span>
            <input
              type="number"
              value={editedFields.upi_paid}
              onChange={e => setEditedFields(prev => ({ ...prev, upi_paid: e.target.value }))}
              className="input-field pl-7 text-sm text-fintech-upi"
            />
          </div>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-fintech-udhar flex items-center gap-1">
            <CreditCard className="w-3 h-3" /> Udhar
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">₹</span>
            <input
              type="number"
              value={editedFields.credit_amount}
              onChange={e => setEditedFields(prev => ({ ...prev, credit_amount: e.target.value }))}
              className="input-field pl-7 text-sm text-fintech-udhar"
            />
          </div>
        </div>
      </div>

      {/* ── Items ── */}
      {draft.items && draft.items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {draft.items.map((item, i) => (
            <span key={i} className="text-xs bg-fintech-surface/50 px-3 py-1.5 rounded-lg text-gray-300 border border-fintech-border/30">
              {item.item_name}
              {item.price && ` • ₹${Number(item.price).toLocaleString('en-IN')}`}
            </span>
          ))}
        </div>
      )}

      {/* ── Due Date ── */}
      {draft.due_date && (
        <div className="flex items-center gap-2 text-sm">
          <Calendar className="w-4 h-4 text-fintech-warning" />
          <span className="text-gray-300">Due: {new Date(draft.due_date).toLocaleDateString('hi-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</span>
        </div>
      )}

      {/* ── Validation Badge ── */}
      <div className={`flex items-center gap-3 p-3 rounded-xl ${
        localValid
          ? 'bg-emerald-500/10 border border-emerald-500/20'
          : 'bg-red-500/10 border border-red-500/20'
      }`}>
        {localValid ? (
          <>
            <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-emerald-400">✓ Math Verified</p>
              <p className="text-xs text-emerald-400/70">
                ₹{Number(editedFields.total_amount).toLocaleString('en-IN')} = Cash ₹{Number(editedFields.cash_paid).toLocaleString('en-IN')} + UPI ₹{Number(editedFields.upi_paid).toLocaleString('en-IN')} + Udhar ₹{Number(editedFields.credit_amount).toLocaleString('en-IN')}
              </p>
            </div>
          </>
        ) : (
          <>
            <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-400">⚠ Discrepancy Detected — Action Required</p>
              <p className="text-xs text-red-400/70">
                Delta: ₹{localDelta.toFixed(2)} • Total ₹{actualTotal} ≠ Cash ₹{parseFloat(editedFields.cash_paid || 0)} + UPI ₹{parseFloat(editedFields.upi_paid || 0)} + Udhar ₹{parseFloat(editedFields.credit_amount || 0)}
              </p>
            </div>
          </>
        )}
      </div>

      {/* ── Flags ── */}
      {flags && flags.length > 0 && (
        <div className="space-y-2">
          {flags.map((flag, i) => (
            <div key={i} className="flex items-center gap-2 p-2.5 rounded-xl bg-red-500/10 border border-red-500/20">
              <Shield className="w-4 h-4 text-red-400 flex-shrink-0" />
              <span className="text-xs text-red-300 font-medium">{flag}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Confidence Score ── */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-fintech-bg/50 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full transition-all duration-500 ${
              draft.confidence_score >= 0.8 ? 'bg-emerald-500' :
              draft.confidence_score >= 0.5 ? 'bg-amber-500' : 'bg-red-500'
            }`}
            style={{ width: `${(draft.confidence_score || 0) * 100}%` }}
          />
        </div>
        <span className="text-xs text-gray-400">
          {Math.round((draft.confidence_score || 0) * 100)}% confidence
        </span>
      </div>

      {/* ── Commit Error ── */}
      {commitError && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20">
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{commitError}</p>
        </div>
      )}

      {/* ── Action Buttons ── */}
      <div className="flex gap-3 pt-2">
        <button
          id="btn-confirm-commit"
          onClick={handleCommit}
          disabled={!localValid || isCommitting || customer_match?.is_ambiguous || (flags && flags.some(f => f.includes('INJECTION') || f.includes('DUPLICATE')))}
          className="btn-success flex-1 flex items-center justify-center gap-2 text-base"
        >
          {isCommitting ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Recording...
            </>
          ) : (
            <>
              <CheckCircle2 className="w-5 h-5" />
              Confirm & Record
            </>
          )}
        </button>
        <button
          onClick={onDismiss}
          className="btn-ghost"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
