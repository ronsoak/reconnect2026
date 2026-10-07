# urls.py
from django.urls import path
from .views import home, ArticleListView, SiteListView

urlpatterns = [
    path('', home, name='home'),  # Homepage
]