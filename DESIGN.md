---
name: Reconnect
description: "A calm catalogue for independent writing about games."
colors:
  paper-ground: "#f5f5f2"
  white-surface: "#ffffff"
  mist-surface: "#e9eeeb"
  charcoal-ink: "#24282e"
  muted-slate: "#56616a"
  quiet-divider: "#dfe2df"
  ocean-blue: "#45627a"
  deep-ocean-blue: "#304b62"
  warm-advert-stock: "#eee9dc"
typography:
  display:
    fontFamily: "Manrope, sans-serif"
    fontSize: "clamp(1.9rem, 3.3vw, 2.7rem)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Manrope, sans-serif"
    fontSize: "1.04rem"
    fontWeight: 700
    lineHeight: 1.28
    letterSpacing: "-0.015em"
  search:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  filter:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.84rem"
    fontWeight: 600
    lineHeight: 1.2
  navigation:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.83rem"
    fontWeight: 600
    lineHeight: 1.5
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.075em"
rounded:
  compact: "0.3rem"
  control: "0.45rem"
  card: "0.75rem"
spacing:
  compact: "0.4rem"
  control-gap: "0.55rem"
  card-gap: "0.9rem"
  card-gap-wide: "1rem"
  card-gap-mobile: "0.65rem"
  section: "1.4rem"
components:
  button-primary:
    backgroundColor: "{colors.ocean-blue}"
    textColor: "{colors.white-surface}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0.44rem 1.15rem"
    height: "2.9rem"
  search-input:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.charcoal-ink}"
    typography: "{typography.search}"
    rounded: "{rounded.control}"
    padding: "0.4rem 0.65rem"
    height: "2.9rem"
  filter-control:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.charcoal-ink}"
    typography: "{typography.filter}"
    rounded: "{rounded.control}"
    padding: "0.36rem 0.78rem"
    height: "2.55rem"
  feed-tab-active:
    backgroundColor: "{colors.ocean-blue}"
    textColor: "{colors.white-surface}"
    typography: "{typography.navigation}"
    rounded: "{rounded.compact}"
    padding: "0.35rem 0.9rem"
    height: "2.1rem"
  article-card:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.charcoal-ink}"
    rounded: "{rounded.card}"
    padding: "0.9rem 1rem 1rem"
---

# Design System: Reconnect

## Overview

**Creative North Star: "A Game Library for Independent Writing"**

Reconnect presents independent games writing as a changing collection of
publication covers. The interface is editorial rather than retail: cover art
helps readers recognize a story, while its title, publication and date remain
the information used to scan and choose what to read.

The visual language is calm and catalogue-like. Cool paper tones, restrained
blue actions, clean rules and confident sans typography give varied sources a
shared frame without making the site feel like a storefront or social network.

**Key Characteristics:**
- Cover-led discovery with clear article attribution.
- Equal-width cards whose image area and height vary by size.
- Quiet, bordered surfaces instead of elevated or decorative panels.
- Column-first feed flow that keeps visual order aligned with keyboard order.

## Colors

The palette pairs cool paper and charcoal neutrals with a restrained ocean-blue
accent; a warmer paper tone is reserved for advert cards.

### Primary
- **Muted Ocean Blue** (`#45627a`): Primary actions, selected feed navigation,
  focus rings and article-category labels.
- **Deep Ocean Blue** (`#304b62`): The stronger interaction state for primary
  controls and article titles on hover or focus.

### Neutral
- **Cool Paper** (`#f5f5f2`): The page ground and quiet navigation surfaces.
- **White Surface** (`#ffffff`): Search, filter and article-card surfaces.
- **Mist Surface** (`#e9eeeb`): Missing-cover placeholders and disabled controls.
- **Charcoal Ink** (`#24282e`): Primary text and the Reconnect wordmark.
- **Muted Slate** (`#56616a`): Supporting text, dates and the page lede.
- **Quiet Divider** (`#dfe2df`): Borders and separators.
- **Warm Advert Stock** (`#eee9dc`): Advert image and placeholder areas.

**The Cover-First Rule.** Use cover art to signal an article's subject, but keep
its title, publication and date legible.

## Typography

**Display Font:** Manrope (with a sans-serif fallback)  
**Body Font:** DM Sans (with a sans-serif fallback)

**Character:** Manrope gives page headings and article titles a confident
editorial shape; DM Sans keeps controls, metadata and longer copy practical and
quiet.

### Hierarchy
- **Display** (700, `clamp(1.9rem, 3.3vw, 2.7rem)`, `1.12`): Page headings such
  as “Browse stories.”
- **Title** (700, `1.04rem`, `1.28`): Article titles on feed cards. Large cards
  may scale the title up to `1.45rem`.
- **Body** (400, `1rem`, `1.5`): General copy and ledes. Keep reading measures
  near the existing 65–70ch content widths.
- **Label** (700, `0.68rem`, `0.075em`, uppercase): Article categories and
  compact editorial labels.
- **Metadata** (400, `0.78rem`): Publication names and dates; dates use
  tabular numerals.

## Layout

The page uses a centered Bulma container around a full-width paper ground. The
masthead keeps the brand, search and About link together on wide screens; at
768px and below, the brand and About link sit above a full-width search field.
Feed controls form a separate rail, with the filters and feed navigation
stacking on smaller screens.

The feed is a CSS grid with two columns up to 768px, three from 769px and four
from 1024px, on a fixed `17rem` row unit. A small card fills one cell, a medium
card is one column wide and two rows tall, and a large card is two columns wide
and two rows tall. Dense packing lets small cards fill the gaps beside the
larger ones. Gaps are `0.65rem` on narrow screens, `0.9rem` by default and
`1rem` on wide screens.

Use generous space above page headings, tighter spacing inside controls and
cards, and consistent gutters between columns. Search results retain the same
compact card language without adverts; About uses a narrow reading measure.

**The Grid-Unit Rule.** Card sizes are whole multiples of one small cell; never
use arbitrary heights or widths.

## Elevation & Depth

The system is border-led and flat at rest. A quiet one-pixel divider defines
cards and controls; tonal differences distinguish the page, surface and
placeholder layers. Avoid adding shadows beneath these bordered surfaces.

## Shapes

Cards use a 12px radius. Search and filter controls use a smaller 7.2px radius,
with the active feed tab at 4.8px. Use clean rectangular catalogue forms rather
than pill-shaped panels. Cover art is clipped to the card's rounded top edge;
the card content remains on a white surface.

## Components

### Buttons
- **Shape:** Compact rounded rectangles (`0.45rem`).
- **Primary:** Ocean blue with white text; use for Search, Apply and the dynamic
  feed's refresh action.
- **Hover / Focus:** Hover deepens to deep ocean blue. Keyboard focus uses a
  visible 3px ocean-blue outline with offset.
- **Secondary:** White surface, charcoal text and a quiet divider border; use
  for filter and reset controls.

### Cards / Containers
- **Corner Style:** 12px for feed cards.
- **Background:** White, with a one-pixel quiet-divider border and no shadow.
- **Internal Padding:** `0.9rem 1rem 1rem` on wide screens, reduced on narrow
  screens.
- **Cover Art:** Use the publication image when valid. Missing or failed images
  receive a neutral placeholder; text-only cards stay small.
- **Size:** Small is 1x1, medium is 1x2 and large is 2x2 grid cells. The cover
  art fills the space left by the text.

### Inputs / Fields
- **Style:** White search field with charcoal text, quiet-divider border and
  `0.45rem` corners. The joined Search button shares the same control height.
- **Focus:** Keep the visible ocean-blue focus outline and caret.

### Navigation
- **Feed Tabs:** A bordered paper-tone rail with Dynamic, Newest and Popular
  links; the current feed uses an ocean-blue fill and white text.
- **Header:** Keep About directly available and the Reconnect wordmark linked
  to the home feed. Stack the search field below the brand on mobile.
- **Filters:** Category and Focus controls open anchored menus without shifting
  feed content. Keep Apply and Reset explicit.

### Refresh Control
- Keep the refresh action fixed to the lower edge on the Dynamic feed only.
  Widen it and lift it above the footer when the page reaches the footer.

## Do's and Don'ts

### Do:
- **Do** use real publication cover art as the visual entry point; keep the
  title, publication and date legible.
- **Do** size cards in whole grid cells: 1x1, 1x2 or 2x2.
- **Do** use ocean blue for primary actions and the selected feed.
- **Do** use a calm placeholder when a cover is missing or fails to load.

### Don't:
- **Don't** turn the feed into a storefront or social network.
- **Don't** add large shadows beneath bordered cards and controls.
- **Don't** give a text-only or broken-image article a medium or large size.
- **Don't** invent readership figures, testimonials or publication claims.
