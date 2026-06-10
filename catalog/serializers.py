from rest_framework import serializers

from .models import (
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Document,
    Product,
    ProductImage,
)


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
        return CategoryTreeSerializer(obj.children.all(), many=True, context=self.context).data


class CharacteristicOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CharacteristicOption
        fields = ("id", "value")


class CharacteristicSerializer(serializers.ModelSerializer):
    options = CharacteristicOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Characteristic
        fields = ("id", "name", "code", "type", "unit", "options")


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "name", "number", "file")


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
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "external_id", "name", "slug", "short_description", "brand", "category", "thumbnail")

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
    logistics = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "external_id", "name", "slug", "short_description", "full_description",
            "manufacturer_sku", "brand", "category", "logistics",
            "images", "characteristics", "documents", "group",
        )

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
            items.append({
                "code": ch.code,
                "name": ch.name,
                "type": ch.type,
                "unit": ch.unit,
                "value": av.value,
            })
        return items

    def get_group(self, obj):
        """Серия товара и список её вариантов для переключателя на карточке."""
        grp = obj.group
        if grp is None:
            return None
        request = self.context.get("request")

        levels = list(grp.levels.all())  # упорядочены полем order
        siblings = grp.products.prefetch_related(
            "images", "group_values__level", "group_values__value"
        ).order_by("group_order", "name")

        variants = []
        for p in siblings:
            level_values = {gv.level.name: gv.value.value for gv in p.group_values.all()}
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
                "levels": level_values,
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
    class Meta:
        model = Product
        fields = (
            "id", "external_id", "name", "slug", "short_description", "full_description",
            "manufacturer_sku", "category", "brand",
            "gross_width_mm", "gross_height_mm", "gross_depth_mm", "gross_weight_kg",
            "documents",
            "group", "group_order", "variant_label",
        )
        extra_kwargs = {"slug": {"required": False}}
