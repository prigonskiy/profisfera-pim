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


def category_descendant_ids(category_id):
    """Id категории и всех её потомков одним запросом (через MPTT).

    Единая реализация «категория с потомками». Раньше их было две — обход
    parent_id в API и обход карты категорий в импорте/экспорте; обе заменены
    этой, опирающейся на дерево MPTT (поля lft/rght).

    Category импортируется локально: utils подключается из models.py, и импорт
    модели на уровне модуля дал бы циклическую зависимость.
    """
    from .models import Category
    node = Category.objects.filter(pk=category_id).first()
    if node is None:
        return [category_id]
    return list(node.get_descendants(include_self=True).values_list("id", flat=True))


def normalize_hex_color(value):
    """Привести цвет к каноническому «#RRGGBB» или вернуть None, если это не цвет.

    Принимает «#c8a165», «C8A165», «#CA6» (короткая форма) и пробелы по краям.
    Ничего не выбрасывает — решение, что делать с непонятным значением,
    принимает вызывающий код (форма ругается, импорт пишет предупреждение).
    """
    if not value:
        return None
    text = str(value).strip().lstrip("#").upper()
    if len(text) == 3 and all(c in "0123456789ABCDEF" for c in text):
        text = "".join(c * 2 for c in text)  # #CA6 → #CCAA66
    if len(text) != 6 or not all(c in "0123456789ABCDEF" for c in text):
        return None
    return "#" + text


def validate_hex_color(value):
    """Валидатор поля: пусто допустимо, иначе обязателен корректный HEX."""
    if not value:
        return
    if normalize_hex_color(value) is None:
        raise ValidationError(
            "Укажите цвет в формате #RRGGBB, например #C8A165."
        )


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
