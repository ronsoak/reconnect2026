from django import template

from website.feed import visible_articles


register = template.Library()


@register.simple_tag(takes_context=True)
def footer_article_count(context):
    if "article_count" in context:
        return context["article_count"]
    return visible_articles().count()
