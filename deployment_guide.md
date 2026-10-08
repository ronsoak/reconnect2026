# Deployment Guide (Railway)

Work through the sections in order. Tick items off as you go and add your own notes.

Sections marked **TODO** are things the project does not do yet. They must be done before the first deploy.

---

## 0. Before you deploy: code changes still needed

The settings file is still set up for local development. Do not deploy until these are done.

- [ ] **Move settings to environment variables** in `reconnect/settings.py`:
  - `DEBUG` is hard-coded `True`. Read it from an env var and default it to `False`.
  - `ALLOWED_HOSTS` only lists `localhost`. Add your Railway domain and your real domain.
  - `SECRET_KEY` falls back to `fallback-secret-key`. Remove the fallback so the site refuses to start without a real key.
  - Add `CSRF_TRUSTED_ORIGINS` with your `https://` domains.
  - Add `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` and `SECURE_SSL_REDIRECT`.
- [ ] **Switch the database to PostgreSQL.** `DATABASES` is SQLite now. Add `psycopg[binary]` and `dj-database-url` to `requirements.txt` and read `DATABASE_URL`.
- [ ] **Add a production web server:** add `gunicorn` to `requirements.txt`.
- [ ] **Serve static files:** add `whitenoise` and its middleware, so the Bulma and CSS files load when `DEBUG` is off.
- [ ] Make sure `db.sqlite3`, `media/` and `staticfiles/` are in `.gitignore` and not pushed to GitHub.
- [ ] Pin the Python version (for example a `.python-version` file containing `3.14`) so Railway builds with the version you tested on.
- [ ] Fix the SSRF concern in `ingest_batch` (on your feature list).
- [ ] Run `python manage.py test website` locally. Everything should pass.
- [ ] Commit and push to GitHub.

---

## 1. Create the Railway project

- [ ] In Railway choose **New Project → Deploy from GitHub repo** and pick `reconnect2026`.
- [ ] Add a PostgreSQL database: **New → Database → PostgreSQL**.
- [ ] Open the web service and set the **Start Command**:
  ```
  gunicorn reconnect.wsgi --bind 0.0.0.0:$PORT
  ```
- [ ] Set a **Pre-deploy Command**, so migrations and static files run on every deploy:
  ```
  python manage.py migrate && python manage.py collectstatic --noinput
  ```

---

## 2. Environment variables (web service)

Set these under the web service's **Variables** tab.

| Variable | Value |
|---|---|
| `SECRET_KEY` | A new random string. Generate one with `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DEBUG` | `False` |
| `DATABASE_URL` | Reference the Postgres service: `${{Postgres.DATABASE_URL}}` |
| `ALLOWED_HOSTS` | Your Railway domain and your real domain |
| `MEDIA_ROOT` | `/data/media` (see section 3) |

Add your own notes here:

-

---

## 3. Persistent storage for advert images

Railway wipes the container disk on every deploy. Advert images are uploaded files, so they need a Volume.

- [ ] Open the web service → **Volumes → New Volume**, mount path `/data`.
- [ ] Set `MEDIA_ROOT=/data/media` (section 2).
- [ ] After deploy, upload a test advert image in the admin and redeploy. The image should still be there.
- [ ] A volume attaches to one service only, so the cron services in section 7 can't see the images. None of the scheduled commands need them.

---

## 4. First deploy checks

- [ ] The deploy log shows the migrations ran with no errors.
- [ ] Open the Railway URL. The front page loads and the CSS is applied.
- [ ] `/robots.txt` and `/sitemap.xml` load.
- [ ] `/api/filters/` returns JSON.

---

## 5. Create the admin user

The admin is at `/backdoor/`.

- [ ] Run this from your computer using the Railway CLI, or from the service's shell:
  ```
  railway run python manage.py createsuperuser
  ```
- [ ] If you use `railway run` from your computer, make sure it uses the **public** database URL, not the internal one.
- [ ] Log in at `/backdoor/` and confirm it works.

---

## 6. Load the starting data, in this order

Run each of these once.

1. [ ] `python manage.py seed_db`: fills the Logic model (categories, tags, site types, ad sizes and click types). The click tracking needs the **Article** and **Advert** click types to exist.
2. [ ] `python manage.py import_sites`: loads your sites from CSV (check the script header for the file path and format).
3. [ ] `python manage.py batch_sites`: puts the sites into batches.
4. [ ] `python manage.py ingest_all --days 365`: first load of articles. It can take a while, so run it in a Railway shell, not as a web request.
5. [ ] `python manage.py import_articles`: only if you are bringing in articles from CSV.
6. [ ] `python manage.py filter_articles`: hides articles that match your keywords.
7. [ ] `python manage.py hide_articles`: applies each site's hide setting.
8. [ ] `python manage.py count_articles`: updates the article counts on sites.
9. [ ] `python manage.py last_article`: records days since each site's last article.
10. [ ] `python manage.py backfill_images`: fills missing article images. Try `--dry-run` first, then `--limit 50`, then without a limit.
11. [ ] Check the front page, then Newest, Popular and Search.

Do **not** upload your local `db.sqlite3`. Start Railway's database fresh from the steps above.

---

## 7. Scheduled scripts (Railway cron)

How Railway cron works:

- A cron job is its own service in the project. Railway starts the service on the schedule, runs its **Start Command** and expects it to **exit** when finished.
- Set the schedule under the service's **Settings → Cron Schedule**.
- Schedules are in **UTC**, not Melbourne time. Melbourne is UTC+10, or UTC+11 during daylight saving, so a job at `0 19 * * *` UTC runs at 5am or 6am Melbourne.
- The smallest interval is 5 minutes. If the previous run is still going when the next is due, the new run is skipped.
- Each cron service needs the same variables as the web service (`SECRET_KEY`, `DATABASE_URL` and the rest). The easiest way is shared variables, or a reference to the web service's variables.

For each job below: **New → GitHub Repo → same repo**, set the Start Command, set the Cron Schedule, add the variables.

| Service name | Start Command | Suggested schedule (UTC) | Notes |
|---|---|---|---|
| `cron-ingest` | `python manage.py ingest_all` | `0 */4 * * *` | Reads the RSS feeds. Batches mean each run only does part of the sites. Tune the frequency to match |
| `cron-maintenance` | `python manage.py filter_articles && python manage.py hide_articles && python manage.py count_articles && python manage.py last_article` | `30 19 * * *` (daily) | Runs after the ingest. Confirm the order is right for you |
| `cron-age` | `python manage.py age_articles` | Your choice | Lowers article ranks so popular articles don't stay on top. Check the script header for how often it should run |
| `cron-hide-sites` | `python manage.py hide_sites` | `0 20 * * 0` (weekly) | Hides sites with no articles for a long time. Runs after `last_article` |
| `cron-aggregate` | `python manage.py aggregate_clicks` | `0 18 2 * *` (monthly, 2nd) | Totals **last month's** clicks into Analytics |
| `cron-purge` | `python manage.py purge_clicks` | `0 18 3 * *` (monthly, 3rd) | Deletes the clicks from four months ago, but only if Analytics matches |

Notes:

- The aggregate job must always run before the purge job. The purge refuses to delete anything Analytics doesn't already hold, so a failed aggregation is safe. The purge fails with an error and tells you what to run.
- `purge_clicks` keeps about 90 days of clicks in full, so you have time to notice a failure.
- Check the **Logging** model in the admin after the first run of each job to confirm they work.
- Any run that finishes with an error shows as failed in the Railway dashboard. Look there first.

Cron services use your build minutes and memory. If you want fewer services, you can chain related commands with `&&` in one service, as `cron-maintenance` does above.

---

## 8. After the first scheduled runs

- [ ] Check the Logging admin page for ingest, filter and analytics entries.
- [ ] Click a few articles and an advert on the live site. Check the Clicks model records them and the article's click count goes up.
- [ ] After the 1st of next month, check the Analytics model has last month's rows.
- [ ] Check the sites count and article count in the admin look sensible.

---

## 9. Domain, search engines and extras

- [ ] Add your custom domain: web service → **Settings → Networking → Custom Domain**, then add the DNS record Railway shows you.
- [ ] Add the domain to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
- [ ] Submit `https://yourdomain/sitemap.xml` to Google Search Console.
- [ ] Consider adding `Disallow: /search/` to robots.txt.
- [ ] Set up a Postgres backup routine: take a manual backup before risky changes such as migrations or bulk deletes.

---

## 10. Ongoing checklist

| When | What |
|---|---|
| Every deploy | Check the deploy log for migration errors |
| Weekly | Look at the Logging admin page for failures |
| Monthly | Confirm Analytics has the new month and the old month's clicks were purged |
| Before any model change | Back up the database |

---

## Your own notes

-
