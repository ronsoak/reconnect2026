from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from .models import Logic


def filter_context(request):
    """
    Options and current selections for the header filters.
    Multiple choices are sent as repeated parameters, e.g. /?category=1&category=2&tag=5
    """
    return {
        "categories": Logic.objects.filter(logic_type="CATEGORY"),
        "tags": Logic.objects.filter(logic_type="TAG"),
        "selected_categories": request.GET.getlist("category"),
        "selected_tags": request.GET.getlist("tag"),
    }


def home(request):
    return render(request, "home.html", filter_context(request))


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
