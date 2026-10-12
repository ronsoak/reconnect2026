# Custom admin pages (not tied to one model).
from django.contrib import admin
from django.http import HttpResponse
from django.template.response import TemplateResponse

from website.newsletter import build_newsletter, render_markdown, week_start_for


def newsletter_export(request):
    """Preview of the weekly recap with a button to download it as markdown.

    /backdoor/newsletter/               this week (Monday to Sunday)
    /backdoor/newsletter/?week=last     previous week
    /backdoor/newsletter/?download=1    the same data as a .md file
    """
    which = "last" if request.GET.get("week") == "last" else "this"
    data = build_newsletter(week_start_for(which))

    if request.GET.get("download"):
        response = HttpResponse(render_markdown(data), content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="recap-{data["week_start"]:%Y-%m-%d}.md"'
        return response

    context = {
        **admin.site.each_context(request),
        "title": "Newsletter export",
        "which": which,
        **data,
    }
    return TemplateResponse(request, "admin/newsletter_export.html", context)
