# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
# API
#
# Read-only JSON endpoints that reuse the same feed code as the website.
# Filters are repeated parameters and are never taken from the cookie:
#   category = ids of Logic rows (site types), tag = ids of Logic rows (genres)
#
# Examples
#   curl "http://127.0.0.1:8000/api/feed/"
#   curl "http://127.0.0.1:8000/api/feed/?feed=newest&page=2"
#   curl "http://127.0.0.1:8000/api/feed/?feed=popular&category=1&category=2&tag=5"
#   curl "http://127.0.0.1:8000/api/search/?q=zelda+dragons"
#   curl "http://127.0.0.1:8000/api/filters/"
#
# Tests
#   python manage.py test website.test_api
# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .feed import build_dynamic_feed, build_ordered_feed, search_articles
from .models import Logic
from .serializers import CardSerializer, LogicOptionSerializer

FEEDS = ("dynamic", "newest", "popular")


class PublicReadOnlyView(APIView):
    """GET only, no login, JSON only."""

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    http_method_names = ["get", "head", "options"]


def id_list(request, name):
    """Whole-number ids from a repeated parameter. Anything else is ignored."""
    return [int(v) for v in request.query_params.getlist(name) if v.isascii() and v.isdigit()]


def page_details(page_obj):
    if page_obj is None:
        return {"page": 1, "num_pages": 0, "count": 0}
    return {
        "page": page_obj.number,
        "num_pages": page_obj.paginator.num_pages,
        "count": page_obj.paginator.count,
    }


class FeedView(PublicReadOnlyView):
    """/api/feed/?feed=dynamic|newest|popular&category=..&tag=..&page=.."""

    def get(self, request):
        feed = request.query_params.get("feed", "dynamic")
        if feed not in FEEDS:
            return Response({"detail": f"feed must be one of: {', '.join(FEEDS)}"}, status=400)

        categories, tags = id_list(request, "category"), id_list(request, "tag")
        if feed == "dynamic":
            cards, details = build_dynamic_feed(category_ids=categories, tag_ids=tags), {}
        else:
            cards, page_obj = build_ordered_feed(
                feed, category_ids=categories, tag_ids=tags, page=request.query_params.get("page", 1)
            )
            details = page_details(page_obj)

        return Response({"feed": feed, **details, "cards": CardSerializer(cards, many=True).data})


class SearchView(PublicReadOnlyView):
    """/api/search/?q=..&page=.. Filters do not apply and there are no adverts."""

    def get(self, request):
        query = request.query_params.get("q", "").strip()[:200]
        cards, page_obj, _ = search_articles(query, page=request.query_params.get("page", 1))
        return Response({"query": query, **page_details(page_obj), "cards": CardSerializer(cards, many=True).data})


class FiltersView(PublicReadOnlyView):
    """/api/filters/ lists the category and tag ids that the feed accepts."""

    def get(self, request):
        return Response({
            "categories": LogicOptionSerializer(Logic.objects.filter(logic_type="CATEGORY"), many=True).data,
            "tags": LogicOptionSerializer(Logic.objects.filter(logic_type="TAG"), many=True).data,
        })
