# Template tag that picks the placeholder text for the search bar.
#
# Phrases live in the Logic model with the type SEARCH_PLACEHOLDER. Add, edit or
# delete them in the admin (Logic) like any other list. One is picked at random
# on every page load. With none saved, DEFAULT_PLACEHOLDER is used.
#
# Template use:
#   {% load search_tags %}
#   placeholder="{% search_placeholder %}"
import random

from django import template

from website.models import Logic

register = template.Library()

DEFAULT_PLACEHOLDER = "Search articles, games, topics, and more..."


@register.simple_tag
def search_placeholder():
    phrases = list(
        Logic.objects.filter(logic_type="SEARCH_PLACEHOLDER").values_list("value", flat=True)
    )
    return random.choice(phrases) if phrases else DEFAULT_PLACEHOLDER
