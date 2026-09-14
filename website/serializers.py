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
    category_text = serializers.CharField(source='category.value', read_only=True)  # Access the related Logic model's name field
    tags_text = serializers.SerializerMethodField()  # Custom field to fetch tags

    class Meta:
        model = Sites
        fields = ['id', 'name', 'category_text', 'tags_text']  # Include only the fields you want in the API response
        
    def get_tags_text(self, obj):
        # Fetch the tag values from the related Logic model
        return [tag.value for tag in obj.tags.all()]