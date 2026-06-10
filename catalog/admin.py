from adminsortable2.admin import SortableAdminBase, SortableInlineAdminMixin
from django import forms
from django.contrib import admin
from image_uploader_widget.admin import OrderedImageUploaderInline
from tinymce.widgets import TinyMCE

from .models import (
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Document,
    Product,
    ProductImage,
    ProductAttributeValue,
)

admin.site.site_header = "ProfiSfera PIM"
admin.site.site_title = "ProfiSfera PIM"
admin.site.index_title = "Управление каталогом"


# ---------------------------------------------------------------------------
# Простые сущности
# ---------------------------------------------------------------------------
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    list_filter = ("parent",)
    search_fields = ("name",)
    autocomplete_fields = ("parent",)


class CharacteristicOptionInline(SortableInlineAdminMixin, admin.TabularInline):
    model = CharacteristicOption
    extra = 1
    fields = ("value", "order")


@admin.register(Characteristic)
class CharacteristicAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ("name", "code", "type", "unit")
    list_filter = ("type", "categories")
    search_fields = ("name", "code")
    filter_horizontal = ("categories",)
    inlines = [CharacteristicOptionInline]
    fieldsets = (
        (None, {"fields": ("name", "code", "type", "unit")}),
        ("Привязка к категориям", {"fields": ("categories",)}),
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "number", "file")
    search_fields = ("name", "number")


# ---------------------------------------------------------------------------
# Карточка товара с динамическими категорийными характеристиками
# ---------------------------------------------------------------------------
def build_characteristic_field(characteristic):
    """Создаёт поле формы под тип характеристики и привязывает её к полю."""
    T = Characteristic.Type
    label = characteristic.name
    if characteristic.unit:
        label = f"{label}, {characteristic.unit}"

    if characteristic.type == T.TEXT:
        field = forms.CharField(label=label, required=False)
    elif characteristic.type == T.NUMBER:
        field = forms.DecimalField(label=label, required=False)
    elif characteristic.type == T.BOOLEAN:
        field = forms.NullBooleanField(label=label, required=False)
    elif characteristic.type == T.SINGLE_SELECT:
        field = forms.ModelChoiceField(
            label=label, required=False, queryset=characteristic.options.all()
        )
    elif characteristic.type == T.MULTI_SELECT:
        field = forms.ModelMultipleChoiceField(
            label=label,
            required=False,
            queryset=characteristic.options.all(),
            widget=forms.CheckboxSelectMultiple,
        )
    else:
        field = forms.CharField(label=label, required=False)

    field.characteristic = characteristic  # пригодится при сохранении/инициализации
    return field


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"
        widgets = {
            # Полное описание — визуальный редактор; краткое остаётся простым.
            "full_description": TinyMCE(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if not (instance and instance.pk):
            return
        # подставляем сохранённые значения категорийных характеристик
        existing = {
            av.characteristic_id: av
            for av in instance.attribute_values.all().prefetch_related("value_options")
        }
        T = Characteristic.Type
        for name, field in self.fields.items():
            ch = getattr(field, "characteristic", None)
            if ch is None:
                continue
            av = existing.get(ch.id)
            if av is None:
                continue
            if ch.type == T.TEXT:
                self.initial[name] = av.value_text
            elif ch.type == T.NUMBER:
                self.initial[name] = av.value_number
            elif ch.type == T.BOOLEAN:
                self.initial[name] = av.value_boolean
            elif ch.type == T.SINGLE_SELECT:
                self.initial[name] = av.value_options.first()
            elif ch.type == T.MULTI_SELECT:
                self.initial[name] = list(av.value_options.values_list("pk", flat=True))


class ProductImageInline(OrderedImageUploaderInline):
    model = ProductImage
    order_field = "order"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "category", "brand", "manufacturer_sku", "external_id", "updated_at")
    list_filter = ("category", "brand")
    search_fields = ("name", "manufacturer_sku", "external_id")
    autocomplete_fields = ("category", "brand")
    filter_horizontal = ("documents",)
    inlines = [ProductImageInline]
    base_fieldsets = (
        ("Основное", {
            "fields": ("name", "slug", "external_id", "brand", "category", "manufacturer_sku"),
        }),
        ("Описания", {
            "fields": ("short_description", "full_description"),
        }),
        ("Логистические параметры (брутто)", {
            "fields": (
                "gross_width_mm",
                "gross_height_mm",
                "gross_depth_mm",
                "gross_weight_kg",
            ),
        }),
        ("Документы", {
            "fields": ("documents",),
        }),
    )

    def _category_characteristics(self, obj):
        """Характеристики, привязанные к категории товара (или пустой список)."""
        if obj and obj.category_id:
            return list(
                obj.category.characteristics.all().prefetch_related("options")
            )
        return []

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(self.base_fieldsets)
        chars = self._category_characteristics(obj)
        if chars:
            names = [f"char_{ch.id}" for ch in chars]
            fieldsets.append(("Категорийные характеристики", {"fields": names}))
        return fieldsets

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Объявляем динамические поля характеристик на классе формы, чтобы
        # они прошли валидацию набора полей и отрисовались в своём филдсете.
        extra = {
            f"char_{ch.id}": build_characteristic_field(ch)
            for ch in self._category_characteristics(obj)
        }
        base_form = kwargs.get("form", self.form)
        if extra:
            base_form = type("ProductDynamicForm", (base_form,), extra)
        kwargs["form"] = base_form
        return super().get_form(request, obj, change=change, **kwargs)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        self._save_attribute_values(form)

    def _save_attribute_values(self, form):
        """Пишет значения категорийных характеристик в EAV-таблицу."""
        product = form.instance
        T = Characteristic.Type
        for name, field in form.fields.items():
            ch = getattr(field, "characteristic", None)
            if ch is None:
                continue
            value = form.cleaned_data.get(name)
            av, _ = ProductAttributeValue.objects.get_or_create(
                product=product, characteristic=ch
            )
            av.value_text = ""
            av.value_number = None
            av.value_boolean = None
            is_empty = True

            if ch.type == T.TEXT:
                av.value_text = value or ""
                is_empty = not (value or "").strip()
            elif ch.type == T.NUMBER:
                av.value_number = value
                is_empty = value is None
            elif ch.type == T.BOOLEAN:
                av.value_boolean = value
                is_empty = value is None
            av.save()

            if ch.type == T.SINGLE_SELECT:
                av.value_options.set([value] if value else [])
                is_empty = value is None
            elif ch.type == T.MULTI_SELECT:
                chosen = list(value) if value else []
                av.value_options.set(chosen)
                is_empty = len(chosen) == 0
            else:
                av.value_options.clear()

            # пустые значения не храним — таблица остаётся чистой
            if is_empty:
                av.delete()
