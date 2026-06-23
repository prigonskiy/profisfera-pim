from datetime import timedelta

from adminsortable2.admin import SortableAdminBase, SortableAdminMixin, SortableInlineAdminMixin
from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from image_uploader_widget.admin import OrderedImageUploaderInline
from tinymce.widgets import TinyMCE

from .catalog_io import (
    build_export_workbook,
    category_labels,
    category_with_descendants,
    import_workbook,
    workbook_response,
)

from .storefront import trigger_rebuild

from .models import (
    Audience,
    Brand,
    Category,
    Characteristic,
    CharacteristicOption,
    Direction,
    Document,
    GroupLevel,
    GroupLevelValue,
    Product,
    ProductGroup,
    ProductGroupValue,
    ProductImage,
    ProductAttributeValue,
)

admin.site.site_header = "ProfiSfera PIM"
admin.site.site_title = "ProfiSfera PIM"
admin.site.index_title = "Управление каталогом"


# ---------------------------------------------------------------------------
# Простые сущности
# ---------------------------------------------------------------------------
class BrandAdminForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = "__all__"
        widgets = {
            # Описание бренда — визуальный HTML-редактор, как у полного описания товара.
            "description": TinyMCE(),
        }


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandAdminForm
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
    list_display = ("name", "code", "type", "unit", "is_global", "show_to_customer")
    list_editable = ("show_to_customer",)
    list_filter = ("type", "is_global", "show_to_customer", "categories")
    search_fields = ("name", "code")
    filter_horizontal = ("categories",)
    inlines = [CharacteristicOptionInline]
    fieldsets = (
        (None, {"fields": ("name", "code", "type", "unit", "is_global", "show_to_customer")}),
        ("Привязка к категориям (только для НЕ общих)", {"fields": ("categories",)}),
    )


class DocumentValidityFilter(admin.SimpleListFilter):
    title = "Срок действия"
    parameter_name = "validity"

    def lookups(self, request, model_admin):
        return [
            ("expired", "Просрочен"),
            ("expiring", "Скоро истекает"),
            ("valid", "Действует"),
            ("perpetual", "Бессрочный"),
            ("unknown", "Срок не указан"),
        ]

    def queryset(self, request, qs):
        today = timezone.localdate()
        soon = today + timedelta(days=Document.EXPIRY_SOON_DAYS)
        return {
            "expired": qs.filter(is_perpetual=False, valid_until__lt=today),
            "expiring": qs.filter(is_perpetual=False, valid_until__gte=today, valid_until__lte=soon),
            "valid": qs.filter(is_perpetual=False, valid_until__gt=soon),
            "perpetual": qs.filter(is_perpetual=True),
            "unknown": qs.filter(is_perpetual=False, valid_until__isnull=True),
        }.get(self.value(), qs)


class ProductDocumentInline(admin.TabularInline):
    """Привязка товаров прямо со страницы документа (другая сторона M2M)."""
    model = Product.documents.through
    extra = 1
    autocomplete_fields = ("product",)
    verbose_name = "Связанный товар"
    verbose_name_plural = "Связанные товары"


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "doc_type", "number", "status_badge", "valid_until")
    list_filter = ("doc_type", DocumentValidityFilter)
    search_fields = ("name", "number", "issuing_authority")
    inlines = [ProductDocumentInline]
    fieldsets = (
        (None, {"fields": ("name", "doc_type", "number", "issuing_authority", "file")}),
        ("Срок действия", {
            "fields": ("issued_date", "valid_until", "is_perpetual"),
            "description": "Для бессрочного документа поставьте галочку «Бессрочный». "
                           "Если срок неизвестен — оставьте «Действует до» пустым.",
        }),
    )

    @admin.display(description="Статус")
    def status_badge(self, obj):
        colors = {
            "perpetual": "#0A6E73", "valid": "#2E7D32", "expiring": "#B4541F",
            "expired": "#C62828", "unknown": "#8A8A8A",
        }
        status = obj.status
        label = Document.Status(status).label
        days = obj.days_left
        if status == Document.Status.EXPIRING and days is not None:
            label = f"{label} ({days} дн.)"
        elif status == Document.Status.EXPIRED and days is not None:
            label = f"{label} ({-days} дн. назад)"
        return format_html('<b style="color:{}">{}</b>', colors.get(status, "#8A8A8A"), label)


# ---------------------------------------------------------------------------
# Навигационные фасеты: аудитории и направления
# ---------------------------------------------------------------------------
class DirectionInline(SortableInlineAdminMixin, admin.TabularInline):
    model = Direction
    extra = 1
    fields = ("name", "slug", "order")
    show_change_link = True  # перейти на направление (описание для SEO и т.д.)


@admin.register(Audience)
class AudienceAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "order")
    search_fields = ("name",)
    inlines = [DirectionInline]


@admin.register(Direction)
class DirectionAdmin(admin.ModelAdmin):
    list_display = ("name", "audience", "slug", "order")
    list_filter = ("audience",)
    search_fields = ("name",)
    autocomplete_fields = ("audience",)
    ordering = ("audience__order", "order", "name")


# ---------------------------------------------------------------------------
# Группировка вариантов (серии, уровни, значения уровней)
# ---------------------------------------------------------------------------
class GroupLevelValueInline(SortableInlineAdminMixin, admin.TabularInline):
    model = GroupLevelValue
    extra = 1
    fields = ("value", "order")


@admin.register(GroupLevel)
class GroupLevelAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ("name", "group", "order")
    list_filter = ("group",)
    search_fields = ("name",)
    inlines = [GroupLevelValueInline]


class GroupLevelInline(SortableInlineAdminMixin, admin.TabularInline):
    model = GroupLevel
    extra = 1
    fields = ("name", "order")
    show_change_link = True  # перейти на уровень, чтобы добавить его значения


@admin.register(ProductGroup)
class ProductGroupAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    inlines = [GroupLevelInline]


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


class ProductGroupValueInline(admin.TabularInline):
    """Значения товара по уровням его серии (для переключателя вариантов)."""
    model = ProductGroupValue
    extra = 0
    fields = ("level", "value")
    verbose_name = "значение по уровню серии"
    verbose_name_plural = (
        "Значения по уровням серии (выбирайте уровень и значение одной и той же серии)"
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("sku", "name", "category", "brand", "group", "manufacturer_sku", "external_id", "updated_at")
    list_filter = ("category", "brand", "group", "country_of_origin", "audiences", "directions")
    search_fields = ("name", "manufacturer_sku", "external_id", "gtin", "sku")
    readonly_fields = ("sku",)
    autocomplete_fields = ("category", "brand", "group")
    filter_horizontal = ("documents", "audiences", "directions")
    inlines = [ProductImageInline, ProductGroupValueInline]
    change_list_template = "admin/catalog/product/change_list.html"
    actions = ["export_general", "export_full"]

    # ---- Экспорт в Excel -------------------------------------------------
    @admin.action(description="Экспорт в Excel: базовые поля + общие характеристики")
    def export_general(self, request, queryset):
        wb = build_export_workbook(queryset, include_category_chars=False)
        return workbook_response(wb, "catalog_obshchie")

    @admin.action(description="Экспорт в Excel: + категорийные характеристики выбранных")
    def export_full(self, request, queryset):
        wb = build_export_workbook(queryset, include_category_chars=True)
        return workbook_response(wb, "catalog_polnyy")

    def get_urls(self):
        custom = [
            path("export/", self.admin_site.admin_view(self.export_view),
                 name="catalog_product_export"),
            path("import/", self.admin_site.admin_view(self.import_view),
                 name="catalog_product_import"),
            path("rebuild/", self.admin_site.admin_view(self.rebuild_view),
                 name="catalog_product_rebuild"),
        ]
        return custom + super().get_urls()

    def import_view(self, request):
        report = None
        if request.method == "POST":
            dry_run = bool(request.POST.get("dry_run"))
            f = request.FILES.get("file")
            if not f:
                self.message_user(request, "Файл не выбран.", level=messages.ERROR)
            else:
                try:
                    report = import_workbook(f, dry_run=dry_run)
                except Exception as e:
                    self.message_user(request, f"Не удалось прочитать файл: {e}", level=messages.ERROR)
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Импорт каталога из Excel",
            "opts": self.model._meta,
            "report": report,
        }
        return render(request, "admin/catalog/product/import.html", ctx)

    def export_view(self, request):
        if request.method == "POST":
            if request.POST.get("mode") == "category" and request.POST.get("category"):
                ids = category_with_descendants(int(request.POST["category"]))
                qs = Product.objects.filter(category_id__in=ids)
                return workbook_response(build_export_workbook(qs, True), "catalog_category")
            qs = Product.objects.all()
            return workbook_response(build_export_workbook(qs, False), "catalog_vse")
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Экспорт каталога в Excel",
            "categories": category_labels(),
            "opts": self.model._meta,
        }
        return render(request, "admin/catalog/product/export.html", ctx)

    def rebuild_view(self, request):
        # Только POST запускает пересборку (чтобы случайный переход/префетч
        # ссылки не дёргал GitHub). GET — просто вернуться к списку.
        if request.method == "POST":
            ok, msg = trigger_rebuild()
            self.message_user(
                request, msg,
                level=messages.SUCCESS if ok else messages.ERROR,
            )
        return redirect(reverse("admin:catalog_product_changelist"))
    base_fieldsets = (
        ("Основное", {
            "fields": ("sku", "name", "slug", "external_id", "gtin", "brand", "category", "manufacturer_sku"),
        }),
        ("Классификация и производство", {
            "fields": ("tnved_code", "country_of_origin"),
        }),
        ("Навигация (для кого / направления)", {
            "fields": ("audiences", "directions"),
            "description": "Многозначные фасеты для профильных разделов магазина. "
                           "Универсальный товар можно отметить сразу несколькими аудиториями/направлениями.",
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
        ("Группировка вариантов", {
            "fields": ("group", "group_order", "variant_label"),
            "description": (
                "Серия объединяет карточки в переключатель. Значения по уровням "
                "серии (напр. «Комплектность») задаются ниже, в блоке «Значения по "
                "уровням серии»."
            ),
        }),
    )

    def _global_characteristics(self):
        """Общие характеристики — показываются у любого товара."""
        return list(
            Characteristic.objects.filter(is_global=True).prefetch_related("options")
        )

    def _category_characteristics(self, obj):
        """Категорийные характеристики (НЕ общие), привязанные к категории товара."""
        if obj and obj.category_id:
            return list(
                obj.category.characteristics.filter(is_global=False).prefetch_related("options")
            )
        return []

    def _dynamic_characteristics(self, obj):
        return self._global_characteristics() + self._category_characteristics(obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(self.base_fieldsets)
        global_chars = self._global_characteristics()
        if global_chars:
            fieldsets.append((
                "Общие характеристики",
                {"fields": [f"char_{ch.id}" for ch in global_chars]},
            ))
        cat_chars = self._category_characteristics(obj)
        if cat_chars:
            fieldsets.append((
                "Категорийные характеристики",
                {"fields": [f"char_{ch.id}" for ch in cat_chars]},
            ))
        return fieldsets

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Объявляем динамические поля характеристик (общие + категорийные) на классе
        # формы, чтобы они прошли валидацию набора полей и отрисовались в филдсетах.
        extra = {
            f"char_{ch.id}": build_characteristic_field(ch)
            for ch in self._dynamic_characteristics(obj)
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
