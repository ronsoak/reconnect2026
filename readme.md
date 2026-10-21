# Reconnect

Reconnect is a Django website that aggregates writing about video games, TTRPGs, TCGs and board games. A script reads the RSS feeds of listed sites several times a day and saves new articles. Visitors come back to find new articles to read and new blogs to follow.

## Stack

- Python and Django
- Django REST Framework and django-filter
- django-unfold (admin theme)
- Bulma (vendored in `static/css/`) with a small `custom.css`
- SQLite for development, PostgreSQL planned for production (Railway)

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: create a .env file next to manage.py containing
# SECRET_KEY=your-secret-key

python manage.py migrate
python manage.py seed_db          # loads categories, tags, site types and other logic values
python manage.py createsuperuser
python manage.py runserver
```

- Site: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/backdoor/

## Tests

```bash
python manage.py test website
```

## Project layout

| Path | Purpose |
|------|---------|
| `website/models.py` | Logic, Sites, Articles, Logging, Clicks and Adverts models |
| `website/views.py`, `website/urls.py` | Pages, `robots.txt` and `sitemap.xml` |
| `website/feed.py` | Builds the dynamic, newest, popular and search feeds, used by both the pages and the API |
| `website/api.py`, `website/serializers.py` | The public JSON API |
| `website/management/commands/` | Scripts listed below |
| `templates/base.html` | Base layout every page extends |
| `templates/components/` | Reusable pieces: header, search bar, menu, filters, footer |
| `static/css/custom.css` | Styling Bulma cannot do |

## Public API

Reconnect has a read-only JSON API so other people can build on the same feed, for example a reader app, a bot or a personal dashboard. The website itself does not use it, it calls the same feed code directly. Anyone can use it without logging in, and the default limit is 120 requests a minute per visitor (`API_ANON_THROTTLE_RATE`).

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/feed/` | The article feed, with adverts |
| `/api/search/` | Search articles by title or site name |
| `/api/filters/` | Lists the category and tag ids the feed accepts |
| `/feeds/all.rss` | Up to `RSS_FEED_ITEM_LIMIT` newest dated public articles (default 150) |
| `/feeds/category/<category_id>.rss` | Same configured RSS limit, restricted to a category |

API endpoints accept `GET` only and return JSON. RSS endpoints return RSS XML.

RSS links route through Reconnect so article clicks from feed readers are included in click analytics.
Visit `/publications/` for the all-articles and category feeds, and to browse visible publications.
Publication pages list each site's visible articles and offer newest, popular, and random ordering.

### Feed parameters

| Parameter | Meaning |
|-----------|---------|
| `feed` | `dynamic` (default, a fresh mix of new, older and popular), `newest` or `popular` |
| `category` | A site type id from `/api/filters/`. Repeat it to choose several, they are treated as "or" |
| `tag` | A genre id from `/api/filters/`. Repeat it to choose several, they are treated as "or" |
| `page` | Page number. Only used by `newest` and `popular` |

A category choice together with a tag choice is an "and". The API does not use the website's saved-filters cookie. The parameters are the only input.

By default, `dynamic` returns about 100 cards in random order and gives a different batch each time. `newest` and `popular` return 100 cards per page along with `page`, `num_pages` and `count`. These API sizes can be configured independently of the website (see Runtime tuning below).

### Search parameters

| Parameter | Meaning |
|-----------|---------|
| `q` | Search words. An article only needs to match some of them, case does not matter |
| `page` | Page number, 250 results per page by default (`API_SEARCH_PAGE_SIZE`) |

Search ignores the filters and returns no adverts. Hidden articles and sites are never returned.

### Use cases

```bash
# List the category and tag ids
curl "http://127.0.0.1:8000/api/filters/"

# A fresh dynamic feed
curl "http://127.0.0.1:8000/api/feed/"

# The newest articles, second page
curl "http://127.0.0.1:8000/api/feed/?feed=newest&page=2"

# The most popular video game and card game articles about news
curl "http://127.0.0.1:8000/api/feed/?feed=popular&category=1&category=2&tag=5"

# Search for articles
curl "http://127.0.0.1:8000/api/search/?q=zelda+dragons"
```

### Response

Every card has a `kind` (`article` or `advert`), a `size` (`small`, `medium` or `large`) and an `item`.

```json
{
  "feed": "newest",
  "page": 1,
  "num_pages": 14,
  "count": 1304,
  "cards": [
    {
      "kind": "article",
      "size": "small",
      "item": {
        "id": 904,
        "title": "Article title",
        "url": "https://example.com/post",
        "image_url": "https://example.com/image.jpg",
        "published": "2026-10-06",
        "site": "Site name",
        "site_id": 114,
        "category": "Video Games"
      }
    },
    {
      "kind": "advert",
      "size": "medium",
      "item": {"id": 1, "message": "Advert text", "site_name": "Blog", "site_url": "https://blog.example.com"}
    }
  ]
}
```

`size` is a layout hint for the website's grid, so other apps can ignore it. Clicks, boosts and hidden flags are never exposed. An unknown `feed` value returns a `400` error.

Tests live in `website/tests/`. Run them all with `python manage.py test website`, or one file with `python manage.py test website.tests.test_api`

## Runtime tuning

Set these optional variables in the local `.env` file, or in Railway's Variables
tab. The local file includes descriptive comments and is ignored by Git.
Environment variables take precedence over the file. Restart/redeploy the web
service and any affected command/cron services after changes; this is not a
live admin configuration. Missing variables use the defaults below.

All counts and pool sizes must be positive integers. Day windows can be zero.
Percentages must each be 0-100 and total at most 100. Invalid values stop startup
with a configuration error naming the setting.

Operational upper bounds are enforced at startup, not silently clamped:

| Settings | Maximum |
|---|---:|
| Website/API Dynamic and ordered feed sizes | 1,000 |
| Website/API search page sizes | 1,000 |
| Publications directory and individual-publication page sizes | 500 |
| Total browsable articles per publication | 10,000 |
| RSS items | 1,000 |
| Dynamic popular and Highlight Reel candidate pools | 10,000 |
| Weekly/monthly newsletter top counts | 1,000 |
| Ticker titles | 100 |
| Random minimum age, ticker lookback and Bluesky lookback | 3,650 days |

These are configuration guardrails, not performance guarantees. Dynamic rounding
can still exceed its configured target slightly; widgets remain additional.
API request rates retain their positive-count/unit validation without an upper
ceiling. All existing defaults remain unchanged.

### Public response sizes

| Variable | Default | Meaning |
|---|---:|---|
| `WEB_DYNAMIC_FEED_SIZE` | 100 | Dynamic website card target, including adverts but excluding widgets |
| `WEB_ORDERED_FEED_PAGE_SIZE` | 100 | Newest/Popular website cards per page, including adverts |
| `API_DYNAMIC_FEED_SIZE` | 100 | Independent Dynamic API card target |
| `API_ORDERED_FEED_PAGE_SIZE` | 100 | Independent Newest/Popular API cards per page |
| `WEB_SEARCH_PAGE_SIZE` | 250 | Website search results per page |
| `API_SEARCH_PAGE_SIZE` | 250 | API search results per page |
| `API_ANON_THROTTLE_RATE` | `120/min` | Anonymous API requests per visitor/IP; positive count per second, minute, hour or day, e.g. `30/second` |
| `PUBLICATIONS_PAGE_SIZE` | 100 | Publications directory entries per page |
| `PUBLICATION_ARTICLES_PAGE_SIZE` | 50 | Articles per individual publication page |
| `PUBLICATION_ARTICLES_LIMIT` | 250 | Total articles browsable per publication, for every sort mode |
| `RSS_FEED_ITEM_LIMIT` | 150 | Newest dated public articles per all-articles/category RSS feed |

Dynamic percentage rounding can put the feed slightly above its target; tight
filters and limited eligible articles can return fewer cards. Widgets are
additional to the website quota. Search sizes limit each page, not the total
number of matches. A publication page size larger than its total limit results
in one page. API pagination metadata reflects the configured size and adverts
still take slots from the ordinary article quota.

### Editorial selection

| Variable | Default | Meaning |
|---|---:|---|
| `FEED_NEW_PERCENT` | 50 | Newest-article share of Dynamic article slots, web and API |
| `FEED_RANDOM_PERCENT` | 30 | Older-random share; Popular receives the remaining percentage |
| `FEED_RANDOM_MIN_AGE_DAYS` | 7 | Random articles must be strictly older than today minus this many days; zero means before today |
| `FEED_POPULAR_POOL_SIZE` | 100 | Top-ranked pool sampled for the Dynamic popular bucket; grows to its quota if needed |
| `NEWSLETTER_WEEKLY_TOP_COUNT` | 30 | Maximum weekly top-by-clicks articles |
| `NEWSLETTER_MONTHLY_TOP_COUNT` | 60 | Maximum monthly top-by-clicks articles |
| `TICKER_ARTICLE_COUNT` | 10 | Maximum unique articles selected for the ticker |
| `TICKER_LOOKBACK_DAYS` | 7 | Ticker dates from today minus this many days through today, inclusive |
| `HIGHLIGHT_POOL_SIZE` | 50 | Top current-month Article/RSS click leaders from which the reel samples up to three |
| `BLUESKY_LOOKBACK_DAYS` | 7 | Eligible publication dates from today minus this many days through today, inclusive |

Zero ticker/Bluesky lookback selects today only. Hidden-content, date, filtering,
deduplication and per-site posting rules still apply. These settings do not change
card sizes, advert spacing, widget spacing, the five Newest Sites, the three-card
reel layout, or the one-article-per-run Bluesky limit. Newsletter counts affect
only the top section; all remaining eligible articles are still exported.
Weekly and monthly counts may be equal without changing their labels.

API throttling uses Django's configured cache; its existing local-memory default
is per process, not a shared deployment-wide limiter.
Tests: `python manage.py test website.tests.test_configuration`.

## Editing the About page

The shared header keeps the logo and navigation on its top row, with a full-width
search row underneath at all screen sizes. The entire header, including feed
options when present, stays pinned to the top while scrolling. Its markup is in
`templates/components/header.html` and layout is in `static/css/custom.css`.
The logo is `static/images/branding/reconnect_full_title.svg`; its width scales
with the screen via `.site-brand__logo`.
Site colours are CSS variables at the top of `static/css/custom.css`, matching
the brand palette in agents.md. Highlight Reel and ticker backgrounds use the
full-strength brand green (#00ef6c), with dark headings and ticker text.
The feed options bar joins Category/Focus and
Apply/Reset into two pairs, with rounded outer ends and square inner corners.
On phones both pairs expand to fill their row, while dropdown panels fit below it.
Apply uses the same light background as Reset. The search placeholder is hidden
at phone widths (768px and below); entered search text remains visible.
Category labels render through
`templates/components/category_pill.html` as a coloured dot followed by the
category name. It adds a `category-pill--<slug>` class (e.g.
`category-pill--video-games`) that sets the dot colour; add a matching rule in
custom.css when a new category is created, otherwise the dot is neutral grey.
The header's second row shows the subtitle and the public article count (the
same count as the footer).
The main menu (`templates/components/menu.html`) shows Home, Publications and
About as outlined round buttons, highlighting the current section. At 768px and
below `static/js/menu.js` collapses them behind a hamburger toggle (Escape or an
outside click closes it); without JavaScript the links stay visible.
`static/js/header.js` measures its responsive height so anchor/focus scrolling
clears it and filter dropdowns fit the remaining viewport.

The About page is assembled in `templates/about.html` from five components:
`about_intro.html`, `about_newsletter.html`, `about_using.html`, `about_contact.html` and `about_credits.html`
in `templates/components/`. Edit those components to replace the draft copy.
Marked placeholders reserve space for the Bluesky profile, Substack welcome letter
and newsletter signup, and personal credits. No external embeds load until you add
their official embed code. Counts are calculated from public articles and their
distinct publications, independently of feed filters and cached site article counts.

## Contact form

The About page ends with a contact form (`templates/components/about_contact.html`)
that posts to `/about/contact/`. Visitors give a name, email, a reason (Advertising,
Suggest a site or Other) and a message. Each message is saved as a
`ContactMessage` (admin: **Contact messages**, with a **Handled** tick box) and
emailed to `CONTACT_EMAIL`, with the visitor as the Reply-To. A failed email never
loses the message; the admin shows **Email sent** for each one.

Spam protection lives in `website/contact.py`:

- **Honeypot**: a hidden `website` field. Bots that fill it see a fake success and nothing is saved.
- **Signed timer**: messages sent within 3 seconds of loading, or after 2 hours, are rejected.
- **Rate limit**: 3 messages per visitor per hour, using a hashed IP in the cache. No IP is stored.
- **Cloudflare Turnstile**: verified server-side. The script only loads on About.

Without Turnstile keys the check is skipped while `DEBUG` is on, and the form
refuses messages when `DEBUG` is off. Locally, emails print to the runserver
terminal. Settings: `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `CONTACT_EMAIL`,
`CLIENT_IP_HEADER`, `CONTACT_RATE_LIMIT` and the `EMAIL_*` variables (see
`deployment_guide.md`). The default cache is per-process memory, so with several
web workers the rate limit is per worker until Redis is added.

## Editing the footer

The shared footer lives in `templates/components/footer.html`, with layout in
`static/css/custom.css`. Its article count uses the same public-article query as
About and ignores filters. `static/js/footer.js` adds a one-time entrance when the
count enters view; the final number remains readable without JavaScript or with
reduced motion enabled.

## Privacy policy

`/privacy/` is linked from the footer only and included in the sitemap. Its
modular templates describe actual click fields, filter/repeat-click cookies,
Django session/CSRF cookies, external images, Google Fonts and Substack.
It explicitly flags unfinished hosting-log/backup retention and automated
click-maintenance scheduling rather than promising a deletion deadline.
It also covers the About-page contact form: what it stores, the hashed-IP rate
limit, Cloudflare Turnstile and manual message deletion. Complete the operational
details, review the copy before launch, and revisit it when adding embeds.
This page is not a consent banner or a guarantee of legal compliance.

## Article cards

Public article cards show the publication name but no publication date, including
Dynamic, Newest, Popular, search, publication feeds and Highlight Reel. Stored
dates remain available for sorting, RSS, the API and newsletter exports.

## Floating feed buttons

Dynamic, Newest and Popular share `templates/components/floating_actions.html`
and `static/js/floating_actions.js`. A back-to-top button appears once the first
screen has scrolled away; it scrolls smoothly (instantly with reduced motion) and
moves keyboard focus to the Reconnect home link. The Dynamic feed also shows the
Refresh the mix button beside it, which widens and centres near the bottom. The
group lifts above the footer so it never covers it.

## Newest Sites widget

Dynamic, Newest and Popular include `templates/components/newest_additions.html`, titled
"Newest Sites", on a brand-green background at 50% opacity with dark text.
On tablet and desktop it is a medium
(one column by two rows) card; on the two-column phone grid it spans the full
row at one row tall. It lists up to five public publications
with public articles, newest site ID first, respecting Category and Focus
filters. Links open each publication's article page.

The widget is additional to the article/advert quota. On each refresh its
position is randomly chosen from 11 through 50 (or the end of a shorter feed),
after at least ten existing cards. Feeds with fewer than ten cards omit it.
Search and publication-specific feeds do not include it.
Placement refers to source/card order; the dense responsive grid may fill gaps
with later cards.

## Article ticker

Dynamic, Newest and Popular include up to `TICKER_ARTICLE_COUNT` random public articles
(default ten), published from today minus `TICKER_LOOKBACK_DAYS` (default seven)
through today inclusive, respecting Category and Focus. Titles link through the
normal article click tracker. There is no visible heading. The ticker uses the
full-strength brand-green background (#00ef6c) with dark text.

`templates/components/article_ticker.html` renders a static list without
JavaScript. `static/js/feed_widgets.js` coordinates its full-width row with the
other widgets; `static/js/ticker.js` only manages the scrolling text.
The ticker waits for a filled, flat grid boundary near its randomized target
rather than forcing a break with empty cells. It is additional to the card quota.

Titles are separated by `|`. Motion is a linear CSS transform at about 40 pixels
per second and pauses on mouse hover, without a visible pause button.
Keyboard focus presents a static, horizontally
scrollable list. Reduced motion presents a wrapped static list. Repeated visual
titles are excluded from screen readers and the tab order. No recent matching
articles means no ticker; search and publication-specific feeds do not include it.

## Highlight Reel and widget spacing

Dynamic, Newest and Popular sample up to three articles from the top
`HIGHLIGHT_POOL_SIZE` (default 50) by **clicks
received during the current calendar month**, regardless of publication date
or lifetime rank. Both Article and RSS click events count; advert clicks do not.
Only public articles matching Category and Focus qualify. Articles without a
click this month are excluded. This uses current-month `Clicks` records, not
`Analytics` snapshots, avoiding double-counting when a month is aggregated.
Keep current-month click records; the normal purge policy retains them.

The full-width Highlight Reel uses existing article cards and local image
fallbacks. All three cards display together in equal-width columns when the
widget has at least 600px of available width; on phones they become a swipeable
row that snaps one card at a time, with the next card peeking in.
There are no carousel controls; native horizontal scrolling and snapping work
without JavaScript on narrow layouts.
Horizontal divider lines frame a full-strength brand-green background with a dark
heading and inset padding. Highlight images cover the full
card, with white text over a dark bottom scrim (at least 82% black behind text)
for readable contrast even on bright artwork. Regular feed cards are unchanged.
Missing/broken images retain the existing local fallback and text-card behavior.

Widgets are additional to the ordinary card quota. Their source positions are
planned independently on every page, including later pagination pages on Newest
and Popular, without changing the ordinary articles' ordering or pagination. Positions are
spread across the feed, jittered, and their order shuffled on refresh; Newest
Additions stays after 10-49 ordinary cards. There must be at least **10 ordinary
article/advert cards and two fully occupied grid rows between visible widgets**.
The shared layout recalculates on resize and ordinary card image failures,
reserving clean full-width rows for the ticker and reel. Targets may move later,
up to the next widget, to find a completely filled boundary. If no natural
boundary exists, the planner tries the fewest size reductions among up to eight
nearby medium/large article cards. The first card and adverts are never resized.
Ordinary card order, counts and pagination are preserved; nothing is duplicated
or pulled forward. Small cards can fill beside Newest Sites on tablet and desktop.
Responsive recalculation starts from the original sizes, so temporary reductions
do not persist when the new layout no longer needs them.

Short feeds first omit excess widgets in this priority order: retain Newest
Additions, then ticker, then Highlight Reel. Fewer than ten ordinary cards
omits all widgets. The browser omits later widgets if their targets cannot meet
the complete-row spacing rule or a gap-free boundary at that viewport. With JavaScript disabled,
source-order card spacing remains, but exact filled-row spacing is not measured.
No monthly clicked articles means no reel.

Run the grid planner regression tests with:
`node --test website/tests/js/feed_widgets.test.cjs`.

## Management scripts

Each script has its own usage examples at the top of its file. Add `--dry-run` where it is offered to preview changes.

| Script | Purpose |
|--------|---------|
| `seed_db` | Fills the Logic model from the seed file |
| `import_sites --file sites.csv` | Creates or updates sites from a CSV |
| `import_articles articles.csv` | Imports articles from a CSV |
| `batch_sites` | Puts sites into ingest batches |
| `ingest_all` | Ingests every batch (`--batch N` for one batch) |
| `ingest_batch` | Fetches articles for one batch, called by `ingest_all` |
| `count_articles` | Updates the article count per site |
| `last_article` | Updates the days since each site's last article |
| `hide_sites` | Hides sites with no recent articles and marks them dormant |
| `check_dormant_sites` | Checks hidden dormant sites for newer RSS entries and reactivates them |
| `post_bluesky` | Posts one eligible article to Bluesky, oldest first; supports `--dry-run` |
| `hide_articles` | Hides or unhides articles to match their site's setting |
| `filter_articles` | Hides articles that match keywords in the Logic model |
| `age_articles` | Lowers article rank so popular articles do not stay on top |
| `aggregate_clicks` | Totals last month's clicks into the Analytics model (`--month 2026-09`, `--month current`, `--dry-run`). Run it before purging clicks |
| `purge_clicks` | Deletes the month of Clicks that is four months old (keeps about 90 days). Refuses unless Analytics already matches. `--dry-run`, `--month`, `--force` |

### Dormant publication recovery

Run `python manage.py last_article` before `hide_sites`. Sites hidden by
`hide_sites` are marked **Dormant**, allowing a monthly recovery check:

```sh
python manage.py check_dormant_sites --dry-run
python manage.py check_dormant_sites
# Check one publication, or throttle a manual run:
python manage.py check_dormant_sites --site 5 --dry-run
python manage.py check_dormant_sites --limit 10 --request-timeout 15
```

Only sites with both **Site Hidden** and **Dormant** checked are fetched, using
the same guarded HTTP fetcher as ingest. The command compares the newest dated
RSS/Atom entry against the latest stored publication date, including hidden
articles. A site without any stored dates can recover if its feed has a dated
entry. Undated entries never count as evidence of renewed activity.

Recovery clears Site Hidden, Dormant, and Load Error, then runs `hide_articles`
for that publication. Individually hidden articles stay hidden. Site recovery
and the article sync are transactional; a sync failure rolls back recovery.
The command does not import articles: the next scheduled ingest does that.
Ingest normally looks back 14 days; use `ingest_all --days 365` if you deliberately
want to backfill older entries after recovery.

The admin **Hidden** bulk action clears Dormant so manually excluded sites are
not recovered. When editing a hidden site directly, clear **Dormant** to exclude
it from automatic recovery. Existing hidden sites are **not** marked dormant by
the migration: opt in only the ones you know were hidden for inactivity.

Feed fetch failures are reported to stderr and recorded under **Dormant Sites
Check** in Logging; other sites are still checked, and the command exits with an
error status if any fetch failed. Parse/undated-entry warnings appear in command
output. `--dry-run` checks feeds but writes nothing, including no logs.
The `--limit` option selects the first eligible sites by ID, not a rotating batch;
leave it unset for the monthly job.

### Bluesky article posting

Set these environment variables (or add them to your ignored local `.env`):

```dotenv
BLUESKY_IDENTIFIER=your-account.bsky.social
BLUESKY_APP_PASSWORD=your-app-password
```

Use a Bluesky **app password**, not your main account password. Never commit it
or paste it into logs. The command currently targets Bluesky-hosted accounts
through `https://bsky.social`; custom/self-hosted PDS accounts are not supported.

```sh
# Safe preview: no credentials, network calls, uploads, or database writes.
python manage.py post_bluesky --dry-run
# Live: posts at most one article.
python manage.py post_bluesky
```

Each run selects the oldest unposted public article with a publication date from
today minus `BLUESKY_LOOKBACK_DAYS` (default seven) through today (inclusive), breaking ties by creation time
and ID. Undated/future articles and hidden articles/publications are excluded.
Sites with **Auto Post** disabled are excluded unless the article has **Manual
Post** enabled; that override never bypasses hiding.

Posts contain `🟨 Reconnect Recommends:`, then `✍️ By: <publication>` with an
optional clickable Bluesky mention on the same line, then a lowercase category
hashtag without spaces or a trailing apostrophe-s, each separated by a blank line:

```
🟨 Reconnect Recommends:

✍️ By: Example Blog, @example.bsky.social

#videogames
```
 Store only the publication's handle in Sites.bluesky (an initial
`@` is accepted), not a profile URL. Handle resolution failures stop the run
rather than silently omitting a requested mention.

The article URL/title is embedded as a rich link. Its image is downloaded through
the guarded fetcher; absent, invalid, inaccessible or oversized images produce
a warning and use a stable local image from `static/images/article-fallbacks/`.
Thumbnails are flattened to JPEG and compressed below 1 MB. Missing/broken local
fallbacks or upload errors stop the run without marking the article posted.

Before any publishing request, an additive `Articles.bluesky_rkey` field stores
a reserved AT Protocol timestamp ID. Retries check that exact record key and
reconcile a post already created before marking Articles.bluesky true. This
protects against overlapping runs and a crash between Bluesky acceptance and
the database save. Do not clear reserved keys or delete remote posts expecting
automatic reposting. Keep one production database/account pair; do not run live
posting from a copied/staging database against the same account.

Errors are surfaced in stderr with a non-zero exit status; the oldest failing
article stays at the head of the queue for correction. Credentials and remote
error response bodies are not printed. Dry-run shows planned text and link,
but does not validate handles or download/preview thumbnails.

Schedule `post_bluesky` every 15 minutes (`*/15 * * * *`) only after checking one
live post manually. Each run creates **at most one** new post; an empty queue
does nothing. Articles expire from the queue after the lookback window, so one
post every 15 minutes has a maximum capacity of 96 articles per day.
Custom promotional/newsletter posts are not part of this command.

## Deploying

1. Commit all migrations in `website/migrations/`.
2. Set `SECRET_KEY` and the other environment variables on the host.
3. Run `python manage.py migrate --noinput`.
4. Run `python manage.py seed_db`, then the import scripts.

### Uploaded images (advert images)

Railway wipes the container's disk on every deploy, so uploads must live on a Volume:

1. In Railway, add a Volume to the service and mount it at `/data`.
2. Set the environment variable `MEDIA_ROOT=/data/media`.
3. Upload advert images in the admin as normal. They are saved to the volume and served from `/media/`.

Locally, with no `MEDIA_ROOT` set, uploads go to the `media/` folder next to `manage.py`. Back up the volume as well as the database.

`reconnect/settings.py` is still a development configuration (`DEBUG`, `ALLOWED_HOSTS`, SQLite). Harden it before going live.
