"""Сгенерировать уменьшенные копии (thumb/card/main) для изображений товаров.

Прогоняет все существующие ProductImage. Без --force пропускает те, у которых
копии уже актуальны; с --force перегенерирует всё заново.

    python manage.py generate_image_derivatives
    python manage.py generate_image_derivatives --force
"""
from django.core.management.base import BaseCommand

from catalog.image_derivatives import sync_derivatives
from catalog.models import ProductImage


class Command(BaseCommand):
    help = "Создать/обновить уменьшенные копии изображений товаров."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Перегенерировать даже уже обработанные изображения.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        qs = ProductImage.objects.all()
        total = qs.count()
        self.stdout.write(f"Изображений к обработке: {total}")

        done = ok = 0
        for img in qs.iterator():
            done += 1
            sync_derivatives(img, force=force)
            img.refresh_from_db(fields=["thumb", "card", "main"])
            if img.thumb and img.card and img.main:
                ok += 1
            if done % 25 == 0:
                self.stdout.write(f"  {done}/{total}...")

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Обработано {done}, с копиями {ok}."))
