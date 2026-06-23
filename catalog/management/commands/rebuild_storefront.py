"""Запуск пересборки витрины из командной строки / крона.

Пример:
    python manage.py rebuild_storefront
"""
from django.core.management.base import BaseCommand

from catalog.storefront import trigger_rebuild


class Command(BaseCommand):
    help = "Запускает пересборку витрины (GitHub repository_dispatch)."

    def handle(self, *args, **options):
        ok, msg = trigger_rebuild()
        if ok:
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stderr.write(self.style.ERROR(msg))
            raise SystemExit(1)
