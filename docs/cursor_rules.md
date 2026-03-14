---
applyTo: '**'
---

# FacePay — Cursor Collaboration Rules

We are teammates building a biometric transit payment system for Durham Region Transit, Oshawa.
You have full context on this project via `docs/`. Read that folder before touching any code.

---

## 1. How we work together

We are teammates, not user↔tool. Help me think better and ship higher-quality code faster.

- For complex or ambiguous tasks, ask up to 1–3 targeted clarifying questions — only if the task cannot be answered safely with reasonable assumptions. If it can be assumed, assume and proceed.
- Push me beyond my first idea. Show multiple meaningfully different approaches when the tradeoffs are real. Do not show variations that are superficially different.
- When reviewing my ideas, drafts, or code — explain *why* one approach is better. Coach me to be a better engineer, not just a faster one.
- Ruthlessly simplify. Remove redundancy. Avoid over-engineering. Favor boring, transparent code that is easy to read at 2am during a hackathon when something breaks.
- Always ground answers in the actual codebase. Consult `docs/` first, then the relevant code. If you find a gap between the docs and the code, call it out immediately.

---

## 2. Project context (read before generating anything)

This is a two-app monorepo. One backend. One database. Read the right doc for the right task.

| Task | Read first |
|------|-----------|
| Any backend route or CV logic | `docs/APP_FLOW.md` + `docs/SCHEMA.md` |
| Any database query or schema | `docs/SCHEMA.md` |
| Any frontend component | `docs/FRONTEND_GUIDELINES.md` + `docs/APP_FLOW.md` |
| Any API endpoint | `docs/APP_FLOW.md` + `docs/TECH_STACK.md` |
| Install or environment questions | `docs/TECH_STACK.md` |
| Build order or what to build next | `docs/IMPLEMENTATION_PLAN.md` |
| Product decisions or edge cases | `docs/PRD.md` |

---

## 3. FacePay-specific rules — never violate these

### Payment and security
- Stripe **always** receives `amount_cents` from the `fare_rules` table. Never hardcode a payment amount anywhere in the codebase.
- The `service_role` Supabase key **never** appears in frontend code, `.env.local`, or any file that gets bundled by Vite. Railway env vars only.
- Raw image data **never** reaches the database. The `/embed` endpoint discards image buffers immediately after generating the embedding. If you are writing code that stores, logs, or passes image data beyond the embedder, stop and rethink.
- The `face_embeddings` table is only accessible via the service_role key. RLS policy blocks all anon key access. Never write a frontend query to this table.

### CV and liveness
- The terminal uses **passive liveness only** (frame-delta + texture analysis). Never add interactive challenges (blink, smile prompts) to the terminal. That belongs in registration only.
- The registration flow uses **interactive liveness only** (MediaPipe EAR for blink, lip corners for smile). Never use passive frame-delta at registration — it adds nothing there.
- The camera frame loop on the terminal must have a **5-second cooldown** after any scan attempt. Without this, multiple `POST /identify` calls fire on the same face while the success screen is showing. This causes duplicate Stripe charges.

### Confidence routing — never change these thresholds without discussion
```
> 98%      → auto charge
90–98%     → PIN fallback (4-digit, max 3 attempts)
< 90%      → hard reject, log to failed_scans, never to transactions
```

### GTFS
- GTFS is **display only**. The payment flow must have zero dependency on GTFS data. If the GTFS fetch fails, fares must still work. Never put GTFS inside a payment code path.
- Cache GTFS responses. TTL is 30 seconds. If cache is older than 5 minutes, return empty — the frontend hides the panel. Never let a stale GTFS response block a boarding event.

### U-Pass logic
- `pass_expires_at` is checked on **every scan**, not just at login. The check happens inside the `resolve_fare()` Supabase function. Do not duplicate this logic in the backend Python — call the DB function.
- When a U-Pass is expired: charge adult fare ($3.73), set `pass_was_expired: true` on the transaction, show amber warning on the success screen. Never silently charge adult fare without the warning.

---

## 4. When creating or reviewing code

### Structure and scope
- Clear function/component names that describe intent, not implementation
- Explicit dependencies between files — if file A imports from file B, file B must exist first (see `docs/IMPLEMENTATION_PLAN.md` file creation order)
- YAGNI/KISS/DRY — no placeholder code, no `// TODO: handle this later`, no unused imports
- No future-proofing for features that are explicitly out of scope (see `docs/PRD.md` Section 11)

### Implementation readiness
Before generating any file, confirm:
- **State and data flow**: where does the data come from, what shape is it, where does it go
- **New abstractions**: if creating a hook, context, or utility — define the full interface before writing the implementation
- **File paths**: match exactly what is listed in `docs/IMPLEMENTATION_PLAN.md` — do not invent new paths
- **Integration points**: show how the new code connects to existing code (props, context, direct import, API call)

### Exit criteria
Every piece of code you generate should be verifiable. When you finish a function or component, tell me:
- What specific input produces what specific output
- What to check in the browser, terminal, or Supabase dashboard to confirm it worked
- What the most likely failure mode is and how to diagnose it

### Review checklist — ask these when I share code or a plan
- "Could I implement this today without stopping to ask clarifying questions?"
- "Is there any state, ref, or variable that is mentioned but not defined?"
- "Does the riskiest code (CV, liveness, Stripe) happen early enough to validate before building the UI on top of it?"
- "What would break this during a live demo?"

---

## 5. FacePay code style

### Python (backend)
- Functions that touch the database use `async def` — FastAPI is async by default
- Every router function validates inputs before touching Supabase or Stripe
- CV functions (`embedder.py`, `liveness.py`) have no Supabase or Stripe imports — keep CV pure
- Use `python-dotenv` — never access `os.environ` directly without a fallback
- Errors that would strand a passenger (Stripe failure, GTFS failure) must be caught and handled gracefully — the passenger always boards

### JavaScript / React (frontend)
- Use plain JS, not TypeScript — this is a hackathon build
- shadcn/ui components are the base — override via CSS variables, not by rewriting components
- All CSS values that appear in `docs/FRONTEND_GUIDELINES.md` use CSS variables (`--reg-accent`, `--term-bg`, etc.) — never hardcode hex values in components
- The camera frame loop on the terminal uses `setInterval` with a ref cleanup on unmount — always clean up
- Supabase Realtime subscriptions are created on mount and unsubscribed on unmount — always clean up
- `React.memo()` on terminal state components — the camera loop triggers re-renders at 5fps

### Naming conventions
```
Backend files:      snake_case        (supabase_client.py, identify.py)
Frontend files:     PascalCase        (WebcamCapture.jsx, SuccessScreen.jsx)
CSS variables:      --reg-* or --term-* prefix for theme tokens
API endpoints:      kebab-case        (/pay/pin-confirm, /gtfs/route-status)
DB columns:         snake_case        (fare_category, pass_expires_at, stripe_pi_id)
React components:   PascalCase        (PinFallback, SuccessScreen)
React hooks:        camelCase, use*   (useTerminalState, useGtfsPolling)
```

---

## 6. The two apps at a glance

### Registration (`/register`) — what Cursor needs to know
- Max width 420px, centred, single column, dark surface cards
- 6 screens in linear sequence — cannot skip forward
- Font: Sora (display) + DM Sans (body)
- Accent: `#00FF94` — only colour that moves
- Stripe Elements appearance: `{ theme: 'night', variables: { colorPrimary: '#00FF94', colorBackground: '#0F1B2D' } }`
- Interactive liveness: blink (MediaPipe EAR < 0.2) then smile (lip corners)
- Screen transitions: fade out 150ms, then fade in 200ms + translateY(12px → 0)

### Terminal (`/terminal`) — what Cursor needs to know
- Fullscreen kiosk, `requestFullscreen()` on mount
- 9 states — every state has a distinct visual signature readable from 2 metres
- Font: JetBrains Mono (display) + DM Sans (body)
- Background cuts instantly on state change — never transition background colour
- Two independent loops: camera loop (200ms interval) + GTFS loop (30s interval)
- Supabase Realtime subscription drives success screen — not the Stripe response
- 5-second cooldown after any scan attempt — critical, never remove this
- Success screen: deep green `#041A0E`, passenger first name in Sora 700, checkmark SVG stroke animation

---

## 7. The most common mistakes to prevent

| Mistake | Why it matters | Rule |
|---------|---------------|------|
| Hardcoding `amount_cents` | Charges wrong amount, fails the demo | Always read from `fare_rules` table |
| Forgetting the camera cooldown | Duplicate Stripe charges mid-demo | 5 seconds after any scan attempt |
| Using service_role key in frontend | Bypasses all RLS, major security hole | Railway env vars only |
| Adding blink/smile to terminal | Terminal cannot prompt passengers | Passive liveness only on terminal |
| GTFS inside payment path | GTFS outage breaks boarding | GTFS is display only, zero payment dependency |
| Calling resolve_fare logic in Python | Duplicates DB function, gets out of sync | Call `SELECT resolve_fare($user_id)` from Python |
| Transitioning background on success | Looks wrong for the moment | Cut background instantly, then fade content |
| `console.log` in camera loop | Spams console at 5fps, kills perf | Remove all logging from frame loop |
| Storing images in Supabase | Breaks the zero-knowledge privacy pitch | Discard image buffers immediately in `/embed` |
| Not cleaning up Realtime subscriptions | Memory leak, duplicate events | Always unsubscribe on component unmount |

---

## 8. When I ask you to build something new

Use this checklist before generating code:

1. Which file does this go in? (Check `docs/IMPLEMENTATION_PLAN.md` file creation order)
2. What does this file import? Do all those files exist yet?
3. What DB tables or columns does this touch? (Check `docs/SCHEMA.md`)
4. What API endpoints does this call? (Check `docs/APP_FLOW.md`)
5. Does this involve payment, biometric data, or liveness? (Apply Section 3 rules)
6. Which CSS variables does this use? (Check `docs/FRONTEND_GUIDELINES.md`)
7. What is the verify step — how do I confirm this worked?

---

## 9. Demo safety rules

The demo is the product. These rules exist to prevent visible failures in front of judges.

- Never make a Stripe charge in the UI without first confirming the identify endpoint returned confidence > 90%
- The success screen must always show — even if Stripe fails (show `payment_failed` state, never a blank screen or JS error)
- GTFS panel failure must always be graceful — hide the panel, never show an error or crash the terminal
- The registration flow must handle camera permission denied with a clear instructional screen — never a blank page or console error
- All `async` calls in the camera loop must have `try/catch` — a CV exception must not crash the terminal
- Test with the expired U-Pass scenario before demo day — it is the most likely judge question and the most visible edge case