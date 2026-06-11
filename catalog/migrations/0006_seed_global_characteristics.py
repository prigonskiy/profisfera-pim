# Data-миграция: создаёт четыре ОБЩИЕ характеристики (доработка 3).
#
# КАК ПРИМЕНИТЬ:
#   1. Сначала сгенерируй схемную миграцию по изменениям моделей:
#          python manage.py makemigrations catalog
#      Она добавит is_global, gtin, tnved_code, country_of_origin. Запомни её имя
#      (например, 0005_characteristic_is_global_product_gtin_and_more).
#   2. Переименуй ЭТОТ файл в следующий по порядку номер, напр.:
#          0006_seed_global_characteristics.py
#   3. В dependencies ниже впиши имя схемной миграции из шага 1 (без «.py»).
#   4. Применяй: python manage.py migrate
#
# Миграция идемпотентна (get_or_create) — повторный прогон ничего не дублирует.

from django.db import migrations


GLOBAL_CHARACTERISTICS = [
    {"code": "chestny_znak", "name": "Честный Знак", "type": "boolean", "order": 100},
    {"code": "manufacturer_plant", "name": "Завод-изготовитель", "type": "text", "order": 110},
    {"code": "storage_conditions", "name": "Условия хранения", "type": "text", "order": 120},
    {
        "code": "med_device_class",
        "name": "Класс медицинского изделия",
        "type": "single_select",
        "order": 130,
        "options": ["1", "2а", "2б", "3"],
    },
]


def seed(apps, schema_editor):
    Characteristic = apps.get_model("catalog", "Characteristic")
    CharacteristicOption = apps.get_model("catalog", "CharacteristicOption")
    for spec in GLOBAL_CHARACTERISTICS:
        ch, _ = Characteristic.objects.get_or_create(
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "type": spec["type"],
                "is_global": True,
                "order": spec["order"],
            },
        )
        if not ch.is_global:           # на случай, если запись уже была не общей
            ch.is_global = True
            ch.save(update_fields=["is_global"])
        for i, value in enumerate(spec.get("options", [])):
            CharacteristicOption.objects.get_or_create(
                characteristic=ch, value=value, defaults={"order": i}
            )


def unseed(apps, schema_editor):
    Characteristic = apps.get_model("catalog", "Characteristic")
    codes = [s["code"] for s in GLOBAL_CHARACTERISTICS]
    Characteristic.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        # ↓↓↓ ЗАМЕНИ на имя схемной миграции из шага 1 (без «.py»):
        ("catalog", "0005_characteristic_is_global_product_country_of_origin_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
