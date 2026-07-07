from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers
from django_countries.serializer_fields import CountryField as CountrySerializerField

from .models import (
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Document,
    Audience,
    Direction,
    Product,
    ProductImage,
)


# ---------------------------------------------------------------------------
# Цены торговых предложений (демо: показываем все каналы/единицы)
# ---------------------------------------------------------------------------
def _per_piece(term):
    """Цена за одну базовую единицу (штуку) с учётом размера коробки."""
    base = term.unit_base_qty or 1
    return (term.price / base) if base else term.price


def _money(value):
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _iter_active_terms(product):
    # использует префетч offers/terms — без доп. запросов
    for offer in product.offers.all():
        if not offer.is_active:
            continue
        for term in offer.terms.all():
            if term.is_active:
                yield offer, term


def price_from(product):
    """Минимальная розничная цена за штуку (публичный каталог — только individuals).
    Оптовые цены отдаёт приватный эндпоинт /pricing/ по токену клиента."""
    prices = [_per_piece(t) for _, t in _iter_active_terms(product) if t.channel == "individuals"]
    return _money(min(prices)) if prices else None


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------
class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug", "logo", "description")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent")


class CategoryTreeSerializer(serializers.ModelSerializer):
    """Категория с вложенными детьми — для построения дерева навигации."""
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "children")

    def get_children(self, obj):
        return CategoryTreeSerializer(obj.get_children(), many=True, context=self.context).data


class CharacteristicOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacteristicOption
        fields = ("id", "value")


class CharacteristicSerializer(serializers.ModelSerializer):
    options = CharacteristicOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Characteristic
        fields = ("id", "name", "code", "type", "unit", "is_global", "options")


class DocumentSerializer(serializers.ModelSerializer):
    doc_type_display = serializers.CharField(source="get_doc_type_display", read_only=True)
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id", "name", "doc_type", "doc_type_display", "number", "issuing_authority",
            "issued_date", "valid_until", "is_perpetual", "status", "status_display", "file",
        )

    def get_status(self, obj):
        return obj.status.value

    def get_status_display(self, obj):
        return obj.status.label


# ---------------------------------------------------------------------------
# Навигационные фасеты
# ---------------------------------------------------------------------------
class AudienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Audience
        fields = ("id", "name", "slug", "icon", "order")


class DirectionSerializer(serializers.ModelSerializer):
    audience = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Direction
        fields = ("id", "name", "slug", "icon", "order", "audience")


class AudienceMenuSerializer(serializers.ModelSerializer):
    """Аудитория со вложенными направлениями — для построения меню магазина."""
    directions = DirectionSerializer(many=True, read_only=True)

    class Meta:
        model = Audience
        fields = ("id", "name", "slug", "icon", "order", "directions")


# ---------------------------------------------------------------------------
# Товары
# ---------------------------------------------------------------------------
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("image", "alt", "order")


class ProductListSerializer(serializers.ModelSerializer):
    """Облегчённая выдача для списков каталога."""
    brand = serializers.StringRelatedField()
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    audiences = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    directions = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "sku", "manufacturer_sku", "name", "slug", "short_description",
                  "brand", "category", "audiences", "directions", "thumbnail", "price_from")

    def get_price_from(self, obj):
        return price_from(obj)

    def get_thumbnail(self, obj):
        first = obj.images.all().first()
        if not first:
            return None
        request = self.context.get("request")
        url = first.image.url
        return request.build_absolute_uri(url) if request else url


class ProductDetailSerializer(serializers.ModelSerializer):
    """Полная карточка товара для отображения в каталоге."""
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    audiences = AudienceSerializer(many=True, read_only=True)
    directions = DirectionSerializer(many=True, read_only=True)
    logistics = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    country_of_origin = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()
    courses = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "sku", "name", "slug", "short_description", "full_description",
            "manufacturer_sku", "gtin", "tnved_code", "country_of_origin",
            "brand", "category", "audiences", "directions", "logistics",
            "images", "characteristics", "documents", "group",
            "price_from", "offers", "courses",
        )

    def get_courses(self, obj):
        request = self.context.get("request")
        result = []
        for c in obj.courses.all():
            if not c.is_active:
                continue
            modules = []
            for m in c.modules.all():
                if not m.is_active:
                    continue
                mod = {"kind": m.kind, "kind_display": m.get_kind_display(), "title": m.title}
                if m.kind == "video":
                    mod["video_url"] = m.video_url
                else:
                    slides = []
                    for sl in m.slides.all():
                        img = sl.image.url if sl.image else None
                        if img and request is not None:
                            img = request.build_absolute_uri(img)
                        slides.append({"title": sl.title, "body": sl.body, "image": img})
                    mod["slides"] = slides
                modules.append(mod)
            result.append({"title": c.title, "slug": c.slug, "subtitle": c.subtitle, "modules": modules})
        return result

    def get_price_from(self, obj):
        return price_from(obj)

    def get_offers(self, obj):
        result = []
        for offer in obj.offers.all():
            if not offer.is_active:
                continue
            terms = []
            for t in offer.terms.all():
                if not t.is_active or t.channel != "individuals":
                    continue  # публичный каталог — только розница
                terms.append({
                    "channel": t.channel,
                    "channel_display": t.get_channel_display(),
                    "unit_name": t.unit_name,
                    "unit_base_qty": t.unit_base_qty,
                    "step": t.step,
                    "min_qty": t.min_qty,
                    "price": _money(t.price),
                    "per_piece": _money(_per_piece(t)),
                })
            if not terms:
                continue
            terms.sort(key=lambda x: (x["channel"], Decimal(x["per_piece"])))
            result.append({
                "seller": offer.warehouse.seller.name if offer.warehouse_id else None,
                "in_stock": (offer.stock_qty or 0) > 0,
                "currency": offer.currency,
                "terms": terms,
            })
        return result

    def get_logistics(self, obj):
        return {
            "gross_width_mm": obj.gross_width_mm,
            "gross_height_mm": obj.gross_height_mm,
            "gross_depth_mm": obj.gross_depth_mm,
            "gross_weight_kg": obj.gross_weight_kg,
        }

    def get_characteristics(self, obj):
        items = []
        values = sorted(
            obj.attribute_values.all(),
            key=lambda av: (av.characteristic.order, av.characteristic.name),
        )
        for av in values:
            ch = av.characteristic
            if not ch.show_to_customer:
                continue  # служебные характеристики (напр. код 1С) не показываем покупателю
            items.append({
                "code": ch.code,
                "name": ch.name,
                "type": ch.type,
                "unit": ch.unit,
                "is_global": ch.is_global,
                "value": av.value,
            })
        return items

    def get_country_of_origin(self, obj):
        country = obj.country_of_origin
        if not country:
            return None
        return {"code": country.code, "name": country.name}

    def get_group(self, obj):
        """Серия товара и список её вариантов для переключателя на карточке."""
        grp = obj.group
        if grp is None:
            return None
        request = self.context.get("request")

        levels = list(grp.levels.all())  # упорядочены полем order
        siblings = grp.products.select_related("group_level").prefetch_related(
            "images"
        ).order_by("group_order", "name")

        variants = []
        for p in siblings:
            first = p.images.all().first()
            thumbnail = None
            if first:
                url = first.image.url
                thumbnail = request.build_absolute_uri(url) if request else url
            variants.append({
                "slug": p.slug,
                "label": p.variant_label or p.name,
                "thumbnail": thumbnail,
                "is_current": p.pk == obj.pk,
                "level": p.group_level.name if p.group_level_id else None,
            })

        return {
            "name": grp.name,
            "slug": grp.slug,
            "current": obj.slug,
            "levels": [{"name": lvl.name, "order": lvl.order} for lvl in levels],
            "variants": variants,
        }


class ProductWriteSerializer(serializers.ModelSerializer):
    """
    Запись товара по токену. Покрывает постоянные поля, категорию, бренд и
    привязку документов. Изображения и значения категорийных характеристик
    в этой версии управляются через админку.
    """
    country_of_origin = CountrySerializerField(required=False, allow_blank=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "slug", "short_description", "full_description",
            "manufacturer_sku", "gtin", "tnved_code", "country_of_origin",
            "category", "brand", "audiences", "directions",
            "gross_width_mm", "gross_height_mm", "gross_depth_mm", "gross_weight_kg",
            "documents",
            "group", "group_order", "variant_label",
        )
        extra_kwargs = {"slug": {"required": False}}
