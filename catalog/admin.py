import re
from datetime import timedelta

from adminsortable2.admin import SortableAdminBase, SortableAdminMixin, SortableInlineAdminMixin
from mptt.admin import DraggableMPTTAdmin
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import quote
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q
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
    CategoryFilter,
    Characteristic,
    CharacteristicOption,
    Direction,
    Document,
    GroupLevel,
    Product,
    ProductGroup,
    ProductImage,
    ProductAttributeValue,
)
from .group_editor import GroupEditorAdminMixin
from . import admin_offers  # noqa: F401

admin.site.site_header = "ProfiSfera PIM"
admin.site.site_title = "ProfiSfera PIM"
admin.site.index_title = "Управление каталогом"
# главная админки с панелью метрик сервера (шаблон расширяет штатный admin/index.html)
admin.site.index_template = "admin/dashboard_index.html"


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

    def clean_logo(self):
        """Разрешаем SVG как логотип, но отклоняем SVG со скриптами/обработчиками."""
        f = self.cleaned_data.get("logo")
        name = (getattr(f, "name", "") or "").lower()
        if isinstance(f, UploadedFile) and name.endswith(".svg"):
            try:
                f.seek(0)
                raw = f.read(100000)
                f.seek(0)
            except Exception:
                raw = b""
            text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
            low = text.lower()
            if ("<script" in low or "javascript:" in low or "<foreignobject" in low
                    or re.search(r"\son\w+\s*=", low)):
                raise forms.ValidationError(
                    "SVG содержит потенциально небезопасное содержимое (скрипты или "
                    "обработчики событий). Загрузите «чистый» логотип."
                )
        return f


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandAdminForm
    list_display = ("name", "slug")
    search_fields = ("name",)


class CharacteristicSelectWithType(forms.Select):
    """Select характеристик, добавляющий каждому <option> data-ftype с типом.

    По нему JS в админке оставляет в списке «Вид фильтра» только подходящие виды.
    """
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        ftype = getattr(instance, "type", None)
        if ftype:
            option["attrs"]["data-ftype"] = ftype
        return option


class CategoryFilterInline(SortableInlineAdminMixin, admin.TabularInline):
    """Настройка фильтров витрины для категории (наследуется вниз по дереву)."""
    model = CategoryFilter
    extra = 0
    fields = ("characteristic", "display", "config", "order")
    verbose_name = "Фильтр"
    verbose_name_plural = "Фильтры витрины (наследуются вложенными категориями)"

    class Media:
        js = ("catalog/category_filter_admin.js",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "characteristic":
            qs = Characteristic.objects.exclude(type=Characteristic.Type.TEXT)
            cat = getattr(self, "_parent_category", None)
            if cat is not None:
                qs = qs.filter(Q(is_global=True) | Q(categories=cat)).distinct()
            kwargs["queryset"] = qs.order_by("name")
            kwargs["widget"] = CharacteristicSelectWithType()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_formset(self, request, obj=None, **kwargs):
        # запоминаем редактируемую категорию, чтобы ограничить список характеристик
        self._parent_category = obj
        return super().get_formset(request, obj, **kwargs)


class CategoryAdminForm(forms.ModelForm):
    """Состав характеристик категории редактируется прямо здесь (обратная сторона
    Characteristic.categories) — одним списком с поиском, как у документов."""
    characteristics = forms.ModelMultipleChoiceField(
        label="Характеристики категории",
        queryset=Characteristic.objects.all().order_by("name"),
        required=False,
        widget=FilteredSelectMultiple("характеристики", is_stacked=False),
        help_text="Характеристики, доступные товарам этой категории. Глобальные "
                  "характеристики показываются у всех товаров независимо от этого списка.",
    )

    class Meta:
        model = Category
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["characteristics"].initial = self.instance.characteristics.all()

    def save(self, commit=True):
        instance = super().save(commit)

        def _persist():
            instance.characteristics.set(self.cleaned_data["characteristics"])

        if commit:
            _persist()
        else:
            base_save_m2m = self.save_m2m

            def save_m2m():
                base_save_m2m()
                _persist()

            self.save_m2m = save_m2m
        return instance


@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin, SortableAdminBase):
    form = CategoryAdminForm
    change_list_template = "admin/catalog/category/change_list.html"
    list_display = ("tree_actions", "indented_title")
    list_display_links = ("indented_title",)
    mptt_level_indent = 22
    search_fields = ("name",)
    autocomplete_fields = ("parent",)
    inlines = [CategoryFilterInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "parent")}),
        ("Характеристики категории", {
            "fields": ("characteristics",),
            "description": "Какие характеристики доступны товарам этой категории. "
                           "Ниже, в «Фильтрах витрины», из них (и из глобальных) "
                           "настраиваются фильтры. Сначала сохраните набор характеристик, "
                           "затем настраивайте по ним фильтры.",
        }),
    )

    def get_urls(self):
        custom = [
            path("rebuild/", self.admin_site.admin_view(self.rebuild_view),
                 name="catalog_category_rebuild"),
        ]
        return custom + super().get_urls()

    def rebuild_view(self, request):
        # только POST запускает пересборку (см. ProductAdmin.rebuild_view)
        if request.method == "POST":
            ok, msg = trigger_rebuild()
            self.message_user(
                request, msg,
                level=messages.SUCCESS if ok else messages.ERROR,
            )
        return redirect(reverse("admin:catalog_category_changelist"))


class CharacteristicOptionInline(SortableInlineAdminMixin, admin.TabularInline):
    model = CharacteristicOption
    extra = 1
    fields = ("value", "order")


@admin.register(Characteristic)
class CharacteristicAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "admin_label", "code", "type", "unit",
                    "is_global", "show_to_customer", "categories_col")
    list_editable = ("show_to_customer",)
    list_filter = ("type", "is_global", "show_to_customer", "categories")
    search_fields = ("name", "code", "admin_label")
    filter_horizontal = ("categories",)
    inlines = [CharacteristicOptionInline]
    fieldsets = (
        (None, {"fields": ("name", "admin_label", "code", "type", "unit",
                           "is_global", "show_to_customer")}),
        ("Привязка к категориям (только для НЕ общих)", {"fields": ("categories",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("categories")

    @admin.display(description="Категории")
    def categories_col(self, obj):
        cats = list(obj.categories.all())
        return ", ".join(c.name for c in cats) if cats else ("общая" if obj.is_global else "—")


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


class DocumentAdminForm(forms.ModelForm):
    """Привязка документа к товарам одним списком с поиском (вместо строк-инлайнов).

    `products` — обратная сторона M2M (Product.documents), поэтому это
    кастомное поле формы с тем же виджетом, что и filter_horizontal.
    """
    products = forms.ModelMultipleChoiceField(
        label="Товары",
        queryset=Product.objects.all().order_by("name"),
        required=False,
        widget=FilteredSelectMultiple("товары", is_stacked=False),
        help_text="Найдите товары в левом списке и перенесите нужные направо. "
                  "Перенесённые исчезают из доступных — повторно не выберутся.",
    )

    class Meta:
        model = Document
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["products"].initial = self.instance.products.all()

    def save(self, commit=True):
        instance = super().save(commit)

        def _persist():
            instance.products.set(self.cleaned_data["products"])

        if commit:
            _persist()
        else:
            # админка сохраняет с commit=False, затем зовёт save_m2m()
            base_save_m2m = self.save_m2m

            def save_m2m():
                base_save_m2m()
                _persist()

            self.save_m2m = save_m2m
        return instance


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ("name", "doc_type", "number", "status_badge", "valid_until")
    list_filter = ("doc_type", DocumentValidityFilter)
    search_fields = ("name", "number", "issuing_authority")
    fieldsets = (
        (None, {"fields": ("name", "doc_type", "number", "issuing_authority", "file")}),
        ("Срок действия", {
            "fields": ("issued_date", "valid_until", "is_perpetual"),
            "description": "Для бессрочного документа поставьте галочку «Бессрочный». "
                           "Если срок неизвестен — оставьте «Действует до» пустым.",
        }),
        ("Товары", {
            "fields": ("products",),
            "description": "Документ будет привязан ко всем выбранным товарам. "
                           "Список ищется и наполняется в один проход.",
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
@admin.register(GroupLevel)
class GroupLevelAdmin(SortableAdminBase, admin.ModelAdmin):
    list_display = ("name", "group", "order")
    list_filter = ("group",)
    search_fields = ("name",)


class GroupLevelInline(SortableInlineAdminMixin, admin.TabularInline):
    model = GroupLevel
    extra = 1
    fields = ("name", "order")
    show_change_link = True


@admin.register(ProductGroup)
class ProductGroupAdmin(GroupEditorAdminMixin, SortableAdminBase, admin.ModelAdmin):
    list_display = ("name", "slug", "editor_link")
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

    def clean(self):
        cleaned = super().clean()
        group = cleaned.get("group")
        level = cleaned.get("group_level")
        if level and not group:
            self.add_error("group_level", "Сначала выберите серию.")
        elif level and group and level.group_id != group.id:
            self.add_error("group_level", "Уровень должен принадлежать выбранной серии.")
        return cleaned

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


class ProductChangeList(ChangeList):
    """Список товаров: ссылки на карточку строятся по sku, а не по pk."""

    def url_for_result(self, result):
        return reverse(
            "admin:%s_%s_change" % (self.opts.app_label, self.opts.model_name),
            args=(quote(result.sku),),
            current_app=self.model_admin.admin_site.name,
        )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("sku", "name", "category", "brand", "group", "manufacturer_sku", "updated_at")
    list_filter = ("category", "brand", "group", "country_of_origin", "audiences", "directions")
    search_fields = ("name", "manufacturer_sku", "gtin", "sku")
    readonly_fields = ("sku", "group_editor_link")
    autocomplete_fields = ("category", "brand", "group")
    filter_horizontal = ("documents", "audiences", "directions")
    inlines = [ProductImageInline]
    change_list_template = "admin/catalog/product/change_list.html"
    actions = ["export_general", "export_full"]

    # ---- Адресация карточки по sku (с откатом на pk для старых ссылок) ----
    def get_changelist(self, request, **kwargs):
        return ProductChangeList

    def get_object(self, request, object_id, from_field=None):
        # Сначала пытаемся по sku; если не нашли — стандартный поиск по pk
        # (так прежние ссылки /…/<pk>/change/ продолжают работать).
        if from_field is None:
            try:
                return self.get_queryset(request).get(sku=object_id)
            except (self.model.DoesNotExist, ValueError, ValidationError):
                pass
        return super().get_object(request, object_id, from_field)

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
            "fields": ("sku", "name", "slug", "gtin", "brand", "category", "manufacturer_sku"),
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
            "fields": ("group", "group_editor_link", "group_level", "group_order", "variant_label"),
            "description": (
                "Серия объединяет карточки в переключатель вариантов. Уровень — "
                "раздел переключателя (напр. «Наборы» / «Отдельные шприцы»), он "
                "должен принадлежать выбранной серии. Подпись — текст на кнопке варианта."
            ),
        }),
    )

    @admin.display(description="Редактор группировки")
    def group_editor_link(self, obj):
        if obj and obj.pk and obj.group_id:
            url = reverse("admin:catalog_productgroup_editor", args=[obj.group_id])
            return format_html('<a class="button" href="{}">Открыть редактор серии</a>', url)
        return "— выберите серию и сохраните товар, затем настраивайте её в редакторе"

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
