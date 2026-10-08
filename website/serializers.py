# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
# Serializers
#
# Turn feed cards into JSON for the API. Only public fields are exposed
# (no clicks, boost, hidden flags or other internal values).
# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
from rest_framework import serializers

from .models import Adverts, Articles, Logic


class LogicOptionSerializer(serializers.ModelSerializer):
    """A category or tag choice for the filters."""

    class Meta:
        model = Logic
        fields = ["id", "value"]


class ArticleSerializer(serializers.ModelSerializer):
    site = serializers.CharField(source="site.name")
    site_id = serializers.IntegerField(source="site.pk")
    category = serializers.CharField(source="site.category.value")

    class Meta:
        model = Articles
        fields = ["id", "title", "url", "image_url", "published", "site", "site_id", "category"]


class AdvertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adverts
        fields = ["id", "message", "site_name", "site_url", "image"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["image"] = instance.image.url if instance.image else ""
        return data


class CardSerializer(serializers.Serializer):
    """
    One feed card: {"kind": "article" | "advert", "size": "small" | "medium" | "large", "item": {...}}
    """

    kind = serializers.CharField()
    size = serializers.CharField()
    item = serializers.SerializerMethodField()

    def get_item(self, card):
        serializer = AdvertSerializer if card.is_advert else ArticleSerializer
        return serializer(card.item).data
