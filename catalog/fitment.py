"""Фасет «Система совместимости» (fitment): к каким системам подходит товар.

Система = «к чему подходит» (Straumann BLT, Dentium SuperLine…). Это ОТДЕЛЬНАЯ
ось от бренда (бренд = «кто произвёл»): у совместимого абатмента бренд свой, а
система — чужая. Не смешивать.

Плоский справочник значений; поле group — ось («Имплантация»/«Ортодонтия»…),
нужно только для порядка/группировки в админке. Куда монтировать срез на
витрине, решает конфиг витрины — PIM про это не знает.
"""
from django.db import models

from .utils import unique_slugify

_SLUG_HELP = "Оставьте пустым — сгенерируется автоматически из названия (транслитерацией)."


class FitmentType(models.TextChoices):
    ORIGINAL = "original", "Оригинал"
    COMPATIBLE = "compatible", "Совместимый"


class CompatibilitySystem(models.Model):
    name = models.CharField("Название", max_length=255, help_text="Напр. «Straumann BLT».")
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=_SLUG_HELP)
    group = models.CharField(
        "Группа/ось", max_length=255, blank=True,
        help_text="Напр. «Имплантация», «Ортодонтия». Для порядка и группировки в админке.",
    )
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Система совместимости"
        verbose_name_plural = "Системы совместимости"
        ordering = ["group", "order", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group}: {self.name}" if self.group else self.name
