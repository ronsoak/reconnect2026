# ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.contrib import admin
from website.models import Logic, Sites 
from django import forms

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Website Logic
# ===== ===== ===== ===== ===== ===== ===== ===== 
@admin.register(Logic)
class LogicAdmin(admin.ModelAdmin):
    list_display=('logic_type','parent','value')
    list_filter=['logic_type','parent']
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

class SitesAdmin(admin.ModelAdmin):
    form = SitesAdminForm

admin.site.register(Sites, SitesAdmin)