"""Админка обучения. Курс → модули (инлайн). Слайды и лонгрид — zip-пакет iSpring."""
from django.contrib import admin
from django.db import models as dj_models
from tinymce.widgets import TinyMCE

from .education import Course, CourseModule


class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 0
    fields = ("kind", "title", "video_url", "package", "order", "is_active")

    class Media:
        js = ("catalog/js/module_kind.js",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "order", "products_count")
    list_filter = ("is_active",)
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("products",)
    inlines = [CourseModuleInline]

    @admin.display(description="Товаров")
    def products_count(self, obj):
        return obj.products.count()


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "kind", "order", "is_active", "package_status")
    list_filter = ("kind", "is_active", "course")
    search_fields = ("title", "course__title")
    readonly_fields = ("package_status",)
    fields = (
        "course", "kind", "title", "order", "is_active",
        "video_url", "body", "package", "package_status",
    )
    # TinyMCE применяется к TextField 'body' (legacy-лонгрид текстом); контент идёт через пакет.
    formfield_overrides = {dj_models.TextField: {"widget": TinyMCE()}}

    class Media:
        js = ("catalog/js/module_kind.js",)

    # типы, которым нужен zip-пакет iSpring
    PACKAGE_KINDS = (CourseModule.Kind.SLIDES, CourseModule.Kind.LONGREAD)

    @admin.display(description="Статус пакета")
    def package_status(self, obj):
        if not obj or not obj.pk:
            return "Сохраните модуль, затем загрузите пакет."
        if obj.kind not in self.PACKAGE_KINDS:
            return "—"
        if not obj.package:
            return "Пакет не загружен."
        if obj.entry_path:
            return f"OK, точка входа: {obj.entry_path}"
        return "Пакет не распознан — проверьте, что это zip-экспорт iSpring/xAPI."
