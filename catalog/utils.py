"""Вспомогательные функции: транслитерация, слаги, валидация GTIN."""
from django.core.exceptions import ValidationError
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


def validate_gtin(value):
    """
    Проверяет штрих-код по стандарту GTIN: только цифры, длина 8/12/13/14,
    корректная контрольная цифра. Пустое значение пропускается (поле необязательное).
    """
    if not value:
        return
    code = str(value).strip()
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        raise ValidationError(
            "GTIN должен состоять только из цифр и иметь длину 8, 12, 13 или 14 знаков."
        )
    digits = [int(c) for c in code]
    payload, check = digits[:-1], digits[-1]
    # крайняя справа цифра тела имеет вес 3, далее веса чередуются 3/1
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(payload)))
    expected = (10 - (total % 10)) % 10
    if expected != check:
        raise ValidationError("Неверная контрольная цифра GTIN — проверьте штрих-код.")
