from django.shortcuts import render

from .models import Logic


def home(request):
    # Options for the category and genre filters in the header
    context = {
        "categories": Logic.objects.filter(logic_type="CATEGORY"),
        "tags": Logic.objects.filter(logic_type="TAG"),
    }
    return render(request, "home.html", context)
