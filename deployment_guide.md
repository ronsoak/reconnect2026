# Reconnect: local development to Railway, through GitHub

Reviewed against the repository and Railway documentation on **13 November 2026**.

Follow the numbered steps in order. A checkbox is a task to complete, not a claim
that it has already been done. Stop at a failed check.

## The deployment this guide uses

- **Source:** the `ronsoak/reconnect2026` GitHub repository.
- **Railway plan:** Hobby.
- **Database:** Railway PostgreSQL, separate from your local SQLite database.
- **Advert images:** a Railway volume mounted at `/data`, with uploads in `/data/media`.
- **Web serving:** Caddy serves static files and uploaded images; Gunicorn runs Django.
  Both run in the same web container so they can access the same volume.
- **Contact email:** Resend's HTTPS API through Django Anymail, not SMTP.
- **Scheduled work:** separate Railway cron services using the same GitHub revision.
- **Initial capacity:** one web replica and one Gunicorn worker. The existing
  in-process rate limits are not shared across workers and reset on restarts.

**Important: the repository is not production-ready yet.** Step 2 lists required
development work. The Docker packaging, production settings, health endpoint and
HTTPS email integration described below are requirements to implement, not files
or features this documentation rewrite has added. Do not skip that step and try
to enable them just by setting Railway variables.

Railway's current rules affect this plan:

- Hobby does **not** support outbound SMTP. SMTP requires Pro or higher.
- Volumes are available at runtime, not during builds or pre-deploy commands.
- Files created by a pre-deploy command do not appear in the running container.
- A volume-backed web service has some downtime when redeployed. Do not promise
  zero-downtime deployments, even with health checks.

## Where to run commands

- **LOCAL:** Terminal on your Mac, in this repository.
- **REMOTE:** a shell opened inside the selected Railway service with `railway ssh`.
- **DASHBOARD:** Railway, GitHub or the named provider's website.

Unless a block says otherwise, commands in Steps 1-5 run **locally**.
Never paste `.env` contents, database URLs, keys or passwords into GitHub,
screenshots, tickets or import logs.

---

## 1. Save your current local work

1. Stop your development server and any local ingestion or maintenance jobs.
2. Commit the work you want to keep. Inspect `git status --short` and preserve
   unrelated changes.
3. Make a separate backup of:
   - `db.sqlite3`;
   - `media/`, if you have uploaded advert images;
   - the reviewed CSV files in [migration/](migration/);
   - your private `.env`;
   - any local-only configuration or editorial notes you need.
4. Put the backup outside the repository. Treat database and environment backups
   as sensitive; use encrypted storage.
5. Open Terminal in the repository and activate the existing environment:

   ```sh
   source .venv/bin/activate
   python --version
   ```

The local interpreter reviewed for this guide is Python **3.14.5**. Keep the
production Python version aligned with the version you actually test.

**Done when:** your work is saved, the backup can be opened, and `python` resolves
to the repository's virtual environment.

## 2. Complete the production code locally — required development gate

This is an implementation step, not Railway dashboard configuration. Have the
following changes implemented and reviewed before proceeding to Step 3.
Do not replace unrelated application settings or rebuild delivered features.

### 2.1 Make Django settings production-aware

Update [reconnect/settings.py](reconnect/settings.py) to:

- Read `DEBUG` as a boolean, defaulting to `False`. Set `DEBUG=True` explicitly
  in your ignored local `.env` for ordinary local development.
- Require a non-empty `SECRET_KEY`; remove the insecure fallback.
- Read comma-separated `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
  Hostnames have no scheme; trusted origins include `https://`.
- Read `DATABASE_URL` using `dj-database-url` and PostgreSQL's `psycopg` driver.
  Preserve SQLite for explicit local development only. Production must fail
  clearly if its database configuration is missing, not silently use SQLite.
- Configure secure session/CSRF cookies, HTTPS redirects and
  `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` for the
  verified Railway -> Caddy -> Gunicorn proxy chain.
- Make HSTS configurable. Start with a short duration, such as 300 seconds, after
  HTTPS works. Do not enable subdomain coverage or preload before checking every
  affected hostname.
- Exempt the readiness endpoint from HTTPS redirection so Railway's internal
  HTTP health probe can succeed without weakening HTTPS for ordinary pages.
- Keep `STATIC_ROOT=/app/staticfiles` in the container and support
  `MEDIA_ROOT=/data/media`.
- Retain `TIME_ZONE="Australia/Melbourne"`.

Add `gunicorn`, `dj-database-url`, `psycopg[binary]` and `django-anymail` to
[requirements.txt](requirements.txt), plus the process manager chosen below.
Install from the updated manifest, resolve compatible versions, then pin the
tested versions in the repository's existing style. Do not replace the whole
manifest with an unrelated global `pip freeze`.

### 2.2 Add the Hobby-compatible email backend

Use Django Anymail's Resend backend:

```python
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
```

Wire a private `RESEND_API_KEY` environment variable into
`ANYMAIL["RESEND_API_KEY"]` in settings. Setting an environment variable alone
does not make it a Django setting.

Preserve the existing contact flow: save the message, attempt delivery, and keep
the saved message plus its error state when delivery fails. Test both outcomes.
Keep the console backend available for normal local development.

Only outbound sending is required. Do not add inbound-email handling, webhook
routes or webhook dependencies just to send contact notifications.

### 2.3 Package the volume-backed production web service

Add and test a root `Dockerfile` and supporting files under `deploy/`.
Use Caddy plus Gunicorn, managed by Supervisor, in **one container**:

| Required item | Behaviour to implement |
|---|---|
| `Dockerfile` | Installs the pinned Python dependencies, Caddy and Supervisor; copies the app into `/app`; uses the tested Python release |
| `.dockerignore` | Excludes `.env` and private env variants, `.git`, `.venv`, SQLite databases, `media/`, backups, logs and generated `staticfiles/`; retains source `static/`, templates and Django migrations |
| `deploy/start-web.sh` | Creates/checks writable media directories after the volume is mounted, runs `python manage.py collectstatic --noinput`, then starts Supervisor in the foreground |
| `deploy/supervisord.conf` | Starts Caddy and Gunicorn, forwards logs to stdout/stderr and handles child restarts and container shutdown |
| `deploy/Caddyfile` | Listens on `0.0.0.0:$PORT`; serves `/static/` from `/app/staticfiles` and `/media/` from `/data/media`; proxies other routes to Gunicorn on loopback |

Use `/bin/sh /app/deploy/start-web.sh` as the web start command.
Keep the Docker default command overridable: a cron service must be able to run
a management command **without** starting Caddy or Supervisor.

For Gunicorn, use this application and initially one synchronous worker:

```sh
gunicorn reconnect.wsgi:application --bind 127.0.0.1:8001 --workers 1 --access-logfile - --error-logfile -
```

Caddy must:

- Leave TLS termination to Railway; do not request its own public certificates.
- Remove the `/static/` or `/media/` prefix before looking up the corresponding
  file under its root. Do not accidentally look for `/data/media/media/...`.
- Serve uploaded files as files, not executable scripts; disable directory
  browsing and include `X-Content-Type-Options: nosniff`.
- Preserve Railway's `X-Forwarded-Proto` and `X-Real-IP` when proxying to Django.
  Caddy's default proxy handling must not turn external HTTPS into an upstream
  `http` scheme and cause a redirect loop.
- Run the application with appropriate filesystem permissions. Test write access
  on a fresh Railway volume; do not solve this with world-writable permissions.

Remove or restrict the unconditional development media-serving route in
[reconnect/urls.py](reconnect/urls.py). Production `/media/` requests must be
handled by Caddy, not `django.views.static.serve`.

WhiteNoise is not required in this chosen arrangement: Caddy handles static
files as well as media. Do not add a second static-serving layer without a reason.

### 2.4 Add a real readiness endpoint

Add `/healthz/`, returning HTTP 200 only when Django can respond and perform a
small database query. Return no credentials, configuration or diagnostic data.
Database unavailability must produce a failing response, not a success fallback.

Include `healthcheck.railway.app` in the production allowed-host list.
Do not implement readiness as a constant Caddy response that succeeds while
Gunicorn or PostgreSQL is down.

Add focused regressions for production configuration, the readiness endpoint and
the email backend's successful/failed delivery paths.

### 2.5 Review files going to GitHub

The current [ignore file](.gitignore) already ignores `.env`, `db.sqlite3` and
`media/`. Extend it for private environment variants and backups as needed.
Never ignore Django's migration history.

Generated `staticfiles/` files are currently tracked. The new image must rebuild
them from [static/](static/) rather than depend on that tracked output.
Adding an ignore rule does not untrack existing files. Untracking generated
files can be a separate reviewed cleanup after the rebuild is proven; do not
delete source assets as part of deployment.

**Stop here until all of Step 2 is implemented.** The remaining steps assume
these settings, files and endpoint exist and have been tested.

## 3. Run the final local checks

1. Install dependencies from the updated manifest:

   ```sh
   python -m pip install -r requirements.txt
   python -m pip check
   ```

2. Run the Django and JavaScript checks:

   ```sh
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test website
   node --test website/tests/js/*.test.cjs
   ```

3. Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
   if it is not already available, start it,
   then build the production image:

   ```sh
   docker build -t reconnect:release .
   ```

4. Test that image against a **separate disposable PostgreSQL test database**,
   never your working SQLite file or production database. Verify:
   - migrations apply and the Django tests pass against PostgreSQL;
   - `DEBUG=False` is effective;
   - `python manage.py check --deploy` has no unexplained warnings;
   - `/healthz/` reports database failure correctly;
   - Caddy serves CSS, admin assets and uploaded advert images;
   - the start command works with a fresh writable media mount;
   - restarting the container retains mounted images;
   - SIGTERM shuts down both web processes cleanly;
   - a management-command override exits instead of leaving web processes alive.
5. Check the site manually on mobile, tablet and desktop. Include filters,
   pagination, search, widgets, About, privacy, contact and admin reports.
6. Review launch copy, credits, destinations, icons and privacy information.
   Record anything deliberately deferred. A dark theme is not a prerequisite.

**Done when:** tests and the image build pass, and the production-mode behaviour
has been exercised. Earlier passing tests do not certify new production changes.

## 4. Prepare the launch data and provider accounts

1. Keep the eight reviewed site CSVs and article CSV unchanged as source files:
   [re_import_01.csv](migration/re_import_01.csv) through
   [re_import_08.csv](migration/re_import_08.csv), and
   [re_import_articles.csv](migration/re_import_articles.csv).
2. Review [seed_data.py](website/seed_data.py). Every CSV site type, category and
   tag must match a seeded Logic value. Review filtering and newsletter-exclusion
   terms before importing.
3. Check reviewed hidden flags, `auto_post`, modifiers and optional `recap` values.
   Do not silently rename publications to fix display issues.
4. Remember the importer limitations:
   - sites match by URL; categories/tags use semicolon-separated Logic values;
   - blank tags do not clear existing tags;
   - omitted `recap` preserves existing values and defaults new sites to true;
   - `dormant` and `article_count` are not imported;
   - article imports can update existing records and their supplied click totals;
   - imports commit incrementally, not as one all-or-nothing transaction.
5. Decide which local admin-only content must be recreated: adverts, notice
   banner, custom Logic entries and any other settings not in the CSVs.
   These CSV commands do not migrate your entire local database, users, messages,
   historical monthly Analytics or uploaded files.
6. In Resend, verify your sending domain using the DNS records it supplies.
   Create a sending-only API key and choose a verified `DEFAULT_FROM_EMAIL`.
7. In Cloudflare Turnstile, create/configure the widget. Add the Railway hostname
   and final hostname when they are known; use real production keys for live tests.
8. Prepare a Bluesky app password only if enabling article auto-posting at launch.
   Never use the main account password.

Do not run a real import into the working local database merely to test these
steps. The Railway rehearsal below is the final production-like import test.

## 5. Commit and push the release candidate to GitHub

1. Review the diff, including the production files and requirements:

   ```sh
   git diff --check
   git status --short
   git diff
   git branch --show-current
   ```

2. Stage only reviewed release files in VS Code or by naming them explicitly.
   Do not blindly stage private backups or exports.
3. Commit, then push the current release branch:

   ```sh
   git push origin HEAD
   git log -1 --oneline
   ```

4. Open GitHub and confirm that exact commit is visible on the branch you will
   select in Railway. Record the branch and commit hash.

**Done when:** GitHub contains the tested code, and no credentials, database,
private media or backups are included.

---

## 6. Create a Railway rehearsal environment from GitHub

**DASHBOARD**

1. Choose **New Project -> Empty Project** and name the project. Leave its
   default production environment empty. Create an empty environment named
   `staging` and select it before adding services.
2. Inside this project/environment, choose **New -> GitHub Repo**, authorise
   access if requested, and select `ronsoak/reconnect2026`.
   Do not use the final production database for rehearsal.
3. Name the application service `web`. Set its source branch to the release
   branch from Step 5 and the root directory to the repository root.
4. Add a PostgreSQL service, named `Postgres`. Keep it private; the web service
   will use the internal database connection.
5. Attach a **new empty volume** to `web`, mounted at `/data`.
   Do not mount it over `/app`, which would hide application files.
6. Use one web replica. Disable sleeping/serverless behaviour for the initial
   launch and do not enable cron services yet.
7. If the automatically triggered first deployment fails before variables are
   configured, leave it failed while completing Steps 7-8. Do not turn on debug
   or weaken host checks to make it green.

Keep the staging site without a public domain during the first import.
Railway SSH can target a service without a public domain.

## 7. Set Railway variables

**DASHBOARD -> `staging` -> `web` -> Variables**

Use the following contract implemented in Step 2. Replace example hostnames and
addresses with your actual values; do not use literal placeholders.

| Variable | Set to |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | A new random production-quality key, unique to this environment |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `ALLOWED_HOSTS` | `healthcheck.railway.app`, plus the exact Railway/custom hostnames when assigned; comma-separated, no schemes |
| `CSRF_TRUSTED_ORIGINS` | Your actual `https://` origins when assigned; comma-separated |
| `MEDIA_ROOT` | `/data/media` |
| `CLIENT_IP_HEADER` | `HTTP_X_REAL_IP`, after validating the proxy chain in Step 11 |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_SSL_REDIRECT` | `True` |
| `SECURE_HSTS_SECONDS` | `300` initially; increase after successful HTTPS checks |
| `EMAIL_BACKEND` | `anymail.backends.resend.EmailBackend` |
| `RESEND_API_KEY` | The sending-only API key |
| `DEFAULT_FROM_EMAIL` | Your verified sender, e.g. `Reconnect <noreply@example.com>` |
| `CONTACT_EMAIL` | The inbox that should receive contact messages |
| `TURNSTILE_SITE_KEY` | Turnstile public site key |
| `TURNSTILE_SECRET_KEY` | Matching Turnstile secret key |

To generate a Django secret key **locally** and copy it to the Mac clipboard:

```sh
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())' | pbcopy
```

Paste it directly into Railway Variables. Do not add it to this document.
Do not use the local development key for production.

Railway supplies `PORT`; the container must listen on it. Do not publish
Gunicorn's loopback port separately.

Leave SMTP variables out of this deployment. Hobby cannot deliver the existing
SMTP configuration, regardless of the email provider's hostname or port.

Leave runtime tuning at its defaults for the first deployment unless you have
approved changes. See [Runtime tuning](readme.md#runtime-tuning).
Railway does not upload/read your local `.env` automatically.

## 8. Configure build, deployment and readiness

**DASHBOARD -> `staging` -> `web` -> Settings**

1. Confirm Railway detects the root `Dockerfile`. Do not mix this configuration
   with an unrelated automatic-build recipe.
2. Set **Pre-deploy Command** to:

   ```sh
   python manage.py migrate --noinput
   ```

3. Give migrations a sensible pre-deploy timeout, initially 300 seconds, and
   increase it only when the rehearsed migration needs longer.
4. Set **Start Command** to:

   ```sh
   /bin/sh /app/deploy/start-web.sh
   ```

5. Set **Healthcheck Path** to `/healthz/`, initially with a 300-second timeout.
6. Deploy the staged changes. Check build, migration and runtime logs separately.
7. Confirm migrations succeed, `collectstatic` runs during web startup, and
   Caddy and Gunicorn remain running.

**Do not put `collectstatic` in the pre-deploy command.** That container's
filesystem is discarded, and the media volume is not mounted there.
Do not add seeding, imports, baseline capture or destructive maintenance to
builds, startup or pre-deploy commands.

## 9. Install/link the Railway CLI and enter the correct container

**LOCAL**

Install the CLI through Homebrew if you use it, otherwise use Railway's official
[CLI installation instructions](https://docs.railway.com/cli):

```sh
brew install railway
railway login
railway link
railway status
```

During linking, select this project, the `staging` environment and `web` service.
Verify those selections before running any database-changing command.

Enter the deployed web container:

```sh
railway ssh --service web --environment staging
```

**REMOTE, inside `web`:**

```sh
cd /app
python manage.py showmigrations --plan
python manage.py check --deploy
python manage.py createsuperuser
```

Use a unique strong admin password. The admin path is `/backdoor/`.
Explain or fix every deployment warning; do not silence warnings indiscriminately.

For long imports, use a persistent session:

```sh
railway ssh --service web --environment staging --session
```

That command runs **locally** to open the remote session.
Do not redeploy the service during an import.

**Do not substitute `railway run` or `railway shell`.** Those execute locally
with Railway variables; they are not shells inside the deployed container.
Internal PostgreSQL addresses generally cannot be reached directly from your Mac.

## 10. Rehearse the complete data import

All commands in this step run **REMOTE inside staging `web`, from `/app`**.
Keep cron disabled and public traffic off until baseline capture is finished.

### 10.1 Seed Logic

```sh
python manage.py seed_db
```

Confirm the Article, Advert and RSS click types exist, along with the CSV lookup
values. Seeding does not copy custom local admin data automatically.

### 10.2 Preview all eight site files

```sh
python manage.py import_sites --file migration/re_import_01.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_02.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_03.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_04.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_05.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_06.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_07.csv --dry-run --stop-on-first-error
python manage.py import_sites --file migration/re_import_08.csv --dry-run --stop-on-first-error
```

Stop on any error. Fix the reviewed source/seed mismatch locally, test, commit,
push and deploy the corrected revision. Do not choose an arbitrary Logic value
just to get an import past validation.

### 10.3 Import the sites

Only after all previews succeed:

```sh
python manage.py import_sites --file migration/re_import_01.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_02.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_03.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_04.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_05.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_06.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_07.csv --stop-on-first-error
python manage.py import_sites --file migration/re_import_08.csv --stop-on-first-error
```

### 10.4 Preview and import the historical articles

```sh
python manage.py import_articles migration/re_import_articles.csv --dry-run --stop-on-error > /tmp/reconnect-article-preview.log 2>&1
```

Read the log and confirm **Errors: 0**, the site matches and the expected input
row count. A dry run is not proof that the real database writes will succeed.

Then run:

```sh
python manage.py import_articles migration/re_import_articles.csv --stop-on-error > /tmp/reconnect-article-import.log 2>&1
```

Inspect the exit status immediately (`echo $?`) and the summary in the log.
Confirm the created/updated totals and **Errors: 0**. Keep the reviewed results.
Logs under `/tmp` disappear on redeploy; download evidence you need to retain.
Watch memory during the real rehearsal: the article importer loads the CSV into
memory. Increase the service's allocation if required before the production run.

Never use `--first-match` as a general workaround for ambiguous publication names.
Do not blindly rerun a partially completed import: rows already written remain,
and supplied historical totals can overwrite newer values.

### 10.5 Capture the historical click baseline, once

Do this **after the final historical import and before test clicks, public
traffic, ingestion schedules or monthly aggregation**:

```sh
python manage.py aggregate_clicks --baseline --dry-run
```

Check the target month, object count and total. Then:

```sh
python manage.py aggregate_clicks --baseline
```

This captures **all current article and advert click totals**, including zeros,
into the previous calendar month as protected historical baseline rows.
For example, capture during November 2026 targets October 2026; it is not a
claim that those lifetime clicks occurred in October.

- If historic advert totals are also being migrated, finish that approved
  migration before this snapshot. The article CSV importer does not migrate adverts.
- The target month must have no Analytics rows; a baseline may only be captured once.
- Stop if the command refuses. Do not delete Analytics to bypass its guards.
- Do not cross a month boundary between reviewing the preview and capturing it.
- Never add `--baseline` to cron or the deployment process.
- Do not rerun historical click imports after opening the site to live traffic.

### 10.6 Apply initial maintenance and fetch missing images

```sh
python manage.py filter_articles --dry-run
python manage.py hide_articles --dry-run
```

Review the effects, then:

```sh
python manage.py filter_articles
python manage.py hide_articles
python manage.py count_articles --mode full
python manage.py last_article
python manage.py hide_sites --dry-run
```

Review dormant-site candidates and approved hidden flags before running
`python manage.py hide_sites`. Its default inactivity threshold is 270 days.

Then:

```sh
python manage.py batch_sites --only-active
python manage.py backfill_images --dry-run --limit 50
python manage.py backfill_images --limit 50
```

Inspect the sample before optionally running `python manage.py backfill_images`
without a limit. These image commands fetch remote URLs and may take time.

Use the explicit `--only-active` flag when batching. Do not rely on the command
header's claim about its default.

Finally run one normal catch-up ingestion, not an automatic 365-day backfill:

```sh
python manage.py ingest_all
python manage.py filter_articles
python manage.py hide_articles
python manage.py count_articles --mode full
python manage.py last_article
```

If ingestion fails, stop and investigate before continuing the sequence.
It covers all configured batches with a 14-day lookback by default.
Use `--days 365` only for an explicitly approved deeper backfill.

**Done when:** imports have zero errors, the baseline exists, counts and hidden
flags look right, and initial ingestion has been reviewed.

## 11. Expose staging and perform the live checks

**DASHBOARD**

1. Generate a Railway domain for staging `web`. Point its target port to the
   Caddy listener's `PORT`, not Gunicorn's loopback port.
2. Add the exact hostname to `ALLOWED_HOSTS` and its `https://` origin to
   `CSRF_TRUSTED_ORIGINS`. Redeploy.
3. Add that hostname to Turnstile. Keep staging access restricted while testing;
   use a tested Caddy access gate if necessary. A secret URL and `robots.txt`
   are not access control. Exclude Railway's readiness probe from the gate.
4. Open `/`, `/newest/`, `/popular/`, `/publications/`, `/search/?q=game`,
   `/about/`, `/privacy/`, `/robots.txt`, `/sitemap.xml`, `/feeds/all.rss` and
   `/api/filters/`.
5. Check CSS, logo, admin assets, article images and links at phone/tablet/desktop
   widths. Inspect network failures, not just the HTML response.
6. Log in at `/backdoor/`. Check newsletter previews/downloads and monthly
   advert, publication and article analytics reports.
7. Upload an advert image. Record its `/media/adverts/...` URL, redeploy, then
   confirm the exact image and admin record still work.
8. Submit a contact message through the actual form. Wait past the signed
   minimum time and complete Turnstile. Confirm:
   - the saved message appears in admin;
   - delivery is marked successful;
   - the email actually arrives in the intended inbox.
9. In staging only, rehearse a provider failure, verify the message remains
   saved with failed delivery, then restore the valid email configuration.
10. Verify HTTPS, secure cookies, admin CSRF submission and generated HTTPS
    sitemap/RSS URLs. Check for redirect loops.
11. Verify distinct visitors reach Django with distinct trusted client IPs, and
    a forged `X-Real-IP` header is not accepted as authoritative. Do not leave a
    public diagnostics endpoint or log unnecessary personal data.
12. Check an article website click, an RSS article click and an advert click.
    Verify Article/RSS/Advert event types, repeat-click protection and totals.
    Check hidden-publication links return 404 immediately.

Railway's health check is a deployment gate, **not continuous uptime monitoring**.
Arrange ongoing alerts separately.

## 12. Configure backups and prove restoration before production

1. In Railway, enable the available daily and weekly backup schedules on:
   - the PostgreSQL service's data volume;
   - the separate `web` media volume.
2. Take a manual snapshot of both and confirm completed backups appear.
   A database backup alone does not include advert-image files.
3. Confirm your plan's capacity, costs and retention in the dashboard. Do not
   promise retention periods in the privacy policy until configured and verified.
4. Rehearse restoration in the disposable staging environment before it is
   needed for production. Pause jobs and take fresh snapshots first.
   Railway native volume backups restore within the **same project and
   environment**; do not assume a production snapshot can be restored directly
   into staging through the dashboard.
5. Check restored site/article counts, baseline Analytics, admin login and an
   advert image. Record the recovery procedure and approximate time required.

Keep an additional encrypted off-platform database export and media copy when
your recovery policy requires protection beyond Railway. For example:

**LOCAL:**

```sh
railway ssh --service Postgres --environment staging
```

**REMOTE inside Postgres, not `web`:**

```sh
pg_dump -h 127.0.0.1 -U "$PGUSER" -d "$PGDATABASE" --format=custom --file=/tmp/reconnect-backup.dump
pg_restore --list /tmp/reconnect-backup.dump
```

Use the registered Railway SSH key and `scp` to download that file to your
encrypted backup location. Railway's SSH instructions explain using the
**service instance ID** as the SSH username when the service has no public domain:

```sh
scp YOUR_POSTGRES_SERVICE_INSTANCE_ID@ssh.railway.com:/tmp/reconnect-backup.dump /absolute/path/to/encrypted-backups/reconnect-backup.dump
```

Replace the instance ID and destination path; keep the destination outside the
repository. Do not enable a public PostgreSQL endpoint just for this
transfer. A listable dump is not proof of restoration: test it in a separate,
empty compatible PostgreSQL database using `pg_restore --no-owner --no-acl
--exit-on-error`, then check the restored data.

For media, link the CLI to the correct environment and `web` service, then use
`railway volume browse /` to download the `media` directory. Browser paths are
relative to the volume root, so `/media` corresponds to `/data/media` in `web`.
Treat dumps and media backups as sensitive; do not commit them.

## 13. Create the production environment and repeat the rehearsed import

Do not turn the tested staging database into production: it now contains test
clicks, contacts and possibly other synthetic changes.

1. Create/select the final `production` environment in Railway.
2. Add a production `web` service from `ronsoak/reconnect2026`, connected to the
   **same tested GitHub branch and commit**.
3. Add a fresh `Postgres` service and attach a fresh media volume to this `web`
   service at `/data`. Verify neither references staging storage.
4. Repeat Steps 7-9 for production:
   - generate a different secret key;
   - reference production's own `${{Postgres.DATABASE_URL}}`;
   - configure the verified sender, inbox and Turnstile keys;
   - configure migrations, startup and readiness exactly as rehearsed;
   - verify `railway status` and SSH using `--environment production`.
5. Enable and verify production database/media backups before importing.
6. Keep public traffic and cron disabled. Repeat **all of Step 10** against the
   fresh production database using the final approved CSVs.
7. Confirm zero import errors and verify the production baseline captured in
   Step 10.5. Do not capture it a second time or copy staging's Analytics,
   Clicks or contact messages.
8. Recreate remaining admin-only content and upload new advert images. Any
   historic advert totals belong before Step 10.5, as noted there. Preserve
   relative paths when restoring approved existing media; do not nest
   `/data/media/media/` accidentally.
9. Take fresh database and media snapshots after the successful launch import.
10. Record the deployed Git commit, import summaries, baseline target month,
    snapshot dates and any explicitly accepted limitations.

**Stop if production differs from the rehearsal.** Do not fix import errors by
flushing the database or reusing an old SQLite file.

## 14. Connect the real domain and open the site

1. In production `web` -> Networking, add your custom domain.
2. At your DNS provider, add the exact CNAME/ALIAS/TXT records Railway requests.
   Do not guess the DNS target from the service name.
3. Wait until Railway confirms routing and the HTTPS certificate is ready.
   If using Cloudflare, start with DNS-only records to avoid adding another
   proxy layer during diagnosis.
4. Add the real hostname to `ALLOWED_HOSTS` and its HTTPS origin to
   `CSRF_TRUSTED_ORIGINS`. Add every hostname you actually support, not `*`.
5. Add those hostnames to Turnstile and redeploy.
6. Repeat the smoke checks from Step 11 on the real domain, including contact
   delivery and an uploaded image after redeployment.
7. If both `www` and the bare domain are offered, configure and test a deliberate
   canonical redirect. Do not redirect the Railway healthcheck hostname.
8. Remove any temporary launch access restriction only after checks pass.
9. Review privacy wording against actual hosting logs, API providers, Substack
   embeds, cookies, backups and configured retention.
10. Submit the real-domain sitemap to search engines. `/search/` is already
    disallowed by the application; do not add a duplicate robots requirement.

Your imported baseline is historical, not the first measured month's performance.
Leave it labelled that way in client/editorial reporting.

## 15. Add scheduled services after the import and launch checks

Do not enable schedules while the final import is running. The following is a
**proposed launch schedule to approve**, not evidence that jobs are configured.
All schedule expressions are UTC; Django's reporting dates remain Melbourne time.
Daylight saving changes the corresponding local wall-clock times.

For each service:

1. Add a service from the same GitHub repository and tested branch.
2. Give it the name below. Confirm the Dockerfile is used.
3. Reference production's database and the necessary shared Django settings.
   Use the same secret key within this environment; never point to staging.
4. Set its command exactly as shown. `/bin/sh -c` is deliberate for `&&`.
5. Leave its pre-deploy command and healthcheck path **empty**. Only `web`
   runs migrations; do not run them concurrently on every cron deployment.
6. Do not attach the media volume, generate a public domain or start web servers.
7. Set the cron schedule and a **Never** restart policy to avoid unintended
   retries of partially completed maintenance.
8. Trigger/review the first run deliberately and confirm the process exits.
   Inspect application summaries and Logging as well as Railway's exit status.

| Service | Start command | UTC schedule |
|---|---|---|
| `cron-ingest` | `/bin/sh -c 'python manage.py ingest_all && python manage.py filter_articles && python manage.py hide_articles && python manage.py count_articles --mode full && python manage.py last_article'` | `0 */4 * * *` |
| `cron-age` | `python manage.py age_articles` | `0 17 * * *` |
| `cron-hide-sites` | `/bin/sh -c 'python manage.py last_article && python manage.py hide_sites'` | `0 18 * * 0` |
| `cron-dormant-sites` | `python manage.py check_dormant_sites` | `0 19 1 * *` |
| `cron-bluesky` | `python manage.py post_bluesky` | `15 * * * *` |
| `cron-aggregate` | `python manage.py aggregate_clicks` | `0 18 2 * *` |
| `cron-purge` | `python manage.py purge_clicks` | `0 18 3 * *` |

Operational checks:

- The ingest service chains its dependent maintenance, rather than assuming a
  separately scheduled job will wait for ingestion. It reads all batches.
- Preview `age_articles --dry-run` and approve daily rank ageing. It changes
  modifiers, not just display order. Some maintenance dry runs can write
  informational Logging entries; rehearse them in staging.
- Preview `hide_sites --dry-run` and `check_dormant_sites --dry-run` before
  approving these jobs. Dormant recovery must not reinstate manually excluded
  sites, and successful recovery waits for the next ingestion to load articles.
- `batch_sites --only-active` is needed after material publication additions;
  it does not need its own weekly job unless you want recurring reshuffling.
- Give **only** `cron-bluesky` the `BLUESKY_IDENTIFIER` and
  `BLUESKY_APP_PASSWORD` credentials. Preview `post_bluesky --dry-run`, then
  approve and verify one live post before enabling its schedule. The proposed
  hourly cadence is adjustable; each run posts at most one eligible article.
  Newsletter/promotion posts are a separate, unimplemented feature.
- Share non-default editorial settings, such as `BLUESKY_LOOKBACK_DAYS`, with
  the affected service; web-service variables are not automatically inherited.
- Aggregation records the previous calendar month. If that month contains your
  protected baseline, refusal is expected. Do not erase the baseline; begin
  normal monthly aggregation when it targets the first measured launch month.
- Purging targets the month four calendar months ago, retaining the current
  month and preceding three. It requires matching Analytics and cannot use a
  baseline to authorise deletion. Never add `--force` to a cron command.
- Separate cron services are not mutually locked. Do not manually launch a
  second ingestion during an active run. Railway skips a service's next
  scheduled run if its previous run is still active; it does not queue it.
- Monthly timings give aggregation a day before purge, but timing alone is not
  a guarantee. Review failures; the purge guards remain essential.

None of these services needs Celery or a copy of the media volume.

## 16. Verify the first scheduled runs

1. Confirm each job terminates and the next run is not skipped as still active.
2. Check Logging for completed ingestion, filtering, counts and maintenance.
   An `INGEST_COMPLETE` entry alone does not establish that the final count
   refresh or every batch succeeded.
3. If the final count refresh fails, completed imports remain saved. Resolve
   the error, run `python manage.py count_articles --mode full`, and investigate
   before retrying. Do not blindly replay a partially applied mini count.
4. Confirm new articles arrive and their dates, visibility and images are right.
5. Confirm the first measured month's aggregation and its admin report agree.
   Keep the baseline separate from measured month-to-month performance.
6. Confirm the purge only removes the intended old raw-click month, never
   Analytics or recent recap data. Do not delete report-completion Logging
   records as a generic log cleanup.
7. Configure deployment/job failure notifications and ongoing uptime checks.
   Watch database/media storage use and Hobby costs.

## 17. Future releases and recovery

For each release:

1. Commit and back up local work; rehearse migrations/imports in staging.
2. Run the local checks in Step 3, review the diff, commit and push.
3. Back up production PostgreSQL and media before migration or bulk changes.
4. Pause affected cron jobs while deploying incompatible schema changes.
   GitHub-triggered services must not race migrations.
5. Deploy the approved commit through the connected GitHub branch. Check the
   logs and smoke-test the live site. Resume jobs only after compatibility checks.
6. Do not rerun seed/import/baseline steps merely because the code redeployed.

If a deployment fails:

- Inspect build, pre-deploy and runtime logs; do not enable production debug.
- A Railway code rollback does **not** undo database migrations or restore media.
  Only roll back to code compatible with the database now in place.
- Check variables after a rollback: Railway can restore the prior deployment's
  variable configuration as well as its image.
- For data recovery, pause writes/jobs and use the rehearsed restoration
  procedure with explicit approval. Restoring an old database loses later
  writes; coordinate matching media and keep current snapshots first.
- Never delete a volume, flush the database or fake migrations as a routine
  deployment repair.

After launch, consider a shared cache before increasing workers/replicas.
One worker is an initial constraint, not a claim of scalable shared rate limiting.

## Final go/no-go checklist

- [ ] Step 2's production code exists, is reviewed and tested.
- [ ] GitHub and Railway point to the recorded release commit.
- [ ] Production uses PostgreSQL, debug is off and secrets are private.
- [ ] Caddy serves static/media; uploaded images survive redeployment.
- [ ] The database-backed health check succeeds.
- [ ] The final import has zero errors and its baseline was captured once.
- [ ] HTTPS, admin login, Turnstile and real HTTPS email delivery work.
- [ ] Mobile/tablet/desktop checks and analytics/report checks pass.
- [ ] Database and media backups exist; restoration was rehearsed.
- [ ] Cron commands, schedules, exit behaviour and first runs are verified.
- [ ] Remaining limitations and privacy/retention decisions are recorded.

## Official references

Railway interface labels and plan limits can change. If a screen differs, use
these references rather than guessing or weakening safeguards:

- [Django deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/)
- [Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles)
- [Pre-deploy commands and filesystem limitations](https://docs.railway.com/deployments/pre-deploy-command)
- [Volumes](https://docs.railway.com/volumes) and [backups](https://docs.railway.com/volumes/backups)
- [PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Health checks and volume-backed downtime](https://docs.railway.com/deployments/healthchecks)
- [CLI installation](https://docs.railway.com/cli), [SSH/file transfers](https://docs.railway.com/cli/ssh)
  and [local `railway run`](https://docs.railway.com/cli/run)
- [Cron behaviour and UTC schedules](https://docs.railway.com/cron-jobs)
- [Hobby email restrictions](https://docs.railway.com/networking/outbound-networking)
- [Railway proxy headers](https://docs.railway.com/networking/public-networking/specs-and-limits)
- [Custom domains](https://docs.railway.com/networking/domains)
- [Deployment rollback](https://docs.railway.com/deployments/deployment-actions)
- [Anymail's Resend backend](https://anymail.dev/en/stable/esps/resend/)
- [Caddy reverse proxy configuration](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
