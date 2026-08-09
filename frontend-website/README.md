# XIE Alumni Hackathon — Bid to Build (Frontend)

> **BID TO BUILD** · Presented by **XIE Alumni Committee**
>
> Hackathon × Live Auction × Poker Table × Technology Event

This repository contains the **public-facing frontend** for the XIE Alumni
Hackathon. It is a **presentation-only** layer: the UI reflects the official
"Bid to Build" poster aesthetic. No backend, database, or real authentication
is implemented here.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Available Scripts](#available-scripts)
- [Navigation & Routes](#navigation--routes)
- [Project Structure](#project-structure)
- [Homepage Section Order](#homepage-section-order)
- [Visual Assets / Image Locations](#visual-assets--image-locations)
- [How to Replace a Homepage Image](#how-to-replace-a-homepage-image)
- [Where to Change Things](#where-to-change-things)
- [Content Configuration](#content-configuration)
- [Design System & Theme](#design-system--theme)
- [Responsiveness](#responsiveness)
- [Accessibility](#accessibility)
- [Current Limitations](#current-limitations)
- [License](#license)

---

## Tech Stack

| Layer          | Choice                        |
| -------------- | ----------------------------- |
| UI Library     | React 18                      |
| Language       | TypeScript (strict)           |
| Build Tool     | Vite 5                        |
| Styling        | Tailwind CSS v3               |
| Routing        | React Router v6               |
| Icons          | Lucide React                  |
| Fonts          | Space Grotesk, JetBrains Mono |

---

## Getting Started

Requires **Node.js** and **npm**.

```bash
# 1. Install dependencies
npm install
```

> **Note (Windows / npm `allow-scripts`):** `esbuild` has a postinstall script
> that may be blocked by npm's `allow-scripts` policy. If the Vite build fails
> with an esbuild-related error, approve it first:
>
> ```bash
> npm approve-scripts esbuild
> ```

```bash
# 2. Start the dev server (http://localhost:5173)
npm run dev
```

---

## Available Scripts

| Script              | Description                                  |
| ------------------- | -------------------------------------------- |
| `npm run dev`       | Start the Vite dev server with HMR           |
| `npm run build`     | Type-check (`tsc -b`) then production build  |
| `npm run preview`   | Preview the production build locally         |
| `npm run typecheck` | Run the TypeScript type-checker only         |

---

## Navigation & Routes

Routes are defined in `src/App.tsx` under a shared `PublicLayout`
(`src/layouts/PublicLayout.tsx`):

| Path      | Component    | Notes                                                  |
| --------- | ------------ | ------------------------------------------------------ |
| `/`       | `HomePage`   | Full landing page with all sections                    |
| `/event`  | `EventsPage` | Event details page                                     |
| `/login`  | `LoginPage`  | Presentation placeholder, no auth                      |
| `*`       | `HomePage`   | Fallback to home                                       |

Navbar items (`src/components/layout/PublicNavbar.tsx`) and footer links:

| Nav item      | Target       | On click sidebar                      |
| ------------- | ------------ | ------------------------------------- |
| **Home**      | `/`          | navigates to home, scroll to top      |
| **Event**     | `/event`     | navigates to the Event page           |
| **Timeline**  | `/#timeline` | scrolls to the Timeline section       |
| **Rules**     | `/#rules`    | scrolls to the Rules section          |
| **How It Works** | `/event`  | navigates to the Event page           |
| **Login**     | `/login`     | navigates to the placeholder Login    |

Anchor / hash scrolling is handled by `ScrollToHash.tsx` and `ScrollToTop.tsx`
(mounted in `PublicLayout`), plus `smoothScrollToTop()` in `src/utils/scroll.ts`.
Both helpers respect `prefers-reduced-motion`.

---

## Project Structure

```text
.
├── index.html                      # Entry HTML, fonts, meta
├── package.json
├── vite.config.ts
├── tailwind.config.js              # Theme color tokens → Tailwind utilities
├── postcss.config.js
├── public/
│   └── spade.svg                   # Favicon (poker-spade motif)
└── src/
    ├── main.tsx                    # React entry (BrowserRouter)
    ├── App.tsx                     # Route definitions
    ├── index.css                   # Tailwind + theme imports
    ├── vite-env.d.ts               # Vite/TS client types (PNG imports)
    ├── styles/
    │   └── theme.css               # CSS variables + base + utilities
    ├── config/
    │   └── eventContent.ts         # Centralized event copy / rules config
    ├── utils/
    │   └── scroll.ts               # Shared smooth-scroll helpers
    ├── layouts/
    │   └── PublicLayout.tsx        # Navbar + main + contact + footer + scroll handlers
    ├── components/
    │   ├── common/                 # Reusable presentational components
    │   │   ├── NeonButton.tsx
    │   │   ├── GlassCard.tsx
    │   │   ├── StatusBadge.tsx
    │   │   ├── SectionHeading.tsx
    │   │   ├── ScrollToTop.tsx
    │   │   └── ScrollToHash.tsx
    │   ├── layout/                 # Site-wide public chrome
    │   │   ├── PublicNavbar.tsx
    │   │   ├── ContactSection.tsx
    │   │   └── PublicFooter.tsx
    │   └── home/                   # Homepage sections (see order below)
    │       ├── HeroSection.tsx
    │       ├── AboutSection.tsx
    │       ├── EventDetailsSection.tsx
    │       ├── RulesSection.tsx    # Rules of the Table (Round 1, Wild Card, Round 2, Evaluation)
    │       ├── RoyaltySection.tsx  # The Twist – Royalty Bonus
    │       ├── TimelineSection.tsx # Event Timeline (#timeline)
    │       ├── FAQSection.tsx
    │       ├── FinalCtaSection.tsx
    │       ├── RuleCards.tsx       # Card image components (AuctionCard, RoundTwoCard, etc.)
    │       ├── RuleUI.tsx          # Shared rule blocks / lists / highlight
    │       └── FinalScoreExample.tsx # Sample final-score formula widget
    └── pages/
        └── public/
            ├── HomePage.tsx        # Composes all home sections
            ├── EventsPage.tsx      # Event detail / how-it-works page
            └── LoginPage.tsx       # Placeholder (no auth)
```

---

## Homepage Section Order

`src/pages/public/HomePage.tsx` renders sections in this order:

1. Hero
2. About
3. Event Details
4. Rules (`#rules`) — Round 1, Wild Card, Round 2 Build, Evaluation, Score Example
5. Royalty (“The Twist” — Royalty Bonus)
6. Timeline (`#timeline`)
7. FAQ
8. Final CTA

Contact and footer are provided by `PublicLayout`.

---

## Visual Assets / Image Locations

Fallback: pre-built **artwork PNGs** live in `src/components/home/`. The
imports are centralized in `src/config/../components/home/RuleCards.tsx`
(`src/components/home/RuleCards.tsx`).

| Asset        | File (path)                    | Used by component (`RuleCards.tsx` export) | Rendered in                                | Notes                          |
| ------------ | ------------------------------ | ------------------------------------------ | ------------------------------------------ | ------------------------------ |
| Round 1      | `src/components/home/round1.png`      | `AuctionCard`                               | `RulesSection.tsx` (Section A)             | 1122×1402 px                   |
| Wild Card    | `src/components/home/wildcard.png`    | `WildCardCard`                              | `RulesSection.tsx` (Section B Wild Card)   | 1054×1492 px                   |
| Round 2      | `src/components/home/round2.png`      | `RoundTwoCard`                              | `RulesSection.tsx` (Section C Build)       | —                              |
| Evaluation   | `src/components/home/evaluation.png`  | `EvaluationCard`                            | `RulesSection.tsx` (Section D Evaluation)  | —                              |
| Royalty      | `src/components/home/royalty.png`     | `RoyaltyCard`                               | `RoyaltySection.tsx` (Twist/Royalty)       | 581×961 px                     |

**Every image** is imported only through `src/components/home/RuleCards.tsx`;
the other components reference the exported card components (`AuctionCard`,
`WildCardCard`, `RoundTwoCard`, `EvaluationCard`, `RoyaltyCard`).
PNG imports are typed via `src/vite-env.d.ts` (`/// <reference types="vite/client" />`).

---

## How to Replace a Homepage Image

1. Add the new artwork at the same path (e.g. overwrite
   `src/components/home/round1.png`).
2. Ensure the filename + extension match the import statement in
   `src/components/home/RuleCards.tsx` (or update the import).
3. Re-run `npm run dev`; the image is used `object-contain` so it scales inside
   its card frame (aspect ratio is preserved; very tall/wide images may leave
   empty space).

> To add an entirely new card, export a new component from `RuleCards.tsx`
> (mirroring the pattern of `AuctionCard`) and render it from a section
> component.

---

## Where to Change Things

| What you want to change            | Where to look                                                                 |
| ---------------------------------- | ----------------------------------------------------------------------------- |
| Event name, date, venue, contact, copies | `src/config/eventContent.ts` (`eventContent`, `aboutPoints`, etc.)           |
| Auction parameters (coins, top-5, wildcards, bonus statements) | `auctionConfig` in `src/config/eventContent.ts` |
| Rules / gold-words                | `roundOneRules`, `wildcardRules`, `roundTwoSteps`, `evaluationCriteria` in `src/config/eventContent.ts` + `GOLD_TERMS` in `src/components/home/RuleUI.tsx` |
| Homepage section order            | `src/pages/public/HomePage.tsx`      |
| Rules rendering/layout            | `src/components/home/RulesSection.tsx`, `src/components/home/RuleUI.tsx`, `src/components/home/RuleCards.tsx` |
| Royalty / “The Twist” section     | `src/components/home/RoyaltySection.tsx` (uses `royaltyHowItWorks`) |
| Timeline steps                    | `eventFlowSteps` in `src/config/eventContent.ts`; rendered by `src/components/home/TimelineSection.tsx` |
| Navigation labels/destinations    | `src/components/layout/PublicNavbar.tsx`, `PublicFooter.tsx` |
| Route paths                       | `src/App.tsx`                            |
| Theme colors, glow, fonts, utilities | `src/styles/theme.css` + `tailwind.config.js` |

---

## Content Configuration

All public copy, event details, timelines, rules, FAQ, and contact info are
centralized in **`src/config/eventContent.ts`**.

Highlights of exported data:

- `eventContent` — brand, tagline, date, time, venue, `teamSize` (“2–4
  Members”), contact phone/email, event summary.
- `auctionConfig` — starting coins (1000), Top 5 winners, timer range, example
  team count, wildcard counts (3 wildcards, 3 bonus statements).
- Rule arrays — `roundOneRules`, `wildcardRules`, `roundTwoSteps`,
  `evaluationCriteria`, `royaltyHowItWorks`, all as `RuleItem[]`
  (`{ title, description, icon }`).
- `eventFlowSteps` — timeline steps used by `TimelineSection`.
- `royaltyScoreExample` — Example final-score numbers shown by
  `FinalScoreExample`.
- `faqItems` — FAQ data.
- Types — `RuleItem`, `RuleIconKey`, `FaqItem`.

Update it once and every section reflects the change.

---

## Design System & Theme

Color values are defined in `src/styles/theme.css` as RGB triplets on `:root`
and mapped to Tailwind utilities in `tailwind.config.js`. **Do not scatter raw
hex values across components** — use the theme tokens.

| Token            | Value      | Tailwind usage                                  |
| ---------------- | ---------- | ----------------------------------------------- |
| `--bg-main`        | `#05030A`  | `bg-bg-main`                                    |
| `--bg-secondary`   | `#090411`  | `bg-bg-secondary`                               |
| `--surface`        | `#0D0618`  | `bg-surface`                                    |
| `--purple`         | `#8200FF`  | `text-purple`, `bg-purple`                      |
| `--purple-bright`  | `#B419FF`  | `text-purple-bright`                            |
| `--purple-neon`    | `#DA32FF`  | `text-purple-neon`, `bg-purple-neon`            |
| `--gold`           | `#D6A23D`  | `text-gold`, `bg-gold`                          |
| `--gold-bright`    | `#F2C969`  | `text-gold-bright`                              |
| `--text-main`      | `#F8F5FF`  | `text-ink-main`                                 |
| `--text-muted`     | `#B9AEC8`  | `text-ink-muted`                                |
| `--success`        | `#4ED68F`  | `text-success` / timeline marker                |
| `--danger`         | `#FF5279`  | `text-danger` / `border-danger`                 |

**Fonts:** `font-display` (Space Grotesk) and `font-mono` (JetBrains Mono).

**Glow shadows:** `shadow-glow-purple`, `shadow-glow-purple-lg`,
`shadow-glow-gold`, `shadow-glow-soft`.

**Custom utilities:**
- `bg-hex-grid` — subtle purple hexagonal network pattern.
- `bg-noise` — faint grain overlay.
- `text-gradient-purple` / `text-gradient-gold` — clipped text gradients.

**Scroll behavior:** `html { scroll-behavior: smooth; }` with
`scroll-padding-top: 5.5rem` so anchors clear the sticky navbar, and
`prefers-reduced-motion` handled site-wide.

---

## Responsiveness

- Layouts verified around **375, 430, 768, 1024, and 1440 px**.
- `body { overflow-x: hidden }` — no horizontal overflow.
- Navbar collapses to a hamburger menu below `lg`.
- Hero display headings use `clamp()`.
- Cards, timelines, and grids stack naturally via responsive layouts.

---

## Accessibility

- Adequate text contrast using the theme tokens.
- Visible keyboard focus (`:focus-visible`).
- Semantic buttons/navs and `aria-label`s.
- Accessible hamburger menu (mobile navman).
- FAQ is a collapsible button list with `aria-expanded`.
- `prefers-reduced-motion` respected.

---

## Current Limitations

- **Presentation-only harness.** No backend, database, authentication, or
  real-time data.
- **Rules are static content.**
- The **Login** page is a visual placeholder only.
- This is not the bidding/judging engine; it simply presents the poster
  content for the public site.

---

## License

See `LICENSE` in the repository root.