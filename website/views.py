# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator


# ===== ===== ===== ===== ===== ===== ===== ===== 
# Home Page
# ===== ===== ===== ===== ===== ===== ===== ===== 
def home(request):
    return HttpResponse("Welcome to your Django app!")
