# FacePay — Frontend Design Guidelines

Design tokens, CSS variables, component patterns, and animation rules.
Two apps, one codebase, deliberately distinct visual identities.

---

## 1. Philosophy

FacePay has two experiences in the same monorepo. They share a brand but not a tone.

| | Registration `/register` | Bus Terminal `/terminal` |
|-|--------------------------|--------------------------|
| User context | Sitting down, one-time setup, phone or laptop | Standing in a bus aisle, motion possible, others behind them |
| Tone | Calm · trustworthy · guided | Fast · confident · frictionless |
| Priority | User feels safe giving biometric + payment data | Every state readable in under one second |
| Animations | Deliberate, staggered, premium | Instant or functional — never decorative |

**The bridge:** The same green accent (`#00FF94`) appears in both themes. It is the only visual element that connects them.

---

## 2. Design tokens

### Fonts

Install both from Google Fonts. Add to `index.html`.

```html
<!-- Registration -->
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">

<!-- Terminal -->
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
```

| App | Display font | Body font | Why |
|-----|-------------|-----------|-----|
| Registration | Sora | DM Sans | Geometric, approachable, premium fintech feel |
| Terminal | JetBrains Mono | DM Sans | Monospaced creates a data-terminal feel. Fares, route IDs, confidence scores look native. |

> Never use Inter, Roboto, Arial, or system fonts. They undercut the product quality immediately.

---

### Registration theme (`/register`)

Dark, professional, calm. Feels like a banking app.

```css
:root {
  /* Registration */
  --reg-bg:        #0D1F2D;
  --reg-surface:   #0F1B2D;
  --reg-border:    #1E2A3A;
  --reg-accent:    #00FF94;   /* FacePay green — only colour that moves */
  --reg-text:      #E2E8F0;
  --reg-muted:     #64748B;
  --reg-error:     #A32D2D;
  --reg-warning:   #BA7517;
}
```

---

### Terminal theme (`/terminal`)

Darker, more severe. Amber creates urgency. Success is full-screen green.
Optimised for readability in mixed ambient light (bus stop in January).

```css
:root {
  /* Terminal */
  --term-bg:       #080B12;
  --term-surface:  #0A0E18;
  --term-text:     #E2E8F0;
  --term-dim:      #4A5568;
  --term-amber:    #BA7517;   /* warning states, PIN screen */
  --term-success:  #1D9E75;   /* welcome aboard */
  --term-error:    #A32D2D;
}
```

---

### Spacing scale

Use only these values. Do not invent intermediate values.

```css
:root {
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  24px;
  --space-6:  32px;
  --space-8:  48px;
  --space-12: 64px;
}
```

---

### Border radius

```css
:root {
  --radius-sm:   6px;     /* badges, tags */
  --radius-md:   10px;    /* inputs, buttons */
  --radius-lg:   16px;    /* cards, panels */
  --radius-xl:   24px;    /* modals, large containers */
  --radius-full: 9999px;  /* oval face guide, toggle switches, dots */
}
```

---

### Animation durations

```css
:root {
  --duration-instant:   0ms;
  --duration-fast:      150ms;
  --duration-default:   200ms;
  --duration-deliberate:350ms;
  --duration-slow:      600ms;
  --duration-breathing: 1200ms;
}
```

---

## 3. Registration app — /register

### Layout shell

```css
.reg-shell {
  min-height: 100vh;
  background: var(--reg-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-5);
}

.reg-card {
  width: 100%;
  max-width: 420px;
  background: var(--reg-surface);
  border: 1px solid var(--reg-border);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
}
```

---

### Progress indicator (Screens 2–6)

5 dots at top of card. Active dot fills with green. Completed dots fade.

```css
.progress-bar {
  display: flex;
  gap: var(--space-2);
  justify-content: center;
  margin-bottom: var(--space-6);
}

.progress-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  background: var(--reg-border);
  transition: background var(--duration-default) ease;
}

.progress-dot.active { background: var(--reg-accent); }
.progress-dot.done   { background: var(--reg-accent); opacity: 0.4; }
```

---

### Form inputs

```css
/* Override shadcn/ui Input */
.reg-input {
  background: var(--reg-surface);
  border: 1px solid var(--reg-border);
  border-radius: var(--radius-md);
  color: var(--reg-text);
  font-family: 'DM Sans', sans-serif;
  transition: border-color var(--duration-default) ease;
}

.reg-input:focus {
  border-color: var(--reg-accent);
  outline: none;
}

.reg-label {
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
  font-size: 12px;
  color: var(--reg-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.reg-error-text {
  font-size: 12px;
  color: var(--reg-error);
  margin-top: var(--space-1);
}
```

---

### Fare category cards (Screen 3)

```css
.fare-card {
  background: var(--reg-surface);
  border: 1px solid var(--reg-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  cursor: pointer;
  transition: border-color var(--duration-default) ease;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.fare-card:hover    { border-color: var(--reg-accent); opacity: 0.8; }
.fare-card.selected {
  border-color: var(--reg-accent);
  border-left-width: 3px;
}

.fare-price {
  font-family: 'Sora', sans-serif;
  font-weight: 700;
  font-size: 20px;
  color: var(--reg-accent);
}
```

**U-Pass conditional fields animation:**
```css
.upass-fields {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height var(--duration-deliberate) ease,
              opacity   var(--duration-deliberate) ease;
}

.upass-fields.open {
  max-height: 200px;   /* set to a value safely above actual height */
  opacity: 1;
}
```

---

### Webcam oval overlay (Screen 4)

```svg
<!-- Render absolutely over the video element -->
<svg viewBox="0 0 300 400" class="oval-svg">
  <ellipse cx="150" cy="200" rx="110" ry="155"
    fill="none" stroke="#00FF94" stroke-width="2"
    stroke-dasharray="8 4" class="face-oval" />
</svg>
```

```css
.face-oval.detected {
  stroke-dasharray: none;
  animation: oval-pulse var(--duration-breathing) ease-in-out infinite;
}

@keyframes oval-pulse {
  0%, 100% { transform: scale(1);    opacity: 1; }
  50%       { transform: scale(1.02); opacity: 0.7; }
}

/* transform-origin must be centre of the ellipse */
.oval-svg {
  transform-origin: 150px 200px;
}
```

---

### SVG checkmark animation (Screen 6 + terminal success)

```svg
<svg viewBox="0 0 80 80" width="80" height="80">
  <path d="M16 40 L34 58 L64 24"
    fill="none"
    stroke="#00FF94"
    stroke-width="4"
    stroke-linecap="round"
    stroke-linejoin="round"
    class="checkmark-path" />
</svg>
```

```css
.checkmark-path {
  stroke-dasharray: 80;   /* approximate path length — adjust to fit actual path */
  stroke-dashoffset: 80;
  animation: draw-check var(--duration-slow) ease-in-out forwards;
}

@keyframes draw-check {
  to { stroke-dashoffset: 0; }
}
```

---

### Screen transitions

```css
.screen-enter {
  opacity: 0;
  transform: translateY(12px);
}

.screen-enter-active {
  opacity: 1;
  transform: translateY(0);
  transition: opacity var(--duration-default) ease-out,
              transform var(--duration-default) ease-out;
}

.screen-exit-active {
  opacity: 0;
  transition: opacity 150ms ease-in;
}
```

Fade out first (150ms), then fade in (200ms). Do not slide both simultaneously.

---

### Stripe Elements appearance config

```js
const stripeAppearance = {
  theme: 'night',
  variables: {
    colorPrimary:    '#00FF94',
    colorBackground: '#0F1B2D',
    colorText:       '#E2E8F0',
    colorDanger:     '#A32D2D',
    fontFamily:      'DM Sans, sans-serif',
    borderRadius:    '10px',
  }
}

const elements = stripe.elements({ appearance: stripeAppearance, clientSecret })
```

---

## 4. Bus terminal — /terminal

### Layout shell

```css
.term-shell {
  width: 100vw;
  height: 100vh;
  background: var(--term-bg);
  overflow: hidden;
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  flex-direction: column;
}
```

Call `document.documentElement.requestFullscreen()` on component mount.

---

### GTFS route panel (idle left side)

```css
.route-panel {
  width: 60%;
  height: 100%;
  padding: var(--space-8);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.route-number {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: clamp(64px, 8vw, 96px);  /* scales with viewport, always readable from 2m away */
  color: var(--term-text);
  line-height: 1;
}

.route-headsign {
  font-family: 'DM Sans', sans-serif;
  font-size: clamp(18px, 2vw, 24px);
  color: var(--term-dim);
  margin-top: var(--space-3);
}

.delay-badge {
  display: inline-block;
  background: var(--term-amber);
  color: #080B12;
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font-size: 14px;
  font-weight: 600;
  margin-top: var(--space-3);
}
```

---

### Camera indicator dot (idle right side)

```css
.camera-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--radius-full);
  background: var(--term-success);
  animation: dot-pulse 3s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1);   opacity: 1; }
  50%       { transform: scale(1.3); opacity: 0.6; }
}
```

---

### Scanning state (States 2–3)

Replace dot with pulsing ring:

```css
.scan-ring {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  border: 2px solid var(--term-amber);
  animation: ring-pulse 0.8s ease-in-out infinite;
}

@keyframes ring-pulse {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50%       { opacity: 1;   transform: scale(1.1); }
}
```

---

### Identifying state (State 4)

Full-width loading bar at bottom of screen:

```css
.identifying-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  height: 3px;
  background: var(--term-amber);
  width: 0%;
  animation: identify-progress 1.2s linear forwards;
}

@keyframes identify-progress {
  to { width: 100%; }
}
```

Text: "Identifying..." — JetBrains Mono 600 32px centred.

---

### PIN pad (State 5b)

```css
.pin-pad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
  max-width: 360px;
  margin: 0 auto;
}

.pin-button {
  min-height: 80px;
  background: var(--term-surface);
  border: 1px solid var(--term-amber);
  border-radius: var(--radius-lg);
  color: var(--term-text);
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  font-size: 28px;
  cursor: pointer;
  transition: transform var(--duration-fast) ease-out;
}

.pin-button:active { transform: scale(0.94); }

/* Wrong PIN shake */
.pin-dots.shake {
  animation: pin-shake 0.4s ease-out;
}

@keyframes pin-shake {
  0%, 100% { transform: translateX(0); }
  20%       { transform: translateX(-8px); }
  40%       { transform: translateX(8px); }
  60%       { transform: translateX(-8px); }
  80%       { transform: translateX(8px); }
}
```

---

### Success screen (State 6)

> ⚠️ Critical rule: the background colour must change **instantly** (0ms), not as a transition. Cut the background, then fade in the content.

```css
.term-success {
  background: #041A0E;   /* deep green — not generic CSS green */
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.welcome-name {
  font-family: 'Sora', sans-serif;
  font-weight: 700;
  font-size: clamp(40px, 5vw, 56px);
  color: var(--term-success);
  animation: slide-up var(--duration-default) ease-out 0.2s both;
}

.fare-line {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  font-size: clamp(20px, 2.5vw, 28px);
  color: var(--term-text);
  animation: slide-up var(--duration-default) ease-out 0.3s both;
}

.upass-expired-band {
  background: rgba(186, 117, 23, 0.15);
  color: var(--term-amber);
  padding: var(--space-2) var(--space-5);
  border-radius: var(--radius-sm);
  font-size: 14px;
  margin-top: var(--space-3);
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

---

### State transitions (terminal)

Terminal uses fade only — no slides. A passenger mid-boarding must not see content shift sideways.

```css
.term-state {
  position: absolute;
  inset: 0;
  transition: opacity 150ms ease-in-out;
}

.term-state.entering { opacity: 0; }
.term-state.active   { opacity: 1; }
.term-state.exiting  { opacity: 0; }
```

---

## 5. Component patterns

### Buttons

| Variant | Use case | Styling |
|---------|----------|---------|
| Primary | Main CTA — Get Started, Continue, Save Card | `background: var(--reg-accent); color: var(--reg-bg); font-family: Sora; font-weight: 600; min-height: 48px; border-radius: var(--radius-md)` |
| Secondary | Cancel, back actions | `background: transparent; border: 1px solid var(--reg-border); color: var(--reg-muted)` |
| Disabled | Before selection or validation | `opacity: 0.4; pointer-events: none` — do not change size or shape |
| Terminal text | Cancel on PIN screen | `color: var(--term-dim); font-size: 14px; no border; no background` |

Button press micro-interaction:
```css
.btn-primary:active { transform: scale(0.97); transition: transform 150ms ease-out; }
```

---

### shadcn/ui components to install

```bash
npx shadcn@latest add button card input label select dialog badge progress
```

| Component | Used in | Key customisation |
|-----------|---------|------------------|
| Button | Both | Override variants via CSS variables |
| Input | Registration | Override border-color on focus: `var(--reg-accent)` |
| Label | Registration | Uppercase, 12px, `letter-spacing: 0.08em` |
| Select | Registration | Dark surface via CSS variables |
| Card | Registration | Replace white bg with `var(--reg-surface)` |
| Dialog | Registration | Error states only — prefer inline errors |
| Badge | Both | Fare category chips, delay indicators |
| Progress | Terminal | Identifying state loading bar |

> **shadcn/ui dark mode note:** Do not use shadcn's built-in class-based dark mode toggle. Apply dark styles directly via CSS variables scoped to `.register-root` and `.terminal-root`. This avoids conflicts and gives full control over both themes simultaneously.

---

## 6. Do and don't

### Visual

| Do | Don't |
|----|-------|
| Use `clamp()` for terminal font sizes — scales with viewport | Use system fonts (Arial, system-ui) — they undercut quality |
| Let the success screen be full-bleed with no container | Add gradients to backgrounds — solid dark surfaces look more premium |
| Use JetBrains Mono for anything "computed" — fares, IDs, scores | Use more than 2 accent colours on one screen simultaneously |
| Cut the success screen background instantly (0ms) | Transition the background colour on the success screen — it must cut |
| Keep registration card padding generous — space = trust | Use toasts or notification popups on the terminal |

### Technical

| Do | Don't |
|----|-------|
| Use CSS custom properties for all theme values | Hardcode any colour or spacing value in a component |
| Scope CSS: `.terminal-root .x { }` and `.register-root .x { }` | Share theme state between /register and /terminal |
| Use `React.memo()` on terminal state components | Import Framer Motion or GSAP — bundle size matters for live demos |
| Keep animation durations as CSS variables — easy to tune | Use inline styles for animated properties — CSS transitions won't work |
| Add a 5-second cooldown after terminal scan attempts | `console.log()` in the camera frame loop — it runs at 5fps |

### Accessibility minimums

| Requirement | How |
|------------|-----|
| All interactive elements keyboard navigable | shadcn/ui handles this — do not remove focus styles |
| Error messages associated with inputs | `aria-describedby={errorId}` on each `<Input>` |
| Terminal state announced | `role="status" aria-live="polite"` on state container |
| Text contrast ≥ 4.5:1 | `--term-text #E2E8F0` on `--term-bg #080B12` = 16:1 ✓ |
| Camera permission denied handled | Show browser settings instructions — not a blank page |