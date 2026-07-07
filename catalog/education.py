"""Обучение (курсы) — отдельный блок со своей группировкой товаров.

Не завязан на вариантную серию (ProductGroup): у курса свой набор товаров (M2M),
поэтому группировка может отличаться. Карточка любого привязанного товара
показывает блок «Обучение». Слайды рендерит собственный плеер на витрине.
"""
from django.db import models


class Course(models.Model):
    title = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True)
    subtitle = models.CharField("Подзаголовок", max_length=255, blank=True)
    products = models.ManyToManyField(
        "catalog.Product", verbose_name="Товары", related_name="courses", blank=True,
        help_text="Карточки этих товаров покажут блок обучения. Своя группировка, независимая от серии.",
    )
    is_active = models.BooleanField("Активно", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Обучение (курс)"
        verbose_name_plural = "Обучение (курсы)"
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


class CourseModule(models.Model):
    class Kind(models.TextChoices):
        SLIDES = "slides", "Слайды"
        VIDEO = "video", "Видео"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules", verbose_name="Курс")
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.SLIDES)
    title = models.CharField("Название", max_length=255)
    video_url = models.URLField(
        "Ссылка на видео (embed)", blank=True,
        help_text="Для типа «Видео»: URL для вставки через iframe (embed-ссылка YouTube/RuTube).",
    )
    order = models.PositiveIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активно", default=True)

    class Meta:
        verbose_name = "Модуль курса"
        verbose_name_plural = "Модули курса"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class Slide(models.Model):
    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name="slides", verbose_name="Модуль")
    title = models.CharField("Заголовок", max_length=255, blank=True)
    body = models.TextField("Содержимое (HTML)", blank=True, help_text="Текст слайда, редактируется визуально.")
    image = models.ImageField("Изображение", upload_to="courses/", blank=True, null=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Слайд"
        verbose_name_plural = "Слайды"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or f"Слайд {self.order}"
