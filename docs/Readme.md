<div align="center">

<br/>

```
███████╗ █████╗  ██████╗███████╗██████╗  █████╗ ██╗   ██╗
██╔════╝██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗╚██╗ ██╔╝
█████╗  ███████║██║     █████╗  ██████╔╝███████║ ╚████╔╝ 
██╔══╝  ██╔══██║██║     ██╔══╝  ██╔═══╝ ██╔══██║  ╚██╔╝  
██║     ██║  ██║╚██████╗███████╗██║     ██║  ██║   ██║   
╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝     ╚═╝  ╚═╝   ╚═╝   
```

### **Your face is your ticket.**
*Biometric transit payment for Durham Region Transit — board in under 3 seconds.*

<br/>

[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Stripe](https://img.shields.io/badge/Stripe-Test_Mode-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://stripe.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-00FF94?style=for-the-badge)](#)

<br/>

> Built in **24 hours** at the DRT Hackathon · March 2026 · Finished **5th place**

</div>

---

<br/>

## ◈ What is FacePay?

A passenger registers their face **once**, links a payment card, and boards any DRT bus by **looking at a camera**. No tap. No phone. No card. No friction.

The system identifies them in under 3 seconds, resolves their exact fare category — including live U-Pass expiry checks for Ontario Tech, Durham College, and Trent Durham students — and charges the correct **2025 DRT PRESTO rate** through Stripe automatically.

<br/>

```
  BEFORE  ──────────────────────────────────────────────────────  AFTER
  
 Bus arrives                                        Bus arrives
 Passenger fumbles for PRESTO card                  Passenger walks up
Tap (maybe fails, balance unknown)                 Camera detects face  
Driver checks screen                              $3.73 charged — 2.1s
~7-10 seconds                                         Doors close
Doors finally close
```

<br/>

---

## ◈ Architecture

<div align="center">

![FacePay Architecture](docs/architecture.jpeg)

*Single React monorepo · `/register` route · `/terminal` route · One Vercel deploy*

</div>

<br/>

---

## ◈ The Boarding Flow

<div align="center">

![Boarding Flow](docs/boarding-flow.svg)

</div>

<br/>

```
Camera detects face
        │
        ▼
┌───────────────────┐     fails      ┌─────────────────────────┐
│  Passive Liveness  │ ─────────────▶ │  REJECTED               │
│  frame-delta +    │                │  "Look at the camera"   │
│  texture analysis  │                │  → logs failed_scans    │
└────────┬──────────┘                └─────────────────────────┘
         │ passes
         ▼
┌───────────────────┐
│  POST /identify   │
│  pgvector cosine  │
│  similarity       │
└────────┬──────────┘
         │
         ├── confidence > 0.55 ──────▶ AUTO CHARGE  → Stripe PI → ✅ Success
         │
         ├── confidence 0.40–0.55 ───▶ PIN FALLBACK  (4-digit, 3 attempts)
         │                                  │
         │                                  ├── correct ──▶ Stripe PI → ✅ Success
         │                                  └── 3 fails ──▶ "Board with cash"
         │
         └── confidence < 0.40 ────▶ HARD REJECT  → logs failed_scans
```

<br/>

---

## ◈ Screenshots

### Registration App — `/register`

| Landing | Create Account | Fare Category |
|:---:|:---:|:---:|
| ![Landing](docs/screenshots/01-landing.jpeg) | ![Create Account](docs/screenshots/02-create-account.jpeg) | ![Fare Category](docs/screenshots/03-fare-category.jpeg) |
| *"Your face is your ticket."* | *Account creation with 4-digit PIN* | *All 7 DRT fare categories with live prices* |

| Face Capture | Registration Complete |
|:---:|:---:|
| ![Face Capture](docs/screenshots/04-face-capture.jpeg) | ![Registration Complete](docs/screenshots/05-registration-complete.jpeg) |
| *Live webcam with green oval overlay + liveness challenge* | *U-Pass registered — free boarding confirmed* |

### Bus Terminal — `/terminal`

| Terminal Success |
|:---:|
| ![Terminal Success](docs/screenshots/06-terminal-success.jpeg) |
| *Full-screen success — $3.73 charged, passenger greeted by name* |

### Backend — Zero-Knowledge Biometrics

| Supabase — Embeddings | Stripe — Customers |
|:---:|:---:|
| ![Supabase](docs/screenshots/07-supabase-embeddings.jpeg) | ![Stripe](docs/screenshots/08-stripe-customers.jpeg) |
| *128-dim float vectors only — no images, no thumbnails, ever* | *Real Stripe customers and payment methods created during testing* |

<br/>

---

## ◈ Privacy — Zero-Knowledge Biometrics

> **Raw images never touch disk, database, or logs. Ever.**

```python
# This is the entire privacy model, in one function:

def embed(frames: list[bytes]) -> list[float]:
    embedding = generate_embedding(frames)   # ← 128 floats computed in RAM
    del frames                               # ← image buffers destroyed
    store_in_pgvector(embedding)             # ← only math reaches Supabase
    return embedding_id                      # ← caller never sees pixel data
```

A leaked database contains **128-dimensional float vectors**. You cannot reconstruct a face from them. You cannot even confirm whether a specific person's face is in the database without already having their face.

<br/>

---

## ◈ DRT Fare Structure

All fares reflect real **DRT 2025 PRESTO rates**, seeded into a `fare_rules` table. Stripe receives the exact `amount_cents` from the database — there is no hardcoded fare anywhere in the codebase.

| Category | Fare | Stripe charged? | Notes |
|---|---|---|---|
|  Adult PRESTO | **$3.73** | ✅ Yes | Default |
|  Senior (65+) | **$2.46** | ✅ Yes | 34% discount |
|  Youth (13–19) | **$3.35** | ✅ Yes | 10% discount |
|  Child (12 & under) | **$0.00** | ❌ No | Always free |
|  U-Pass (valid) | **$0.00** | ❌ No | Expiry checked every scan |
|  U-Pass (expired) | **$3.73** | ✅ Yes | Adult fallback + amber warning |
|  TAP (< 14 trips) | **$52.22** | ✅ Yes | Monthly cap |
|  TAP (≥ 14 trips) | **$0.00** | ❌ No | Unlimited travel active |
|  Armed Forces | **$0.00** | ❌ No | DRT fare-free policy |

<br/>

---

## ◈ Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| **Frontend** | React 18 + Vite | Single monorepo — `/register` + `/terminal` |
| **UI** | shadcn/ui + Tailwind | Components + dark design system |
| **Routing** | React Router v7 | Client-side — two routes, one deploy |
| **Backend** | FastAPI (Python 3.11) | CV pipeline, fare logic, Stripe, GTFS |
| **Face embeddings** | DeepFace / Facenet | 128-dimensional float vectors |
| **Reg. liveness** | MediaPipe Face Mesh | Blink (EAR < 0.2) + smile detection |
| **Terminal liveness** | OpenCV frame-delta | Motion score + texture analysis |
| **Database** | Supabase PostgreSQL | Auth, RLS, Realtime WebSockets |
| **Vector search** | pgvector IVFFlat | Cosine similarity — sub-10ms at scale |
| **Payments** | Stripe | SetupIntent + PaymentIntent off-session |
| **Transit data** | Durham Region GTFS | Route info, trip_id on every transaction |
| **Frontend deploy** | Vercel | HTTPS (required for webcam API) |
| **Backend deploy** | Railway | Auto-deploy from GitHub, `$PORT` injection |

<br/>

---

## ◈ Quick Start

### Prerequisites

```bash
brew install python@3.11 cmake node
xcode-select --install
```

### Backend

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
STRIPE_SECRET_KEY=sk_test_51...
GTFS_FEED_URL=https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip
TERMINAL_STOP_ID=1001
```

```bash
uvicorn main:app --reload --port 8000
# → http://localhost:8000/health  ✓  {"status": "ok"}
# → http://localhost:8000/docs    ✓  Swagger UI
```

### Database

Run [`backend/db/schema.sql`](backend/db/schema.sql) in the **Supabase SQL Editor**.

Creates: 5 tables · pgvector index · RLS policies · DRT fare seed data · `resolve_fare()` function · Realtime subscription.

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

```bash
npm run dev
# → http://localhost:5173/register   — passenger onboarding (phone)
# → http://localhost:5173/terminal   — kiosk (laptop, fullscreen)
```

**Test card:** `4242 4242 4242 4242` · any future expiry · any CVC

<br/>

---

## ◈ API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Create Supabase user + Stripe customer |
| `POST` | `/embed` | 5 base64 frames → 128-dim vector → pgvector |
| `POST` | `/identify` | Frame → cosine search → user + fare decision |
| `POST` | `/pay` | Stripe PaymentIntent with exact DRT fare |
| `POST` | `/pay/pin-confirm` | PIN fallback for 0.40–0.55 confidence range |
| `POST` | `/pay/setup-intent` | Create Stripe SetupIntent for card registration |
| `GET`  | `/gtfs/route-status` | Cached DRT route data (30s TTL, 5min stale) |
| `GET`  | `/health` | Always `{"status":"ok"}` — used by Railway |

<br/>

---

## ◈ Database Schema

```
profiles           face_embeddings       fare_rules
──────────────     ─────────────────     ──────────────────
id (UUID, PK) ──┐  id (UUID, PK)         fare_category (PK)
full_name         └─ user_id (FK)         amount_cents
stripe_customer    embedding VECTOR(128)  label
fare_category      created_at            requires_card
pass_expires_at                          requires_pass
institution
pin_hash           transactions           failed_scans
payment_failed_at  ────────────────────   ──────────────────
                   id (UUID, PK)          id (UUID, PK)
                   user_id (FK)           user_id (FK, null)
                   amount_cents           confidence
                   confidence             reason
                   stripe_pi_id           route_id
                   status                 created_at
                   resolved_fare_category
                   pass_was_expired
                   route_id  ◄── GTFS
                   trip_id   ◄── GTFS
                   stop_id   ◄── GTFS
```

<br/>

---

## ◈ Security Model

| Layer | Mechanism |
|---|---|
| **Biometrics** | Only 128-float vectors stored. Images destroyed in-memory after embedding. |
| **Database access** | `face_embeddings` has `USING (false)` RLS — no frontend query can ever reach it. |
| **Payments** | Raw card numbers never touch FacePay. PCI compliance fully delegated to Stripe. |
| **Identity confidence** | No charge fires below 0.40. 0.40–0.55 requires 4-digit PIN. |
| **Liveness** | Frame-delta motion analysis rejects printed photos and phone screens before any identity lookup. |
| **Keys** | `service_role` key lives in Railway env vars only. Frontend uses anon key scoped by RLS. |

<br/>

---

## ◈ Edge Cases — All Handled

| Scenario | What happens |
|---|---|
|  Photo spoofing | Frame-delta detects zero motion. Hard reject before identification. |
|  Identical twins | Confidence 0.40–0.55 → PIN fallback. No charge without it. |
|  U-Pass expired | Adult fare charged automatically. Amber warning on success screen. |
|  Stripe fails | Passenger boards anyway. Logged as `payment_failed`. Account flagged. Mirrors DRT low-balance policy. |
|  GTFS unreachable | Route panel hides gracefully. Payment flow completely unaffected. |
|  Child (free fare) | `amount_cents == 0` — Stripe never called. Transaction still logged. |
|  Two faces in frame | Largest bounding box (closest passenger) selected. |
|  Unknown face | Confidence < 0.40. Registration prompt + cash fallback shown. |

<br/>

---

## ◈ Project Structure

```
facepay/
│
├── backend/
│   ├── main.py                    FastAPI entry — CORS, router mount, /health
│   ├── requirements.txt
│   │
│   ├── routers/
│   │   ├── auth.py                POST /auth/register
│   │   ├── embed.py               POST /embed
│   │   ├── identify.py            POST /identify
│   │   ├── payments.py            POST /pay  +  POST /pay/pin-confirm
│   │   └── gtfs.py                GET /gtfs/route-status
│   │
│   ├── cv/
│   │   ├── embedder.py            DeepFace wrapper — 128-dim, in-memory only
│   │   └── liveness.py            Interactive (MediaPipe) + Passive (OpenCV)
│   │
│   └── db/
│       ├── supabase_client.py     Supabase singleton — service_role key
│       └── schema.sql             Full schema — run in Supabase SQL Editor
│
├── facepay-client/
│   └── src/
│       ├── App.jsx                /register + /terminal routes
│       ├── lib/supabase.js        Frontend client — anon key only
│       │
│       └── routes/
│           ├── register/
│           │   ├── Page.jsx           6-screen state machine
│           │   ├── WebcamCapture.jsx  Liveness challenge + 5-frame capture
│           │   └── PaymentSetup.jsx   Stripe SetupIntent + card save
│           │
│           └── terminal/
│               ├── Page.jsx           Fullscreen kiosk — 9 states, 2 loops
│               ├── Scanner.jsx        200ms camera loop + 5s cooldown
│               ├── PinFallback.jsx    4-digit PIN pad — 3 attempt max
│               └── SuccessScreen.jsx  Realtime-driven result screen
│
└── docs/
    ├── architecture.jpeg          System architecture diagram
    ├── boarding-flow.svg          Boarding flow diagram
    ├── screenshots/               App screenshots
    ├── App_flow.md                Every screen, state, and decision point
    ├── schema.md                  Tables, functions, RLS, Realtime
    ├── Tech_stack.md             Tools, env vars, known risks
    ├── frontend_design.md        Design tokens, CSS variables, animation
    ├── inplementation_plan.md    21-file build order, verify checklists
    └── prd.md                    Product requirements, personas, edge cases
```

<br/>

---

## ◈ Deployment

### Backend → Railway

```bash
# Start command:
uvicorn main:app --host 0.0.0.0 --port $PORT

# requirements.txt note:
# Use opencv-python-headless on Railway (no display server on Linux)
```

### Frontend → Vercel

```bash
# Vercel auto-detects Vite — zero config needed
# After deploy: copy exact Vercel URL into allow_origins in backend/main.py
# Webcam API requires HTTPS — Vercel provides this automatically
```

<br/>

---

## ◈ Hackathon Context

FacePay was designed and built in **~24 hours** at a Durham Region Transit hackathon in March 2026. The team finished **5th place**.

The system is production-architected — not demo-ware:
- Stripe test mode uses identical API paths to live mode. Swapping keys requires zero code changes.
- pgvector IVFFlat index is production-calibrated (`lists = 100`).
- RLS policies block frontend access to biometric data even if the anon key is leaked.
- Every boarding event is a complete transit record with `trip_id`, `route_id`, `stop_id`.

### v2 Roadmap *(out of scope for this build)*
- Institutional U-Pass verification via university enrollment API
- Real-time GTFS vehicle positions (live beyond static schedule)
- Multi-zone and time-of-day fare rules
- PRESTO card reconciliation
- Accessibility: audio cues + screen reader on terminal
- Fleet-wide terminal management dashboard

<br/>

---

<div align="center">

Built for **Durham Region Transit · Oshawa** · March 2026

*Srujan + Riddhi Patel + Mohammed Serour*

<br/>

```
  ██████╗ ██████╗ ████████╗    ██████╗ ███╗   ██╗
  ██╔══██╗██╔══██╗╚══██╔══╝   ██╔═══██╗████╗  ██║
  ██║  ██║██████╔╝   ██║      ██║   ██║██╔██╗ ██║
  ██║  ██║██╔══██╗   ██║      ██║   ██║██║╚██╗██║
  ██████╔╝██║  ██║   ██║      ╚██████╔╝██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝       ╚═════╝ ╚═╝  ╚═══╝
```

</div>
