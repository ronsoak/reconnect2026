# Custom admin pages (not tied to one model).
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.utils import timezone

from website.analytics_reports import AnalyticsReportForm, build_report, render_report_markdown
from website.management.commands.aggregate_clicks import first_of_month, previous_month
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


def analytics_report(request):
    if not request.user.has_perm("website.view_analytics"):
        raise PermissionDenied
    today = timezone.localdate()
    initial = {
        "report": "adverts", "period": "month",
        "month": previous_month(first_of_month(today)).strftime("%Y-%m"),
        "year": today.year,
    }
    params = {**initial, **request.GET.dict()}
    form = AnalyticsReportForm(params)
    data = None
    page = None
    if form.is_valid():
        cleaned = form.cleaned_data
        data = build_report(
            cleaned["report"], cleaned["start"], cleaned["end"],
            object_id=cleaned["object_id"],
            include_baseline=cleaned["include_baseline"], today=today,
        )
        if request.GET.get("download"):
            response = HttpResponse(render_report_markdown(data), content_type="text/markdown; charset=utf-8")
            selection = f"-{cleaned['object_id']}" if cleaned["object_id"] else ""
            filename = (
                f"analytics-{cleaned['report']}{selection}-"
                f"{data['start']:%Y-%m}-to-{data['end']:%Y-%m}.md"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        page = Paginator(data["rows"], 50).get_page(request.GET.get("page"))
    tabs = []
    for kind, label in (("adverts", "Adverts"), ("sites", "Publications")):
        query = request.GET.copy()
        for key in ("object_id", "page", "download"):
            query.pop(key, None)
        query["report"] = kind
        tabs.append({"kind": kind, "label": label, "query": query.urlencode()})
    pagination_query = request.GET.copy()
    for key in ("page", "download"):
        pagination_query.pop(key, None)
    return TemplateResponse(request, "admin/analytics_report.html", {
        **admin.site.each_context(request),
        "title": "Analytics reports", "form": form, "report": data,
        "page": page, "tabs": tabs, "pagination_query": pagination_query.urlencode(),
    }, status=200 if not form.errors else 400)
