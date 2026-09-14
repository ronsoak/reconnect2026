# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from .models import Articles, Sites
from .serializers import ArticleSerializer, SiteSerializer
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.generics import ListAPIView

# ===== ===== ===== ===== ===== ===== ===== ===== 
# API
# ===== ===== ===== ===== ===== ===== ===== ===== 
class ArticleListView(ListAPIView):
    queryset = Articles.objects.filter(hidden=False, site_hide=False)
    serializer_class = ArticleSerializer
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'site__name']
    ordering_fields = ['rank', 'created', 'published']
    filterset_fields = ['site', 'published','site__category__value']  # Allow filtering by site or published date

    def get_queryset(self):
        queryset = super().get_queryset()
        tags = self.request.query_params.getlist('tags')  # Get multiple tags from query params
        category = self.request.query_params.get('site__category__value')  # Get category from query params

        if category:
            queryset = queryset.filter(site__category__value=category)  # Filter by category
        if tags:
            queryset = queryset.filter(site__tags__value__in=tags).distinct()  # Filter by multiple tags

        return queryset

class SiteListView(ListAPIView):
    queryset = Sites.objects.filter(hidden=False)  # Fetch all sites
    serializer_class = SiteSerializer

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Home Page
# ===== ===== ===== ===== ===== ===== ===== ===== 
def home(request):
    return render(request, 'home.html')