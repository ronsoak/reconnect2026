# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from .models import Articles, Sites
from .serializers import ArticleSerializer, SiteSerializer
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
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
    filterset_fields = ['site', 'published']  # Allow filtering by site or published date

class SiteListView(ListAPIView):
    queryset = Sites.objects.filter(hidden=False)  # Fetch all sites
    serializer_class = SiteSerializer

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Home Page
# ===== ===== ===== ===== ===== ===== ===== ===== 
def home(request):
    return render(request, 'home.html')