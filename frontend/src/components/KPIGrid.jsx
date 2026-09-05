import React, { useEffect, useState } from 'react'
import { TrendingUp, Banknote, Smartphone, AlertCircle } from 'lucide-react'

/**
 * KPIGrid — 4 prominent financial metric cards.
 *
 * 1. Aaj ki Bikri (Today's Revenue) — blue accent
 * 2. Cash in Hand — green accent
 * 3. UPI Collection — purple accent
 * 4. Baaki Udhaar (Outstanding) — orange/red accent
 *
 * Uses animated count-up and Indian comma notation.
 */

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

function KPICard({ label, amount, icon: Icon, accentClass, iconBg }) {
  const [displayAmount, setDisplayAmount] = useState(0)

  useEffect(() => {
    const target = Number(amount || 0)
    if (target === 0) {
      setDisplayAmount(0)
      return
    }

    // Animated count-up
    const duration = 800
    const steps = 30
    const increment = target / steps
    let current = 0
    let step = 0

    const timer = setInterval(() => {
      step++
      current = Math.min(current + increment, target)
      setDisplayAmount(Math.round(current))

      if (step >= steps) {
        setDisplayAmount(target)
        clearInterval(timer)
      }
    }, duration / steps)

    return () => clearInterval(timer)
  }, [amount])

  return (
    <div className={`kpi-card ${accentClass}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${iconBg}`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
      </div>
      <p className="amount-display amount-lg text-white animate-count-up">
        {formatIndianCurrency(displayAmount)}
      </p>
      <p className="text-xs text-gray-400 mt-1.5 font-medium">{label}</p>
    </div>
  )
}

export default function KPIGrid({ data }) {
  const metrics = [
    {
      label: "Aaj ki Bikri",
      amount: data?.total_sales || 0,
      icon: TrendingUp,
      accentClass: 'kpi-card-blue',
      iconBg: 'bg-gradient-to-br from-blue-500 to-blue-700',
    },
    {
      label: "Cash in Hand",
      amount: data?.cash_in_hand || 0,
      icon: Banknote,
      accentClass: 'kpi-card-green',
      iconBg: 'bg-gradient-to-br from-emerald-500 to-emerald-700',
    },
    {
      label: "UPI Collection",
      amount: data?.upi_collected || 0,
      icon: Smartphone,
      accentClass: 'kpi-card-purple',
      iconBg: 'bg-gradient-to-br from-purple-500 to-purple-700',
    },
    {
      label: "Baaki Udhaar",
      amount: data?.outstanding_udhaar || 0,
      icon: AlertCircle,
      accentClass: 'kpi-card-orange',
      iconBg: 'bg-gradient-to-br from-amber-500 to-orange-600',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      {metrics.map((metric, i) => (
        <KPICard key={i} {...metric} />
      ))}

      {/* Overdue indicator */}
      {data?.overdue_recoveries > 0 && (
        <div className="col-span-2 lg:col-span-4 flex items-center gap-2 px-4 py-2
                       bg-red-500/10 border border-red-500/20 rounded-xl text-sm">
          <AlertCircle className="w-4 h-4 text-red-400" />
          <span className="text-red-300 font-medium">
            {data.overdue_recoveries} overdue recovery{data.overdue_recoveries > 1 ? 's' : ''} pending
          </span>
        </div>
      )}
    </div>
  )
}
