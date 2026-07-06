"""Синхронизация остатков/цен предложений.

Примеры:
    python manage.py sync_offers --demo                 # случайные остатки (смоук-тест, без источника)
    python manage.py sync_offers --source feed.json     # из локального файла
    python manage.py sync_offers --source https://host/feed.json
    python manage.py sync_offers --seller "Профисфера…"  # источник берётся из настроек продавца (feed_url)
"""
import random

from django.core.management.base import BaseCommand, CommandError

from catalog.offer_sync import apply_records, sync_from_source
from catalog.offers import Offer, Seller


class Command(BaseCommand):
    help = "Синхронизация остатков/цен торговых предложений (URL, файл или демо)."

    def add_arguments(self, parser):
        parser.add_argument("--source", help="URL или путь к JSON-фиду.")
        parser.add_argument("--seller", help="ID или название продавца (ограничить синк).")
        parser.add_argument("--demo", action="store_true",
                            help="Демо: случайные остатки/цены для существующих предложений, без источника.")

    def handle(self, *args, **opts):
        seller = None
        if opts.get("seller"):
            key = opts["seller"]
            seller = (Seller.objects.filter(pk=key).first() if str(key).isdigit()
                      else Seller.objects.filter(name=key).first())
            if not seller:
                raise CommandError("Продавец не найден: %s" % key)

        if opts.get("demo"):
            qs = Offer.objects.all()
            if seller:
                qs = qs.filter(warehouse__seller=seller)
            records = [
                {"erp_code": o.erp_code, "stock": random.randint(0, 200),
                 "price": round(random.uniform(500, 5000), 2)}
                for o in qs.exclude(erp_code="")
            ]
            stats = apply_records(records, seller=seller)
        else:
            source = opts.get("source")
            if not source and seller:
                source = (seller.erp_settings or {}).get("feed_url")
            if not source:
                raise CommandError(
                    "Не задан источник: --source URL/файл, либо feed_url в настройках продавца, либо --demo."
                )
            stats = sync_from_source(source, seller=seller)

        self.stdout.write(self.style.SUCCESS(
            "Записей: %d · обновлено предложений: %d · неизвестных кодов: %d"
            % (stats["records"], stats["updated"], len(stats["unknown"]))
        ))
        if stats["unknown"]:
            head = ", ".join(stats["unknown"][:20])
            tail = "…" if len(stats["unknown"]) > 20 else ""
            self.stdout.write("Неизвестные коды: " + head + tail)
