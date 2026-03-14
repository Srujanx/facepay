# FacePay — Tech Stack Reference

Every tool, install command, environment variable, and known risk.
Read this before touching any code.

---

## Stack overview

| Layer | Tool | Version | Purpose |
|-------|------|---------|---------|
| Frontend | React + Vite | React 18 / Vite 5 | Single monorepo — /register and /terminal |
| UI Components | shadcn/ui | Latest | Production-grade components |
| Routing | React Router v6 | v6 | Client-side routing |
| Backend | FastAPI | 0.110+ | Python API — CV, fare lookup, Stripe, GTFS |
| CV Embeddings | face_recognition | 1.3.0 | 128-dim embeddings via dlib |
| CV Landmarks | MediaPipe | 0.10+ | Blink/smile for registration liveness |
| CV Frame | OpenCV (cv2) | 4.9+ | Face detection, frame analysis, passive liveness |
| Database | Supabase | Cloud | PostgreSQL + pgvector + Auth + Realtime |
| Vector Search | pgvector | 0.7+ | IVFFlat cosine similarity index |
| Payments | Stripe | Test mode | SetupIntent + PaymentIntent |
| Frontend Deploy | Vercel | Cloud | Hosts React monorepo — provides HTTPS for webcam |
| Backend Deploy | Railway | Cloud | Hosts FastAPI — GitHub auto-deploy |
| GTFS Data | Durham Region Open Data | Static feed | DRT route info + trip_id |
| API Testing | Bruno | Latest | Test endpoints before UI exists |

---

## Backend — Python / FastAPI

### Python 3.11 (required)

> Do not use 3.12. dlib has known install issues on 3.12+.
> Do not use the system Python that ships with macOS.

```bash
brew install python@3.11
python3.11 -m venv venv
source venv/bin/activate       # run every time you open a new terminal
which python                   # must show .../venv/bin/python
```

### FastAPI

```bash
pip install fastapi[all]       # FastAPI + Uvicorn + all extras
pip install python-dotenv      # reads .env into environment variables
uvicorn main:app --reload --port 8000
```

**File structure:**
```
backend/
├── main.py                    # CORS config, router registration, /health
├── routers/
│   ├── auth.py                POST /auth/register
│   ├── embed.py               POST /embed
│   ├── identify.py            POST /identify
│   ├── payments.py            POST /pay, POST /pay/pin-confirm
│   └── gtfs.py                GET /gtfs/route-status
├── cv/
│   ├── embedder.py            face_recognition wrapper
│   └── liveness.py            two-mode liveness
└── db/
    ├── supabase_client.py     Supabase singleton (service_role key)
    └── schema.sql             Run in Supabase SQL Editor
```

---

## Computer vision

### face_recognition (core embedding engine)

> dlib compiles from source. Install in this exact order or it will fail.

```bash
xcode-select --install          # accept the popup, wait for it to finish
brew install cmake              # MUST come before pip install dlib
pip install dlib                # takes 10-15 minutes — this is normal, do not close terminal
pip install face_recognition    # fast once dlib is compiled
pip install numpy
```

**Usage:**
```python
import face_recognition

image = face_recognition.load_image_file('frame.jpg')
locations = face_recognition.face_locations(image)
encoding = face_recognition.face_encodings(image, locations)[0]
# encoding is a numpy array of 128 floats — store in pgvector
```

**If dlib install fails:**
- `pip install dlib --verbose` to see the actual error
- "cmake not found" → confirm `brew install cmake` ran and terminal was restarted
- "No module named _dlib_pybindings" → compile succeeded but wrong Python — confirm venv is active
- Nuclear option: `pip install deepface` — drop-in alternative, no compilation needed

### OpenCV (face detection + passive liveness)

```bash
pip install opencv-python       # local dev
# Note: use opencv-python-headless on Railway (no display server on Linux)
```

**Passive liveness frame-delta:**
```python
import cv2

diff1 = cv2.absdiff(frame1, frame2)
diff2 = cv2.absdiff(frame2, frame3)
motion_score = cv2.countNonZero(cv2.bitwise_and(diff1, diff2))
is_live = motion_score > MOTION_THRESHOLD  # tune during testing, start at 500
```

**Face detection:**
```python
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
# faces is a list of (x, y, w, h) bounding boxes
```

### MediaPipe (landmark detection — registration only)

```bash
pip install mediapipe
```

```python
import mediapipe as mp

face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False)
results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
# landmarks[145] and [159] are upper/lower eye points
# EAR (eye aspect ratio) < 0.2 = blink confirmed
```

---

## Database — Supabase + pgvector

### Setup steps
1. supabase.com → sign in with GitHub
2. New Project → name: facepay → region: **Canada (East)** (lowest latency from Oshawa)
3. Set a strong database password — write it down, you will not see it again
4. Wait ~2 minutes for project to spin up
5. Settings → API → copy Project URL, anon key, service_role key, JWT secret
6. SQL Editor → paste `db/schema.sql` → Run
7. Table Editor → confirm 5 tables: profiles, face_embeddings, fare_rules, transactions, failed_scans
8. Click fare_rules → confirm 7 rows with DRT fares
9. Database → Replication → confirm transactions is in supabase_realtime publication

### Supabase keys

| Key | Where it lives | What it can do |
|-----|---------------|---------------|
| anon (public) key | Frontend .env + Railway .env | Auth, read fare_rules, read own data. Cannot touch face_embeddings. |
| service_role key | **Railway .env ONLY** | Bypasses RLS. Reads/writes any table including face_embeddings. Never in frontend. |
| JWT secret | Railway .env | Verifies tokens from frontend |
| Database password | Nowhere in code | Only for direct psql connection |

### pgvector cosine similarity query

```sql
SELECT user_id, 1 - (embedding <=> $1::vector) AS confidence
FROM face_embeddings
ORDER BY confidence DESC
LIMIT 1;
```

`<=>` is cosine distance. Subtract from 1 for similarity (1.0 = identical, 0.0 = different).
IVFFlat index makes this sub-10ms.

### Supabase Realtime subscription (terminal)

```js
const channel = supabase
  .channel('terminal-boarding')
  .on('postgres_changes',
    { event: 'INSERT', schema: 'public', table: 'transactions' },
    (payload) => handleBoardingResult(payload.new)
  )
  .subscribe()
```

---

## Payments — Stripe

### Setup
1. stripe.com → create free account (no bank account needed)
2. Confirm toggle says **Test mode** — not Live
3. Developers → API Keys → copy publishable key (`pk_test_...`) and secret key (`sk_test_...`)

### Two flows

| Flow | Stripe object | When | What |
|------|--------------|------|------|
| Save card at registration | SetupIntent | Once per user, Screen 5 | Tokenises card, attaches to Customer. No money moves. |
| Charge fare at boarding | PaymentIntent | Every boarding where amount > 0 | Charges saved card off-session. Amount from fare_rules, never hardcoded. |

```bash
pip install stripe                                          # backend
npm install @stripe/stripe-js @stripe/react-stripe-js      # frontend
```

### Test cards

| Number | Result | Use for |
|--------|--------|---------|
| 4242 4242 4242 4242 | Always succeeds | Main demo |
| 4000 0000 0000 0002 | Always declines | Testing State 7 payment failed |
| 4000 0025 0000 3155 | Requires 3D Secure | Optional — showing auth challenge |

*Any future expiry, any CVC, any postcode.*

---

## Frontend — React + Vite

### Scaffold

```bash
npm create vite@latest facepay-client -- --template react
cd facepay-client && npm install
npm install react-router-dom @supabase/supabase-js react-webcam
npm install @stripe/stripe-js @stripe/react-stripe-js
npx shadcn@latest init
npx shadcn@latest add button card input label select dialog badge progress
```

### Route structure

```jsx
// src/App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import RegisterPage from './routes/register/Page'
import TerminalPage from './routes/terminal/Page'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path='/register' element={<RegisterPage />} />
        <Route path='/terminal' element={<TerminalPage />} />
      </Routes>
    </BrowserRouter>
  )
}
```

### Why HTTPS matters
Browsers only allow webcam access on `localhost` or HTTPS. Vercel provides HTTPS automatically.
The webcam will NOT work on plain HTTP deployments.

### Camera permission reset
If webcam stops working: Chrome → address bar camera icon → Reset permissions.
Or: `chrome://settings/content/camera`

---

## Deployment

### Vercel (frontend)

```bash
# Push facepay-client to GitHub
# vercel.com → Add New Project → select facepay-client
# Vercel auto-detects Vite — no config needed
# Add environment variables (see below)
# Deploy — copy the generated URL
# Update CORS allow_origins in backend main.py with this exact URL
```

> Vercel generates a URL like `facepay-client-xyz123.vercel.app`.
> Copy it exactly including any suffix. This URL goes in backend CORS config.

### Railway (backend)

```bash
# Push backend folder to GitHub
# railway.app → New Project → Deploy from GitHub → select backend
# Set start command: uvicorn main:app --host 0.0.0.0 --port $PORT
# Add all environment variables (see below)
# Railway generates a URL like facepay-api.up.railway.app
# Update VITE_API_URL in Vercel with this Railway URL
```

### requirements.txt (Railway reads this automatically)

```
fastapi[all]
python-dotenv
face_recognition
opencv-python-headless
mediapipe
numpy
stripe
supabase
gtfs-realtime-bindings
requests
```

> Use `opencv-python-headless` on Railway — excludes GUI dependencies that fail on Linux servers.

---

## Environment variables

### Backend — backend/.env (Railway Variables tab)

```env
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_JWT_SECRET=your-jwt-secret
STRIPE_SECRET_KEY=sk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=http://localhost:5173
GTFS_FEED_URL=https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip
TERMINAL_ROUTE_ID=110
TERMINAL_STOP_ID=1001
```

### Frontend — facepay-client/.env.local (Vercel Environment Variables)

> Vite only exposes variables prefixed with `VITE_` to the browser.
> Never put secret keys here — they are visible in the browser.

```env
VITE_SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
VITE_STRIPE_PK=pk_test_51...
VITE_API_URL=http://localhost:8000
```

---

## Installation risks

| Tool | Risk | Fix | Level |
|------|------|-----|-------|
| dlib / face_recognition | Compilation fails — cmake not found | `xcode-select --install` first, then `brew install cmake`, then activate venv, then `pip install dlib` | HIGH |
| dlib / face_recognition | Takes 10-15 min — looks frozen | It is not frozen. dlib compiles ~30k lines of C++. Leave it running. | LOW |
| OpenCV | ImportError on Railway Linux | Use `opencv-python-headless` in requirements.txt | MED |
| Webcam | Camera permission denied | Chrome → camera icon in address bar → Reset permissions | MED |
| Supabase Realtime | Terminal success screen doesn't update | Database → Replication → confirm transactions is in supabase_realtime publication | MED |
| Supabase cold start | First request after inactivity takes 3-4s | Add keep-alive: frontend calls `GET /health` every 4 minutes | MED |
| CORS | Frontend blocked after Vercel deploy | Copy exact Vercel URL into `allow_origins` in main.py and redeploy Railway | HIGH |
| Railway | uvicorn command not found | Add Procfile: `web: uvicorn main:app --host 0.0.0.0 --port $PORT` | MED |
| Python version | face_recognition fails on 3.12 | Use Python 3.11 specifically. Check: `python --version` inside venv | HIGH |
| MediaPipe | No module on M1/M2 Mac | `pip install mediapipe` (now ships Apple Silicon wheels). If fails: `pip install mediapipe-silicon` | MED |