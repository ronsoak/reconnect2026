from django import forms
from datetime import datetime, timedelta

class ArticleFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Start Date'
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='End Date'
    )
    hidden = forms.NullBooleanField(
        required=False,
        widget=forms.Select(choices=[('', '---'), (True, 'Hidden'), (False, 'Visible')]),
        label='Status'
    )
    site = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='All Sites'
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from website.models import Sites
        self.fields['site'].queryset = Sites.objects.all()