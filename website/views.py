import random
import time
from urllib.parse import urlencode

from django.core import signing
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpResponse, HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .feed import (
    arrange_large_cards,
    build_article_cards,
    build_dynamic_feed,
    build_ordered_feed,
    search_articles,
    visible_articles,
)
from .contact import (
    ContactForm,
    is_rate_limited,
    record_submission,
    send_notification,
    turnstile_enabled,
    verify_turnstile,
)
from .models import Adverts, Articles, Clicks, FrontPageNotice, Logic, Sites
from .widgets import dynamic_widgets


FILTER_COOKIE = "reconnect_filters"
FILTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 12 months
SITE_ARTICLE_SORTS = {"newest", "popular", "random"}
SITE_ARTICLE_ORDERS = (
    ("newest", "Newest"),
    ("popular", "Popular"),
    ("random", "Random"),
)


def current_filters(request):
    """
    The category and tag ids to use for this request, plus whether they came from the URL.
    The URL wins (Apply submits it). With nothing in the URL the saved cookie is used.
    Choices are repeated parameters, e.g. /?category=1&category=2&tag=5
    """
    if "apply" in request.GET or "category" in request.GET or "tag" in request.GET:
        source, from_url = request.GET, True
    else:
        source, from_url = QueryDict(request.COOKIES.get(FILTER_COOKIE, "")), False
    categories = [v for v in source.getlist("category") if v.isascii() and v.isdigit()]
    tags = [v for v in source.getlist("tag") if v.isascii() and v.isdigit()]
    return categories, tags, from_url


def filter_context(request):
    """Options and current selections for the header filters."""
    categories, tags, _ = current_filters(request)
    return {
        "categories": Logic.objects.filter(logic_type="CATEGORY"),
        "tags": Logic.objects.filter(logic_type="TAG"),
        "selected_categories": categories,
        "selected_tags": tags,
    }


def remember_filters(response, context, request):
    """Saves filters the user has just applied (12 months)."""
    _, _, from_url = current_filters(request)
    if from_url:
        saved = QueryDict(mutable=True)
        saved.setlist("category", context["selected_categories"])
        saved.setlist("tag", context["selected_tags"])
        response.set_cookie(
            FILTER_COOKIE, saved.urlencode(), max_age=FILTER_COOKIE_MAX_AGE, samesite="Lax"
        )
    return response


def filter_ids(context):
    return (
        [int(value) for value in context["selected_categories"]],
        [int(value) for value in context["selected_tags"]],
    )


@never_cache
def home(request):
    """
    Dynamic feed. Refreshing the page gives a new random batch.
    ?reset=1 clears the saved filters.
    """
    if "reset" in request.GET:
        response = redirect(request.path)
        response.delete_cookie(FILTER_COOKIE)
        return response

    context = filter_context(request)
    category_ids, tag_ids = filter_ids(context)
    context["cards"] = build_dynamic_feed(category_ids=category_ids, tag_ids=tag_ids)
    context.update(dynamic_widgets(context["cards"], category_ids, tag_ids))
    context["active_feed"] = "dynamic"
    context["front_page_notice"] = FrontPageNotice.objects.filter(is_active=True).first()
    return remember_filters(render(request, "home.html", context), context, request)


def ordered_feed(request, order):
    """Shared by the Newest and Popular pages. ?page=2 shows older or lower ranked articles."""
    if "reset" in request.GET:
        response = redirect(request.path)
        response.delete_cookie(FILTER_COOKIE)
        return response

    context = filter_context(request)
    category_ids, tag_ids = filter_ids(context)
    context["cards"], context["page_obj"] = build_ordered_feed(
        order, category_ids=category_ids, tag_ids=tag_ids, page=request.GET.get("page", 1)
    )
    context.update(dynamic_widgets(context["cards"], category_ids, tag_ids))
    context["active_feed"] = order
    return remember_filters(render(request, "home.html", context), context, request)


def newest(request):
    return ordered_feed(request, "newest")


def popular(request):
    return ordered_feed(request, "popular")


def search(request):
    """Search results at /search/?q=. Filters are not applied and there are no adverts."""
    query = request.GET.get("q", "").strip()[:200]
    context = filter_context(request)
    context["query"] = query
    context["hide_filters"] = True
    context["cards"], context["page_obj"], context["terms"] = search_articles(
        query, page=request.GET.get("page", 1)
    )
    context["query_string"] = "&" + urlencode({"q": query})
    return render(request, "search.html", context)


# Article clicks. A signed cookie remembers which articles this browser has counted and when.
CLICK_COOKIE = "reconnect_clicks"
CLICK_WINDOW_SECONDS = 60 * 60 * 24  # one counted click per article per 24 hours
CLICK_COOKIE_MAX_ENTRIES = 100  # keeps the cookie small


def read_recent_clicks(request, now):
    """Article id -> time of last counted click, for clicks inside the 24 hour window."""
    try:
        recent = signing.loads(request.COOKIES.get(CLICK_COOKIE, ""), salt=CLICK_COOKIE)
        return {str(k): v for k, v in recent.items() if now - v < CLICK_WINDOW_SECONDS}
    except (signing.BadSignature, AttributeError, TypeError):
        return {}


def count_click(request, key, record):
    """
    Runs record() (which saves the click) unless this browser already counted `key` in the last
    24 hours. Returns the cookie value to save, or None when nothing was counted.
    """
    now = int(time.time())
    recent = read_recent_clicks(request, now)
    if key in recent:
        return None
    with transaction.atomic():
        record()
    recent[key] = now
    newest = dict(sorted(recent.items(), key=lambda item: item[1])[-CLICK_COOKIE_MAX_ENTRIES:])
    return signing.dumps(newest, salt=CLICK_COOKIE)


def redirect_with_click_cookie(url, cookie_value):
    response = HttpResponseRedirect(url)
    if cookie_value:
        response.set_cookie(
            CLICK_COOKIE, cookie_value, max_age=CLICK_WINDOW_SECONDS, httponly=True, samesite="Lax"
        )
    return response


def click_type(value):
    return Logic.objects.filter(logic_type="CLICK_TYPE", value=value).first()


def go_article(request, pk):
    """
    Counts a click on an article, then sends the visitor on to it.
    The click is added to the article and recorded in the Clicks model, at most once
    per article per browser every 24 hours. Repeat clicks still go through, they just aren't counted.
    Example: /go/123/
    """
    article = get_object_or_404(Articles.objects.select_related("site"), pk=pk, hidden=False, site_hide=False)

    def record():
        # F() adds to the stored value, so simultaneous clicks are not lost
        Articles.objects.filter(pk=article.pk).update(clicks=F("clicks") + 1)
        Clicks.objects.create(type=click_type("Article"), article=str(article.pk), site=article.site)

    cookie_value = count_click(request, str(article.pk), record)
    return redirect_with_click_cookie(article.url, cookie_value)


def go_article_from_rss(request, pk):
    """Record an RSS click, then redirect the reader to the original article."""
    article = get_object_or_404(
        Articles.objects.select_related("site"),
        pk=pk,
        hidden=False,
        site_hide=False,
        site__hidden=False,
    )
    rss_type = Logic.objects.get(logic_type="CLICK_TYPE", value="RSS")

    def record():
        Articles.objects.filter(pk=article.pk).update(clicks=F("clicks") + 1)
        Clicks.objects.create(
            type=rss_type,
            article=str(article.pk),
            site=article.site,
        )

    cookie_value = count_click(request, f"rss{article.pk}", record)
    return redirect_with_click_cookie(article.url, cookie_value)


def go_advert(request, pk):
    """
    Counts a click on an advert, then sends the visitor to the advertiser.
    Same rules as articles: once per advert per browser every 24 hours, recorded in the Clicks
    model with the Advert type (its article column holds the advert id). Adverts that are
    not running today still redirect, so an old open page keeps working, but are not counted.
    Example: /go/ad/4/
    """
    advert = get_object_or_404(Adverts, pk=pk)
    today = timezone.localdate()
    if not advert.start_date <= today <= advert.end_date:
        return HttpResponseRedirect(advert.site_url)

    def record():
        Adverts.objects.filter(pk=advert.pk).update(clicks=F("clicks") + 1)
        Clicks.objects.create(type=click_type("Advert"), article=str(advert.pk))

    cookie_value = count_click(request, f"ad{advert.pk}", record)
    return redirect_with_click_cookie(advert.site_url, cookie_value)


def render_about(request, contact_form=None, status=200):
    context = filter_context(request)
    context["hide_filters"] = True
    articles = visible_articles()
    context["article_count"] = articles.count()
    context["site_count"] = articles.order_by().values("site_id").distinct().count()
    context["rss_feed_item_limit"] = settings.RSS_FEED_ITEM_LIMIT
    context["contact_form"] = contact_form or ContactForm()
    context["contact_sent"] = request.GET.get("sent") == "1"
    context["turnstile_site_key"] = settings.TURNSTILE_SITE_KEY if turnstile_enabled() else ""
    return render(request, "about.html", context, status=status)


def about(request):
    return render_about(request)


@require_POST
def contact(request):
    sent_url = f"{reverse('about')}?sent=1#contact"
    form = ContactForm(request.POST)

    # Bots that fill the hidden field are told it worked, so they learn nothing.
    if form.is_honeypot_filled:
        return HttpResponseRedirect(sent_url)

    if is_rate_limited(request):
        form.is_valid()
        form.add_error(None, "You've sent a few messages recently. Please try again in an hour.")
        return render_about(request, form, status=429)

    if not form.is_valid():
        return render_about(request, form, status=400)

    if not verify_turnstile(request):
        form.add_error(None, "We couldn't confirm you're human. Please complete the check and send again.")
        return render_about(request, form, status=400)

    contact_message = form.save()
    record_submission(request)
    send_notification(contact_message)
    return HttpResponseRedirect(sent_url)


def privacy(request):
    return render(request, "privacy.html", {"hide_filters": True})


def publications(request):
    selected_categories = [
        value for value in request.GET.getlist("category")
        if value.isascii() and value.isdigit()
    ]
    selected_tags = [
        value for value in request.GET.getlist("tag")
        if value.isascii() and value.isdigit()
    ]
    sort = request.GET.get("sort", "alpha")
    if sort not in {"alpha", "newest", "reverse", "random"}:
        sort = "alpha"

    sites = Sites.objects.filter(hidden=False).annotate(
        visible_article_count=Count(
            "articles",
            filter=Q(articles__hidden=False, articles__site_hide=False),
            distinct=True,
        )
    ).filter(visible_article_count__gt=0)
    if selected_categories:
        sites = sites.filter(category_id__in=selected_categories)
    if selected_tags:
        sites = sites.filter(tags__pk__in=selected_tags)
    sites = sites.select_related("category", "site_type").prefetch_related("tags").distinct()
    if sort == "newest":
        sites = sites.order_by("-pk")
    elif sort == "reverse":
        sites = sites.order_by("-name", "-pk")
    elif sort == "random":
        sites = sites.order_by("?")
    else:
        sites = sites.order_by("name", "pk")

    page_obj = Paginator(sites, settings.PUBLICATIONS_PAGE_SIZE).get_page(request.GET.get("page", 1))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    context = {
        "categories": Logic.objects.filter(logic_type="CATEGORY").order_by("value"),
        "tags": Logic.objects.filter(logic_type="TAG").order_by("value"),
        "selected_categories": selected_categories,
        "selected_tags": selected_tags,
        "sort": sort,
        "page_obj": page_obj,
        "extra_query": f"&{query_params.urlencode()}" if query_params else "",
        "hide_filters": True,
    }
    return render(request, "publications.html", context)


def site_articles(request, site_id):
    site = get_object_or_404(
        Sites.objects.filter(hidden=False).select_related("category", "site_type").prefetch_related("tags"),
        pk=site_id,
    )
    order = request.GET.get("order", "newest")
    if order not in SITE_ARTICLE_SORTS:
        order = "newest"

    articles = visible_articles().filter(site=site).select_related("site__category")
    if order == "popular":
        articles = articles.order_by("-rank", "-published", "run_id", "pk")
    elif order == "random":
        articles = articles.order_by("?")
    else:
        articles = articles.order_by("-published", "run_id", "pk")

    page_obj = Paginator(
        articles[:settings.PUBLICATION_ARTICLES_LIMIT], settings.PUBLICATION_ARTICLES_PAGE_SIZE
    ).get_page(
        request.GET.get("page", 1)
    )
    rng = random.Random()
    cards = build_article_cards(list(page_obj.object_list), rng)

    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "site_articles.html",
        {
            "site": site,
            "cards": arrange_large_cards(cards, rng),
            "page_obj": page_obj,
            "order": order,
            "article_orders": SITE_ARTICLE_ORDERS,
            "extra_query": f"&{query_params.urlencode()}" if query_params else "",
            "hide_filters": True,
        },
    )


def robots_txt(request):
    """Allows crawling of the public site, keeps the admin out and points to the sitemap."""
    lines = [
        "User-agent: *",
        "Disallow: /backdoor/",
        "Disallow: /go/",
        "Disallow: /search/",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('django.contrib.sitemaps.views.sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
