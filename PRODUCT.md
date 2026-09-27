# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A single vehicle buyer in New Zealand actively monitoring and evaluating used and dealer inventory of Polestar 2 electric fastbacks across TradeMe Motors and Facebook Marketplace.

## Product Purpose

Provide an immediate, frictionless feed of all active Polestar 2 cars for sale in New Zealand. Eliminates manual searching across disparate marketplaces, tracks price changes/drops over time, accurately classifies battery and motor trim levels, and links directly to original listings.

## Positioning

Unlike generic automotive search engines or ad-saturated portals, this is an austere, high-density personal vehicle hunting tool tailored exclusively to the Polestar 2 market in New Zealand, with instant local market metrics and persistent triage.

## Operating Context

- **Environment**: Desktop and mobile web browser for quick daily check-ins.
- **Data Flow**: Scheduled Python scrapers (`Playwright` + SQLite) aggregate Facebook Marketplace and TradeMe Motors, exporting static JSON/JS bundles consumed client-side by a static web application hosted on GitHub Pages.
- **Workflow**: Open tracker -> review new additions or price drops in top ribbon -> scan high-density vehicle feed -> star favorites / classify trim -> open outbound vehicle listing to inspect or contact seller.

## Capabilities and Constraints

- **Confirmed Functionality**:
  - Live scraping & deduplication of TradeMe Motors and Facebook Marketplace.
  - Automatic detection of price reductions with historical delta badges.
  - Drivetrain classification (`SRSM`, `LRSM`, `LRDM`, `Performance`) with client-side override persistence (`localStorage`).
  - Personal favorite bookmarks stored locally.
  - Instant text filter and pill filters (`All`, `Price Drops`, `Saved ★`, `New`, `Last 3 Days`, `TradeMe`, `Facebook`).
  - Secondary market intelligence tab (variant price breakdown, price distribution, year depreciation curve, regional distribution).
- **Roadmap Capabilities**:
  - Detailed equipment package identification (Pilot / Pilot Lite, Plus Pack, Performance Pack).
- **Constraints**:
  - Client-side static execution for hosting on GitHub Pages without persistent server requirement.
  - Zero decorative fluff or generic AI template clutter; high information density.

## Brand Commitments

- Polestar design language inspiration: Scandinavian minimalism, monochromatic dark canvas, hairline borders, and subtle Swedish gold accents (`#E5A93C`) matching Polestar Performance dampers and seatbelts.
- Clear geometric typography (`DM Sans` stack) with tabular numerals on all numeric and monetary figures.

## Evidence on Hand

- Live scraped SQLite database (`polestar.db`) and static datasets (`data/listings.json`, `data/listings.js`, `data/run_meta.json`).
- Production deployment setup via GitHub Actions workflow (`.github/workflows/scrape.yml`) and containerized scraper (`Dockerfile`).

## Product Principles

1. **Cars First, Zero Friction**: The user is looking at cars to buy. The feed must be dense, clear, and visible the instant the page loads.
2. **Scanability Over Decoration**: Data density, high contrast, and tabular alignment outrank novel UI gimmicks and decorative cards.
3. **True Vehicle Identity**: Highlight the exact trim, year, and options that actually drive Polestar valuation (drivetrain, battery size, option packs).
4. **Resilient Portability**: Run seamlessly as a standalone static dashboard while staying synchronized with automated scraper runs.
