# FacePay — Implementation Plan

Build order, step-by-step instructions, verify checklists.
Do not move to the next step until the current one passes its verification.

---

## Rules

| Rule | Why |
|------|-----|
| Backend before frontend | The frontend calls the backend — cannot test one without the other |
| Verify each step before the next | A bug in Step 3 takes 5 minutes. The same bug found in Step 12 takes an hour. |
| Test with Bruno before building UI | Confirm every API endpoint works before wiring a React component to it |
| Never skip the schema step | A missing column at demo time cannot be fixed without data loss |
| Commit after each phase | If Phase 4 breaks, you can roll back to Phase 3 |
| GTFS is last | GTFS is optional display data. Never block the payment loop for it. |

---

## File creation order (21 files, dependency sorted)

| # | File | What it is |
|---|------|------------|
| 1 | backend/main.py | FastAPI app entry point |
| 2 | backend/.env | Secret keys — never committed |
| 3 | backend/requirements.txt | Python dependencies |
| 4 | backend/db/supabase_client.py | Supabase connection singleton |
| 5 | backend/db/schema.sql | Run in Supabase SQL Editor |
| 6 | backend/cv/embedder.py | face_recognition wrapper |
| 7 | backend/cv/liveness.py | Two-mode liveness detection |
| 8 | backend/routers/auth.py | POST /auth/register |
| 9 | backend/routers/embed.py | POST /embed |
| 10 | backend/routers/identify.py | POST /identify |
| 11 | backend/routers/payments.py | POST /pay + POST /pay/pin-confirm |
| 12 | backend/routers/gtfs.py | GET /gtfs/route-status |
| 13 | facepay-client/src/lib/supabase.js | Frontend Supabase client |
| 14 | facepay-client/src/App.jsx | Router — /register and /terminal |
| 15 | facepay-client/src/routes/register/Page.jsx | Registration flow orchestrator |
| 16 | facepay-client/src/routes/register/WebcamCapture.jsx | Webcam + liveness challenge |
| 17 | facepay-client/src/routes/register/PaymentSetup.jsx | Stripe SetupIntent + card save |
| 18 | facepay-client/src/routes/terminal/Page.jsx | Terminal orchestrator + GTFS |
| 19 | facepay-client/src/routes/terminal/Scanner.jsx | Always-on camera + detection loop |
| 20 | facepay-client/src/routes/terminal/PinFallback.jsx | PIN entry screen |
| 21 | facepay-client/src/routes/terminal/SuccessScreen.jsx | Realtime-driven result screen |

---

## Pre-build setup (45–60 min)

### Step 1 — System dependencies

```bash
brew --version               # if this errors, install Homebrew from brew.sh first
brew install python@3.11 cmake node
xcode-select --install       # accept the popup, wait for it to finish

python3.11 --version         # must show 3.11.x
node --version               # must show v18+
cmake --version              # must show 3.x
```

**Verify:** All three version commands return numbers. Xcode popup completed.

---

### Step 2 — GitHub repo + folder structure

```bash
git clone https://github.com/YOUR_USERNAME/facepay.git
cd facepay
mkdir -p backend/routers backend/cv backend/db
mkdir -p facepay-client
```

Add to `backend/.gitignore` and `facepay-client/.gitignore`:
```
.env
.env.local
venv/
node_modules/
```

**Verify:** Both folders exist. Neither `.env` file appears in `git status`.

---

### Step 3 — Supabase project

1. supabase.com → sign in with GitHub → New Project → name: facepay
2. Region: **Canada (East)**
3. Write down the database password
4. Wait 2 minutes for spin-up
5. Settings → API → copy Project URL, anon key, service_role key, JWT secret
6. SQL Editor → paste full `db/schema.sql` → Run
7. Table Editor → confirm 5 tables exist
8. Click `fare_rules` → confirm 7 rows with DRT fares
9. Database → Replication → confirm `transactions` is in `supabase_realtime`

**Verify:**
- [ ] 5 tables visible in Table Editor
- [ ] fare_rules has 7 rows (adult $3.73, senior $2.46, youth $3.35, child $0, u_pass $0, tap $52.22, armed_forces $0)
- [ ] transactions table is in supabase_realtime publication
- [ ] All 4 key values saved

---

### Step 4 — Stripe account

1. stripe.com → create free account
2. Confirm top-right toggle shows **Test mode**
3. Developers → API Keys → copy publishable key (`pk_test_...`) and secret key (`sk_test_...`)

> ⚠️ If toggle shows Live mode, switch to Test immediately. Live mode charges real cards.

**Verify:** Stripe dashboard is in Test mode. Both keys copied.

---

### Step 5 — .env files

`backend/.env`:
```env
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_JWT_SECRET=your-jwt-secret
STRIPE_SECRET_KEY=sk_test_51...
FRONTEND_URL=http://localhost:5173
GTFS_FEED_URL=https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip
TERMINAL_ROUTE_ID=110
TERMINAL_STOP_ID=1001
```

`facepay-client/.env.local`:
```env
VITE_SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
VITE_STRIPE_PK=pk_test_51...
VITE_API_URL=http://localhost:8000
```

**Verify:** Both files exist with all variables filled in. `git status` shows neither file.

---

## Phase 1 — Backend core (~2 hrs · Day 1 morning)

### Step 6 — Python venv + dependencies

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install dlib                # 10-15 minutes — do not close terminal
pip install face_recognition opencv-python mediapipe fastapi[all] python-dotenv stripe supabase numpy requests
pip freeze > requirements.txt
```

> ⚠️ If dlib fails: confirm `cmake --version` works, confirm `which python` shows `.../venv/bin/python`, and that `xcode-select --install` completed.

**Verify:**
- [ ] `python -c "import face_recognition"` — no error
- [ ] `python -c "import cv2"` — no error
- [ ] `python -c "import mediapipe"` — no error
- [ ] `requirements.txt` exists

---

### Step 7 — main.py

CORS config, router registration, `/health` endpoint.

Key rules:
- `allow_origins` must include `http://localhost:5173` and your eventual Vercel URL (add in Phase 5)
- Comment out router imports until their files exist
- `/health` must always return instantly

```bash
uvicorn main:app --reload --port 8000
```

**Verify:**
- [ ] `http://localhost:8000/health` returns `{"status": "ok", "service": "facepay-api"}`
- [ ] `http://localhost:8000/docs` shows Swagger UI
- [ ] No import errors in terminal

---

### Step 8 — db/supabase_client.py

Supabase singleton using `SUPABASE_SERVICE_KEY` (service_role, not anon).
All routers import this one instance.

```bash
python -c "from db.supabase_client import supabase; print(supabase)"
```

**Verify:** Import succeeds. Printed output shows a Supabase client object.

---

### Step 9 — cv/embedder.py

Two functions:
- `generate_embedding(frames: list[bytes]) -> list[float]` — 5 frames → averaged 128-dim vector. Returns None if no face detected.
- `extract_embedding_from_frame(frame: bytes) -> list[float]` — single frame version for terminal.

Key: never write images to disk. All buffer operations in memory.

**Verify:**
- [ ] Import succeeds
- [ ] With a test image: returns exactly 128 floats
- [ ] With no-face image: returns None, no exception

---

### Step 10 — cv/liveness.py

Two completely separate modes:

**Interactive (registration):**
- `detect_blink(frame)` — MediaPipe EAR < 0.2
- `detect_smile(frame)` — lip corner upward movement
- 10-second timeout per challenge

**Passive (terminal):**
- `check_passive_liveness(frames)` — frame-delta motion score + texture analysis
- Returns True if real face, False if spoofing attempt
- Start MOTION_THRESHOLD at 500, tune during testing

> ⚠️ MOTION_THRESHOLD needs tuning. Test with your face, then test holding a photo to the camera. Must reject the photo.

**Verify:**
- [ ] `check_passive_liveness` returns True for live webcam
- [ ] `check_passive_liveness` returns False when static image shown to camera
- [ ] `detect_blink` returns True on deliberate blink

---

### Step 11 — routers/auth.py + routers/embed.py

**auth.py** — `POST /auth/register`:
- Receives: email, password, full_name, fare_category, pass_expires_at, institution
- Creates Stripe customer
- Inserts profiles row with stripe_customer_id

**embed.py** — `POST /embed`:
- Receives: 5 base64 JPEG frames + user_id
- Calls `embedder.generate_embedding()`
- Stores vector in face_embeddings
- Returns embedding_id
- Zero image data reaches the database

Uncomment router imports in main.py.

```bash
# Test with Bruno:
POST http://localhost:8000/auth/register
{"email":"test@test.com","password":"testpass123","full_name":"Test User","fare_category":"adult"}
```

**Verify:**
- [ ] POST /auth/register returns user_id and stripe_customer_id
- [ ] New row visible in Supabase → profiles
- [ ] New customer in Stripe Dashboard → Customers
- [ ] POST /embed returns embedding_id
- [ ] New row in Supabase → face_embeddings with 128-element vector

---

### Step 12 — routers/identify.py + routers/payments.py

**identify.py** — `POST /identify`:
- Receives: single frame + route_id
- Runs passive liveness
- Generates embedding
- pgvector cosine search
- Calls `SELECT resolve_fare($user_id)` DB function
- Returns: user_id, full_name, confidence, fare_category, amount_cents, pass_expired, trip_id

**payments.py** — `POST /pay`:
- If amount_cents == 0: skip Stripe, log transaction
- If amount_cents > 0: `stripe.PaymentIntent.create(amount, currency='cad', customer, confirm=True, off_session=True)`
- Log to transactions with route_id, trip_id, stop_id
- Supabase Realtime fires automatically on INSERT

**Verify:**
- [ ] POST /identify returns confidence > 0.98 for registered face
- [ ] POST /identify returns confidence < 0.90 for unknown face
- [ ] POST /pay creates PaymentIntent in Stripe Dashboard
- [ ] Transaction row appears in Supabase → transactions
- [ ] POST /pay with amount_cents=0 skips Stripe but still logs transaction

---

## Phase 2 — Registration frontend (~2 hrs · Day 1 mid-morning)

### Step 13 — Scaffold React monorepo

```bash
npm create vite@latest facepay-client -- --template react
cd facepay-client && npm install
npm install react-router-dom @supabase/supabase-js react-webcam
npm install @stripe/stripe-js @stripe/react-stripe-js
npx shadcn@latest init
npx shadcn@latest add button card input label select dialog badge progress
npm run dev
```

**Verify:** `http://localhost:5173` loads without errors.

---

### Step 14 — supabase.js + App.jsx

`src/lib/supabase.js` — Supabase client using anon key (NOT service_role).
`src/App.jsx` — BrowserRouter with /register and /terminal routes.

**Verify:**
- [ ] Both routes render without errors
- [ ] No console errors about missing env vars

---

### Step 15 — routes/register/Page.jsx

6-screen state machine: welcome → create-account → fare-category → face-capture → add-payment → complete.

Skip payment logic:
```js
const skipPayment = ['child', 'armed_forces'].includes(fareCategory)
  || (fareCategory === 'u_pass' && passExpiresAt > today)
```

Screen 3 (fare category): U-Pass reveals institution dropdown + date picker via `max-height` + `opacity` transition.

**Verify:**
- [ ] All 6 screens render
- [ ] Selecting U-Pass shows conditional fields
- [ ] Selecting Child skips to Screen 6
- [ ] Form validation blocks progression on empty fields

---

### Step 16 — routes/register/WebcamCapture.jsx

Handles Screen 4: webcam → blink challenge → smile challenge → 5 frames → POST /embed.

Sequence:
1. `getUserMedia({ video: true })` — requires HTTPS
2. Detect face in oval
3. Blink challenge (10s timeout)
4. Smile challenge (10s timeout)
5. Capture 5 frames → POST /embed

> ⚠️ Decide: client-side MediaPipe WASM for liveness detection, or add dedicated backend endpoints. Client-side is faster to demo.

**Verify:**
- [ ] Webcam feed appears
- [ ] Blink detected with visual confirmation
- [ ] Smile detected
- [ ] POST /embed called and returns embedding_id

---

### Step 17 — routes/register/PaymentSetup.jsx

Screen 5 (skipped for free categories). Stripe Elements card input.

Stripe appearance config:
```js
const appearance = {
  theme: 'night',
  variables: { colorPrimary: '#00FF94', colorBackground: '#0F1B2D' }
}
const elements = stripe.elements({ appearance, clientSecret })
```

Test card: `4242 4242 4242 4242` · expiry: `12/29` · CVC: `123`

**Verify:**
- [ ] Stripe Elements renders
- [ ] Test card saves successfully
- [ ] Payment method visible in Stripe Dashboard → Customers
- [ ] User advances to Screen 6

---

## Phase 3 — Bus terminal frontend (~2 hrs · Day 1 afternoon)

### Step 18 — routes/terminal/Page.jsx

Fullscreen kiosk. Manages terminalState: idle → face_detected → liveness_check → identifying → charging / pin_required / rejected → success / payment_failed.

Two loops on mount:
- Camera loop: `setInterval` every 200ms → calls Scanner
- GTFS loop: `setInterval` every 30s → `GET /gtfs/route-status`

Supabase Realtime subscription on mount:
```js
supabase.channel('terminal-boarding')
  .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'transactions' },
    (payload) => handleResult(payload.new))
  .subscribe()
```

Fullscreen: `document.documentElement.requestFullscreen()` on mount.

**Verify:**
- [ ] Renders fullscreen, no browser UI visible
- [ ] GTFS panel shows Route 110 data (or hides gracefully)
- [ ] Supabase WebSocket connection visible in Network tab

---

### Step 19 — routes/terminal/Scanner.jsx

Hidden camera. Frame loop. Auto-detection.

```
Capture frame every 200ms
→ OpenCV face detection
→ If face: buffer 3 frames → POST /identify
→ On response: emit to parent via callback
→ 5-second cooldown after any scan attempt
```

Two faces: select largest bounding box (closest passenger).

> ⚠️ Add 5-second cooldown. Without it, multiple POST /identify calls fire on the same face while the success screen shows. This creates duplicate charges.

**Verify:**
- [ ] Camera activates silently on load
- [ ] POST /identify fires when face enters frame
- [ ] Confidence > 0.98 → charging state
- [ ] Confidence 0.90–0.98 → PIN state
- [ ] Confidence < 0.90 → rejected state
- [ ] 5-second cooldown prevents duplicate calls

---

### Step 20 — routes/terminal/PinFallback.jsx

4-digit PIN pad. Auto-submits on 4th digit. No passenger name shown until confirmed.

Attempt logic:
- Attempts 1–2: shake animation, clear digits, "Incorrect PIN — try again"
- Attempt 3: "Too many attempts. Please board with cash." → idle after 8s

**Verify:**
- [ ] Auto-submits on 4th digit
- [ ] Wrong PIN shakes and clears
- [ ] 3rd wrong attempt returns to idle after 8s
- [ ] Correct PIN proceeds to charge

---

### Step 21 — routes/terminal/SuccessScreen.jsx

Driven by Supabase Realtime payload. Three variants:

- `success`: green full-screen, passenger first name, fare, route, "Welcome aboard". Auto-resets 4s.
- `payment_failed`: amber screen, driver instruction. Auto-resets 5s.
- `rejected`: amber screen, no name, "Face not recognised." Auto-resets 5s.

U-Pass expired variant: amber warning band "$3.73 charged · U-Pass expired — please renew."

**Verify:**
- [ ] Walking in front of camera triggers full flow end-to-end
- [ ] Success shows correct name and fare
- [ ] Screen auto-resets after 4s
- [ ] U-Pass expired shows amber warning
- [ ] Payment failed shows amber screen with driver instruction

---

## Phase 4 — GTFS integration (~1 hr · Day 2 morning)

### Step 22 — routers/gtfs.py

`GET /gtfs/route-status` — fetch, cache 30s, return JSON.

DRT feed: `https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip`
Parse `routes.txt`, `trips.txt`, `stop_times.txt` in memory (Python zipfile module, never write to disk).

Response shape:
```json
{
  "route_number": "110",
  "headsign": "Towards Oshawa GO",
  "delay_seconds": 0,
  "next_departure": "14:32",
  "alerts": [],
  "current_trip_id": "DRT_110_20260314_1432"
}
```

Cache strategy: < 30s → return cached. Fetch fails → return stale with flag. Cache > 5 min → return empty (frontend hides panel).

**Verify:**
- [ ] Returns valid JSON with route_number and current_trip_id
- [ ] Second call within 30s returns cached data
- [ ] Feed timeout returns cached data, not error
- [ ] Terminal idle shows route panel

---

### Step 23 — Wire trip_id into transactions

In `payments.py`, before the Stripe charge:
```python
trip_data = await get_cached_gtfs(route_id=settings.TERMINAL_ROUTE_ID)
trip_id   = trip_data.get('current_trip_id', None)
stop_id   = settings.TERMINAL_STOP_ID
```

Add to transaction INSERT.

**Verify:**
- [ ] Transaction rows in Supabase have non-null trip_id, route_id, stop_id

---

## Phase 5 — Polish + deploy (~1 hr · Day 2 morning)

### Step 24 — RLS verification

Run in Supabase SQL Editor:
```sql
-- Must return 0 rows (anon key cannot see embeddings)
SELECT * FROM face_embeddings LIMIT 1;

-- Must return 7 rows (public read)
SELECT * FROM fare_rules;

-- Confirm RLS enabled
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
```

**Verify:** face_embeddings returns 0 rows. All 5 tables show `rowsecurity = true`.

---

### Step 25 — Deploy backend to Railway

1. Push backend to GitHub
2. railway.app → New Project → Deploy from GitHub
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add all 9 backend env vars
5. Copy Railway URL

> ⚠️ If Railway fails with "No module named dlib": add `Procfile` with `web: uvicorn main:app --host 0.0.0.0 --port $PORT`. Ensure requirements.txt uses `opencv-python-headless`.

**Verify:** `https://your-railway-url.up.railway.app/health` returns `{"status": "ok"}`

---

### Step 26 — Deploy frontend to Vercel

1. Push facepay-client to GitHub
2. vercel.com → Add New Project → select facepay-client
3. Add 4 env vars. Set `VITE_API_URL` to Railway URL.
4. Deploy → copy exact Vercel URL
5. Update `allow_origins` in backend main.py with exact Vercel URL
6. Commit + push → Railway auto-redeploys

> The Vercel URL must be exact — including any random suffix like `-abc123`. Copy it precisely.

**Verify:**
- [ ] /register loads without errors
- [ ] /terminal loads without errors
- [ ] No CORS errors in browser console
- [ ] Webcam permission prompt appears on /register

---

### Step 27 — Two-device end-to-end test

Device 1 (laptop): open `/terminal` → press F11 for fullscreen.
Device 2 (phone or second laptop): open `/register` → complete Adult registration + card `4242 4242 4242 4242`.

Walk in front of Device 1 camera.

**Verify:**
- [ ] Terminal detects face within 3 seconds
- [ ] $3.73 charged for Adult
- [ ] Success screen shows correct passenger name
- [ ] Stripe Dashboard shows new PaymentIntent
- [ ] Supabase transaction row has confidence, route_id, trip_id, stop_id
- [ ] Screen auto-resets to idle after 4 seconds

---

## Demo prep (Day 2 afternoon — no new features after this)

### Hardware checklist

- [ ] Laptop battery > 80% or charger available
- [ ] Both devices on same WiFi
- [ ] Laptop camera permission allowed in Chrome (`chrome://settings/content/camera`)
- [ ] Phone camera permission allowed in Chrome
- [ ] `/terminal` loads fullscreen with F11
- [ ] GTFS panel shows Route 110 data
- [ ] Stripe Dashboard open in separate tab
- [ ] Supabase Table Editor open in separate tab

---

### Judge Q&A

| Question | Answer |
|----------|--------|
| What if the database is hacked? | Only 128-dimensional float vectors are stored. No images. A leaked database cannot be reverse-engineered into a photograph. |
| What about twins? | Confidence 90–98% triggers a 4-digit PIN set at registration. No charge fires without it. |
| What if someone holds up a photo? | Passive liveness detects zero micro-movement in a printed photo. Hard reject before any identity lookup. |
| How are fares determined? | From a fare_rules table seeded with real DRT 2025 PRESTO prices. Stripe receives the exact amount — never hardcoded. |
| What about U-Pass students? | pass_expires_at checked on every scan. If expired, adult fare charged automatically. No manual intervention. |
| Is real money charged? | Stripe test mode — all behaviour identical to production, zero real money moves. Swap test keys for live keys. Zero code changes. |
| How would this work in production? | DRT creates a Stripe merchant account. Swap test API keys for live keys. U-Pass verification would be an API integration with Durham College and Ontario Tech enrollment systems. |
| Why face recognition over a phone app? | Phones can be forgotten, lost, or dead. A face cannot. Reduces boarding friction and dwell time — DRT's documented operational priority. |