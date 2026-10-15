# urls.py
from django.contrib.sitemaps.views import sitemap
from django.urls import path

from .api import FeedView, FiltersView, SearchView
from .sitemaps import SiteArticlesSitemap, StaticPagesSitemap
from .rss import ArticlesFeed
from .views import (
    about,
    home,
    go_advert,
    go_article,
    go_article_from_rss,
    newest,
    popular,
    privacy,
    publications,
    robots_txt,
    search,
    site_articles,
)

sitemaps = {"static": StaticPagesSitemap, "sites": SiteArticlesSitemap}

urlpatterns = [
    path('', home, name='home'),  # Homepage
    path('newest/', newest, name='newest'),
    path('popular/', popular, name='popular'),
    path('search/', search, name='search'),
    path('publications/', publications, name='publications'),
    path('publications/<int:site_id>/', site_articles, name='site_articles'),
    path('feeds/all.rss', ArticlesFeed(), name='rss_feed_all'),
    path(
        'feeds/category/<int:category_id>.rss',
        ArticlesFeed(),
        name='rss_feed_category',
    ),
    path('api/feed/', FeedView.as_view(), name='api_feed'),
    path('api/search/', SearchView.as_view(), name='api_search'),
    path('api/filters/', FiltersView.as_view(), name='api_filters'),
    path('go/<int:pk>/', go_article, name='go_article'),
    path('go/rss/<int:pk>/', go_article_from_rss, name='rss_article_click'),
    path('go/ad/<int:pk>/', go_advert, name='go_advert'),
    path('about/', about, name='about'),
    path('privacy/', privacy, name='privacy'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
]
