# 🎤 Voice Ledger & AI Finance Controller

> **Bolkar hisaab rakho. Udhaar bhoolo mat. Payment jaldi pao.**

A production-grade, voice-first financial control system for Indian retail micro-merchants (Kirana stores). Converts Hinglish voice notes into verified accounting transactions with UPI recovery workflows.

## ✨ Key Features

- **🎙️ Voice-First Input** — Speak in Hinglish to record transactions
- **🤖 AI Extraction** — Automatic customer, amount, and payment split detection
- **🔒 Deterministic Guardrails** — AI proposes, deterministic code disposes
- **📊 Real-Time Dashboard** — Today's revenue, cash, UPI, outstanding Udhar
- **💰 UPI Recovery** — Auto-generated UPI deep links for pending payments
- **📱 WhatsApp Reminders** — One-click payment reminder dispatch
- **🛡️ Prompt Injection Defense** — Malicious transcripts are flagged, never committed
- **🔁 Idempotency** — Duplicate voice notes don't create duplicate transactions

## 🏗️ Architecture

```
Audio → ASR → Extraction → Sanitization → Validation → Customer Matching → Draft
Draft → Merchant Confirmation → Server Revalidation → Atomic Commit → Balance Update → Recovery
```

**Core Principle:** No AI output ever directly modifies the financial ledger. Every transaction passes through deterministic validation before commitment.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2 |
| Database | SQLite (dev) / PostgreSQL-compatible |
| AI/ASR | OpenAI Whisper, Groq (swappable), Mock mode |
| Frontend | React 18, Vite, Tailwind CSS 3, Lucide React |
| Audio | HTML5 MediaRecorder API (WebM) |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Backend Setup

```bash
cd voice-ledger

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux)
# source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Copy environment file
copy .env.example .env

# Seed demo data
python -m backend.seed

# Start backend server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## 📦 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./ledger.db` | Database connection string |
| `ASR_PROVIDER` | `mock` | ASR provider: `mock`, `openai`, `groq` |
| `LLM_PROVIDER` | `mock` | LLM provider: `mock`, `openai`, `groq` |
| `OPENAI_API_KEY` | - | Required if using OpenAI providers |
| `GROQ_API_KEY` | - | Required if using Groq providers |
| `MERCHANT_VPA` | `demo@upi` | Demo merchant UPI VPA |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allowed origin |

### Mock Mode (Default)

The application runs fully in **mock mode** without any API keys. The mock ASR provider returns realistic Hinglish transcripts, and the mock extraction provider uses deterministic regex parsing.

### OpenAI Mode

```env
ASR_PROVIDER=openai
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

### Groq Mode

```env
ASR_PROVIDER=groq
LLM_PROVIDER=groq
GROQ_API_KEY=gsk-your-key-here
```

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/voice/process` | Voice → draft pipeline |
| `POST` | `/api/ledger/commit` | Atomic ledger commit |
| `GET` | `/api/ledger/summary` | Daily KPI summary |
| `GET` | `/api/ledger/entries` | Paginated ledger history |
| `POST` | `/api/recovery/send-reminder` | WhatsApp reminder (mock) |
| `GET` | `/api/customers/dues` | Customers with outstanding |
| `POST` | `/api/demo/seed` | Load demo data |

## 🎮 Demo Flow (2-3 minutes)

1. **Open dashboard** → See seeded KPI data
2. **Click "Demo Data"** → Load sample transactions
3. **Click a demo sentence** (e.g., "Sharma ji ne 450 ka rashan liya...")
4. **Review the draft** → See extracted customer, amounts, validation
5. **Check "✓ Math Verified"** → Financial invariant passes
6. **Click "Confirm & Record"** → Transaction committed atomically
7. **See KPIs update** → Revenue, cash, Udhar change in real-time
8. **Check Recovery Feed** → Sharma ji's Udhar appears
9. **Click "Send WhatsApp"** → WhatsApp URL generated
10. **Try a malformed transaction** → See "⚠ Discrepancy Detected"

### Demonstrating Math Mismatch

Type this in the text input:
```
Sharma ji ka bill 450 hai, 200 cash diya aur 100 udhar.
```

The system detects: `ERR_MATH_MISMATCH, delta = 150` and blocks commitment.

## 🧪 Testing

```bash
cd voice-ledger
python -m pytest backend/tests/ -v
```

### Test Coverage

- **Validator Tests**: Financial invariant, VPA validation, prompt injection, idempotency
- **Ledger Tests**: Outstanding balance changes, negative balance prevention, duplicate rejection
- **API Tests**: All endpoints, error handling, pagination

## 🔒 Security Features

- Server-side financial validation (never trust frontend)
- Decimal arithmetic for all monetary calculations
- Database CHECK constraints on all amount fields
- Prompt injection detection (20+ patterns)
- Idempotency hash with DB unique constraint
- MIME type validation for audio uploads
- 10MB upload size limit
- No API keys in frontend code
- Transaction rollback on any failure

## 📁 Project Structure

```
voice-ledger/
├── backend/
│   ├── __init__.py
│   ├── main.py           # FastAPI app & all endpoints
│   ├── models.py          # SQLAlchemy ORM models
│   ├── database.py        # Engine, session, init
│   ├── schemas.py         # Pydantic request/response models
│   ├── config.py          # Environment configuration
│   ├── validator.py       # Financial validation & security
│   ├── extractor.py       # AI/mock extraction providers
│   ├── seed.py            # Demo data seeding
│   ├── requirements.txt
│   ├── services/
│   │   ├── transcription.py      # ASR providers
│   │   ├── customer_matching.py  # Fuzzy name matching
│   │   └── recovery.py           # UPI & WhatsApp generation
│   └── tests/
│       ├── test_validator.py
│       ├── test_ledger.py
│       └── test_api.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── index.css
│       └── components/
│           ├── VoiceRecorder.jsx
│           ├── DraftTransaction.jsx
│           ├── KPIGrid.jsx
│           └── RecoveryFeed.jsx
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

## 🏭 Production Considerations

- Replace SQLite with PostgreSQL for concurrent access
- Add authentication (JWT, OAuth)
- Implement rate limiting
- Add real WhatsApp Business API integration
- Configure HTTPS/TLS
- Add database migrations (Alembic)
- Implement audit logging
- Add multi-merchant support
- Integrate real-time websockets for live updates

## 📄 License

MIT
