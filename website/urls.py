from . import views
from django.urls import path
from django.urls import path
from website.views import ArticleRecapView

urlpatterns = [
    path('', views.home, name='home'),
]