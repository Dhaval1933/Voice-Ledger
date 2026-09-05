import React, { useState, useRef, useEffect } from 'react'
import { Mic, MicOff, Square, Loader2, AlertCircle, MessageSquare, Zap } from 'lucide-react'

/**
 * VoiceRecorder — Push-to-talk microphone with demo quick-select.
 *
 * States: IDLE → LISTENING → TRANSCRIBING → ANALYZING → READY_FOR_REVIEW → ERROR
 *
 * Uses MediaRecorder API for WebM audio capture.
 * Includes text input fallback and demo quick-buttons for mock mode.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const DEMO_SENTENCES = [
  { label: '🛒 Sharma ji — Sale + Cash + Udhar', text: 'Sharma ji ne 450 ka rashan liya, 200 cash diya baaki kal denge.' },
  { label: '📱 Ramesh bhai — Full UPI', text: 'Ramesh bhai ne 1200 ka saman liya, pura UPI kar diya.' },
  { label: '💰 Sita ji — Payment Received', text: 'Sita ji ka purana udhar 800 tha, 500 cash de diya.' },
  { label: '📝 Mohan — Full Udhar', text: 'Mohan ne 600 ka kirana liya, pura udhar likh do.' },
  { label: '💳 Gupta ji — Cash + UPI', text: 'Gupta ji ne 950 ka maal liya, 450 cash aur 500 UPI kiya.' },
]

const STATES = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  TRANSCRIBING: 'TRANSCRIBING',
  ANALYZING: 'ANALYZING',
  ERROR: 'ERROR',
}

export default function VoiceRecorder({ onDraftReady, apiStatus, token }) {
  const [state, setState] = useState(STATES.IDLE)
  const [error, setError] = useState(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const [textInput, setTextInput] = useState('')
  const [showTextMode, setShowTextMode] = useState(false)
  const [showDemoButtons, setShowDemoButtons] = useState(true)
  const [processingText, setProcessingText] = useState('')

  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const streamRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
      }
    }
  }, [])

  // ── Start Recording ──
  const startRecording = async () => {
    setError(null)
    chunksRef.current = []

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        }
      })
      streamRef.current = stream

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      })
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }

      mediaRecorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach(t => t.stop())
        clearInterval(timerRef.current)

        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (audioBlob.size < 100) {
          setError('Recording too short. Please try again.')
          setState(STATES.ERROR)
          return
        }

        await processAudio(audioBlob)
      }

      mediaRecorder.start(100)
      setState(STATES.LISTENING)
      setRecordingTime(0)

      // Timer
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1)
      }, 1000)

    } catch (err) {
      console.error('Microphone access error:', err)
      setError('Microphone access denied. Use text input or demo buttons instead.')
      setState(STATES.ERROR)
    }
  }

  // ── Stop Recording ──
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    clearInterval(timerRef.current)
    setState(STATES.TRANSCRIBING)
    setProcessingText('Transcribing audio...')
  }

  // ── Process Audio ──
  const processAudio = async (audioBlob) => {
    setState(STATES.ANALYZING)
    setProcessingText('Analyzing transaction...')

    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'recording.webm')

      const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}

      const res = await fetch(`${API_BASE}/voice/process`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.error?.message || `Server error: ${res.status}`)
      }

      const data = await res.json()
      onDraftReady(data)
      setState(STATES.IDLE)
    } catch (err) {
      setError(err.message || 'Failed to process audio')
      setState(STATES.ERROR)
    }
  }

  // ── Process Text Input ──
  const handleTextSubmit = async () => {
    if (!textInput.trim()) return

    setState(STATES.ANALYZING)
    setProcessingText('Analyzing transaction...')
    setError(null)

    try {
      const formData = new FormData()
      formData.append('transcript_text', textInput.trim())

      const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}

      const res = await fetch(`${API_BASE}/voice/process`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.error?.message || `Server error: ${res.status}`)
      }

      const data = await res.json()
      onDraftReady(data)
      setState(STATES.IDLE)
      setTextInput('')
    } catch (err) {
      setError(err.message || 'Failed to process text')
      setState(STATES.ERROR)
    }
  }

  // ── Process Demo Sentence ──
  const handleDemoSelect = async (index) => {
    setState(STATES.ANALYZING)
    setProcessingText('Processing demo transaction...')
    setError(null)

    try {
      const formData = new FormData()
      formData.append('demo_index', index.toString())

      const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}

      const res = await fetch(`${API_BASE}/voice/process`, {
        method: 'POST',
        headers: authHeaders,
        body: formData,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.error?.message || `Server error: ${res.status}`)
      }

      const data = await res.json()
      onDraftReady(data)
      setState(STATES.IDLE)
    } catch (err) {
      setError(err.message || 'Failed to process demo')
      setState(STATES.ERROR)
    }
  }

  // Format recording time
  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const isProcessing = state === STATES.TRANSCRIBING || state === STATES.ANALYZING

  return (
    <div className="glass-card p-5 space-y-4">
      {/* ── Section Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Zap className="w-4 h-4 text-fintech-accent" />
            Bolkar Entry Karein
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">Record a voice note or type in Hinglish</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowTextMode(!showTextMode)}
            className={`text-xs px-3 py-1.5 rounded-lg transition-all ${
              showTextMode ? 'bg-fintech-accent/20 text-fintech-accent' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 inline mr-1" />
            Type
          </button>
        </div>
      </div>

      {/* ── Microphone Button ── */}
      <div className="flex flex-col items-center gap-3 py-3">
        {state === STATES.LISTENING ? (
          // Recording state
          <button
            id="btn-stop-recording"
            onClick={stopRecording}
            className="mic-recording"
          >
            <Square className="w-8 h-8 sm:w-10 sm:h-10 text-white fill-white" />
          </button>
        ) : isProcessing ? (
          // Processing state
          <div className="mic-processing">
            <Loader2 className="w-8 h-8 sm:w-10 sm:h-10 text-white animate-spin" />
          </div>
        ) : (
          // Idle state
          <button
            id="btn-start-recording"
            onClick={startRecording}
            disabled={apiStatus === 'offline'}
            className="mic-idle disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Mic className="w-8 h-8 sm:w-10 sm:h-10 text-white" />
          </button>
        )}

        {/* Status text */}
        <div className="text-center">
          {state === STATES.LISTENING && (
            <div className="flex items-center gap-2 text-red-400 animate-recording-pulse">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
              <span className="text-sm font-medium">Recording • {formatTime(recordingTime)}</span>
            </div>
          )}
          {isProcessing && (
            <p className="text-sm text-amber-400 animate-pulse">{processingText}</p>
          )}
          {state === STATES.IDLE && (
            <p className="text-xs text-gray-500">Tap to record • Bolkar entry karein</p>
          )}
        </div>
      </div>

      {/* ── Text Input Fallback ── */}
      {showTextMode && (
        <div className="flex gap-2 animate-fade-in">
          <input
            id="input-transcript"
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTextSubmit()}
            placeholder='e.g. "Sharma ji ne 450 ka rashan liya, 200 cash diya"'
            className="input-field text-sm flex-1"
            disabled={isProcessing}
          />
          <button
            id="btn-submit-text"
            onClick={handleTextSubmit}
            disabled={!textInput.trim() || isProcessing}
            className="btn-primary text-sm whitespace-nowrap"
          >
            Process
          </button>
        </div>
      )}

      {/* ── Demo Quick-Select ── */}
      {showDemoButtons && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Demo Transactions</p>
            <button
              onClick={() => setShowDemoButtons(false)}
              className="text-xs text-gray-600 hover:text-gray-400"
            >
              Hide
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {DEMO_SENTENCES.map((demo, index) => (
              <button
                key={index}
                id={`btn-demo-${index}`}
                onClick={() => handleDemoSelect(index)}
                disabled={isProcessing}
                className="text-left p-3 rounded-xl bg-fintech-bg/50 border border-fintech-border/30
                         hover:border-fintech-accent/30 hover:bg-fintech-accent/5
                         transition-all duration-200 disabled:opacity-40 group"
              >
                <p className="text-xs font-medium text-gray-300 group-hover:text-white">{demo.label}</p>
                <p className="text-xs text-gray-500 mt-1 italic truncate">"{demo.text}"</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Error Display ── */}
      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 animate-fade-in">
          <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-red-300">{error}</p>
            <button
              onClick={() => { setError(null); setState(STATES.IDLE) }}
              className="text-xs text-red-400 hover:text-red-300 mt-1 underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
