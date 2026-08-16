# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from website.models import Logic, Sites, Articles, Logging, Adverts, Clicks
from unfold.admin import ModelAdmin                                     # for the Admin theme
from unfold.contrib.forms.widgets import ArrayWidget, WysiwygWidget     # for the Admin theme

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Website Logic
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Logic)
class LogicAdmin(ModelAdmin):
    list_display=('logic_type','value')
    list_filter=['logic_type',]
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['value']
    # Methods
    def get_ordering(self, request):
        return ['logic_type']
    
# ===== ===== ===== ===== ===== ===== ===== ===== 
# Sites
# ===== ===== ===== ===== ===== ===== ===== ===== 
class SitesAdminForm(forms.ModelForm):
    class Meta:
        model = Sites
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'category' in self.fields and self.instance.pk:
            # Limit tags to those under the selected category
            self.fields['tags'].queryset = Logic.objects.filter(
                logic_type='TAG',
                parent=self.instance.category
            )

class SitesAdmin(ModelAdmin):
    form = SitesAdminForm

@admin.register(Sites)
class SiteAdmin(ModelAdmin):
    form = SitesAdminForm  # Use the custom form
    list_display = ('name', 'hidden', 'last_article','site_type','category')
    list_filter = ['modifier', 'hidden', 'last_article','category','load_error']
    list_per_page = 500
    actions = ['hide_site']
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['name']

    # Methods
    def get_ordering(self, request):
        return ['name']

    def hide_site(self, request, queryset):
        queryset.update(hidden=True)
    hide_site.short_description = "Hidden"

    def save_model(self, request, obj, form, change):
        """
        Save the instance and its Many-to-Many relationships.
        """
        # Save the instance first
        super().save_model(request, obj, form, change)
        # Save Many-to-Many relationships
        form.save_m2m()

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Articles
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Articles)
class ArticleAdmin(ModelAdmin):
    list_display=('title','rank','site','published','hidden','site_hide')
    list_filter=['hidden','site_hide','site']
    actions = ['mark_as_hidden']
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['title']
    # Methods
    def get_ordering(self, request):
        return ['-created']

    def mark_as_hidden(self, request, queryset):
        queryset.update(hidden = True)
    mark_as_hidden.short_description = "Hidden"

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Logging
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Logging)
class LogicAdmin(ModelAdmin):
    list_display=('log_type','created','value')
    list_filter=['log_type']
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['value']
    # Methods
    def get_ordering(self, request):
        return ['log_type']

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Adverts
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Adverts)
class AdvertAdmin(ModelAdmin):
    list_display=('title','site_name','start_date','end_date')
    list_filter=['site_name']
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['title']
    # Methods
    def get_ordering(self, request):
        return ['-end_date']
    

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Clicks
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Clicks)
class ClicksAdmin(ModelAdmin):
    list_display=('type','article','site','date')
    list_filter=['type']
    show_facets = admin.ShowFacets.ALWAYS
    search_fields = ['type']
    # Methods
    def get_ordering(self, request):
        return ['-date']