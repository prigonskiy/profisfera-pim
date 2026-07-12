"""Разовая уборка файлов изображений товаров: перевести на content-addressed
имена (одинаковые файлы схлопнуть в один) и удалить осиротевшее.

Идемпотентно — повторный запуск ничего не ломает. Затрагивает ТОЛЬКО файлы
изображений товаров (image/thumb/card/main); документы, пакеты курсов и логотипы
брендов не трогает. Обрабатывает по одному файлу за раз (память не пухнет).

    python manage.py dedup_media            # выполнить
    python manage.py dedup_media --dry-run  # показать, что изменится, без записи
"""
from django.core.management.base import BaseCommand

from catalog.image_derivatives import migrate_to_cas
from catalog.models import ProductImage


class Command(BaseCommand):
    help = "Схлопнуть дубли файлов изображений товаров и убрать осиротевшее."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Только показать, сколько файлов будет переименовано.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        images = ProductImage.objects.all()
        total = images.count()
        self.stdout.write(f"Записей изображений: {total}{' (dry-run)' if dry else ''}")

        done = renamed = 0
        for img in images.iterator():
            done += 1
            renamed += migrate_to_cas(img, dry_run=dry)
            if done % 25 == 0:
                self.stdout.write(f"  {done}/{total}...")

        verb = "будет переименовано" if dry else "переименовано"
        self.stdout.write(self.style.SUCCESS(
            f"Готово. Обработано записей: {done}, файлов {verb}: {renamed}."))
