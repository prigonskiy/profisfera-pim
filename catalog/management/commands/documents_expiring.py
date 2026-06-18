"""
Отчёт по срокам действия документов: просроченные и истекающие в ближайшие N дней.

    python manage.py documents_expiring            # горизонт 30 дней
    python manage.py documents_expiring --days 60

Удобно повесить на cron, а позже — слать результат на почту ответственному.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import Document


class Command(BaseCommand):
    help = "Показывает просроченные и скоро истекающие документы."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Горизонт «скоро истекает», дней.")

    def handle(self, *args, **opts):
        today = timezone.localdate()
        horizon = today + timedelta(days=opts["days"])

        expired = Document.objects.filter(
            is_perpetual=False, valid_until__lt=today
        ).order_by("valid_until")
        expiring = Document.objects.filter(
            is_perpetual=False, valid_until__gte=today, valid_until__lte=horizon
        ).order_by("valid_until")

        def line(doc):
            n = doc.products.count()
            return f"  • {doc.valid_until}  {doc.name} (№ {doc.number or '—'}) — товаров: {n}"

        if expired:
            self.stdout.write(self.style.ERROR(f"ПРОСРОЧЕНЫ ({expired.count()}):"))
            for d in expired:
                self.stdout.write(line(d))
        if expiring:
            self.stdout.write(self.style.WARNING(
                f"\nИСТЕКАЮТ в ближайшие {opts['days']} дн. ({expiring.count()}):"
            ))
            for d in expiring:
                self.stdout.write(line(d))
        if not expired and not expiring:
            self.stdout.write(self.style.SUCCESS("Просроченных и скоро истекающих документов нет."))
