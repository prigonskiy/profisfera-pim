from decimal import Decimal, ROUND_HALF_UP
import re

from django.conf import settings
from django.utils.html import escape as html_escape
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
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
    CompatibilitySystem,
    Product,
    ProductImage,
    Case,
    CaseMedia,
    CaseProduct,
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

    @extend_schema_field(OpenApiTypes.STR)
    def get_status(self, obj):
        return obj.status.value

    @extend_schema_field(OpenApiTypes.STR)
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


class CompatibilitySystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompatibilitySystem
        fields = ("id", "name", "slug", "group", "order")


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
    thumb = serializers.SerializerMethodField()
    main = serializers.SerializerMethodField()
    original = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("thumb", "main", "original", "alt", "order")

    def _abs(self, filefield):
        if not filefield:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(filefield.url) if request else filefield.url

    @extend_schema_field(OpenApiTypes.URI)
    def get_thumb(self, obj):
        return self._abs(obj.thumb or obj.image)  # fallback на оригинал, если копии нет

    @extend_schema_field(OpenApiTypes.URI)
    def get_main(self, obj):
        return self._abs(obj.main or obj.image)

    @extend_schema_field(OpenApiTypes.URI)
    def get_original(self, obj):
        return self._abs(obj.image)


class ProductListSerializer(serializers.ModelSerializer):
    """Облегчённая выдача для списков каталога."""
    brand = serializers.StringRelatedField()
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    audiences = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    directions = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    systems = serializers.SlugRelatedField(
        slug_field="slug", many=True, read_only=True, source="compatibility_systems")
    fitment = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "sku", "manufacturer_sku", "name", "slug", "short_description",
                  "brand", "category", "audiences", "directions", "systems", "fitment",
                  "thumbnail", "price_from")

    @extend_schema_field(OpenApiTypes.STR)
    def get_fitment(self, obj):
        # признак имеет смысл только у системозависимого товара
        if obj.fitment_type and obj.compatibility_systems.all():
            return obj.fitment_type
        return None

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_price_from(self, obj):
        return price_from(obj)

    @extend_schema_field(OpenApiTypes.URI)
    def get_thumbnail(self, obj):
        first = obj.images.all().first()
        if not first:
            return None
        request = self.context.get("request")
        url = (first.card or first.image).url  # каталог использует копию 400
        return request.build_absolute_uri(url) if request else url


class ProductDetailSerializer(serializers.ModelSerializer):
    """Полная карточка товара для отображения в каталоге."""
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    documents = DocumentSerializer(many=True, read_only=True)
    audiences = AudienceSerializer(many=True, read_only=True)
    directions = DirectionSerializer(many=True, read_only=True)
    systems = CompatibilitySystemSerializer(many=True, read_only=True, source="compatibility_systems")
    fitment = serializers.SerializerMethodField()
    logistics = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    country_of_origin = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    offers = serializers.SerializerMethodField()
    courses = serializers.SerializerMethodField()
    cases = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "sku", "name", "slug", "short_description", "full_description",
            "manufacturer_sku", "gtin", "tnved_code", "country_of_origin",
            "brand", "category", "audiences", "directions", "systems", "fitment", "logistics",
            "images", "characteristics", "documents", "group",
            "price_from", "offers", "courses", "cases",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_fitment(self, obj):
        if obj.fitment_type and obj.compatibility_systems.all():
            return obj.fitment_type
        return None

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
    def get_cases(self, obj):
        # опубликованные кейсы, где присутствует этот товар, свежие первыми
        qs = (Case.objects.filter(products__product=obj, status=Case.Status.PUBLISHED)
              .distinct().order_by("-published_at", "-created_at")
              .prefetch_related("directions", "audiences"))
        return CaseTileSerializer(qs, many=True, context=self.context).data

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
    def get_courses(self, obj):
        request = self.context.get("request")
        result = []

        def _embed(entry_path):
            if not entry_path:
                return None
            media_url = settings.MEDIA_URL
            if not media_url.startswith("/"):
                media_url = "/" + media_url
            url = media_url.rstrip("/") + "/" + entry_path.lstrip("/")
            return request.build_absolute_uri(url) if request is not None else url

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
                elif m.kind == "longread":
                    if m.entry_path:
                        mod["embed_url"] = _embed(m.entry_path)
                    else:
                        mod["body"] = m.body
                else:  # slides — встраиваемый пакет iSpring
                    mod["embed_url"] = _embed(m.entry_path)
                modules.append(mod)
            result.append({"title": c.title, "slug": c.slug, "subtitle": c.subtitle, "modules": modules})
        return result

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_price_from(self, obj):
        return price_from(obj)

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
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

    @extend_schema_field({"type": "object", "properties": {"gross_width_mm": {"type": "integer", "nullable": True}, "gross_height_mm": {"type": "integer", "nullable": True}, "gross_depth_mm": {"type": "integer", "nullable": True}, "gross_weight_kg": {"type": "number", "nullable": True}}})
    def get_logistics(self, obj):
        return {
            "gross_width_mm": obj.gross_width_mm,
            "gross_height_mm": obj.gross_height_mm,
            "gross_depth_mm": obj.gross_depth_mm,
            "gross_weight_kg": obj.gross_weight_kg,
        }

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
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

    @extend_schema_field({"type": "object", "nullable": True, "properties": {"code": {"type": "string"}, "name": {"type": "string"}}})
    def get_country_of_origin(self, obj):
        country = obj.country_of_origin
        if not country:
            return None
        return {"code": country.code, "name": country.name}

    @extend_schema_field({"type": "object", "nullable": True})
    def get_group(self, obj):
        """Серия товара и список её вариантов для переключателя на карточке."""
        grp = obj.group
        if grp is None:
            return None
        request = self.context.get("request")

        levels = list(grp.levels.all())  # упорядочены полем order
        siblings = grp.products.filter(is_active=True).select_related("group_level").prefetch_related(
            "images"
        ).order_by("group_order", "name")

        variants = []
        for p in siblings:
            first = p.images.all().first()
            thumbnail = None
            if first:
                url = (first.card or first.image).url  # копия 400 для миниатюры варианта
                thumbnail = request.build_absolute_uri(url) if request else url
            variants.append({
                "slug": p.slug,
                "label": p.variant_label or p.name,
                "color": p.variant_color or None,  # #RRGGBB для образца-точки, либо null
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
            "compatibility_systems", "fitment_type",
            "gross_width_mm", "gross_height_mm", "gross_depth_mm", "gross_weight_kg",
            "documents",
            "group", "group_order", "variant_label", "variant_color",
        )
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs):
        # система заполнена → признак «оригинал/совместимый» обязателен
        systems = attrs.get("compatibility_systems")
        if systems is None and self.instance is not None:
            systems = self.instance.compatibility_systems.all()
        fitment = attrs.get("fitment_type")
        if fitment is None and self.instance is not None:
            fitment = self.instance.fitment_type
        if systems and not fitment:
            raise serializers.ValidationError(
                {"fitment_type": "Укажите «оригинал/совместимый» при заполненной системе совместимости."})
        return attrs


# ---------------------------------------------------------------------------
# Клинические/зуботехнические кейсы (публичная выдача)
# ---------------------------------------------------------------------------
def _abs_url(request, filefield):
    if not filefield:
        return None
    url = filefield.url
    return request.build_absolute_uri(url) if request else url


_FIGURE_RE = re.compile(r'<figure\b[^>]*\bdata-media="(\d+)"[^>]*>.*?</figure>',
                        re.DOTALL | re.IGNORECASE)


def render_case_body(body_html, media_by_id, request):
    """Подставить в тело кейса актуальные URL деривативов вместо того, что вставил
    редактор: каждый <figure data-media="ID"> перерисовывается по свежему preview.
    Если картинку из галереи удалили — блок вырезается целиком."""
    if not body_html:
        return body_html or ""

    def repl(match):
        mid = int(match.group(1))
        media = media_by_id.get(mid)
        if media is None:
            return ""  # удалённая картинка — убираем figure целиком
        src = _abs_url(request, media.preview or media.image) or ""
        alt = html_escape(media.alt or media.caption or "")
        caption = html_escape(media.caption or "")
        figcaption = f"<figcaption>{caption}</figcaption>" if caption else ""
        return (f'<figure data-media="{mid}">'
                f'<img src="{src}" alt="{alt}" loading="lazy">{figcaption}</figure>')

    return _FIGURE_RE.sub(repl, body_html)


class CaseMediaSerializer(serializers.ModelSerializer):
    thumb = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()

    class Meta:
        model = CaseMedia
        fields = ("thumb", "preview", "caption", "alt", "width", "height", "order")

    @extend_schema_field(OpenApiTypes.URI)
    def get_thumb(self, obj):
        return _abs_url(self.context.get("request"), obj.thumb or obj.image)

    @extend_schema_field(OpenApiTypes.URI)
    def get_preview(self, obj):
        return _abs_url(self.context.get("request"), obj.preview or obj.image)


class CaseProductSerializer(serializers.ModelSerializer):
    """Товар внутри кейса (каноническая карточка + примечание из привязки)."""
    slug = serializers.CharField(source="product.slug", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    brand = serializers.StringRelatedField(source="product.brand", read_only=True)
    image = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    has_offers = serializers.SerializerMethodField()

    class Meta:
        model = CaseProduct
        fields = ("slug", "name", "brand", "image", "price_from", "has_offers", "note", "order")

    @extend_schema_field(OpenApiTypes.URI)
    def get_image(self, obj):
        first = obj.product.images.all().first()
        if not first:
            return None
        return _abs_url(self.context.get("request"), first.card or first.image)

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_price_from(self, obj):
        return price_from(obj.product)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_offers(self, obj):
        return obj.product.offers.exists()


class CaseTileSerializer(serializers.ModelSerializer):
    """Плитка кейса — для списков, раздела и блока «Кейсы с этим товаром»."""
    cover = serializers.SerializerMethodField()
    directions = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    audiences = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)

    class Meta:
        model = Case
        fields = ("case_number", "slug", "title", "case_profile", "cover",
                  "directions", "audiences", "published_at")

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_cover(self, obj):
        if not obj.cover:
            return None
        request = self.context.get("request")
        return {
            "thumb": _abs_url(request, obj.cover_thumb or obj.cover),
            "og": _abs_url(request, obj.cover_og or obj.cover),
            "alt": obj.title,
        }


class CaseDetailSerializer(CaseTileSerializer):
    """Полный кейс — страница /cases/{slug}/."""
    body_html = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    products = CaseProductSerializer(many=True, read_only=True)

    class Meta(CaseTileSerializer.Meta):
        fields = CaseTileSerializer.Meta.fields + (
            "body_html", "author_line", "tooth_scope", "teeth", "arches",
            "tooth_groups", "tooth_sides", "dentition",
            "meta_title", "meta_description", "media", "products",
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_body_html(self, obj):
        media_by_id = {m.pk: m for m in obj.media.all()}
        return render_case_body(obj.body_html, media_by_id, self.context.get("request"))

    @extend_schema_field(CaseMediaSerializer(many=True))
    def get_media(self, obj):
        gallery = [m for m in obj.media.all() if m.show_in_gallery]
        return CaseMediaSerializer(gallery, many=True, context=self.context).data
