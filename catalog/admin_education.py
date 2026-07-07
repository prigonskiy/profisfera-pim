"""Админка обучения. Курс → модули (инлайн). Модуль → слайды (инлайн, TinyMCE)."""
from django.contrib import admin
from django.db import models as dj_models
from tinymce.widgets import TinyMCE

from .education import Course, CourseModule, Slide


class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 0
    fields = ("kind", "title", "video_url", "order", "is_active")


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


class SlideInline(admin.StackedInline):
    model = Slide
    extra = 0
    fields = ("order", "title", "body", "image")
    formfield_overrides = {dj_models.TextField: {"widget": TinyMCE()}}


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "kind", "order", "is_active")
    list_filter = ("kind", "is_active", "course")
    search_fields = ("title", "course__title")
    fields = ("course", "kind", "title", "order", "is_active", "video_url", "body")
    formfield_overrides = {dj_models.TextField: {"widget": TinyMCE()}}
    inlines = [SlideInline]
