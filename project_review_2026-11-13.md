# Reconnect: implementation review and improvement plan

**Reviewed:** 13 November 2026  
**Code baseline:** `78a1258` - animated the article count  
**Purpose:** identify worthwhile improvements and removable bloat, without changing application behaviour.

**Follow-up, 13 November 2026:** F02, F03, F04, F05, F06, F07, F09 and F10 are implemented.
F01 (production preparation) and F08 (shared-cache policy) remain open; optional cleanup
has not been performed. Original findings and audit results below describe the reviewed
baseline, not the current status of the completed items.

## Executive summary

**Reconnect does not need a rewrite.** The Django/template approach, small JavaScript layer,
shared feed helpers and existing management commands are appropriate for this product.
Much of the apparent complexity implements deliberate requirements: mixed-size cards,
advert spacing, filtered widgets, import safeguards and historical analytics.

The highest-value work is:

1. Finish and rehearse production configuration.
2. Make random ordering stable across a pagination journey. **Implemented in the follow-up.**
3. Return keyboard focus when a filter dropdown closes. **Implemented.**
4. Fix the Clicks admin search and make ingestion refresh failures observable. **Implemented.**
5. Agree whether newsletter rankings should include RSS clicks. **Confirmed and implemented.**
6. Correct the stale About assertion and reconcile documentation. **Implemented.**

The original audit identified **10 findings: 3 P1 and 7 P2**, plus three small cleanup candidates.
Eight findings have since been actioned; the two operational items remain open.
None justifies deleting a delivered feature or introducing a new application framework.
The cleanup opportunities are mostly generated files, unused scaffolding and one duplicate index.

### Reading the priorities

- **P0:** immediate blocker to ordinary operation. None identified in the exercised local workflows.
- **P1:** address before public launch; production readiness or significant browsing/keyboard behaviour.
- **P2:** targeted correction or conditional operational improvement.
- **P3:** optional cleanup, not a reason to delay launch.
- **S / M / L:** small local change / coordinated change / operational work package.
  These are scope estimates, not delivery promises.

| ID | Priority | Recommendation | Effort | Change risk |
| --- | --- | --- | --- | --- |
| F01 | P1 | Complete production settings, serving and operational verification | L | High if deployed without rehearsal |
| F02 | P1 | **Implemented:** preserve one random ordering across pagination | M | Medium |
| F03 | P1 | **Implemented:** restore filter-trigger focus on Escape | S | Low |
| F04 | P2 | **Implemented:** fix the Clicks admin search field | S | Low |
| F05 | P2 | **Implemented:** combine website and RSS newsletter clicks | S-M | Medium: editorial ranking changes |
| F06 | P2 | **Implemented:** surface ingestion's final count-refresh failure | S | Low |
| F07 | P2 | **Implemented:** align article redirects with publication visibility | S | Low-medium: old links change behaviour |
| F08 | P2 | Decide shared-cache policy before adding web workers | M | Medium |
| F09 | P2 | **Implemented:** calculate the shared article count once per request | S | Low |
| F10 | P2 | **Implemented:** correct stale tests and conflicting documentation | S-M | Low |

## What was reviewed and verified

The review covered the principal implemented paths, not every historical revision:

| Area | Evidence reviewed |
| --- | --- |
| Browsing | Dynamic/Newest/Popular selection, filtering, publication pages, pagination, visibility and search |
| Frontend | Shared components, responsive grid/widget responsibilities, controls, count animation and existing JS tests |
| RSS and API | Feed links, separate RSS clicks, categories, public-query rules and existing tests |
| Operations | Import/ingest, image helpers, maintenance, dormant recovery, Bluesky and cron documentation |
| Analytics | Baselines, aggregation/purge guards, reports, exports, provisional data and completion state |
| Editorial/admin | Newsletter selection, model/admin configuration and contact handling |
| Deployment/maintenance | Settings, dependencies, tracked build output, schema consistency and documentation |

### Original audit validation (before fixes)

| Check | Result |
| --- | --- |
| `.venv/bin/python manage.py test website --verbosity 1` | **364 tests: 363 passed, 1 failed** |
| `node --test website/tests/js/*.test.cjs` | **10 passed** |
| `.venv/bin/python manage.py check` | Passed |
| `.venv/bin/python manage.py check --deploy` | Six warnings: `security.W004`, `W008`, `W009`, `W012`, `W016`, `W018` |
| `.venv/bin/python manage.py makemigrations --check --dry-run` | No changes detected |
| `.venv/bin/python -m pip check` | No broken requirements |

The Django failure was an obsolete About-page placeholder assertion, not a missing signup feature.
Mocked SMTP/Turnstile failure logs appeared during tests; these were not additional test failures.

Additional runtime checks used **isolated synthetic SQLite databases**, not working data:

- Reproduced the Clicks admin search exception.
- Confirmed RSS-only clicks receive zero newsletter-period clicks.
- Confirmed the duplicate Analytics indexes exist.
- Checked the actual failure produced by a management command returning integer `1`.
- Checked how raw-click removal affects newsletter calculations, then verified that the normal
  purge retention prevents this affecting the current/previous-month UI.

A temporary browser fixture exercised Home, Newest, Publications and Search at
**320, 390, 768 and 1280 CSS pixels**: all 16 requests returned 200, with no document-level
horizontal overflow in that fixture. Escape/focus behaviour was tested directly.
External HTTPS resources were blocked during these checks; fixtures used image-free synthetic
articles. This is not a full cover-art, advert, font-loading, browser-engine or physical-device test.
The temporary server and database were removed afterward.

### Follow-up validation after implementation

- **375 Django tests passed:** `.venv/bin/python manage.py test website --verbosity 1`.
- **12 JavaScript tests passed:** `node --test website/tests/js/*.test.cjs`.
- Django system checks passed; migration consistency reported **no changes detected**.
- `git diff --check` passed.
- An isolated browser fixture used the actual filter component, CSS and JavaScript.
  At **390 and 1280 CSS pixels**, both Category and Focus returned focus to their
  own visible trigger on Escape, closed their panel and reset `aria-expanded`.
  Clicking an outside input closed each panel without stealing its focus.
  The fixture returned HTTP 200; its attached server was stopped afterward.
- No models, migrations, dependencies, production configuration or working data
  were changed. No imports, purges or remote posting were run.

The obsolete About assertion is fixed; the complete Django suite now passes.
These results do not replace staging acceptance, physical-device checks or
production verification. The local development guide [agents.md](agents.md) and
product context [PRODUCT.md](PRODUCT.md) were updated but remain Git-ignored;
they were not force-added and will not be included by an ordinary commit.

### Important limits

- The original read-only review changed no application code, models, migrations or working data.
- No production import, purge, posting, email delivery or deployment was performed.
- Railway services, schedules, HTTPS/proxy behaviour, backup restoration and production keys
  were not inspected. Repository settings are not proof of deployed settings.
- This is not a penetration test, exhaustive accessibility certification or production load test.
- Performance opportunities below distinguish duplicate/unbounded work visible in code from
  latency that has actually been measured.

## Detailed findings

### F01 [P1] Production preparation remains a real launch work package

**Evidence:** [settings](reconnect/settings.py#L24),
[database configuration](reconnect/settings.py#L88),
[static/media configuration](reconnect/settings.py#L127),
[media route](reconnect/urls.py#L23), [dependencies](requirements.txt).

Debug is hard-coded on, hosts are local-only and the database is SQLite.
The manifest does not declare a PostgreSQL driver or production application server.
Uploaded media is routed through Django's development file-serving view even outside development.
The deployment check also reports missing HTTPS/cookie protections and a secret-key quality warning.
Those warnings describe this local configuration, not verified production exposure.

**Impact:** a successful local run is not yet a reproducible production release.
Settings, serving, persistent uploads and infrastructure must agree.

**Recommendation:**

- Introduce validated, environment-driven production settings, including the intended PostgreSQL connection.
- Declare the production server and its start command.
- Establish static serving and a production-suitable media strategy; preserve uploaded advert images.
- Configure trusted proxy/HTTPS and secure cookies deliberately. Do not enable HSTS preload blindly.
- Rehearse migrations, import/baseline ordering, backup restoration and a rollback.
- Verify cron completion/alerts, SMTP delivery and Turnstile in the intended environment.

**Acceptance:** a staging deployment passes the deployment checks, serves static/uploaded files,
survives a restart, completes a scheduled job and restores a backup successfully.
**Effort/risk:** L; split into approved deployment steps, not one large refactor.

### F02 [P1] Random pagination can repeat or omit publications/articles

**Status: implemented, 13 November 2026.** Both views now use a bounded URL token and
deterministic database ordering, with a primary-key tie-breaker. Pagination preserves the token,
filters and sort, including the capped publication-article selection. New visits without a token
shuffle again; malformed Random tokens return HTTP 400. No session-stored ID lists or migrations
were added. Content changes can still move page boundaries; this is not a frozen data snapshot.

**Evidence:** [shared ordering](website/views.py#L51),
[publication ordering](website/views.py#L359),
[publication-article ordering](website/views.py#L394).

At the audit baseline, both used database random ordering before pagination. Each request could generate a different
ordering, so page 2 is not necessarily the continuation of page 1. This is especially relevant now
that Publications defaults to Random. A passing test that checks `order_by("?")` does not test
cross-page continuity.

**Impact:** readers may see an item again and never encounter another item while paging.

**Recommendation:** retain Random, but carry a randomisation token through the pagination links
and use a deterministic ordering for that token. A fresh browsing journey can choose a fresh order.
Keep an explicit tie-breaker and preserve filters and the selected sort.
Avoid a large session-stored list of every article merely to implement this.

**Acceptance:** with an unchanged dataset, following every page for one token produces no
duplicates or omissions; a fresh token can change the order. Explicit alphabetical/newest sorts
and filter/reset behaviour remain correct.
**Effort/risk:** M; a focused ordering/pagination change, not a feed rewrite.

**Follow-up verification:** all 43 Publications/configuration tests passed, including traversal
through rendered Next/Previous links, separate-client continuation, filter preservation, fresh
shuffles, invalid tokens and the article limit. Django checks and whitespace checks passed.

### F03 [P1] Escape closes a filter menu without restoring keyboard focus

**Status: implemented.** Escape restores the owning trigger before hiding the menu.
Outside dismissal does not move focus. Focused JavaScript regressions cover both paths.

**Evidence:** [menu hiding](static/js/filters.js#L6),
[Escape handler](static/js/filters.js#L42).

In the original browser fixture, focusing a category checkbox and pressing Escape set the trigger's
`aria-expanded` to false, but left the focused element as an input with no visible client rectangle.

**Impact:** keyboard users lose the visible focus location after dismissing the dropdown.
This is a demonstrated keyboard usability problem; the review does not claim a complete WCAG result.

**Recommendation:** when Escape closes the dropdown containing focus, return focus to its
own trigger. Do not unexpectedly move focus when a menu closes because the user clicked elsewhere.

**Acceptance:** a keyboard test opens Category/Focus, moves to a checkbox, presses Escape
and finds focus on the correct trigger with the menu closed.
**Effort/risk:** S / low. Follow with a small UI hardening and polish pass, not a redesign.

### F04 [P2] Searching the Clicks admin raises an exception

**Status: implemented.** Search uses `type__value`. Regression requests exercise RSS,
Article and Advert names, case-insensitive matches, blank searches and unmatched searches.

**Evidence:** [ClicksAdmin.search_fields](website/admin.py#L132).

At the audit baseline the admin searched `type` directly, but that field is a foreign key.
A runtime probe reproduced:

> FieldError: Unsupported lookup 'icontains' for ForeignKey or join on the field not permitted.

**Impact:** the search box on the raw Clicks page fails instead of helping inspect click records.

**Recommendation:** search a meaningful related field such as `type__value`, with any additional
article-ID/publication searches chosen deliberately. Keep raw records available for investigation.

**Acceptance:** searching for RSS/Article/Advert returns matching records without an exception;
blank and unmatched searches work.
**Effort/risk:** S / low.

### F05 [P2] Newsletter rankings and analytics use different click-source definitions

**Status: implemented with owner approval.** Weekly/monthly recaps combine Article and RSS
events in the selected period, excluding adverts. Preview and Markdown explain the metric.
Regression coverage includes RSS-only and mixed-source rankings and out-of-period events.

**Evidence:** [newsletter counts](website/newsletter.py#L94),
[report click types](website/analytics_reports.py#L94),
[newsletter tests](website/tests/test_newsletter.py#L97).

At the audit baseline the newsletter counted raw `Article` clicks only; analytics combined `Article` and `RSS`.
In an isolated fixture, an eligible article with an RSS click received `week_clicks=0`
and did not reach the newsletter's clicked-article top section.

**Impact:** an article can show activity in reports but appear to have no period clicks in the recap.
Existing newsletter tests do not establish an RSS policy.

**Recommendation:** agree the editorial definition. Combining Article and RSS is the most
consistent choice if the recap means all recorded reader click-throughs. If website-only interest
is intentional, label it accordingly rather than silently presenting the metrics as equivalent.
This is a policy decision, not a reason to change historical totals.

**Acceptance:** add an RSS-only case and a mixed-source ranking case; keep advert clicks,
hidden content and recap exclusions out of the selection.
**Effort/risk:** S-M / medium because the chosen articles can change.

### F06 [P2] Ingestion can finish successfully after its count refresh fails

**Status: implemented.** Refresh errors raise `CommandError`, retaining completed imports.
The failure message explains full-count recovery; incremental updates must not be replayed blindly.
A mocked-child regression verifies the failure and retained imported article without network activity.

**Evidence:** [post-ingest count refresh](website/management/commands/ingest_all.py#L138).

At the audit baseline the wrapper caught exceptions from its final `count_articles --mode mini` call and printed them,
without making the overall run fail.

**Impact:** an operator or cron monitor may see a successful process with stale publication counts.
Successfully imported articles should not be discarded, but the incomplete refresh should be visible.

**Recommendation:** raise a clear `CommandError` after preserving completed imports, or explicitly
define and monitor this as a partial-success outcome. Test the wrapper's result, not just its log text.

**Acceptance:** simulate a failed refresh and verify an observable failed/partial run and a safe retry.
**Effort/risk:** S / low.

### F07 [P2] Ordinary and RSS article redirects apply different publication visibility rules

**Status: implemented with owner approval.** Ordinary links now also check `site__hidden=False`.
A regression verifies immediate 404, no new click and unchanged stale article flags.

**Evidence:** [ordinary redirect](website/views.py#L212),
[RSS redirect](website/views.py#L233), [shared visibility](website/feed.py#L118).

At the audit baseline the ordinary redirect checked article flags but not `site__hidden=False`.
The shared public queryset and RSS redirect do check the publication itself.
An old direct article link can therefore still redirect and record a click while its publication is
hidden but its cached `site_hide` flag has not yet been synchronised.

**Impact:** visibility depends on the route and timing of maintenance.

**Recommendation:** apply the same publication-hidden check to the ordinary redirect, consistent
with the current public-content policy. Confirm that changing old-link behaviour is acceptable.

**Acceptance:** hiding a publication immediately makes both redirect routes behave consistently,
without waiting for a maintenance run; visible content and repeat-click suppression still work.
**Effort/risk:** S / low-medium.

### F08 [P2, conditional] Rate limits are per-process without a shared cache

**Evidence:** [contact limit checks](website/contact.py#L118),
[limit increments](website/contact.py#L122),
[API throttling settings](reconnect/settings.py#L210).

No shared `CACHES` backend is configured, so Django defaults to local-memory caching.
Contact limits and DRF's cache-backed anonymous throttling are not coordinated across workers.
Worker restarts also reset those local counters.

**Impact:** increasing worker count changes effective limiting behaviour.
The contact pre-check and later increment are also not an atomic admission decision.

**Recommendation:** choose and document a worker/cache policy before scaling out.
Use a shared backend when coordinated limits are required, and test the contact admission semantics.
A single-worker launch can be a conscious interim trade-off; Redis is not an unconditional prerequisite.
Shared caching alone should not be described as a perfectly strict global rate limiter.

**Acceptance:** test the intended deployment topology and document the limits actually guaranteed.
**Effort/risk:** M / medium; conditional on the production worker plan.

### F09 [P2] Header and footer repeat the same article-count query

**Status: implemented.** The helper memoizes on the current request while retaining supplied
About-page totals and request-free template support. Tests verify one real count query across
component includes, one helper count for header/footer, and fresh totals on subsequent requests.

**Evidence:** [header tag](templates/components/header.html#L2),
[footer tag](templates/components/footer.html#L2),
[count helper](website/templatetags/footer_tags.py#L10).

At the audit baseline, where `article_count` was absent from context, each tag independently called
`visible_articles().count()`. About supplies the count, but ordinary feed requests do not.
The new animation uses the existing total; it does not itself need repeated database queries.

**Impact:** duplicate work on frequently visited pages. This review establishes the extra query,
not a particular latency or server-cost saving.

**Recommendation:** reuse one total per request, in the tag or shared request context.
Do not introduce long-lived/global caching and invalidation machinery for this small improvement.

**Acceptance:** rendering both counts uses one total-count query, with identical values and
unchanged hidden-content/filter rules. Keep comma formatting, static fallback and reduced motion.
**Effort/risk:** S / low.

### F10 [P2] Tests and project documents describe conflicting product states

**Status: implemented.** The About test checks the delivered signup iframe. README,
product/design context, the development checklist and directly related cron instructions now
describe implemented behaviour without claiming production deployment. Completed checklist
items have moved into the implemented summary. The development guide remains Git-ignored:
back it up separately.

**Evidence:** [failing About test](website/tests/test_about.py#L7),
[README placeholders](readme.md#L271),
[planned RSS/Bluesky statement](PRODUCT.md#L52),
[old card/date and flow descriptions](DESIGN.md#L113).

The audit-baseline suite had one failure expecting an unimplemented newsletter placeholder, although the
signup embed exists. The README still says embeds have not been added. Product context still calls
RSS and scheduled Bluesky planned capabilities. The design document describes older date display,
column-first flow and styling that should not override the approved current components.

**Impact:** future work can rebuild delivered features, remove legitimate behaviour or optimise
against the wrong design. The test suite also cannot serve as a clean launch gate.

**Recommendation:** replace the obsolete assertion with checks for the delivered signup, and align
the documents with code and owner-approved decisions. Distinguish implemented commands from
unverified production scheduling. Keep one authoritative remaining-work checklist, linking to
specialist guides rather than duplicating their details. Back up the ignored development guide separately.

**Acceptance:** all 364 current Django tests pass after correcting the stale expectation,
and the product/design/setup documents no longer contradict implemented features.
**Effort/risk:** S-M / low. No removal or reintroduction of embeds is warranted.

## Bloat: what could safely be reduced

These are candidates for separate approval, not instructions to delete files now.

### B01 [P3] Stop versioning generated collected static files

**Evidence:** Git tracks **156 files** under [staticfiles/](staticfiles/), while
[settings](reconnect/settings.py#L132) declares that directory as `STATIC_ROOT`.
The source directory is [static/](static/), with 17 tracked files.

**Recommendation:** once the production build reliably runs `collectstatic`, untrack generated
output and ignore that directory. Preserve the source assets. Do not remove the directory first
and discover during deployment that the build never recreates it.

**Benefit:** fewer generated/vendor changes and less risk of stale collected assets.
**Effort/risk:** S / low after build verification, higher before it.

### B02 [P3] Remove a small amount of unused scaffolding

**Evidence:** [website/forms.py](website/forms.py) is empty and tracked, with no detected import
references. [SitesAdmin](website/admin.py#L42) is unregistered; the actual registered class is
[SiteAdmin](website/admin.py#L46). `reverse`, `format_html`, `ArrayWidget` and `WysiwygWidget`
are imported in that module without being used.

**Recommendation:** remove the empty module, unused admin class and unused imports after the
normal reference/test checks. Keep the active admin and its form; do not casually collapse
multi-category editing along with the redundant class.

**Benefit:** less misleading scaffolding, but no meaningful performance improvement.
**Effort/risk:** S / low. This is housekeeping, not a major debt programme.

### B03 [P3] Review the redundant Analytics composite index

**Evidence:** the [unique constraint](website/models.py#L251) and
[explicit index](website/models.py#L254) both cover `(type, object_id, month)`.
In-memory SQLite introspection confirmed two indexes with those exact columns:
one unique and one non-unique.

**Recommendation:** retain the uniqueness constraint and consider removing only the redundant
non-unique index through a reviewed migration. Confirm the production PostgreSQL index definitions
and representative query plans before applying it there.

**Benefit:** one less index to store and update. The saving was not benchmarked.
**Effort/risk:** S / medium because it is a schema change requiring the normal backup/migration approval.
Do not delete an old migration file to achieve this.

## Keep: complexity that serves real requirements

- **Shared public query/filter rules and the category through model.** They support multiple
  publication categories and prevent duplicate results. See [feed filtering](website/feed.py#L110).
- **Both server widget placement and responsive client packing.** The former provides document-order
  placement/fallback; the latter responds to columns and image/size changes. They are not interchangeable
  dead copies. Preserve [widget tests](website/tests/test_widgets.py#L69) and the
  [browser-layout algorithm tests](website/tests/js/feed_widgets.test.cjs#L84).
- **Image checks, fallbacks and guarded fetching.** These are active ingest/render paths.
  Keep [connection checks](website/safe_fetch.py#L61),
  [bounded fetching](website/safe_fetch.py#L135) and regression tests.
- **Separate Clicks, Analytics and baseline state.** They answer different questions; baseline totals
  must not become monthly activity. Keep [baseline guards](website/management/commands/aggregate_clicks.py#L92)
  and [purge guards](website/management/commands/purge_clicks.py#L59).
- **Current raw-click retention.** Normal purge keeps four calendar months and cannot purge newer
  months even with `--force`; this protects the current/previous-month recap workflow.
  Do not add a historical newsletter reconstruction subsystem merely because removing synthetic
  raw rows changes a calculation. See [retention](website/management/commands/purge_clicks.py#L31).
- **Analytics completion records.** Reports use [Logging entries](website/analytics_reports.py#L132)
  to distinguish verified zero activity from an unaggregated month. These records are not disposable
  debug clutter. If a future cleanup removes logs, migrate completion state to structured metadata first.
- **Bluesky retry reconciliation and dormant/manual visibility distinctions.** They prevent repeated
  remote posts and accidental reinstatement of manually excluded sources.
  See [Bluesky record-key handling](website/management/commands/post_bluesky.py#L48).
- **Cron-oriented commands rather than an extra task framework.** No present finding establishes
  a need for Celery. Keep supported entry points and dry runs.
- **Existing third-party libraries.** `interruptingcow`, `linkpreview`, `lxml` and `feedparser`
  have active ingestion/image/recovery call sites. Do not remove them based on unfamiliar names.
- **Migration history and reviewed import source files.** They are not bloat merely because they
  are no longer used on every deployment.

## Improvements to profile or agree later

These are not demonstrated launch failures:

- **Large article reports:** [build_report](website/analytics_reports.py#L181) resolves/builds/sorts
  all matching rows before [preview pagination](website/admin_views.py#L73) limits display to 50.
  That limit does not bound report memory. Profile realistic annual/baseline reports before introducing
  database-level preview pagination or streaming downloads.
- **Ticker sampling:** [widget preparation](website/widgets.py#L79) materialises the recent matching
  ID pool before sampling a small ticker. Profile realistic ingestion volume/lookback settings;
  change the sampling strategy only if the cost warrants it.
- **Click-source breakdowns in reports:** website/RSS data is already separate underneath.
  A source split is a reporting enhancement, not a tracking-system rebuild.
- **Themes, icons and Focus dropdown height:** these remain product/design choices. Treat a dark theme
  as an approved feature, not a reason to redesign every component. Check small-screen usability before
  removing dropdown scrolling. Add the chosen favicon/home-screen assets when provided.
- **Contact notification retries:** saved messages survive delivery exceptions; an admin retry action
  may be useful later. A background queue is not required simply to launch the existing form.

## Frontend technical audit notes

**Implementation-integrity verdict: pass for coherence, not a blanket quality certification.**
The delivered catalogue/grid/filter system is product-specific and internally purposeful.
The major frontend finding at the audit baseline was keyboard dismissal behaviour,
not a need to change its visual identity. F03 is now fixed and browser-verified.

Historical UI-only rubric, based on the original source and limited browser smoke checks
(not re-scored after the fixes):

| Dimension | Provisional score / 4 | Basis and limitation |
| --- | ---: | --- |
| Accessibility | 2 | Labels and reduced-motion handling exist; hidden focus was reproduced. Full contrast/screen-reader testing remains. |
| Performance | 3 | Small JS layer and existing query helpers; duplicate counts and growth hotspots remain. No production benchmark. |
| Theming | 2 | Current light styling is deliberate; theme coverage/documentation is incomplete. Dark mode is not delivered. |
| Responsive design | 3 | Four widths passed the exercised overflow checks; real touch devices and diverse media remain untested. |
| Implementation integrity | 4 | Confirmed component responsibilities; detector examples were intentional styling, not evidence of generic replacement UI. |
| **Total** | **14/20: Good within this limited rubric** | **Not a launch-readiness score or WCAG certification.** |

At the audit baseline, the local source detector returned **64 candidates**: 47 colour, 13 font-size, 3 radius and
1 side-accent result. These are **not 64 confirmed defects**. Representative checks found stale
design-token expectations and intentional search/menu/widget/card styling. The side-accent example
at [custom.css:1421](static/css/custom.css#L1421) is a contact status box, not an unwanted side tab.
The design reference has since been reconciled under F10. The historical candidate
count is not a new detector run or a CSS rewrite list.

F03 and F09 have been corrected without a visual redesign. Any further optimisation
should follow measured profiling; any broader polish or audit remains a separately
approved task, not a prerequisite introduced by these fixes.

## Remaining acceptance and next decisions

1. **Owner acceptance of the completed changes:** check real-content pagination,
   filter keyboard dismissal, Clicks admin search and combined website/RSS recap rankings.
   Hidden-publication article links now return 404 immediately, as approved.
2. **Production preparation:** complete F01 and decide F08 as part of the worker/cache plan.
3. **Optional cleanup:** B01/B02 remain untouched; consider B03 only with migration approval.
4. **Staging acceptance:** the full local suite passes, but real-device/media checks,
   email delivery, cron verification, backup restoration and production smoke tests remain.

**Recommended boundary:** the approved correctness batch is complete. Do not expand it into
unapproved cleanup or deployment work. Keep the working application intact, agree each
behavioural change, and use the smallest tests that demonstrate its intended result.
