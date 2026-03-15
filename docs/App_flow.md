# FacePay — App Flow Document

Every screen, state, step, and decision point. Read this before building any component.
Every screen maps to a component file. Every decision point maps to a backend logic branch.

---

## Registration app — /register

Six screens in sequence. Cannot skip ahead. Each unlocks only after the previous completes.

### Screen map

| Screen | State | Unlocks when | Back? |
|--------|-------|-------------|-------|
| 1 Welcome | initial | Always | N/A |
| 2 Create Account | creating-account | Tap Get Started | Yes |
| 3 Fare Category | selecting-fare | Auth user created | No |
| 4 Face Capture | capturing-face | Fare category saved | No |
| 5 Add Payment | adding-payment | Embedding stored | No |
| 6 All Done | complete | Card saved or skipped | No |

---

### Screen 1 — Welcome

Full screen. Logo centred. Tagline: "Your face is your ticket." Single CTA: "Get Started".
No API call. Nothing created until form is submitted.

---

### Screen 2 — Create Account

Fields: Full Name, Email, Password (min 8 chars).

**Flow:**
1. Client-side validation — name not empty, email valid, password ≥ 8 chars
2. `supabase.auth.signUp({ email, password })` — stores full_name in user_metadata. **Email confirmation is disabled** in Supabase, so a session is returned immediately (no "check your email" step).
3. `POST /auth/register` — with `Authorization: Bearer <session.access_token>`; creates profiles row, creates Stripe customer, returns stripe_customer_id
4. Navigate to Screen 3

**Errors:**
- Email already registered → "An account with this email already exists."
- Network failure → "Could not connect. Try again." + retry button
- Weak password → inline, no submit

---

### Screen 3 — Fare Category

Single-select list of all DRT fare categories. Each shows name and price.

**Skip payment logic:**
```js
const skipPayment = ['child', 'armed_forces'].includes(fareCategory)
  || (fareCategory === 'u_pass' && passExpiresAt > today)
```

**U-Pass conditional fields:**
- Institution dropdown: Durham College · Ontario Tech · Trent University Durham GTA
- Semester end date picker — defaults to April 30 of current year
- Both required before Continue enables
- Animate in with `max-height` + `opacity` transition

**On Continue:**
1. PATCH profiles — saves fare_category, pass_expires_at (if U-Pass), institution (if U-Pass)
2. If skipPayment → Screen 6
3. Otherwise → Screen 4

---

### Screen 4 — Face Capture

Live webcam feed. Oval SVG overlay. Instruction text changes per step.
Step indicator: Position · Blink · Smile · Done. Capture is automatic — no shutter button.

**Liveness sequence:**
1. `navigator.mediaDevices.getUserMedia({ video: true })` — requires HTTPS
2. Detect face in frame → "Position your face in the oval"
3. MediaPipe EAR < 0.2 → blink confirmed → "Blink slowly" (10s timeout)
4. MediaPipe lip corners up → smile confirmed → "Give us a smile" (10s timeout)
5. Capture 5 frames immediately after smile
6. `POST /embed` — returns embedding_id
7. Navigate to Screen 5 (if card needed) or Screen 6 (if free category)

**Errors:**
- Camera denied → show browser settings instructions, do not retry automatically
- No face detected (10s) → "Make sure you're in good light" → auto-retry 3s
- Blink timeout → reset to step 2
- Smile timeout → reset to step 3
- POST /embed fails → retry from step 1

---

### Screen 5 — Add Payment Method

Only renders for: Adult, Senior, Youth, TAP. Skipped entirely for Child, valid U-Pass, Armed Forces.

**Flow:**
1. Backend creates Stripe SetupIntent → returns client_secret
2. `stripe.confirmCardSetup(client_secret)` — card tokenised by Stripe, never touches FacePay
3. Backend attaches payment_method to Stripe customer, confirms stripe_customer_id in profiles
4. Navigate to Screen 6

**Stripe appearance (dark theme):**
```js
{ theme: 'night', variables: { colorPrimary: '#00FF94', colorBackground: '#0F1B2D' } }
```

**Errors:**
- Card declined → "Your card was declined. Try a different card."
- Invalid number → inline Stripe error
- Network failure → "Could not save card." + retry

---

### Screen 6 — Registration Complete

Green checkmark SVG stroke animation. Passenger first name. Fare category summary.
No API calls. Purely confirmational. "Done" returns to Screen 1 and clears all state.

---

## Bus terminal — /terminal

Fullscreen kiosk. Always on. Zero passenger interaction required. Camera runs continuously.
Two independent loops: camera loop (200ms interval) and GTFS loop (30s interval).

### State overview

| State | Trigger | Duration | Passenger action |
|-------|---------|----------|-----------------|
| 1 Idle / GTFS | App loads or payment completes | Indefinite | None |
| 2 Face detected | OpenCV detects face | ~0.5s | None |
| 3 Liveness check | Face detected | ~0.5s | None |
| 4 Identifying | Liveness passed | ~1s | None |
| 5a Charging | Confidence > 98% | ~1s | None |
| 5b PIN required | Confidence 90–98% | Until PIN entered | Enter 4-digit PIN |
| 5c Rejected | Confidence < 90% | 5s → idle | None |
| 6 Success | Payment confirmed or $0 fare | 4s → idle | None |
| 7 Payment failed | Stripe error | 5s → idle | None |

---

### State 1 — Idle / GTFS Display

Left 60%: GTFS route panel — route number, direction, on-time status, delay badge, alerts.
Right 40%: subtle "Look at the camera to board" prompt + pulsing camera dot.
Camera scanning invisibly in background. Video feed never shown.

**GTFS refresh loop:**
1. `GET /gtfs/route-status?route_id=110` every 30 seconds
2. If `delay_seconds > 0` → amber delay badge
3. If alerts → amber alert banner
4. If fetch fails → show last cached data with "Last updated X min ago"
5. If cache > 5 min old → hide panel entirely

**Camera loop runs simultaneously.** Does not share state with GTFS loop.

---

### State 2 — Face Detected

Camera ring pulses (thin amber ring around camera area). No text changes.
Triggers when: OpenCV bounding box exceeds minimum area threshold.
Two faces → select largest bounding box (closest passenger).
Immediately begin passive liveness.

---

### State 3 — Passive Liveness Check

Runs on 3–5 consecutive frames. ~200–400ms. Passenger sees nothing.

**Two checks run in parallel:**

| Check | Method | Detects |
|-------|--------|---------|
| Frame-delta motion | `cv2.absdiff()` across 3 frames. Real face has micro-movement. | Printed photos, static images |
| Texture analysis | Frequency spectrum of skin region. Real 3D skin has irregular texture. LCD has repeating grid. | Screens, printed photos |

**Decision:**
- Both pass → proceed to State 4
- Either fails → hard reject. "Scan failed — please use the camera directly." Return to idle after 3s. No identification attempt.

---

### State 4 — Face Identification

Text: "Identifying..." with loading bar growing 0→100% over 1.2s.
No passenger name shown until payment is confirmed — showing name before is a security risk.

**Backend flow:**
1. `POST /identify` — sends frame as base64 + `route_id=110`
2. CV engine generates 128-dim embedding
3. pgvector cosine similarity: `SELECT user_id, 1-(embedding <=> $query) AS confidence FROM face_embeddings ORDER BY confidence DESC LIMIT 1`
4. Fetch profile: fare_category, pass_expires_at, stripe_customer_id, full_name
5. U-Pass expiry check: if `pass_expires_at <= today` → override to adult fare, set `pass_expired = true`
6. Fare lookup: `SELECT amount_cents FROM fare_rules WHERE fare_category = $resolved_category`
7. Return: user_id, full_name, confidence, fare_category, amount_cents, pass_expired, trip_id

**Routing:**
- `> 98%` → State 5a auto-charge
- `90–98%` → State 5b PIN required
- `< 90%` → State 5c rejected

---

### State 5a — Auto Charge

Brief intermediate state. "Charging your fare..." + spinner.

**Flow:**
1. `POST /pay` — user_id, amount_cents, route_id, trip_id, stop_id
2. If `amount_cents == 0` → skip Stripe, log transaction, emit Realtime event
3. If `amount_cents > 0` → `stripe.PaymentIntent.create({ amount, currency: 'cad', customer, confirm: true, off_session: true })`
4. `INSERT INTO transactions` — user_id, amount_cents, confidence, stripe_pi_id, status: success, route_id, trip_id, stop_id
5. Supabase Realtime emits INSERT event → frontend transitions to State 6

---

### State 5b — PIN Required

Large 4-digit PIN pad. Dot indicators. Auto-submits on 4th digit. No passenger name shown.
Cancel button returns to idle.

**Flow:**
1. Display PIN pad. user_id held in local state, never displayed.
2. Passenger enters PIN → auto-submits after 4th digit
3. `POST /pay/pin-confirm` — user_id + entered PIN
4. Backend verifies PIN hash

**Outcomes:**
- Correct PIN → charge via Stripe → State 6
- Wrong PIN (1st or 2nd) → shake animation, clear digits, "Incorrect PIN — try again"
- Wrong PIN (3rd) → lock attempt, "Too many attempts. Please board with cash." → idle after 8s

---

### State 5c — Rejected

Amber background tint. "We don't recognise this face." Cash fallback instruction.
Auto-resets to idle after 5 seconds. No passenger name. No transaction logged.
Logs a `failed_scans` row with reason: `low_confidence`.

---

### State 6 — Success

Full-screen deep green. Checkmark SVG stroke animation (0.5s draw).
Passenger first name: "Welcome, [Name]!"
Fare line: "$3.73 charged" or "Free travel — U-Pass · Valid until [date]"
Route: "Route 110 · Towards Oshawa GO" (from GTFS)
Auto-resets to idle after 4 seconds.

**U-Pass expired variant:** Amber warning stripe below fare: "$3.73 charged · U-Pass expired — please renew."

**Why Supabase Realtime drives this screen:**
The success screen is triggered by an INSERT to `transactions`, not by the Stripe response directly. This means the terminal updates the moment the DB record is written, even if there was a network hiccup between backend and frontend.

---

### State 7 — Payment Failed

Amber-tinted screen. "Payment issue — please see the driver."
Passenger name IS shown. "Your account has been flagged for follow-up."
Passenger always allowed to board. Transaction logged as `payment_failed`.
Auto-resets after 5 seconds. Driver sees amber screen.

---

## Shared backend logic

### POST /embed — embedding flow

1. Accept 5 base64-encoded JPEG frames (max 2MB each)
2. `face_recognition.face_locations(image)` on each frame — skip if no face found
3. `face_recognition.face_encodings(image, locations)` — 128-dim numpy array per frame
4. `np.mean([embedding1...embedding5], axis=0)` — averaged vector is more stable
5. Discard all image buffers from memory
6. `INSERT INTO face_embeddings (user_id, embedding)` — pgvector VECTOR(128)

### POST /identify — identity resolution flow

1. Accept one base64-encoded JPEG
2. Passive liveness: frame-delta + texture on 3 buffered frames → `live: bool`
3. If liveness fails → return immediately with `reason: liveness_failed`
4. `face_recognition.face_encodings(image)` — single frame embedding
5. pgvector cosine search → user_id + confidence
6. Threshold route: >98% auto, 90-98% pin, <90% reject
7. If ≥90%: fetch profile, run `SELECT resolve_fare($user_id)` DB function
8. Return full response

### Fare resolution (resolve_fare DB function)

```
fare_category = adult    → $3.73, Stripe yes
fare_category = senior   → $2.46, Stripe yes
fare_category = youth    → $3.35, Stripe yes
fare_category = child    → $0.00, Stripe no
u_pass AND expires > today → $0.00, Stripe no
u_pass AND expires <= today → $3.73 (adult fallback), Stripe yes, pass_expired: true
armed_forces             → $0.00, Stripe no
tap AND trips_this_month < 14  → $52.22, Stripe yes
tap AND trips_this_month >= 14 → $0.00, Stripe no, "Unlimited travel active"
```

---

## Edge case flows

### Spoofing attempt
1. Person holds phone photo of registered user to camera
2. Passive liveness: frame-delta detects zero motion → fails
3. No identification attempt. Terminal: "Please look directly at the camera."
4. Logs: `failed_scans`, reason: `liveness_failed`, no user_id

### U-Pass expired mid-semester
1. `pass_expires_at = April 30`, today = May 2
2. Face identified >98% confidence
3. `resolve_fare()`: `pass_expires_at <= today` → resolve to adult $3.73
4. Stripe charged $3.73. Transaction: `resolved_fare_category: adult, pass_was_expired: true`
5. Success screen: "$3.73 charged · U-Pass expired — please renew." amber band

### GTFS feed unreachable
1. `GET /gtfs/route-status` returns timeout
2. Backend checks cache age
3. Cache < 5 min → serve stale with asterisk note
4. Cache ≥ 5 min → return empty → frontend hides panel
5. Payment flow completely unaffected

### Stripe charge fails
1. `POST /pay` → Stripe returns `card_declined`
2. Backend: log transaction `status: payment_failed`, `stripe_pi_id: null`
3. Supabase Realtime emits `payment_failed` event
4. Terminal: State 7 amber screen. Passenger boards. Account flagged.

---

## Demo script (10 steps, 3–4 minutes)

| Step | Action | What judges see |
|------|--------|----------------|
| 1 | Open /terminal on laptop — kiosk mode | Route 110 GTFS data on idle screen |
| 2 | Open /register on phone | Fare category selection UI |
| 3 | Register as Adult — blink + smile | "Face captured" — zero images stored |
| 4 | Save test card 4242 4242 4242 4242 | Stripe card form — explain PCI delegation |
| 5 | Walk in front of terminal camera | Auto-detects → $3.73 charged → welcome screen |
| 6 | Register second account as U-Pass — set expiry to yesterday | Date picker, institution dropdown |
| 7 | Walk in front of terminal again | Amber warning: U-Pass expired → $3.73 adult |
| 8 | Hold up phone photo to camera | Terminal rejects — liveness catches spoofing |
| 9 | Open Supabase transactions table | trip_id, route_id, stop_id, confidence on every row |
| 10 | Take judge questions | Every edge case is documented in this file |