from django import template
from news.models import SummaryVersion

register = template.Library()


@register.filter
def status_label(value):
    return dict(SummaryVersion.Status.choices).get(value, "Sem resumo")
