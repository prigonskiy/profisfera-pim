"""Клинические/зуботехнические кейсы (v1).

Кейс: заголовок, HTML-тело, обложка + галерея, независимые аудитории и
направления (мультивыбор, как у товара), зубная формула с производными
фасетами, привязка товаров. Профиль (клинический/лабораторный/совместный)
вычисляется из аудиторий. Приватность/детекция лиц/рентген — вне v1.

Ссылки на модели — строками ("catalog.X"), чтобы модуль подключался в models.py
до объявления Product/Audience/Direction без циклического импорта.
"""
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone

from .storage import product_image_storage
from .utils import unique_slugify


# ---------- зубная формула (FDI) ----------

QUADRANT_ARCH = {1: "upper", 2: "upper", 5: "upper", 6: "upper",
                 3: "lower", 4: "lower", 7: "lower", 8: "lower"}
QUADRANT_SIDE = {1: "right", 4: "right", 5: "right", 8: "right",
                 2: "left", 3: "left", 6: "left", 7: "left"}

# порядок = порядок отрисовки слева направо (для будущей зубной карты в UI)
PERM_UPPER = ["18", "17", "16", "15", "14", "13", "12", "11",
              "21", "22", "23", "24", "25", "26", "27", "28"]
PERM_LOWER = ["48", "47", "46", "45", "44", "43", "42", "41",
              "31", "32", "33", "34", "35", "36", "37", "38"]
PRIM_UPPER = ["55", "54", "53", "52", "51", "61", "62", "63", "64", "65"]
PRIM_LOWER = ["85", "84", "83", "82", "81", "71", "72", "73", "74", "75"]
ALL_FDI = set(PERM_UPPER + PERM_LOWER + PRIM_UPPER + PRIM_LOWER)


def tooth_facets(teeth):
    """Из списка зубов FDI ("46","47") вернуть (arches, sides, groups, dentition)
    как отсортированные списки. Чистая функция, без обращения к БД."""
    arches, sides, groups, dent = set(), set(), set(), set()
    for t in teeth:
        q, p = int(t[0]), int(t[1])
        primary = q >= 5
        arches.add(QUADRANT_ARCH[q])
        sides.add(QUADRANT_SIDE[q])
        dent.add("primary" if primary else "permanent")
        if p <= 2:
            groups.add("incisors")
        elif p == 3:
            groups.add("canines")
        elif primary:
            groups.add("primary_molars")
        elif p <= 5:
            groups.add("premolars")
        else:
            groups.add("molars")
    return sorted(arches), sorted(sides), sorted(groups), sorted(dent)


class CaseNumberCounter(models.Model):
    """Сквозная нумерация кейсов. Отдельная последовательность (не PK), номер не
    переиспользуется после удаления. Ровно одна строка (pk=1)."""
    current = models.PositiveIntegerField("Текущее значение", default=0)

    class Meta:
        verbose_name = "Счётчик номеров кейсов"
        verbose_name_plural = "Счётчик номеров кейсов"

    def __str__(self):
        return str(self.current)

    @classmethod
    def next_value(cls):
        with transaction.atomic():
            cls.objects.get_or_create(pk=1)
            row = cls.objects.select_for_update().get(pk=1)
            row.current += 1
            row.save(update_fields=["current"])
            return row.current


class Case(models.Model):
    class Profile(models.TextChoices):
        CLINICAL = "clinical", "Клинический"
        LAB = "lab", "Лабораторный"
        JOINT = "joint", "Совместный"

    class ToothScope(models.TextChoices):
        TEETH = "teeth", "Отдельные зубы"
        ARCH = "arch", "Челюсть"
        FULL_MOUTH = "full_mouth", "Полный рот"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        ARCHIVED = "archived", "В архиве"

    case_number = models.PositiveIntegerField(
        "Номер кейса", unique=True, null=True, blank=True, editable=False,
        help_text="Сквозной номер, присваивается автоматически и не меняется.")
    title = models.CharField("Заголовок", max_length=255)
    slug = models.SlugField("Slug", max_length=280, unique=True, blank=True, db_index=True)
    slug_locked = models.BooleanField(
        "Slug зафиксирован", default=False,
        help_text="Ставится автоматически при первой публикации; дальше slug меняется только вручную.")
    body_html = models.TextField("Тело кейса (HTML)", blank=True)

    audiences = models.ManyToManyField(
        "catalog.Audience", verbose_name="Аудитории", related_name="cases", blank=True)
    directions = models.ManyToManyField(
        "catalog.Direction", verbose_name="Направления", related_name="cases", blank=True)
    case_profile = models.CharField(
        "Профиль", max_length=16, choices=Profile.choices, blank=True, db_index=True,
        editable=False, help_text="Вычисляется из аудиторий.")

    author_line = models.CharField("Автор (строкой)", max_length=255, blank=True)

    # обложка — отдельное изображение (плитка/OG); деривативы заполняет конвейер (стадия B)
    cover = models.ImageField(
        "Обложка", upload_to="cases/covers/", storage=product_image_storage, blank=True, null=True)
    cover_thumb = models.ImageField(
        upload_to="cases/covers/", storage=product_image_storage, blank=True, null=True, editable=False)
    cover_og = models.ImageField(
        upload_to="cases/covers/", storage=product_image_storage, blank=True, null=True, editable=False)

    # зубная формула
    tooth_scope = models.CharField(
        "Область", max_length=16, choices=ToothScope.choices, default=ToothScope.TEETH)
    teeth = models.JSONField("Зубы (FDI)", default=list, blank=True)
    arches = models.JSONField("Челюсти", default=list, blank=True)
    tooth_groups = models.JSONField(default=list, blank=True, editable=False)
    tooth_sides = models.JSONField(default=list, blank=True, editable=False)
    dentition = models.JSONField(default=list, blank=True, editable=False)

    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField("Опубликован", null=True, blank=True, editable=False)
    is_featured = models.BooleanField(
        "На витрину раздела", default=False,
        help_text="Если есть избранные — в корне раздела показываются они, иначе последние по дате.")

    meta_title = models.CharField("SEO title", max_length=255, blank=True)
    meta_description = models.CharField("SEO description", max_length=320, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Кейс"
        verbose_name_plural = "Кейсы"
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["status", "published_at"])]

    def __str__(self):
        return f"№{self.case_number} {self.title}" if self.case_number else self.title

    @classmethod
    def from_db(cls, db, field_names, values):
        inst = super().from_db(db, field_names, values)
        inst._cover_src = inst.cover.name if inst.cover else ""
        return inst

    # ---- вычисления ----

    def _apply_tooth_facets(self):
        scope = self.tooth_scope
        if scope == self.ToothScope.FULL_MOUTH:
            self.arches = ["lower", "upper"]
            self.teeth = []
        if scope == self.ToothScope.TEETH and self.teeth:
            arches, sides, groups, dent = tooth_facets(self.teeth)
            self.arches, self.tooth_sides, self.tooth_groups, self.dentition = (
                arches, sides, groups, dent)
        elif scope == self.ToothScope.ARCH:
            self.tooth_sides, self.tooth_groups, self.dentition = [], [], []
            self.teeth = []
        else:  # full_mouth или teeth без зубов
            self.tooth_sides, self.tooth_groups, self.dentition = [], [], []
            if scope != self.ToothScope.TEETH:
                self.teeth = []
            if scope == self.ToothScope.TEETH:
                self.arches = []

    def clean(self):
        super().clean()
        # согласованность зубной формулы
        if self.tooth_scope == self.ToothScope.TEETH:
            for t in self.teeth or []:
                if not (isinstance(t, str) and len(t) == 2 and t.isdigit()
                        and int(t[0]) in QUADRANT_ARCH and 1 <= int(t[1]) <= 8):
                    raise ValidationError({"teeth": f"«{t}» не похоже на зуб FDI (например 46)."})
        if self.tooth_scope == self.ToothScope.ARCH and not self.arches:
            raise ValidationError({"arches": "Для области «Челюсть» укажите челюсть(и)."})

    def publish_blockers(self):
        """Причины, по которым кейс нельзя опубликовать (для проверки в админке)."""
        reasons = []
        if not self.title.strip():
            reasons.append("нет заголовка")
        if not self.body_html.strip():
            reasons.append("пустое тело кейса")
        if self.pk:
            if not self.directions.exists():
                reasons.append("не выбрано ни одного направления")
            if not self.cover and not self.media.exists():
                reasons.append("нет ни обложки, ни фотографий")
        if self.tooth_scope == self.ToothScope.TEETH and not self.teeth:
            reasons.append("область «Отдельные зубы», но зубы не отмечены")
        return reasons

    def save(self, *args, **kwargs):
        if self.case_number is None:
            self.case_number = CaseNumberCounter.next_value()
        self._apply_tooth_facets()
        first_publish = (self.status == self.Status.PUBLISHED and self.published_at is None)
        # slug держим в соответствии с заголовком, пока он не зафиксирован
        # и пока мы не фиксируем его прямо сейчас (публикация не должна тихо
        # менять URL из-за одновременной правки заголовка)
        if not self.slug_locked and not first_publish:
            self.slug = unique_slugify(self, f"{self.title}-{self.case_number}")
        if self.status == self.Status.PUBLISHED:
            if self.published_at is None:
                self.published_at = timezone.now()
            self.slug_locked = True  # первая публикация замораживает slug
        if not self.slug:  # страховка: кейс создан сразу опубликованным
            self.slug = unique_slugify(self, f"{self.title}-{self.case_number}")
        super().save(*args, **kwargs)


class CaseMedia(models.Model):
    """Изображение галереи кейса. Может использоваться и в теле (по data-media=id)."""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="media")
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    image = models.ImageField("Изображение", upload_to="cases/media/", storage=product_image_storage)
    thumb = models.ImageField(
        upload_to="cases/media/", storage=product_image_storage, blank=True, null=True, editable=False)
    preview = models.ImageField(
        upload_to="cases/media/", storage=product_image_storage, blank=True, null=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    caption = models.CharField("Подпись", max_length=500, blank=True)
    alt = models.CharField("Alt-текст", max_length=255, blank=True)
    show_in_gallery = models.BooleanField(
        "Показывать в галерее", default=True,
        help_text="Снимите, если картинка нужна только внутри текста.")

    class Meta:
        verbose_name = "Изображение кейса"
        verbose_name_plural = "Изображения кейса"
        ordering = ["order", "id"]

    @classmethod
    def from_db(cls, db, field_names, values):
        inst = super().from_db(db, field_names, values)
        inst._img_src = inst.image.name if inst.image else ""
        return inst

    def save(self, *args, **kwargs):
        if not self.alt:
            self.alt = self.caption or (self.case.title if self.case_id else "")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.caption or f"Изображение #{self.pk}"


class CaseProduct(models.Model):
    """Привязка товара к кейсу (каноническая карточка, не оффер)."""
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="products")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="cases")
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    note = models.CharField("Примечание", max_length=255, blank=True)

    class Meta:
        verbose_name = "Товар кейса"
        verbose_name_plural = "Товары кейса"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["case", "product"], name="uniq_case_product"),
        ]

    def __str__(self):
        return f"{self.product}"


@receiver(post_save, sender=Case)
def _case_cover_derivatives(sender, instance, **kwargs):
    from .case_images import sync_case_cover
    sync_case_cover(instance)


@receiver(post_save, sender=CaseMedia)
def _case_media_derivatives(sender, instance, **kwargs):
    from .case_images import sync_case_media
    sync_case_media(instance)


@receiver(m2m_changed, sender=Case.audiences.through)
def _sync_case_profile(sender, instance, action, **kwargs):
    """Профиль кейса выводится из его аудиторий: только стоматолог → клинический,
    только зубной техник → лабораторный, оба → совместный."""
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not isinstance(instance, Case):
        return
    slugs = set(instance.audiences.values_list("slug", flat=True))
    clinical = "stomatolog" in slugs
    lab = "zubnoy-tehnik" in slugs
    if clinical and lab:
        profile = Case.Profile.JOINT
    elif clinical:
        profile = Case.Profile.CLINICAL
    elif lab:
        profile = Case.Profile.LAB
    else:
        profile = ""
    Case.objects.filter(pk=instance.pk).update(case_profile=profile)
