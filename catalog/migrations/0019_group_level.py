# Этап 1 группировки: одиночный уровень у товара вместо таблиц значений.
import django.db.models.deletion
from django.db import migrations, models


def move_group_levels(apps, schema_editor):
    """Переносим (товар, уровень) из ProductGroupValue в Product.group_level.
    Подпись варианта, если пуста, берём из старого значения уровня."""
    Product = apps.get_model("catalog", "Product")
    ProductGroupValue = apps.get_model("catalog", "ProductGroupValue")
    for pgv in ProductGroupValue.objects.select_related("product", "level", "value"):
        p = pgv.product
        changed = False
        if p.group_level_id is None:             # первый уровень товара побеждает
            p.group_level_id = pgv.level_id
            changed = True
        if not (p.variant_label or "").strip():  # пустую подпись — из старого значения
            p.variant_label = pgv.value.value
            changed = True
        if changed:
            p.save(update_fields=["group_level", "variant_label"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0018_characteristic_admin_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="group_level",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="catalog.grouplevel",
                verbose_name="Уровень в серии",
                help_text="Раздел переключателя, в котором показывается этот вариант. "
                          "Должен принадлежать выбранной серии.",
            ),
        ),
        migrations.RunPython(move_group_levels, noop),
        # удаляем таблицы целиком (без поштучного RemoveField — иначе SQLite падает
        # на UniqueConstraint(product, level)). Сначала ProductGroupValue (ссылается
        # на GroupLevelValue), потом сам GroupLevelValue.
        migrations.DeleteModel(name="ProductGroupValue"),
        migrations.DeleteModel(name="GroupLevelValue"),
    ]
