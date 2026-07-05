from django.db import migrations

DEFAULT_SELLER = "Профисфера (продавец по умолчанию)"
DEFAULT_WAREHOUSE = "Основной склад"


def bootstrap(apps, schema_editor):
    """Переносим external_id товаров в предложения, НЕ трогая сам external_id.
    Заводим продавца по умолчанию + склад и по одному предложению на товар
    с заполненным кодом сопоставления."""
    Product = apps.get_model("catalog", "Product")
    Seller = apps.get_model("catalog", "Seller")
    Warehouse = apps.get_model("catalog", "Warehouse")
    Offer = apps.get_model("catalog", "Offer")

    products = list(
        Product.objects.exclude(external_id__isnull=True).exclude(external_id__exact="")
    )
    if not products:
        return

    seller, _ = Seller.objects.get_or_create(name=DEFAULT_SELLER, defaults={"is_active": True})
    warehouse, _ = Warehouse.objects.get_or_create(
        seller=seller, name=DEFAULT_WAREHOUSE, defaults={"is_active": True},
    )
    for p in products:
        Offer.objects.get_or_create(
            warehouse=warehouse, product=p,
            defaults={"erp_code": p.external_id or "", "is_active": True},
        )


def unbootstrap(apps, schema_editor):
    """Безопасный откат: удаляем только предсозданные предложения/склад/продавца
    по умолчанию. external_id на товарах не затрагивается."""
    Seller = apps.get_model("catalog", "Seller")
    Warehouse = apps.get_model("catalog", "Warehouse")
    Offer = apps.get_model("catalog", "Offer")

    Offer.objects.filter(
        warehouse__name=DEFAULT_WAREHOUSE, warehouse__seller__name=DEFAULT_SELLER
    ).delete()
    Warehouse.objects.filter(name=DEFAULT_WAREHOUSE, seller__name=DEFAULT_SELLER).delete()
    Seller.objects.filter(name=DEFAULT_SELLER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0021_seed_regions"),
    ]

    operations = [
        migrations.RunPython(bootstrap, unbootstrap),
    ]
