# urls.py
from django.contrib.sitemaps.views import sitemap
from django.urls import path

from .api import FeedView, FiltersView, SearchView
from .sitemaps import StaticPagesSitemap
from .views import about, home, go_advert, go_article, newest, popular, robots_txt, search

sitemaps = {"static": StaticPagesSitemap}

urlpatterns = [
    path('', home, name='home'),  # Homepage
    path('newest/', newest, name='newest'),
    path('popular/', popular, name='popular'),
    path('search/', search, name='search'),
    path('api/feed/', FeedView.as_view(), name='api_feed'),
    path('api/search/', SearchView.as_view(), name='api_search'),
    path('api/filters/', FiltersView.as_view(), name='api_filters'),
    path('go/<int:pk>/', go_article, name='go_article'),
    path('go/ad/<int:pk>/', go_advert, name='go_advert'),
    path('about/', about, name='about'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
]
