from django.db import migrations


def rebuild_mptt(apps, schema_editor):
    # historical-модель без MPTT-менеджера; для разового перестроения берём реальную
    from catalog.models import Category
    Category.objects.rebuild()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0016_alter_category_options_category_level_category_lft_and_more'),
     ]

    operations = [
        migrations.RunPython(rebuild_mptt, noop),
    ]