# Data-миграция: присваивает внутренний артикул sku всем уже существующим
# товарам и выставляет счётчик SkuCounter.
#
# КАК ПРИМЕНИТЬ:
#   1. python manage.py makemigrations catalog
#      Создаст СХЕМНУЮ миграцию (новая модель SkuCounter + поле Product.sku).
#      sku объявлен null=True, поэтому добавление столбца к уже заполненной
#      таблице пройдёт без ошибок (у существующих строк sku будет пустым).
#      Запомни имя этой схемной миграции.
#   2. Переименуй этот файл в следующий по порядку номер, напр.
#      0011_backfill_sku.py
#   3. Впиши имя схемной миграции из шага 1 в dependencies ниже (без «.py»).
#   4. python manage.py migrate
#
# Идемпотентна: присваивает sku только там, где он ещё пуст; повторный запуск
# ничего не испортит. Нумерация sku — по порядку id (как товары создавались).

from django.db import migrations

SKU_START = 1000000000  # первый выданный артикул будет 1000000001


def backfill(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    SkuCounter = apps.get_model("catalog", "SkuCounter")
    counter, _ = SkuCounter.objects.get_or_create(pk=1, defaults={"current": SKU_START})
    value = counter.current
    for p in Product.objects.order_by("id"):
        if not p.sku:
            value += 1
            p.sku = str(value)
            p.save(update_fields=["sku"])
    counter.current = value
    counter.save(update_fields=["current"])


def reverse(apps, schema_editor):
    apps.get_model("catalog", "Product").objects.update(sku=None)
    apps.get_model("catalog", "SkuCounter").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        # ↓↓↓ ЗАМЕНИ на имя схемной миграции из шага 1 (без «.py»):
        ("catalog", "0010_skucounter_product_sku"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
