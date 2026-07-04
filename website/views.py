from datetime import datetime
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.http import HttpResponse
from django.shortcuts import render
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from website.forms import ArticleFilterForm
from website.models import Articles

def home(request):
    return HttpResponse("Welcome to your Django app!")

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Recap View
# ===== ===== ===== ===== ===== ===== ===== ===== 
@method_decorator(staff_member_required, name='dispatch')
class ArticleRecapView(View):
    template_name = 'admin/article_recap.html'
    
    def get(self, request):
        form = ArticleFilterForm()
        articles = Articles.objects.all().order_by('-created')
        
        # Apply filters if form is submitted
        if request.GET:
            form = ArticleFilterForm(request.GET)
            if form.is_valid():
                if form.cleaned_data['start_date']:
                    articles = articles.filter(created__gte=form.cleaned_data['start_date'])
                
                if form.cleaned_data['end_date']:
                    articles = articles.filter(created__lte=form.cleaned_data['end_date'])
                
                if form.cleaned_data['hidden'] is not None:
                    articles = articles.filter(hidden=form.cleaned_data['hidden'])
                
                if form.cleaned_data['site']:
                    articles = articles.filter(site=form.cleaned_data['site'])
        
        context = {
            'articles': articles,
            'form': form,
            'title': 'Article Recap',
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        # Handle bulk download
        selected_ids = request.POST.getlist('selected_articles')
        
        if not selected_ids:
            return HttpResponse('No articles selected', status=400)
        
        articles = Articles.objects.filter(id__in=selected_ids)
        
        # Create text file content
        content = self._generate_file_content(articles)
        
        # Return as downloadable file
        response = HttpResponse(content, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="articles_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt"'
        return response
    
    def _generate_file_content(self, articles):
        """Format articles for text file"""
        lines = []
        lines.append("=" * 80)
        lines.append("ARTICLE EXPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        for article in articles:
            lines.append("-" * 80)
            lines.append(f"Title: {article.title}")
            lines.append(f"Site: {article.site.name if article.site else 'N/A'}")
            lines.append(f"Rank: {article.rank}")
            lines.append(f"Published: {article.published}")
            lines.append(f"Hidden: {article.hidden}")
            lines.append(f"Created: {article.created}")
            lines.append("")
        
        return "\n".join(lines)