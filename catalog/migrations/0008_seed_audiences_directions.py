# Data-миграция: стартовый набор аудиторий и направлений (вариант 2).
#
# КАК ПРИМЕНИТЬ (как и в прошлый раз):
#   1. python manage.py makemigrations catalog   — создаст схемную миграцию
#      (модели Audience, Direction + связи M2M у товара). Запомни её имя.
#   2. Переименуй этот файл в следующий по порядку номер, напр.
#      0007_seed_audiences_directions.py
#   3. Впиши имя схемной миграции из шага 1 в dependencies ниже (без «.py»).
#   4. python manage.py migrate
#
# Идемпотентна (get_or_create по slug). Slug'и заданы вручную и «чистые» —
# именно они пойдут в ЧПУ-адреса посадочных страниц, так что правь их осознанно.

from django.db import migrations


AUDIENCES = [
    {"slug": "stomatolog",              "name": "Стоматолог",            "order": 0},
    {"slug": "zubnoy-tehnik",           "name": "Зубной техник",         "order": 1},
    {"slug": "obshchaya-meditsina",     "name": "Общая медицина",        "order": 2},
    {"slug": "patsient-domashniy-uhod", "name": "Пациент / домашний уход", "order": 3},
]

# направление: (slug, name, audience_slug, order)
DIRECTIONS = [
    ("terapiya",            "Терапия",                "stomatolog", 0),
    ("hirurgiya",           "Хирургия",               "stomatolog", 1),
    ("implantologiya",      "Имплантология",          "stomatolog", 2),
    ("ortopediya",          "Ортопедия",              "stomatolog", 3),
    ("ortodontiya",         "Ортодонтия",             "stomatolog", 4),
    ("parodontologiya",     "Пародонтология",         "stomatolog", 5),
    ("estetika-i-gigiena",  "Эстетика и гигиена",     "stomatolog", 6),
    ("cad-cam",             "CAD/CAM",                "zubnoy-tehnik", 0),
    ("metallokeramika",     "Металлокерамика",        "zubnoy-tehnik", 1),
    ("tselnaya-keramika",   "Цельная керамика",       "zubnoy-tehnik", 2),
    ("syomnoe-protezirovanie", "Съёмное протезирование", "zubnoy-tehnik", 3),
    ("byugelnoe-i-lityo",   "Бюгельное и литьё",      "zubnoy-tehnik", 4),
    # У «Общей медицины» и «Пациента» направлений пока нет — добавишь при необходимости.
]


def seed(apps, schema_editor):
    Audience = apps.get_model("catalog", "Audience")
    Direction = apps.get_model("catalog", "Direction")
    by_slug = {}
    for a in AUDIENCES:
        obj, _ = Audience.objects.get_or_create(
            slug=a["slug"], defaults={"name": a["name"], "order": a["order"]}
        )
        by_slug[a["slug"]] = obj
    for slug, name, audience_slug, order in DIRECTIONS:
        Direction.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "audience": by_slug[audience_slug], "order": order},
        )


def unseed(apps, schema_editor):
    Audience = apps.get_model("catalog", "Audience")
    Audience.objects.filter(slug__in=[a["slug"] for a in AUDIENCES]).delete()
    # направления уйдут каскадом вместе с аудиториями


class Migration(migrations.Migration):

    dependencies = [
        # ↓↓↓ ЗАМЕНИ на имя схемной миграции из шага 1 (без «.py»):
        ("catalog", "0007_audience_product_audiences_direction_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
