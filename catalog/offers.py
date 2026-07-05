"""Торговые предложения (этап 1).

Коммерческий слой поверх каталога: продавец → склад (с регионами) → предложение
(остаток + код ERP) → условия продажи (каналы × единицы). Каталожные данные
(название, описание, характеристики) остаются на Product — здесь только коммерция.

Модели определены отдельным файлом и подключаются в catalog/models.py одной
строкой импорта — так их видит система миграций, а большой models.py не трогаем.
"""
from django.core.exceptions import ValidationError
from django.db import models


class Seller(models.Model):
    name = models.CharField("Название", max_length=255)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    kpp = models.CharField("КПП", max_length=9, blank=True)
    contact = models.CharField("Контакты", max_length=255, blank=True)
    erp_settings = models.JSONField(
        "Настройки ERP", blank=True, default=dict,
        help_text="Служебные параметры интеграции с ERP продавца (задел на будущее).",
    )
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Продавец"
        verbose_name_plural = "Продавцы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Region(models.Model):
    """Справочник субъектов РФ. Наполняется разово data-миграцией."""
    code = models.CharField("Код", max_length=10, unique=True)
    name = models.CharField("Название", max_length=255)

    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы (справочник)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    seller = models.ForeignKey(
        Seller, verbose_name="Продавец", on_delete=models.CASCADE, related_name="warehouses",
    )
    name = models.CharField("Название", max_length=255)
    address = models.CharField("Адрес", max_length=500, blank=True)
    regions = models.ManyToManyField(
        Region, verbose_name="Обслуживаемые регионы", blank=True, related_name="warehouses",
        help_text="Какие регионы обслуживает склад. Пусто — продаёт по всей стране.",
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Склад"
        verbose_name_plural = "Склады"
        ordering = ["seller__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.seller.name})"


class Offer(models.Model):
    """Один остаток конкретного товара на конкретном складе. Продавец — из склада."""
    warehouse = models.ForeignKey(
        Warehouse, verbose_name="Склад", on_delete=models.CASCADE, related_name="offers",
    )
    product = models.ForeignKey(
        "catalog.Product", verbose_name="Товар", on_delete=models.CASCADE, related_name="offers",
    )
    erp_code = models.CharField(
        "Код в ERP продавца", max_length=255, blank=True,
        help_text="Идентификатор для синхронизации остатка/цены со стороны продавца.",
    )
    stock_qty = models.PositiveIntegerField("Остаток (базовых единиц)", default=0)
    base_price = models.DecimalField(
        "Справочная цена (из ERP)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Опциональная цена склада из ERP. Цены для покупателя задаются в условиях продажи ниже.",
    )
    currency = models.CharField("Валюта", max_length=3, default="RUB")
    is_active = models.BooleanField("Активно", default=True)
    synced_at = models.DateTimeField("Синхронизировано", null=True, blank=True)

    class Meta:
        verbose_name = "Торговое предложение"
        verbose_name_plural = "Торговые предложения"
        ordering = ["product__name"]
        constraints = [
            models.UniqueConstraint(fields=["warehouse", "product"], name="uniq_warehouse_product"),
        ]

    @property
    def seller(self):
        return self.warehouse.seller if self.warehouse_id else None

    def __str__(self):
        return f"{self.product} — {self.warehouse}"


class OfferTerm(models.Model):
    """Условие продажи: строка «канал × единица» с ценой поверх одного остатка."""

    class Channel(models.TextChoices):
        INDIVIDUALS = "individuals", "Физические лица"
        CLINICS = "clinics", "Клиники"
        DISTRIBUTORS = "distributors", "Дистрибьюторы"
        GOVERNMENT = "government", "Госзакупки"

    offer = models.ForeignKey(
        Offer, verbose_name="Предложение", on_delete=models.CASCADE, related_name="terms",
    )
    channel = models.CharField("Канал продаж", max_length=20, choices=Channel.choices)
    unit_name = models.CharField("Единица продажи", max_length=100, default="Штука")
    unit_base_qty = models.PositiveIntegerField(
        "Базовых единиц в единице продажи", default=1,
        help_text="Штука = 1; коробка = число товаров в оптовой коробке.",
    )
    step = models.PositiveIntegerField("Шаг (в единицах продажи)", default=1)
    min_qty = models.PositiveIntegerField("Минимум в заказе (в единицах продажи)", default=1)
    price = models.DecimalField("Цена за единицу продажи", max_digits=12, decimal_places=2)
    price_floor = models.DecimalField(
        "Мин. цена (не опускать)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Жёсткий порог: ниже этой цены синхронизация опускать не имеет права.",
    )
    is_active = models.BooleanField("Активно", default=True)

    class Meta:
        verbose_name = "Условие продажи"
        verbose_name_plural = "Условия продажи (каналы × единицы)"
        ordering = ["channel", "unit_name"]
        constraints = [
            models.UniqueConstraint(fields=["offer", "channel", "unit_name"], name="uniq_offer_channel_unit"),
        ]

    def clean(self):
        errors = {}
        if self.price is not None and self.price_floor is not None and self.price_floor > self.price:
            errors["price_floor"] = "Минимальная цена не может быть больше цены."
        if self.unit_base_qty is not None and self.unit_base_qty < 1:
            errors["unit_base_qty"] = "Должно быть не меньше 1."
        if self.step is not None and self.step < 1:
            errors["step"] = "Должно быть не меньше 1."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_channel_display()} · {self.unit_name}"
