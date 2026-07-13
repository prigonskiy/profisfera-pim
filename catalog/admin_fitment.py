"""Админка справочника «Системы совместимости»."""
from django.contrib import admin

from .fitment import CompatibilitySystem


@admin.register(CompatibilitySystem)
class CompatibilitySystemAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "slug", "order")
    list_filter = ("group",)
    list_editable = ("order",)
    search_fields = ("name", "slug", "group")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("group", "order", "name")
