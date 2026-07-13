"""Контрольный отчёт по «внешнему каталогу»: находит дыры, из-за которых разделы
витрины получаются пустыми или товары никуда не попадают.

Показывает:
  1) активные товары без направлений (никуда не попадут во внешнем каталоге);
  2) направления с числом активных товаров меньше порога (тонкие разделы).

    python manage.py catalog_audit
    python manage.py catalog_audit --threshold 5
    python manage.py catalog_audit --limit 50   # сколько товаров выводить списком
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from catalog.models import Direction, Product


class Command(BaseCommand):
    help = "Отчёт: товары без направлений и тонкие направления (для внешнего каталога)."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=int, default=3,
                            help="Порог «тонкого» направления (по умолчанию 3).")
        parser.add_argument("--limit", type=int, default=30,
                            help="Сколько товаров показывать списком (по умолчанию 30).")

    def handle(self, *args, **options):
        threshold = options["threshold"]
        limit = options["limit"]

        # 1) активные товары без направлений
        no_dir = Product.objects.filter(is_active=True, directions__isnull=True)
        n_no_dir = no_dir.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n1) Активные товары без направлений: {n_no_dir}"))
        for p in no_dir.order_by("name")[:limit]:
            self.stdout.write(f"   [{p.sku}] {p.name}")
        if n_no_dir > limit:
            self.stdout.write(f"   … и ещё {n_no_dir - limit}")

        # 2) тонкие направления (активных товаров меньше порога)
        dirs = (
            Direction.objects.annotate(
                n=Count("products", filter=Q(products__is_active=True), distinct=True))
            .select_related("audience")
            .order_by("audience__order", "order", "name")
        )
        thin = [d for d in dirs if d.n < threshold]
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n2) Направления с числом активных товаров < {threshold}: {len(thin)}"))
        for d in thin:
            aud = d.audience.name if d.audience else "—"
            self.stdout.write(f"   {aud} → {d.name} ({d.slug}): {d.n}")

        self.stdout.write(self.style.SUCCESS("\nГотово."))
