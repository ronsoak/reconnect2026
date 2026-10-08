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

Reconnect has a read-only JSON API so other people can build on the same feed, for example a reader app, a bot or a personal dashboard. The website itself does not use it, it calls the same feed code directly. Anyone can use it without logging in, and there is a limit of 120 requests a minute per visitor.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/feed/` | The article feed, with adverts |
| `/api/search/` | Search articles by title or site name |
| `/api/filters/` | Lists the category and tag ids the feed accepts |

All endpoints accept `GET` only and return JSON.

### Feed parameters

| Parameter | Meaning |
|-----------|---------|
| `feed` | `dynamic` (default, a fresh mix of new, older and popular), `newest` or `popular` |
| `category` | A site type id from `/api/filters/`. Repeat it to choose several, they are treated as "or" |
| `tag` | A genre id from `/api/filters/`. Repeat it to choose several, they are treated as "or" |
| `page` | Page number. Only used by `newest` and `popular` |

A category choice together with a tag choice is an "and". The API does not use the website's saved-filters cookie. The parameters are the only input.

`dynamic` returns about 100 cards in random order and gives a different batch each time. `newest` and `popular` return 100 cards per page along with `page`, `num_pages` and `count`.

### Search parameters

| Parameter | Meaning |
|-----------|---------|
| `q` | Search words. An article only needs to match some of them, case does not matter |
| `page` | Page number, 250 results per page |

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

Tests: `python manage.py test website.test_api`

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
