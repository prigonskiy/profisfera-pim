"""Вспомогательные функции: транслитерация и генерация уникальных слагов."""
from slugify import slugify


def unique_slugify(instance, value, slug_field_name="slug"):
    """
    Транслитерирует value в латинский slug и гарантирует уникальность в рамках
    модели. Кириллица переводится в латиницу (Дрель ударная -> drel-udarnaia).
    При совпадении добавляется числовой суффикс (drel-udarnaia-2 и т.д.).
    """
    base = slugify(value) or "item"
    model = instance.__class__
    candidate = base
    counter = 2
    queryset = model._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.filter(**{slug_field_name: candidate}).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate
