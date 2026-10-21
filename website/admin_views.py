# Custom admin pages (not tied to one model).
from django.contrib import admin
from django.http import HttpResponse
from django.template.response import TemplateResponse

from website.newsletter import build_newsletter, period_range, render_markdown


def newsletter_export(request):
    """Preview of the recap with a button to download it as markdown.

    /backdoor/newsletter/                          this week (Monday to Sunday)
    /backdoor/newsletter/?which=last               previous week
    /backdoor/newsletter/?period=month             this calendar month
    /backdoor/newsletter/?period=month&which=last  previous calendar month
    add &download=1 to get the same data as a .md file
    """
    period = "month" if request.GET.get("period") == "month" else "week"
    which = "last" if request.GET.get("which") == "last" else "this"
    start, end, top_count = period_range(period, which)
    data = build_newsletter(start, end, top_count, period=period)

    if request.GET.get("download"):
        response = HttpResponse(render_markdown(data), content_type="text/markdown; charset=utf-8")
        name = f"{start:%Y-%m}" if period == "month" else f"{start:%Y-%m-%d}"
        response["Content-Disposition"] = f'attachment; filename="recap-{period}-{name}.md"'
        return response

    context = {
        **admin.site.each_context(request),
        "title": "Newsletter export",
        "period": period,
        "which": which,
        **data,
    }
    return TemplateResponse(request, "admin/newsletter_export.html", context)
