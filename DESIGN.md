# DESIGN.md — Polestar Design Language (Polestar 2 NZ Tracker)

## Visual World: Scandinavian Precision & High-Density Automotive Utility

The interface takes cues directly from Polestar's design philosophy: austere Scandinavian minimalism, clean lines, purposeful typography, and quiet functional confidence. It strips away typical AI template artifacts (rainbow left borders, mixed serif/sans, novelty icons, excessive padding).

### 1. Typography
- **Primary Typeface**: `Inter`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `Roboto`, sans-serif.
- **Weights**: 400 (regular metadata), 500 (labels/chips), 600 (headers/titles), 700 (prices/key metrics).
- **Tabular Figures**: `font-variant-numeric: tabular-nums` enabled on all prices, dates, and metric counters for clean vertical scanning alignment.
- **Letter Spacing**: `-0.015em` on headings; `0.02em` on uppercase micro-badges.

### 2. Color Palette & Tokens
- **Dark Mode (Default & Polestar Signature)**:
  - Background Base: `#0E1114` (Deep charcoal, not pure black)
  - Surface Card / Row: `#161B22`
  - Border Subdued: `rgba(255, 255, 255, 0.08)`
  - Border Active: `rgba(255, 255, 255, 0.2)`
  - Foreground Main: `#F0F3F6`
  - Foreground Muted: `#8B949E`
  - Accent Swedish Gold (Polestar Performance damper/seatbelt gold): `#E5A93C`
  - Accent Subtle Gold BG: `rgba(229, 169, 60, 0.12)`
  - Price Drop Positive Green: `#3FB950`
  - Source Badges:
    - TradeMe: `#E26D24` / `rgba(226, 109, 36, 0.15)`
    - Facebook: `#4A72B2` / `rgba(74, 114, 178, 0.15)`

- **Light Mode**:
  - Background Base: `#F5F6F8`
  - Surface Card / Row: `#FFFFFF`
  - Border Subdued: `rgba(0, 0, 0, 0.08)`
  - Border Active: `rgba(0, 0, 0, 0.2)`
  - Foreground Main: `#161B22`
  - Foreground Muted: `#656D76`
  - Accent Swedish Gold: `#B87B14`
  - Accent Subtle Gold BG: `rgba(184, 123, 20, 0.1)`

### 3. Layout & Density
- High-density car hunting feed.
- Compact header with real-time status summary (total cars, source breakdown, last synced).
- Sticky, streamlined filter bar: search input with instant clear, quick filter pills (All, Favorites, Price Drops, New, Last 3 Days, TradeMe, Facebook).
- Car listing rows designed for rapid visual scanning:
  - Clean aspect-ratio thumbnail (16:10 / 100x64px) with subtle corner radius (4px).
  - Clear hierarchy: Year + Model Trim prominently displayed.
  - Price rendered in tabular digits with price drop delta badge.
  - Location + source tag + date scraped.
  - Outbound link with native arrow SVG indicator and star favorite button.
