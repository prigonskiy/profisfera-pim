"""Админка торговых предложений. Подключается в catalog/admin.py одной строкой
импорта (регистрация выполняется на импорте модуля)."""
from django.contrib import admin, messages

from .offer_sync import sync_from_source
from .offers import Offer, OfferTerm, Region, Seller, Warehouse


@admin.action(description="Синхронизировать остатки/цены из ERP-фида")
def sync_selected_sellers(modeladmin, request, queryset):
    total = 0
    for seller in queryset:
        url = (seller.erp_settings or {}).get("feed_url")
        if not url:
            messages.warning(request, f"{seller.name}: в настройках ERP не задан feed_url.")
            continue
        try:
            stats = sync_from_source(url, seller=seller)
            total += stats["updated"]
            if stats["unknown"]:
                messages.warning(request, f"{seller.name}: неизвестных кодов — {len(stats['unknown'])}.")
        except Exception as exc:  # noqa: BLE001 — показываем причину пользователю
            messages.error(request, f"{seller.name}: ошибка синхронизации — {exc}")
    messages.success(request, f"Готово. Обновлено предложений: {total}.")


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("name", "inn", "kpp", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "inn")
    fields = ("name", "inn", "kpp", "contact", "erp_settings", "is_active")
    actions = [sync_selected_sellers]


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    ordering = ("name",)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "seller", "is_active")
    list_filter = ("seller", "is_active")
    search_fields = ("name", "seller__name")
    autocomplete_fields = ("seller",)
    filter_horizontal = ("regions",)


class OfferTermInline(admin.TabularInline):
    model = OfferTerm
    extra = 0
    fields = ("channel", "unit_name", "unit_base_qty", "step", "min_qty", "price", "price_floor", "is_active")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "seller_col", "stock_qty", "erp_code", "is_active")
    list_filter = ("is_active", "warehouse__seller", "warehouse")
    search_fields = ("product__name", "erp_code", "product__sku", "product__manufacturer_sku")
    autocomplete_fields = ("product", "warehouse")
    readonly_fields = ("synced_at",)
    inlines = [OfferTermInline]
    fieldsets = (
        (None, {"fields": ("warehouse", "product", "is_active")}),
        ("Синхронизация с ERP", {"fields": ("erp_code", "stock_qty", "base_price", "currency", "synced_at")}),
    )

    @admin.display(description="Продавец")
    def seller_col(self, obj):
        return obj.warehouse.seller if obj.warehouse_id else "—"
