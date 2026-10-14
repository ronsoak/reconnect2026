---
version: 1
slug: "templates-home-html"
primary_target: "templates/home.html"
related_targets: ["templates/base.html","templates/search.html","templates/about.html"]
---

# Reconnect public discovery

## Mode
Read

## Direction contract

THESIS: Reconnect is a game library for independent games writing: a broad discovery feed entered through real editorial cover art, not a product storefront or an undifferentiated link list.

OWN-WORLD: Use a soft cool-gray ground (#f5f5f2), ink (#24282e), ocean-blue actions (#45627a), and quiet dividers (#dfe2df). Cover-art windows and clean catalogue rows make the game-library reference legible; restrained rules and confident sans typography keep article titles and publication credits more important than artwork.

STORY: Readers scan a changing mix of tabletop and video-game writing, recognize each article's topic, date, and source before opening it, and can move between Dynamic, Newest, Popular, and Search. Category and focus filters stay explicit and persistent. Nothing should imply that Reconnect is a storefront or a social network.

FIRST VIEWPORT: On desktop, place the Reconnect wordmark and tagline at the left of a compact masthead, a flexible search field next, and About at the right. Put feed navigation and category/focus controls in a calm second rail, followed by a clear “Browse stories” heading and the first row of equal-width article tiles. On mobile, stack the brand and full-width search, keep feed navigation and filters reachable without horizontal overflow, and show a two-column grid immediately below the controls.

FORM: The chosen form is Game library browse, the safer-round-one direction, seed 98759c1f. Respect the existing equal-width-card rule: vary card height and cover-art area, never tile width. Keep the title and publication credit legible on every tile. Treat anchored multi-select filters and the dynamic feed's wide, footer-safe refresh control as the signature interactions. Carry this visual grammar across Dynamic, Newest, Popular, Search, and About; leave Django admin untouched.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
