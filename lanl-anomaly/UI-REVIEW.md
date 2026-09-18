# UI-REVIEW.md — LANL Anomaly Detection Live Demo

## 6-Pillar Visual Audit

**Overall Score: 15/24** — Functional but generic. Login page is the only page with real personality.

---

## Pillar 1: Copywriting — **3/4**

**Strengths:**
- Login terminal copy is bussin: `auth@gateway:~$ authenticate --user` + `UNAUTHORIZED ACCESS IS MONITORED AND PROSECUTED`
- `VERIFY CREDENTIALS` button CTA matches terminal theme
- `SECURE CHANNEL // ENCRYPTED // MONITORED` footer reinforces atmosphere

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| `login.html:318` | `{{ dev_codes[username] }}` renders TOTP code again instead of role name. Shows "756413" next to the code column | BUG |
| `employee.html:155` | "flagged for review" — flagged by who? The system? passive voice weakens the message | Minor |
| `employee.html:166` | `ALLOW // 0.0 // MONITORED` — raw score means nothing to an employee. Remove or reword | Minor |
| Dashboard nav | No active page indicator — "where am I?" | Medium |
| Dashboard KPI | "FALSE POSITIVES" — insider threat context: these are ALLOW decisions that were actually threats. Label is technically correct but jargon-heavy | Minor |

**Recommendations:**
- Fix login role bug: `{{ roles[username] }}` or inline the role
- Employee page: drop the score from footer, employees don't need it
- Dashboard: add active nav state, consider "Benign Alerts" instead of "False Positives"

---

## Pillar 2: Visuals — **2/4**

**Strengths:**
- Login page terminal window is clean — dots, title bar, CRT glow
- KPI cards have colored left borders for semantic meaning (red/amber/green)
- Charts load and render correctly

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| `employee.html` | Both ALLOW and BLOCK use a green checkmark/X icon. BLOCK should use red | HIGH |
| `employee.html` | No entry animation — page just appears. Feels flat | HIGH |
| `employee.html` | 80%+ of page is empty black space. Content is a tiny center column | Medium |
| Dashboard | 5th KPI "THRESHOLD" is cut off on viewport — grid overflow | HIGH |
| Dashboard | Score Distribution chart is tiny, unreadable in full-page view | Medium |
| Dashboard | Heatmap, Alerts, Live Logins sections not visible in viewport — buried below fold | Medium |
| Dashboard | No skeleton/loading states while data loads | Minor |
| Dashboard nav | Nav is just text — no visual hierarchy, no active state, no logout | Medium |

**Recommendations:**
- BLOCK page: red X icon (currently green), red glow, screen shake or flash animation
- ALLOW page: scale-in animation on checkmark, subtle green pulse
- Dashboard: fix KPI grid to 4 columns or make 5th card smaller
- Dashboard: prioritize Live Logins at top (it's the live demo showcase)
- Add skeleton loaders for charts
- Add active nav indicator (underline or highlight)

---

## Pillar 3: Color — **3/4**

**Strengths:**
- Consistent dark palette: `#0a0a0f` bg, `#111118` surface
- Semantic colors used correctly: red=threat, amber=flag, green=allow
- `#00ff41` matrix green is iconic for the terminal theme
- Glassmorphism nav with `backdrop-filter` is clean

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| `employee.html:46-50` | ALLOW icon uses green but BLOCK icon (line 79-83) ALSO uses green for the X. Color doesn't match decision | HIGH |
| `style.css:399` | `.decision-ALLOW` uses `rgba(0, 255, 65, 0.1)` — slightly different green than `--green: #22c55e`. Two greens in the system | Minor |
| Dashboard | Timeline chart is all red — no contrast between normal and threat periods. Needs a baseline color | Minor |
| Score Distribution | Chart bars are all red. Gray bars for normal are invisible against dark bg | Minor |

**Recommendations:**
- BLOCK icon: `filter: drop-shadow(0 0 30px rgba(239, 68, 68, 0.3))` — red glow
- Unify greens: use `--green: #00ff41` everywhere or `#22c55e` everywhere
- Timeline chart: use `--accent: #5e6ad2` for baseline, `--red` for threats
- Score Distribution: make gray bars slightly brighter (`#3d3d46` → `#4a4a55`)

---

## Pillar 4: Typography — **3/4**

**Strengths:**
- JetBrains Mono is perfect for terminal theme
- Plus Jakarta Sans + Clash Display combo for dashboard is premium
- Font scale is reasonable: 32px KPI, 18px section titles, 13px body
- `font-variant-numeric: tabular-nums` on numbers — correct

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| `login.html` | Only loads JetBrains Mono. Dashboard loads Plus Jakarta Sans + Clash Display. Employee page only loads JetBrains Mono. Inconsistent font loading | Minor |
| Dashboard | Section titles use `font-family: var(--font-display)` but KPI labels use `var(--font-body)`. The display font barely differs from body at 18px | Minor |
| Employee page | All text is monospace. "Access granted. Session authenticated." would feel better in a clean sans-serif | Minor |

**Recommendations:**
- Employee page: load Plus Jakarta Sans for body text, keep JetBrains Mono for the prompt/CTA
- Consider bumping section titles to 20-22px for more hierarchy
- Or: commit fully to terminal theme everywhere (all JetBrains Mono)

---

## Pillar 5: Spacing — **2/4**

**Strengths:**
- Consistent token system: `--space-xs` through `--space-3xl`
- KPI cards have good internal padding
- Section margins are consistent

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| `employee.html` | Content is centered vertically but the container has `padding: 48px` — feels cramped on large screens, content floats in void | Medium |
| Dashboard | KPI row uses `grid-template-columns: 28% 22% 18% 20% 12%` — hardcoded percentages, 5th card gets 12% which is too narrow for "0.187195" | HIGH |
| Dashboard | Gap between KPI row and timeline chart is `--space-xl` (32px) — feels tight for the visual weight | Minor |
| Dashboard | Score Distribution + Top 10 Attackers split uses `7fr 5fr` — distribution chart is too small | Medium |
| Login | Form fields have `gap: 16px` between them — could be tighter (12px) | Minor |

**Recommendations:**
- Employee page: increase container max-width to 600px, add more vertical breathing room
- Dashboard KPI: use `repeat(4, 1fr)` and put threshold in a smaller 5th card, or merge with another
- Dashboard charts: `5fr 7fr` (give attackers more space) or stack them
- Login form: tighten field gap to 12px

---

## Pillar 6: Experience Design — **2/4**

**Strengths:**
- Login flow works: username → password → TOTP → redirect
- Dev codes shown in login for easy testing
- Employee page shows clear ALLOW/BLOCK state
- Dashboard auto-refreshes live events every 2s

**Findings:**
| Location | Issue | Severity |
|----------|-------|----------|
| Employee BLOCK | No explanation of WHY access was denied. Just "flagged for review" — user has no idea what happened | HIGH |
| Employee ALLOW | No context about session — where are they going? What can they do? | Medium |
| Employee both | No transition between login → result. Just a page load. Should feel like a system response | HIGH |
| Dashboard | No way to filter alerts, search users, or drill into events | Medium |
| Dashboard | Live Logins panel is at the very bottom — the most interesting part for a demo is buried | HIGH |
| Dashboard | No empty state — what happens when there are 0 live events? | Minor |
| Dashboard | No loading skeleton — page flashes empty then populates | Minor |
| All pages | No keyboard shortcuts, no escape to logout | Minor |

**Recommendations:**
- BLOCK page: add "Threat score: 0.78 — anomalous behavior detected" or similar
- ALLOW page: add "Redirecting to secure workspace..." with a countdown
- Add page transition animation (fade or terminal-style "loading..." → result)
- Move Live Logins to top of dashboard (it's the demo hero)
- Add search/filter to alerts table
- Add skeleton loaders for charts

---

## Priority Fix List

### P0 — Ship Blockers
1. **BLOCK icon is green** — `employee.html:79-83` uses green glow for the X. Change to red.
2. **KPI grid overflow** — 5th card cut off. Fix grid layout.
3. **Live Logins buried** — move to top of dashboard for demo impact.

### P1 — High Impact
4. **Employee page has no animation** — add entry animation (scale-in, fade, terminal "loading")
5. **BLOCK page has no threat context** — show score + "anomalous behavior detected"
6. **Login role bug** — `dev_codes[username]` shows TOTP instead of role
7. **No active nav state** — add underline/highlight on current page
8. **No skeleton loaders** — charts flash empty then populate

### P2 — Polish
9. **Employee page typography** — mix monospace + sans-serif
10. **Score Distribution chart unreadable** — fix bar visibility
11. **Timeline chart all red** — add baseline color
12. **Dashboard nav missing logout** — add logout button
13. **Tighten login form spacing** — 16px → 12px between fields

---

## Overall Verdict

The login page is genuinely good — terminal aesthetic, scanlines, CRT glow, cursor blink. It sets the tone.

Everything after login falls off a cliff. The employee page is a blank screen with a checkmark. The dashboard is functional but generic — it looks like every other dark-themed admin template. The live demo's best moment (seeing an attacker get BLOCKED in real-time) has zero drama.

**The gap:** Login promises a cinematic cybersecurity experience. Employee and dashboard deliver a bland admin panel.

**Fix priority:** Animation + drama on employee page, move live events front-and-center on dashboard, fix the visual bugs (green X on BLOCK, KPI overflow).
