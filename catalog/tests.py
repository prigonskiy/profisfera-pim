"""
Тесты критических путей PIM.

Покрывают то, что молча ломается при правках и бьёт по данным/доступу:
  • присвоение внутреннего артикула sku (формат, уникальность, неизменность);
  • права API (аноним читает, но не пишет; сотрудник пишет);
  • обращение к товару и по slug, и по sku;
  • импорт xlsx: создание/обновление, сопоставление по ключам и ТИПОВАЯ
    предпроверка (мусор в булевой/числовой ячейке отклоняет строку);
  • статусы срока действия документов;
  • совместимость форматов экспорта и импорта (round-trip).

Запуск:  python manage.py test catalog
"""
from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

from catalog import catalog_io
from catalog.models import (
    Category,
    Characteristic,
    Document,
    Product,
    ProductAttributeValue,
    SkuCounter,
)


def make_import_xlsx(id_row, data_rows):
    """Собрать xlsx нашего формата: строка 1 — идентификаторы, строка 2 — подписи, данные с 3-й."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Товары"
    ws.append(id_row)
    ws.append([f"({c})" for c in id_row])  # строка-подписи, импорт её игнорирует
    for row in data_rows:
        ws.append(row)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


class SkuTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Материалы")

    def test_sku_assigned_format_and_sequence(self):
        p1 = Product.objects.create(name="Товар 1", category=self.cat)
        p2 = Product.objects.create(name="Товар 2", category=self.cat)
        # первый артикул = старт счётчика + 1, длиной 10 знаков
        self.assertEqual(p1.sku, str(SkuCounter.SKU_START + 1))
        self.assertEqual(len(p1.sku), 10)
        # счётчик монотонно растёт и не повторяется
        self.assertEqual(int(p2.sku), int(p1.sku) + 1)

    def test_sku_is_stable_on_resave(self):
        p = Product.objects.create(name="Товар", category=self.cat)
        original = p.sku
        p.name = "Товар (переименован)"
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.sku, original)

    def test_sku_not_reused_after_delete(self):
        p1 = Product.objects.create(name="A", category=self.cat)
        first = p1.sku
        p1.delete()
        p2 = Product.objects.create(name="B", category=self.cat)
        self.assertNotEqual(p2.sku, first)
        self.assertGreater(int(p2.sku), int(first))


class ApiPermissionTests(TestCase):
    def setUp(self):
        cache.clear()  # сбросить историю троттлинга, чтобы тесты не влияли друг на друга
        self.cat = Category.objects.create(name="Материалы")
        self.product = Product.objects.create(name="Адгезив", category=self.cat)
        self.staff = User.objects.create_user("staff", password="x", is_staff=True)

    def test_anonymous_can_read_list_and_detail(self):
        client = APIClient()
        self.assertEqual(client.get("/api/products/").status_code, 200)
        self.assertEqual(client.get(f"/api/products/{self.product.slug}/").status_code, 200)

    def test_product_addressable_by_slug_and_sku(self):
        client = APIClient()
        by_slug = client.get(f"/api/products/{self.product.slug}/")
        by_sku = client.get(f"/api/products/{self.product.sku}/")
        self.assertEqual(by_slug.status_code, 200)
        self.assertEqual(by_sku.status_code, 200)
        self.assertEqual(by_slug.data["id"], by_sku.data["id"])

    def test_anonymous_cannot_write(self):
        client = APIClient()
        self.assertIn(client.post("/api/products/", {"name": "X"}).status_code, (401, 403))
        self.assertIn(client.patch(f"/api/products/{self.product.slug}/", {}).status_code, (401, 403))
        self.assertIn(client.delete(f"/api/products/{self.product.slug}/").status_code, (401, 403))

    def test_staff_can_write(self):
        client = APIClient()
        client.force_authenticate(user=self.staff)
        resp = client.patch(f"/api/products/{self.product.slug}/", {})
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_non_staff_cannot_write(self):
        user = User.objects.create_user("plain", password="x", is_staff=False)
        client = APIClient()
        client.force_authenticate(user=user)
        self.assertIn(client.patch(f"/api/products/{self.product.slug}/", {}).status_code, (401, 403))


class DocumentStatusTests(TestCase):
    def _doc(self, **kwargs):
        return Document.objects.create(name="Док", **kwargs)

    def test_perpetual(self):
        self.assertEqual(self._doc(is_perpetual=True).status, Document.Status.PERPETUAL)

    def test_unknown_when_no_date(self):
        self.assertEqual(self._doc().status, Document.Status.UNKNOWN)

    def test_expired(self):
        d = self._doc(valid_until=timezone.localdate() - timedelta(days=1))
        self.assertEqual(d.status, Document.Status.EXPIRED)
        self.assertLess(d.days_left, 0)

    def test_expiring_soon(self):
        d = self._doc(valid_until=timezone.localdate() + timedelta(days=10))
        self.assertEqual(d.status, Document.Status.EXPIRING)
        self.assertEqual(d.days_left, 10)

    def test_valid(self):
        d = self._doc(valid_until=timezone.localdate() + timedelta(days=400))
        self.assertEqual(d.status, Document.Status.VALID)


class XlsxImportTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Материалы")
        self.bool_char = Characteristic.objects.create(
            name="Тестовый флаг", code="test_flag",
            type=Characteristic.Type.BOOLEAN, is_global=True,
        )

    def test_dry_run_creates_nothing_but_reports(self):
        f = make_import_xlsx(
            ["sku", "external_id", "name", "category_slug"],
            [["", "NEW-1", "Новый товар", self.cat.slug]],
        )
        report = catalog_io.import_workbook(f, dry_run=True)
        self.assertEqual(report["created"], 1)
        self.assertFalse(report["applied"])
        self.assertEqual(Product.objects.filter(external_id="NEW-1").count(), 0)  # откатилось

    def test_real_import_creates_product_with_sku(self):
        f = make_import_xlsx(
            ["sku", "external_id", "name", "category_slug", "char:test_flag"],
            [["", "NEW-2", "Адгезив Bond", self.cat.slug, "Да"]],
        )
        report = catalog_io.import_workbook(f, dry_run=False)
        self.assertEqual(report["created"], 1)
        self.assertTrue(report["applied"])
        p = Product.objects.get(external_id="NEW-2")
        self.assertTrue(p.sku)  # внутренний артикул присвоен
        av = ProductAttributeValue.objects.get(product=p, characteristic=self.bool_char)
        self.assertIs(av.value_boolean, True)

    def test_update_by_sku(self):
        p = Product.objects.create(name="Старое имя", category=self.cat)
        f = make_import_xlsx(
            ["sku", "name", "category_slug"],
            [[p.sku, "Новое имя", self.cat.slug]],
        )
        report = catalog_io.import_workbook(f, dry_run=False)
        self.assertEqual(report["updated"], 1)
        p.refresh_from_db()
        self.assertEqual(p.name, "Новое имя")

    def test_garbage_in_boolean_is_rejected(self):
        """Кейс из практики: «цц» в булевой — строка должна отклоняться, а не молча проглатываться."""
        f = make_import_xlsx(
            ["sku", "external_id", "name", "category_slug", "char:test_flag"],
            [["", "BAD-1", "Битый товар", self.cat.slug, "цц"]],
        )
        report = catalog_io.import_workbook(f, dry_run=False)
        self.assertEqual(report["created"], 0)
        self.assertGreaterEqual(len(report["errors"]), 1)
        self.assertEqual(Product.objects.filter(external_id="BAD-1").count(), 0)

    def test_unknown_sku_is_error(self):
        f = make_import_xlsx(
            ["sku", "name", "category_slug"],
            [["9999999999", "Призрак", self.cat.slug]],
        )
        report = catalog_io.import_workbook(f, dry_run=False)
        self.assertEqual(report["created"], 0)
        self.assertEqual(report["updated"], 0)
        self.assertGreaterEqual(len(report["errors"]), 1)


class ExportRoundTripTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(name="Материалы")
        self.product = Product.objects.create(
            name="Адгезив Bond Force", category=self.cat, manufacturer_sku="14926",
        )

    def test_export_structure(self):
        wb = catalog_io.build_export_workbook(Product.objects.all(), include_category_chars=False)
        ws = wb["Товары"]
        self.assertEqual(ws.cell(row=1, column=1).value, "sku")            # строка 1 — идентификаторы
        self.assertEqual(ws.cell(row=3, column=1).value, self.product.sku)  # данные с 3-й строки

    def test_export_then_import_is_consistent(self):
        """Файл из экспорта должен без ошибок читаться импортом — один и тот же формат."""
        wb = catalog_io.build_export_workbook(Product.objects.all(), include_category_chars=False)
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        report = catalog_io.import_workbook(bio, dry_run=True)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["updated"], 1)
        self.assertEqual(report["created"], 0)


class ThrottleConfigTests(TestCase):
    """Троттлинг должен оставаться включённым в настройках API — защита от случайного удаления.

    Живое срабатывание 429 здесь не воспроизводим (поведение троттла под тест-клиентом
    DRF капризно и зависит от кэша/инстансов); проверяем сам факт настройки, а 429
    подтверждается вручную, напр.:  for i in $(seq 1 400); do curl -s -o /dev/null -w "%{http_code}\\n" <API>/api/products/; done | sort | uniq -c
    """

    def test_throttle_classes_and_rates_configured(self):
        from rest_framework.settings import api_settings
        from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

        classes = list(api_settings.DEFAULT_THROTTLE_CLASSES)
        self.assertIn(AnonRateThrottle, classes)
        self.assertIn(UserRateThrottle, classes)
        rates = api_settings.DEFAULT_THROTTLE_RATES
        self.assertTrue(rates.get("anon"))
        self.assertTrue(rates.get("user"))
