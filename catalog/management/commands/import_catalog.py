"""
Массовая загрузка карточек товаров из старой JSON-выгрузки.

Запуск:
    python manage.py import_catalog products.json
    python manage.py import_catalog products.json --dry-run   # прогон без записи

Идемпотентна: ключ сопоставления — код 1С (поле "id" в JSON), который хранится
на предложении продавца по умолчанию (Offer.erp_code). Повторный запуск обновляет
уже созданные карточки и их предложение, а не плодит дубли.

Фаза 1 (этот импорт) переносит: название, артикул, описания, бренд,
дерево категорий (cat2 → cat3), аудиторию (cat1), направления (specializations)
и хорошо заполненные категорийные характеристики (тип материала, консистенция,
вязкость, отверждение, упаковка, показания).

Сознательно НЕ переносим (см. фазу 2 / доработку 2):
  - price  — цена живёт в магазине/1С, в PIM такого поля нет;
  - image  — это внешние ссылки на чужой сайт, картинки заводим своими;
  - series / optionName / deliveryType / colors — серии и варианты;
  - редко заполненные поля (appointment, selfEtching, hardness).
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import (
    Audience,
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Direction,
    Offer,
    Product,
    ProductAttributeValue,
    Seller,
    Warehouse,
)

# продавец/склад по умолчанию — код сопоставления живёт на их предложениях
DEFAULT_SELLER = "Профисфера (продавец по умолчанию)"
DEFAULT_WAREHOUSE = "Основной склад"

# cat1 (как в JSON)  ->  slug аудитории (как в PIM, из сид-миграции)
AUDIENCE_MAP = {
    "Для врача-стоматолога и стоматологического кабинета": "stomatolog",
    "Для зубного техника и зуботехнической лаборатории": "zubnoy-tehnik",
    "Товары общей медицины": "obshchaya-meditsina",
}

# поле JSON -> (название характеристики, код, тип)
SINGLE_SELECT_SPECS = [
    ("materialType", "Тип материала", "material_type"),
    ("consistency", "Консистенция", "consistency"),
    ("viscosity", "Вязкость", "viscosity"),
    ("curing", "Тип отверждения", "curing"),
    ("packaging", "Упаковка", "packaging"),
]
MULTI_SELECT_SPECS = [
    ("purposes", "Показания", "purposes"),
]


class Command(BaseCommand):
    help = "Импорт карточек товаров из старого products.json (фаза 1: минимум информации)."

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Путь к products.json")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Прогнать без записи в базу (показать, что было бы сделано).",
        )

    def handle(self, *args, **opts):
        try:
            with open(opts["json_path"], encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"Файл не найден: {opts['json_path']}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Не удалось разобрать JSON: {e}")

        if not isinstance(data, list):
            raise CommandError("Ожидался список товаров в корне JSON.")

        self.stats = {"created": 0, "updated": 0, "chars": 0, "skipped": 0}
        self._opt_cache = {}

        with transaction.atomic():
            for raw in data:
                self._import_one(raw)
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("\n[dry-run] изменения откатаны, в базу ничего не записано."))

        s = self.stats
        self.stdout.write(self.style.SUCCESS(
            f"\nГотово. Создано: {s['created']}, обновлено: {s['updated']}, "
            f"пропущено: {s['skipped']}, проставлено значений характеристик: {s['chars']}."
        ))

    # ------------------------------------------------------------------ helpers
    def _default_warehouse(self):
        if getattr(self, "_wh", None) is None:
            seller, _ = Seller.objects.get_or_create(name=DEFAULT_SELLER, defaults={"is_active": True})
            self._wh, _ = Warehouse.objects.get_or_create(
                seller=seller, name=DEFAULT_WAREHOUSE, defaults={"is_active": True},
            )
        return self._wh

    def _import_one(self, raw):
        ext = (raw.get("id") or "").strip()
        name = (raw.get("name") or "").strip()
        if not ext or not name:
            self.stats["skipped"] += 1
            return

        brand = None
        brand_name = (raw.get("brand") or "").strip()
        if brand_name:
            brand, _ = Brand.objects.get_or_create(name=brand_name)

        category = self._category(raw.get("cat2"), raw.get("cat3"))

        # Сначала находим/создаём объект в памяти и проставляем ВСЕ обязательные
        # поля (category — NOT NULL), и только потом сохраняем — одной вставкой,
        # без преждевременной «пустой» карточки.
        # сопоставление по коду 1С — через предложение продавца по умолчанию
        offer = (
            Offer.objects.filter(warehouse__seller__name=DEFAULT_SELLER, erp_code=ext)
            .select_related("product").first()
        )
        if offer is not None:
            product = offer.product
            created = False
        else:
            product = Product()
            created = True
        product.name = name
        product.manufacturer_sku = (raw.get("partNumber") or "").strip()
        product.short_description = (raw.get("shortDesc") or "").strip()
        product.full_description = raw.get("fullDesc") or ""
        product.brand = brand
        product.category = category
        product.save()
        self.stats["created" if created else "updated"] += 1

        # код сопоставления храним на предложении продавца по умолчанию
        wh = self._default_warehouse()
        off, _ = Offer.objects.get_or_create(warehouse=wh, product=product)
        if not off.erp_code:
            off.erp_code = ext
            off.save(update_fields=["erp_code"])

        # аудитория (cat1) и направления (specializations)
        aud = self._audience(raw.get("cat1"))
        product.audiences.set([aud] if aud else [])
        dirs = []
        for spec in raw.get("specializations") or []:
            d = self._direction(spec, aud)
            if d:
                dirs.append(d)
        product.directions.set(dirs)

        # категорийные характеристики
        for jf, chname, code in SINGLE_SELECT_SPECS:
            val = (raw.get(jf) or "").strip()
            if val:
                ch = self._char(code, chname, "single_select", category)
                self._set_options(product, ch, [val])
        for jf, chname, code in MULTI_SELECT_SPECS:
            vals = [str(v).strip() for v in (raw.get(jf) or []) if str(v).strip()]
            if vals:
                ch = self._char(code, chname, "multi_select", category)
                self._set_options(product, ch, vals)

    def _category(self, cat2, cat3):
        cat2 = (cat2 or "").strip()
        cat3 = (cat3 or "").strip()
        parent = None
        if cat2:
            parent, _ = Category.objects.get_or_create(name=cat2, parent=None)
        if cat3:
            leaf, _ = Category.objects.get_or_create(name=cat3, parent=parent)
            return leaf
        return parent

    def _audience(self, cat1):
        cat1 = (cat1 or "").strip()
        if not cat1:
            return None
        slug = AUDIENCE_MAP.get(cat1)
        if slug:
            aud, _ = Audience.objects.get_or_create(slug=slug, defaults={"name": cat1})
            return aud
        aud, _ = Audience.objects.get_or_create(name=cat1)
        return aud

    def _direction(self, name, audience):
        name = (name or "").strip()
        if not name:
            return None
        d, _ = Direction.objects.get_or_create(name=name, audience=audience)
        return d

    def _char(self, code, name, ctype, category):
        ch, _ = Characteristic.objects.get_or_create(
            code=code, defaults={"name": name, "type": ctype, "is_global": False}
        )
        if category:
            ch.categories.add(category)
        return ch

    def _set_options(self, product, ch, values):
        av, _ = ProductAttributeValue.objects.get_or_create(product=product, characteristic=ch)
        opts = []
        for v in values:
            key = (ch.id, v)
            opt = self._opt_cache.get(key)
            if opt is None:
                opt, _ = CharacteristicOption.objects.get_or_create(
                    characteristic=ch, value=v, defaults={"order": ch.options.count()}
                )
                self._opt_cache[key] = opt
            opts.append(opt)
        av.value_options.set(opts)
        self.stats["chars"] += 1