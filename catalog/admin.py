from adminsortable2.admin import SortableAdminBase, SortableInlineAdminMixin
from django import forms
from django.contrib import admin
from tinymce.widgets import TinyMCE

from .models import (
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Document,
    Product,
    ProductImage,
)

admin.site.site_header = "ProfiSfera PIM"
admin.site.site_title = "ProfiSfera PIM"
admin.site.index_title = "Управление каталогом"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    list_filter = ("parent",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
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
    prepopulated_fields = {"code": ("name",)}
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


class ProductImageInline(SortableInlineAdminMixin, admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt", "order")


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"
        widgets = {
            # Полное описание редактируется визуальным редактором (HTML).
            # Краткое описание остаётся простым текстовым полем.
            "full_description": TinyMCE(),
        }


@admin.register(Product)
class ProductAdmin(SortableAdminBase, admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "category", "brand", "manufacturer_sku", "updated_at")
    list_filter = ("category", "brand")
    search_fields = ("name", "manufacturer_sku")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category", "brand")
    filter_horizontal = ("documents",)
    inlines = [ProductImageInline]
    fieldsets = (
        ("Основное", {
            "fields": ("name", "slug", "brand", "category", "manufacturer_sku"),
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
    # Блок категорийных характеристик (ProductAttributeValue) подключим
    # на этапе 3 — там нужна динамическая форма, зависящая от категории.
