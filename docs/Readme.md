# FacePay — Project Documentation

Biometric transit payment system for Durham Region Transit, Oshawa.
Hackathon Build v1.0 · March 2026

---

## What this project is

A passenger registers their face once, links a payment card, and boards any DRT bus by looking at a terminal camera. The system identifies them, determines their fare category (including U-Pass validity), and charges the exact DRT PRESTO fare automatically via Stripe. No card tap, no phone required.

---

## Document index

| File | What it covers |
|------|---------------|
| [PRD.md](./PRD.md) | Goals, personas, system architecture, fare structure, edge cases |
| [APP_FLOW.md](./APP_FLOW.md) | Every screen, state, API call, and decision point |
| [TECH_STACK.md](./TECH_STACK.md) | Every tool, install commands, environment variables |
| [SCHEMA.md](./SCHEMA.md) | Full database schema, functions, RLS policies |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | Build order, step-by-step instructions, verify checklists |
| [FRONTEND_GUIDELINES.md](./FRONTEND_GUIDELINES.md) | Design tokens, CSS, components, animation |

---

## Quick reference

### Two apps, one backend

```
facepay/
├── backend/                  ← FastAPI on Railway
│   ├── main.py
│   ├── routers/
│   │   ├── auth.py           POST /auth/register
│   │   ├── embed.py          POST /embed
│   │   ├── identify.py       POST /identify
│   │   ├── payments.py       POST /pay, POST /pay/pin-confirm
│   │   └── gtfs.py           GET /gtfs/route-status
│   ├── cv/
│   │   ├── embedder.py       face_recognition wrapper
│   │   └── liveness.py       two-mode liveness detection
│   └── db/
│       ├── supabase_client.py
│       └── schema.sql
└── facepay-client/           ← React + Vite on Vercel
    └── src/
        ├── App.jsx            /register and /terminal routes
        ├── lib/supabase.js
        └── routes/
            ├── register/      Screen 1–6 registration flow
            └── terminal/      Kiosk — 9 states, always-on camera
```

### API base URL
```
http://localhost:8000          (local dev)
https://facepay-api.railway.app (production)
```

### DRT fare table (seeded into Supabase fare_rules)

| Category | Amount | Stripe called? |
|----------|--------|---------------|
| adult | $3.73 | Yes |
| senior | $2.46 | Yes |
| youth | $3.35 | Yes |
| child | $0.00 | No |
| u_pass (valid) | $0.00 | No |
| u_pass (expired) | $3.73 (adult fallback) | Yes |
| tap | $52.22/mo (free after 14 trips) | Yes / No |
| armed_forces | $0.00 | No |

### Confidence routing
```
> 98%      → auto charge
90–98%     → PIN fallback (4-digit, 3 attempts)
< 90%      → hard reject
```

### Demo hardware
- Device 1 (laptop): `https://your-vercel-url.vercel.app/terminal` — fullscreen kiosk
- Device 2 (phone or second laptop): `https://your-vercel-url.vercel.app/register`
- Both devices, one Vercel deployment

### Test cards (Stripe test mode)
```
4242 4242 4242 4242   → always succeeds
4000 0000 0000 0002   → always declines
Any future expiry, any CVC, any postcode
```