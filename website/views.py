from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from .feed import build_dynamic_feed
from .models import Logic


def selected_ids(request, name):
    """Whole-number ids from a repeated parameter. Anything else is ignored."""
    return [value for value in request.GET.getlist(name) if value.isascii() and value.isdigit()]


def filter_context(request):
    """
    Options and current selections for the header filters.
    Multiple choices are sent as repeated parameters, e.g. /?category=1&category=2&tag=5
    """
    return {
        "categories": Logic.objects.filter(logic_type="CATEGORY"),
        "tags": Logic.objects.filter(logic_type="TAG"),
        "selected_categories": selected_ids(request, "category"),
        "selected_tags": selected_ids(request, "tag"),
    }


def home(request):
    context = filter_context(request)
    context["cards"] = build_dynamic_feed(
        category_ids=[int(value) for value in context["selected_categories"]],
        tag_ids=[int(value) for value in context["selected_tags"]],
    )
    return render(request, "home.html", context)


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
