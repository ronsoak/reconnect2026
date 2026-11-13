from django import template

from website.feed import visible_articles


register = template.Library()


@register.simple_tag(takes_context=True)
def footer_article_count(context):
    if "article_count" in context:
        return context["article_count"]
    request = context.get("request")
    if request is None:
        return visible_articles().count()
    if not hasattr(request, "_reconnect_article_count"):
        request._reconnect_article_count = visible_articles().count()
    return request._reconnect_article_count
