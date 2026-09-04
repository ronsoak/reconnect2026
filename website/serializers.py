from rest_framework import serializers
from .models import Articles, Sites


# ===== ===== ===== ===== ===== ===== ===== ===== 
# Article Query
# ===== ===== ===== ===== ===== ===== ===== ===== 
class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Articles
        fields = ['id', 'title', 'url', 'image_url', 'published', 'rank', 'site']  # Include fields you want to expose

# ===== ===== ===== ===== ===== ===== ===== ===== 
# Site Query
# ===== ===== ===== ===== ===== ===== ===== ===== 
class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sites
        fields = ['id', 'name']  # Include only the fields you want in the API response