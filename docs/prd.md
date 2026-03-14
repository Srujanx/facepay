# FacePay — Product Requirements Document

Durham Region Transit · Oshawa · Hackathon Build v1.0 · March 2026

---

## 1. Problem

Current DRT boarding requires a PRESTO card, loaded transit pass, or exact cash. Friction at the point of boarding slows dwell times and excludes riders who forget or lose their payment method. U-Pass holders must also carry a separate student card.

**FacePay eliminates this. The passenger's face is the ticket.**

---

## 2. Goals

### Primary
- Board a registered passenger in under 3 seconds from face detection to payment confirmation
- Charge the correct DRT fare based on registered fare category — never a hardcoded amount
- Detect and reject spoofing attempts before any identification attempt
- Handle U-Pass expiry automatically — no manual override required

### Demo success metrics
- Face identified with >98% confidence in normal indoor lighting
- Correct fare charged from DRT fare table
- GTFS route information visible on terminal idle screen
- U-Pass expiry scenario demonstrated live
- Transaction audit log shows trip_id, route_id, stop_id

---

## 3. User personas

**Adult commuter** — Boards Route 110 from Oshawa GO daily. Charged $3.73 PRESTO adult fare automatically.

**Ontario Tech U-Pass student** — Rides free while enrolled. On semester expiry, automatically charged adult fare with a screen warning.

**DRT senior** — 65+, charged $2.46 automatically. No senior ID card required after registration.

**Child passenger** — 12 and under, fare_category = child, always $0. Stripe never called. No payment method required at registration.

---

## 4. System architecture

### Component overview

```
Registration App (/register)     Bus Terminal (/terminal)
Phone or second laptop           Laptop, fullscreen kiosk
Webcam, liveness challenge       Always-on camera
Fare category select             Passive liveness
Stripe card save                 Face identify + charge
        │                               │
        └──────────┬────────────────────┘
                   │
          FastAPI Backend (Railway)
          Single Python service
          CV logic, fare lookup, GTFS caching, Stripe
                   │
          Supabase (PostgreSQL + pgvector)
          Embeddings, profiles, fare rules, transactions
          Realtime drives terminal success screen
```

### Critical design decisions

**Zero-knowledge biometrics** — Raw images are never written to disk or stored. FastAPI receives frames, generates the 128-dim embedding in memory, and immediately discards the image buffer. Only the float vector reaches Supabase. A leaked database cannot be reverse-engineered into a photograph.

**Monorepo, one Vercel deploy** — `/register` and `/terminal` are two routes inside one Vite + React app. One deployment, one URL, two routes. Two physical devices load the same URL at different paths.

**Two-mode liveness detection** — Registration uses interactive challenges (blink, smile) because the user is cooperative and stationary. The terminal uses passive liveness only (frame-delta motion + texture analysis) because no prompt is possible mid-boarding.

**GTFS as display layer only** — Route status and vehicle positions appear on the terminal screen. The payment flow has zero dependency on GTFS. If the feed is unreachable, the panel hides — fare collection is unaffected.

---

## 5. GTFS integrations

### Integration 1 — Dynamic fare table (Option A: GTFS-inspired)
We do not parse Durham Region's raw GTFS fare files at runtime. Instead we seed a `fare_rules` table in Supabase with real DRT PRESTO fares mirroring the GTFS Fares v2 structure. After face identification the backend queries `fare_rules` with `fare_category`. The exact `amount_cents` is passed directly to Stripe.

### Integration 2 — GTFS Realtime route display
The terminal idle screen shows live DRT route information from Durham Region's GTFS static schedule feed.
- Feed URL: `https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip`
- Transitland ID: `f-dpz-durhamregiontransit`
- Backend endpoint: `GET /gtfs/route-status` — fetches, caches 30s, returns route number, headsign, delay, alerts
- Terminal polls every 30 seconds

### Integration 3 — GTFS trip_id on transactions
Every GTFS trip has a unique `trip_id`. When a payment fires, the active `trip_id` for the terminal's route is fetched and stored alongside the transaction. The `transactions` table also stores `route_id` and `stop_id`. This turns a payment log into a complete transit record.

---

## 6. DRT fare structure

Source: durhamregiontransit.com — 2025 PRESTO rates. Seeded into `fare_rules` table.

| Category | Amount | Notes |
|----------|--------|-------|
| Adult (PRESTO) | $3.73 | Full fare |
| Senior 65+ | $2.46 | 34% discount |
| Youth 13–19 | $3.35 | 10% discount |
| Child 12 and under | $0.00 | Always free — Stripe never called |
| U-Pass (valid) | $0.00 | Durham College, Ontario Tech, Trent Durham GTA. Free while `pass_expires_at > today` |
| U-Pass (expired) | $3.73 | Falls back to adult fare automatically. Amber warning on terminal. |
| TAP (Transit Assistance) | $52.22/mo | OW/ODSP. Unlimited after 14 paid trips. Trip counter in DB. |
| Canadian Armed Forces | $0.00 | DRT fare-free policy. Self-declared at registration. |

U-Pass institutions: Durham College (Oshawa), Ontario Tech University, Trent University Durham GTA.
`pass_expires_at` checked on every scan — no manual expiry management.

---

## 7. Feature requirements

### Registration app — /register

**Account creation**
- Email + password via Supabase Auth
- Full name stored in profiles

**Fare category selection**
- User selects: Adult, Senior, Youth, Child, U-Pass, TAP, Armed Forces
- U-Pass: institution dropdown + semester end date picker
- Child, valid U-Pass, Armed Forces: card entry skipped with informational message

**Face capture + liveness**
- Interactive challenge: blink prompt → smile prompt
- 5 frames captured after successful liveness
- POST /embed → 128-dim vector stored, image discarded
- Never show camera feed from other users or store any image

**Payment method**
- Stripe SetupIntent for: Adult, Senior, Youth, TAP
- Card saved to Stripe customer — no raw card data on FacePay servers
- `stripe_customer_id` stored in profiles

### Bus terminal — /terminal

**Idle state**
- Fullscreen kiosk — no navigation, no browser chrome
- GTFS route display: route number, direction, on-time status, service alerts
- Route data refreshed every 30 seconds

**Boarding flow**
- Camera always active — face auto-detected, no user interaction
- Passive liveness check before identification
- POST /identify → user_id, confidence, fare_category, pass_expires_at
- Confidence routing: >98% auto-charge, 90–98% PIN fallback, <90% reject
- Fare lookup from fare_rules using fare_category
- U-Pass expiry: if expired → override to adult fare + amber warning
- Stripe PaymentIntent with exact DRT fare amount
- $0 fares: transaction logged, Stripe skipped
- Transaction logged with trip_id, route_id, stop_id

**Result screens**
- Success: passenger name, fare charged, route, "Welcome aboard"
- PIN required: 4-digit entry, no name shown until confirmed
- Rejected: re-scan prompt + cash fallback instruction
- All result states driven by Supabase Realtime subscription

---

## 8. API endpoints

Base URL: `https://facepay-api.railway.app`

| Method | Endpoint | Used by | Description |
|--------|----------|---------|-------------|
| POST | /auth/register | Registration | Create Supabase user + Stripe customer |
| POST | /embed | Registration | Image → 128-dim vector → pgvector, discard image |
| POST | /identify | Terminal | Frame → cosine search → user_id + confidence + fare |
| POST | /pay | Terminal | Stripe PaymentIntent with exact DRT fare |
| POST | /pay/pin-confirm | Terminal | PIN fallback for 90–98% confidence |
| GET | /gtfs/route-status | Terminal | Cached GTFS data: vehicle, delay, headsign, alerts |
| GET | /transactions/{id} | Internal | Audit log with trip_id, route_id, confidence |

---

## 9. Security and privacy

**Zero-knowledge biometrics** — Only 128-dimensional float vectors are stored. No images, no thumbnails, no metadata that could reconstruct a face. A leaked database cannot be reverse-engineered into a photograph.

**Liveness detection** — Two modes prevent spoofing. Interactive (registration): blink + smile challenges. Passive (terminal): frame-delta motion analysis + texture analysis. Neither can be bypassed by a photograph or screen.

**Confidence tiering** — No payment below 90% confidence. 90–98% requires PIN. Only >98% triggers automatic payment. Prevents false positives from lookalikes.

**Row Level Security** — Supabase RLS prevents any authenticated user from reading another user's embeddings or transactions. The service_role key (Railway env var only) is the sole write path to face_embeddings.

**Payment security** — Raw card data never touches FacePay. Stripe SetupIntent + PaymentIntent handle all card processing. PCI compliance fully delegated to Stripe.

**Stripe test mode** — In this build, all payments use Stripe test mode. The test card `4242 4242 4242 4242` simulates real transactions — PaymentIntents appear in the Stripe dashboard, charges are recorded, but no real money moves. To go live, swap test API keys for live keys. Zero code changes required.

---

## 10. Edge cases

| Edge case | Risk | Mitigation |
|-----------|------|-----------|
| Print/screen spoofing | HIGH | Passive liveness: frame-delta detects zero micro-movement. Hard reject before identification. |
| Identical twins / lookalikes | MED | Confidence 90–98% → PIN fallback. 4-digit PIN set at registration. |
| U-Pass expired | HIGH | `pass_expires_at` checked every scan. Override to adult fare automatically. Amber warning on screen. |
| Child passenger (free) | LOW | `amount_cents == 0` → Stripe never called. Transaction logged with $0. |
| Face not in database | LOW | Confidence < 90% → show registration prompt + cash fallback. Passenger never stranded. |
| Stripe payment fails | MED | Log as `payment_failed`. Allow boarding. Flag account for follow-up. Mirrors DRT PRESTO low-balance policy. |
| GTFS feed unreachable | LOW | Backend serves cached data (TTL 5 min). If cache stale, hide route panel. Payment flow unaffected. |
| Poor lighting / no face | LOW | OpenCV returns empty detection. Terminal shows ambient prompt. No scan fired. |
| Two faces in frame | MED | Select largest bounding box (closest passenger). One scan per boarding event. |

---

## 11. Out of scope (v2)

- Institutional verification of U-Pass status via university enrollment API
- Real-time GTFS feed (live vehicle positions beyond static schedule)
- Zone-based, distance-based, or time-of-day fare rules
- PRESTO card reconciliation
- Accessibility accommodations (audio cues, screen reader on terminal)
- Fleet-wide terminal management dashboard
- Age inference from face scan — explicitly excluded for accuracy and privacy reasons
- Transfer fare logic between DRT and connecting transit systems