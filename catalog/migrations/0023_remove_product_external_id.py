# Финал переезда кода сопоставления в торговые предложения:
# значения уже скопированы в Offer.erp_code (миграция 0022), поле на товаре больше не нужно.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0022_bootstrap_offers"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="external_id",
        ),
    ]
