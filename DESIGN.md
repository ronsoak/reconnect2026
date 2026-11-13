---
name: Reconnect
description: "A calm catalogue for independent writing about games."
colors:
  paper-ground: "#f5f6f2"
  white-surface: "#ffffff"
  mist-surface: "#dbdbd9"
  charcoal-ink: "#353032"
  muted-slate: "#5c5759"
  quiet-divider: "#d3d2cf"
  charcoal-action: "#353032"
  deep-charcoal: "#1f1b1d"
  brand-green: "#00ef6c"
  category-video-games: "#0013ff"
  category-ttrpg: "#ffe422"
  category-tabletop: "#8c2918"
  category-tcg: "#ffa1d2"
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
    fontSize: "0.9rem"
    fontWeight: 600
    lineHeight: 1.2
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0.075em"
rounded:
  compact: "0.3rem"
  control: "0.45rem"
  card: "0.3rem"
  pill: "999px"
spacing:
  compact: "0.4rem"
  control-gap: "0.55rem"
  card-gap: "0.9rem"
  card-gap-wide: "1rem"
  card-gap-mobile: "0.65rem"
  section: "1.4rem"
components:
  button-primary:
    backgroundColor: "{colors.charcoal-action}"
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
    rounded: "{rounded.pill}"
    padding: "0 1.1rem"
    height: "2.55rem"
  feed-tab-active:
    backgroundColor: "{colors.charcoal-action}"
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

Reconciled with the delivered stylesheet and components on 13 November 2026.
[static/css/custom.css](static/css/custom.css) and the approved shared components
are the implementation reference; older concept images do not override them.
The current site is explicitly light-only. A deliberate dark theme remains future work.

## Overview

**Creative North Star: "A Game Library for Independent Writing"**

Reconnect presents independent games writing as a changing collection of
publication covers. The interface is editorial rather than retail: cover art
helps readers recognize a story, while its title, publication and categories
remain the information used to scan and choose what to read. Regular cards do
not display publication dates.

The visual language is calm and catalogue-like. Light paper tones, dark-grey
actions, sparing brand green, clean rules and confident sans typography give varied sources a
shared frame without making the site feel like a storefront or social network.

**Key Characteristics:**
- Cover-led discovery with clear article attribution.
- Grid-unit cards spanning one or two columns, with image area and height varying by size.
- Quiet, bordered surfaces instead of elevated or decorative panels.
- Source-order article markup with responsive grid packing; widget placement must
  preserve ordinary article order and keyboard access.

## Colors

The palette pairs light paper and dark-grey neutrals with sparing green highlights;
a warmer paper tone is reserved for advert cards.

### Primary
- **Dark Grey** (`#353032`): Primary text, actions, selected navigation and focus rings.
- **Deep Charcoal** (`#1f1b1d`): The stronger interaction state for primary
  controls and article titles on hover or focus.
- **Brand Green** (`#00ef6c`): Use sparingly, including the ticker and Highlight Reel.
  Keep dark text on green, not green body text on light surfaces.
- **Categories:** Video Games `#0013ff`, TTRPGs `#ffe422`, Tabletop `#8c2918`,
  TCGs `#ffa1d2`. Do not invent a Geek Culture colour.

### Neutral
- **Light Paper** (`#f5f6f2`): The page ground and quiet navigation surfaces.
- **White Surface** (`#ffffff`): Search, filter and article-card surfaces.
- **Alternate Grey** (`#dbdbd9`): Alternate surfaces.
- **Charcoal Ink** (`#353032`): Primary text.
- **Muted Text** (`#5c5759`): Supporting text and the page lede.
- **Quiet Divider** (`#d3d2cf`): Borders and separators.
- **Warm Advert Stock** (`#eee9dc`): Advert image and placeholder areas.

**The Cover-First Rule.** Use cover art to signal an article's subject, but keep
its title, publication and categories legible.

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
- **Metadata** (400, `0.78rem`): Publication attribution, not a visible publication date.

## Layout

The page uses a centered Bulma container around a full-width paper ground. The
masthead keeps the logo, Home/Publications/About navigation, tagline, public
article count and search together. Search occupies a full-width row. At 768px and
below, navigation collapses behind the menu toggle; without JavaScript links remain visible.
Feed controls form a separate rail, with the filters and feed navigation
stacking on smaller screens.

The feed is a CSS grid with two columns up to 768px, three from 769px and four
from 1024px, on a fixed `17rem` row unit. A small card fills one cell, a medium
card is one column wide and two rows tall, and a large card is two columns wide
and two rows tall. Dense packing lets small cards fill the gaps beside the
larger ones. Widget-containing grids use row flow plus a responsive JavaScript
planner that moves only widgets and preserves ordinary card order. Keep the
no-JavaScript fallback. Gaps are `0.65rem` on narrow screens, `0.9rem` by default and
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

Cards use a `0.3rem` radius. Search controls use `0.45rem`; navigation and filter
buttons use pill-shaped outer edges. Joined pairs have flat inner edges.
Cover art is clipped to the card's rounded top edge;
the card content remains on a white surface.

## Components

### Buttons
- **Shape:** Follow the component: search controls are compact rectangles;
  navigation and paired filters use rounded outside edges.
- **Primary:** Dark grey with white text for dark primary actions.
- **Hover / Focus:** Keep component-specific feedback and visible dark focus
  outlines with offset.
- **Secondary:** White surface, charcoal text and a quiet divider border; use
  for filter controls and both Apply/Reset. Category/Focus and Apply/Reset are
  joined pairs, not four separate pills.

### Cards / Containers
- **Corner Style:** `0.3rem` for feed cards.
- **Background:** White, with a one-pixel quiet-divider border and no shadow.
- **Internal Padding:** `0.9rem 1rem 1rem` on wide screens, reduced on narrow
  screens.
- **Cover Art:** Use the publication image when valid. Missing or failed images
  use a stable local fallback from `static/images/article-fallbacks/` when one is
  available; otherwise keep a small text-only card. Preserve broken-image
  handling and image eligibility; do not introduce a new placeholder requirement.
- **Size:** Small is 1x1, medium is 1x2 and large is 2x2 grid cells. The cover
  art fills the space left by the text.

### Inputs / Fields
- **Style:** White search field with charcoal text, quiet-divider border and
  `0.45rem` corners. The joined Search button shares the same control height.
- **Focus:** Keep the visible dark focus outline and caret.

### Navigation
- **Feed Tabs:** A bordered paper-tone rail with Dynamic, Newest and Popular
  links; the current feed uses a dark fill and white text.
- **Header:** Keep the shared logo, search and Home/Publications/About links.
  The header article count animates for 250ms with reduced-motion support;
  header/footer counts use separators and share one request-local total.
- **Filters:** Category and Focus controls open anchored menus without shifting
  feed content. Keep Apply and Reset explicit. Escape restores the owning trigger's
  focus; outside dismissal must not steal focus from the clicked control.
- **Publications:** Default to Random; preserve its URL token through pagination
  while retaining explicit alphabetical/newest sorts and the styled native select.

### Refresh Control
- Keep the refresh action fixed to the lower edge on the Dynamic feed only.
  Widen it and lift it above the footer when the page reaches the footer.

## Do's and Don'ts

### Do:
- **Do** use real publication cover art as the visual entry point; keep the
  title, publication and categories legible.
- **Do** size cards in whole grid cells: 1x1, 1x2 or 2x2.
- **Do** use the delivered brand/category tokens and preserve approved controls.
- **Do** use a stable local fallback cover when available; otherwise use the
  existing small text-only behaviour when no usable cover is available.

### Don't:
- **Don't** turn the feed into a storefront or social network.
- **Don't** add large shadows beneath bordered cards and controls.
- **Don't** give a text-only or broken-image article a medium or large size.
- **Don't** invent readership figures, testimonials or publication claims.
