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
| `website/management/commands/` | Scripts listed below |
| `templates/base.html` | Base layout every page extends |
| `templates/components/` | Reusable pieces: header, search bar, menu, filters, footer |
| `static/css/custom.css` | Styling Bulma cannot do |

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
| `hide_sites` | Hides sites with no recent articles |
| `hide_articles` | Hides or unhides articles to match their site's setting |
| `filter_articles` | Hides articles that match keywords in the Logic model |
| `age_articles` | Lowers article rank so popular articles do not stay on top |

## Deploying

1. Commit all migrations in `website/migrations/`.
2. Set `SECRET_KEY` and the other environment variables on the host.
3. Run `python manage.py migrate --noinput`.
4. Run `python manage.py seed_db`, then the import scripts.

`reconnect/settings.py` is still a development configuration (`DEBUG`, `ALLOWED_HOSTS`, SQLite). Harden it before going live.
