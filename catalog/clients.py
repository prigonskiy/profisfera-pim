"""Клиенты витрины и юридические лица (шаг 2 блока «пользователи/клиники»).

Это НЕ пользователи админки (staff) — отдельные учётки покупателей витрины.
На этом шаге — только модели и админка (заводишь клиентов/юрлиц и привязки сам).
Авторизация и приватный API цен по каналам — следующие шаги.

Видимость каналов цен: у клиента всегда есть «розница» (individuals) плюс сегмент
каждого подтверждённого юрлица, к которому он привязан.
"""
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class LegalEntity(models.Model):
    class Segment(models.TextChoices):
        CLINICS = "clinics", "Клиники"
        DISTRIBUTORS = "distributors", "Дистрибьюторы"
        GOVERNMENT = "government", "Госзакупки"

    inn = models.CharField("ИНН", max_length=12, unique=True)
    name = models.CharField("Название", max_length=255)
    segment = models.CharField(
        "Сегмент (канал цен)", max_length=20, choices=Segment.choices,
        help_text="Определяет, какой оптовый канал видят представители этого юрлица.",
    )
    is_active = models.BooleanField("Активно", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Юридическое лицо"
        verbose_name_plural = "Юридические лица"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_segment_display()})"


class Client(models.Model):
    """Покупатель витрины. Вход по email + паролю (пароль хранится хешем)."""
    email = models.EmailField("Email", unique=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    name = models.CharField("Имя", max_length=255, blank=True)
    password = models.CharField("Пароль (хеш)", max_length=255, blank=True)
    legal_entities = models.ManyToManyField(
        LegalEntity, through="ClientMembership", related_name="clients",
        verbose_name="Юридические лица", blank=True,
    )
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты (покупатели)"
        ordering = ["email"]

    def set_password(self, raw):
        self.password = make_password(raw)

    def check_password(self, raw):
        return bool(self.password) and check_password(raw, self.password)

    def channels(self):
        """Доступные каналы цен: розница + сегменты подтверждённых активных юрлиц."""
        chans = {"individuals"}
        memberships = self.memberships.filter(
            status=ClientMembership.Status.APPROVED
        ).select_related("legal_entity")
        for m in memberships:
            if m.legal_entity.is_active:
                chans.add(m.legal_entity.segment)
        return chans

    def __str__(self):
        return self.name or self.email


class ClientMembership(models.Model):
    """Привязка клиента к юрлицу. Подтверждается в админке (анти-фрод)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        APPROVED = "approved", "Подтверждён"

    client = models.ForeignKey(
        Client, verbose_name="Клиент", on_delete=models.CASCADE, related_name="memberships",
    )
    legal_entity = models.ForeignKey(
        LegalEntity, verbose_name="Юридическое лицо", on_delete=models.CASCADE, related_name="memberships",
    )
    status = models.CharField(
        "Статус", max_length=20, choices=Status.choices, default=Status.APPROVED,
        help_text="Только «Подтверждён» даёт клиенту оптовые цены сегмента.",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Привязка клиента к юрлицу"
        verbose_name_plural = "Привязки клиентов к юрлицам"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["client", "legal_entity"], name="uniq_client_legalentity"),
        ]

    def __str__(self):
        return f"{self.client} → {self.legal_entity}"
