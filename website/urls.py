# urls.py
from django.urls import path
from .views import home, ArticleListView, SiteListView

urlpatterns = [
    path('', home, name='home'),  # Homepage
    path('api/articles/', ArticleListView.as_view(), name='article-list'),  # API endpoint for articles
    path('api/sites/', SiteListView.as_view(), name='site-list'),
]