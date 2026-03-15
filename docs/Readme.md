# FacePay

> Biometric transit payment system for Durham Region Transit, Oshawa.
> Your face is your ticket.

---

## What it does

A passenger registers their face once, links a payment card, and boards any DRT bus by looking at a terminal camera. The system identifies them in under 3 seconds, determines their fare category — including U-Pass validity for Ontario Tech, Durham College, and Trent Durham GTA students — and charges the exact DRT PRESTO fare automatically via Stripe. No card tap. No phone. No friction.

---

## Demo

| Device | URL | Role |
|--------|-----|------|
| Laptop | `http://localhost:5173/terminal` | Bus terminal kiosk — always scanning |
| Phone or second laptop | `http://localhost:5173/register` | Passenger onboarding |

**Test card:** `4242 4242 4242 4242` · any future expiry · any CVC

---

## Architecture

```
┌─────────────────────────┐     ┌─────────────────────────┐
│   Registration App      │     │     Bus Terminal         │
│   /register             │     │     /terminal            │
│                         │     │                          │
│  • Account creation     │     │  • Always-on camera      │
│  • Fare category        │     │  • Passive liveness      │
│  • Face capture         │     │  • Face identify         │
│  • Stripe card save     │     │  • Stripe charge         │
└────────────┬────────────┘     └────────────┬─────────────┘
             │                               │
             └──────────────┬────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │      FastAPI Backend       │
              │                           │
              │  • DeepFace embeddings    │
              │  • Liveness detection     │
              │  • Fare lookup            │
              │  • GTFS caching           │
              │  • Stripe integration     │
              └─────────────┬─────────────┘
                            │
              ┌─────────────▼─────────────┐
              │   Supabase (PostgreSQL)    │
              │                           │
              │  • pgvector face search   │
              │  • Auth + RLS             │
              │  • Realtime events        │
              └───────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite — single monorepo for `/register` and `/terminal` |
| UI Components | shadcn/ui |
| Backend | FastAPI (Python 3.11) |
| Face embeddings | DeepFace (Facenet model) — 128-dimensional float vectors |
| Liveness detection | MediaPipe (registration) + OpenCV frame-delta (terminal) |
| Database | Supabase — PostgreSQL + pgvector + Auth + Realtime |
| Vector search | pgvector IVFFlat cosine similarity index |
| Payments | Stripe test mode — SetupIntent + PaymentIntent |
| GTFS | Durham Region Open Data static feed |

---

## Privacy

**Zero-knowledge biometrics.** Raw images are never written to disk or stored in any database. The backend receives camera frames, generates a 128-dimensional float vector in memory, and immediately discards the image buffer. Only the math reaches Supabase. A leaked database cannot be reverse-engineered into a photograph.

---

## DRT fare structure

| Category | Fare | Stripe charged? |
|----------|------|----------------|
| Adult (PRESTO) | $3.73 | Yes |
| Senior 65+ | $2.46 | Yes |
| Youth 13–19 | $3.35 | Yes |
| Child 12 and under | $0.00 | No |
| U-Pass (valid) | $0.00 | No |
| U-Pass (expired) | $3.73 adult fallback | Yes |
| TAP (Transit Assistance) | $52.22/mo | Yes / No after 14 trips |
| Canadian Armed Forces | $0.00 | No |

All fares reflect DRT 2025 PRESTO rates and are seeded into a `fare_rules` Supabase table. Stripe never receives a hardcoded amount.

---

## Local setup

### Prerequisites

```bash
brew install python@3.11 cmake node
xcode-select --install
```

### Backend

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_JWT_SECRET=your-jwt-secret
STRIPE_SECRET_KEY=sk_test_51...
FRONTEND_URL=http://localhost:5173
GTFS_FEED_URL=https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip
TERMINAL_ROUTE_ID=112
TERMINAL_STOP_ID=1001
```

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

Verify: `http://localhost:8000/health` → `{"status": "ok"}`

### Frontend

```bash
cd facepay-client
npm install
```

Create `facepay-client/.env.local`:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_STRIPE_PK=pk_test_51...
VITE_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

### Database

Run `backend/db/schema.sql` in the Supabase SQL Editor. This creates all 5 tables, RLS policies, pgvector index, and seeds the DRT fare table.

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create Supabase user + Stripe customer |
| POST | `/embed` | Image frames → 128-dim vector → pgvector |
| POST | `/identify` | Frame → cosine search → user + fare decision |
| POST | `/pay` | Stripe PaymentIntent with exact DRT fare |
| POST | `/pay/pin-confirm` | PIN fallback for 90–98% confidence matches |
| GET | `/gtfs/route-status` | Cached DRT route data (30s TTL) |

---

## Confidence routing

```
confidence > 0.55    →  auto charge
confidence 0.40–0.55 →  PIN fallback (4-digit, 3 attempts max)
confidence < 0.40    →  hard reject + cash fallback instruction
```

---

## Security

- **RLS enforced** on all Supabase tables. The `face_embeddings` table has no frontend access — service_role key only.
- **Stripe handles all card data.** Raw card numbers never touch FacePay servers. PCI compliance fully delegated.
- **Liveness detection** prevents photo spoofing at the terminal. Frame-delta motion analysis detects zero micro-movement in printed photos and phone screens before any identification attempt.
- **Confidence tiering** prevents false positives from lookalikes. No charge fires below 0.40 confidence.

---

## Edge cases handled

| Scenario | Behaviour |
|----------|-----------|
| U-Pass expired | Adult fare ($3.73) charged automatically. Amber warning on terminal screen. |
| Stripe payment fails | Passenger boards anyway. Transaction logged as `payment_failed`. Account flagged for follow-up. Mirrors DRT PRESTO low-balance policy. |
| Photo spoofing attempt | Passive liveness rejects before identification. Terminal shows cash fallback. |
| GTFS feed unreachable | Route panel hides gracefully. Payment flow completely unaffected. |
| Two faces in frame | Largest bounding box (closest passenger) selected. One scan per boarding event. |
| Unknown face | Confidence below threshold. Registration prompt + cash fallback shown. |

---

## Project structure

```
facepay/
├── backend/
│   ├── main.py                  FastAPI entry point
│   ├── routers/
│   │   ├── auth.py              POST /auth/register
│   │   ├── embed.py             POST /embed
│   │   ├── identify.py          POST /identify
│   │   ├── payments.py          POST /pay, POST /pay/pin-confirm
│   │   └── gtfs.py              GET /gtfs/route-status
│   ├── cv/
│   │   ├── embedder.py          DeepFace embedding generation
│   │   └── liveness.py          Two-mode liveness detection
│   └── db/
│       ├── supabase_client.py   Supabase singleton (service_role)
│       └── schema.sql           Full DB schema — run in Supabase SQL Editor
├── facepay-client/
│   └── src/
│       ├── App.jsx              /register and /terminal routes
│       ├── lib/supabase.js      Frontend Supabase client (anon key)
│       └── routes/
│           ├── register/
│           │   ├── Page.jsx           6-screen registration flow
│           │   ├── WebcamCapture.jsx  Liveness challenge + face capture
│           │   └── PaymentSetup.jsx   Stripe card save
│           └── terminal/
│               └── Page.jsx           Fullscreen kiosk — 9 states
└── docs/                        Architecture, API flow, schema, build plan
```

---

## Docs

| File | What it covers |
|------|---------------|
| `docs/PRD.md` | Product requirements, personas, edge cases |
| `docs/APP_FLOW.md` | Every screen, state, and API call |
| `docs/SCHEMA.md` | Database tables, functions, RLS policies |
| `docs/TECH_STACK.md` | Tools, install commands, environment variables |
| `docs/IMPLEMENTATION_PLAN.md` | Build order and step-by-step instructions |
| `docs/FRONTEND_GUIDELINES.md` | Design tokens, CSS variables, component patterns |

---

## Hackathon build

FacePay was built in approximately 24 hours as a hackathon project for Durham Region Transit, Oshawa — March 2026.

**v2 roadmap (out of scope for this build):**
- Institutional U-Pass verification via university enrollment API
- Real-time GTFS vehicle positions
- Multi-zone and time-of-day fare rules
- PRESTO card reconciliation
- Accessibility accommodations on the terminal
- Fleet-wide terminal management dashboard
