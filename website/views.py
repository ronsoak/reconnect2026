from django.http import HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .feed import build_dynamic_feed, build_ordered_feed
from .models import Logic


FILTER_COOKIE = "reconnect_filters"
FILTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 12 months


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
    context["active_feed"] = "dynamic"
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
    context["active_feed"] = order
    return remember_filters(render(request, "home.html", context), context, request)


def newest(request):
    return ordered_feed(request, "newest")


def popular(request):
    return ordered_feed(request, "popular")


def about(request):
    return render(request, "about.html", filter_context(request))


def robots_txt(request):
    """Allows crawling of the public site, keeps the admin out and points to the sitemap."""
    lines = [
        "User-agent: *",
        "Disallow: /backdoor/",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('django.contrib.sitemaps.views.sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
