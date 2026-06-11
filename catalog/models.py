from django.core.validators import FileExtensionValidator
from django.db import models
from django_countries.fields import CountryField

from .utils import unique_slugify, validate_gtin

SLUG_HELP = "Оставьте пустым — сгенерируется автоматически из названия (транслитерацией)."


class Brand(models.Model):
    """Бренд (производитель)."""
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    logo = models.ImageField("Логотип", upload_to="brands/", blank=True, null=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренды"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Category(models.Model):
    """Категория каталога. Вложенность через ссылку на саму себя (parent)."""
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    parent = models.ForeignKey(
        "self",
        verbose_name="Родительская категория",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["name"]

    def __str__(self):
        if self.parent_id:
            return f"{self.parent} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Characteristic(models.Model):
    """Характеристика. Привязывается к категориям, имеет один из пяти типов."""

    class Type(models.TextChoices):
        SINGLE_SELECT = "single_select", "Список (единичный выбор)"
        MULTI_SELECT = "multi_select", "Список (множественный выбор)"
        NUMBER = "number", "Числовое поле"
        TEXT = "text", "Текстовое поле"
        BOOLEAN = "boolean", "Булева (да/нет)"

    name = models.CharField("Название", max_length=255)
    code = models.SlugField(
        "Код",
        unique=True,
        max_length=128,
        blank=True,
        help_text="Машинный код для API. Оставьте пустым — сгенерируется из названия.",
    )
    type = models.CharField("Тип", max_length=20, choices=Type.choices)
    unit = models.CharField(
        "Единица измерения",
        max_length=32,
        blank=True,
        help_text="Напр. 'мм', 'кг'. Имеет смысл для числовых характеристик.",
    )
    categories = models.ManyToManyField(
        Category,
        verbose_name="Категории",
        related_name="characteristics",
        blank=True,
    )
    is_global = models.BooleanField(
        "Общая характеристика",
        default=False,
        help_text="Показывать у всех товаров независимо от категории. Если выключено — "
                  "только у товаров категорий из списка ниже.",
    )
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @property
    def is_select(self):
        return self.type in (self.Type.SINGLE_SELECT, self.Type.MULTI_SELECT)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = unique_slugify(self, self.name, "code")
        super().save(*args, **kwargs)


class CharacteristicOption(models.Model):
    """Вариант значения для характеристик-списков."""
    characteristic = models.ForeignKey(
        Characteristic,
        verbose_name="Характеристика",
        on_delete=models.CASCADE,
        related_name="options",
    )
    value = models.CharField("Значение", max_length=255)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Вариант значения"
        verbose_name_plural = "Варианты значений"
        ordering = ["order", "value"]

    def __str__(self):
        return f"{self.characteristic.name}: {self.value}"


class Document(models.Model):
    """Документ на товар: PDF-файл с метаданными. Связь с товарами — многие-ко-многим."""
    name = models.CharField("Название", max_length=255)
    number = models.CharField("Номер", max_length=128, blank=True)
    file = models.FileField(
        "Файл (PDF)",
        upload_to="documents/",
        validators=[FileExtensionValidator(allowed_extensions=["pdf"])],
    )

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductGroup(models.Model):
    """
    Серия товаров: объединяет отдельные карточки в одну группу, чтобы на
    карточке показывать переключатель вариантов. Механизм самостоятельный и
    НЕ связан с каталожными характеристиками (Characteristic): группировка
    однозначная (товар лежит ровно в одном «ведре» каждого уровня).
    """
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)

    class Meta:
        verbose_name = "Группа (серия) вариантов"
        verbose_name_plural = "Группы (серии) вариантов"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class GroupLevel(models.Model):
    """
    Уровень (ось) группировки внутри серии, напр. «Комплектность».
    Порядок уровней задаёт вложенность переключателя. Структурно повторяет
    Characteristic + CharacteristicOption, но это отдельный механизм.
    """
    group = models.ForeignKey(
        ProductGroup,
        verbose_name="Серия",
        on_delete=models.CASCADE,
        related_name="levels",
    )
    name = models.CharField("Название уровня", max_length=255)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Уровень группировки"
        verbose_name_plural = "Уровни группировки"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="uniq_group_level_name"),
        ]

    def __str__(self):
        return f"{self.group.name}: {self.name}"


class GroupLevelValue(models.Model):
    """Допустимое значение уровня группировки, напр. «Одиночный», «Набор»."""
    level = models.ForeignKey(
        GroupLevel,
        verbose_name="Уровень",
        on_delete=models.CASCADE,
        related_name="values",
    )
    value = models.CharField("Значение", max_length=255)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Значение уровня"
        verbose_name_plural = "Значения уровней"
        ordering = ["order", "value"]
        constraints = [
            models.UniqueConstraint(fields=["level", "value"], name="uniq_level_value"),
        ]

    def __str__(self):
        return f"{self.level.name}: {self.value}"


class Audience(models.Model):
    """
    Аудитория (для кого товар): врач-стоматолог, зубной техник, общая медицина,
    пациент и т.д. Навигационная таксономия — многозначная связь с товаром.
    """
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    icon = models.CharField(
        "Иконка", max_length=64, blank=True,
        help_text="Идентификатор иконки для меню магазина (опционально).",
    )
    description = models.TextField(
        "Описание", blank=True, help_text="Текст для посадочной страницы (SEO)."
    )
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Аудитория"
        verbose_name_plural = "Аудитории"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Direction(models.Model):
    """
    Направление/специализация внутри аудитории: у стоматолога — терапия, хирургия…,
    у техника — CAD/CAM, керамика… Привязка к аудитории даёт чистые профильные
    фильтры. audience пусто → общее направление (видно во всех разделах).
    """
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    audience = models.ForeignKey(
        Audience,
        verbose_name="Аудитория",
        on_delete=models.CASCADE,
        related_name="directions",
        blank=True,
        null=True,
        help_text="Чьё это направление. Пусто — общее (для всех аудиторий).",
    )
    icon = models.CharField("Иконка", max_length=64, blank=True)
    description = models.TextField(
        "Описание", blank=True, help_text="Текст для посадочной страницы (SEO)."
    )
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Направление"
        verbose_name_plural = "Направления"
        ordering = ["audience__order", "order", "name"]

    def __str__(self):
        if self.audience_id:
            return f"{self.audience.name}: {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """Карточка товара."""
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)

    # Постоянные характеристики: описания
    short_description = models.TextField("Краткое описание", blank=True)
    full_description = models.TextField(
        "Полное описание (HTML)",
        blank=True,
        help_text="Поддерживает HTML, редактируется через визуальный редактор.",
    )

    # Постоянные характеристики: организационный блок
    category = models.ForeignKey(
        Category,
        verbose_name="Категория",
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        verbose_name="Бренд",
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
    )
    manufacturer_sku = models.CharField("Артикул производителя", max_length=128, blank=True)
    external_id = models.CharField(
        "Глобальный идентификатор (код сопоставления)",
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Код из 1С, по которому товар сопоставляется во внешних системах "
                  "(Litics). Уникальный; оставьте пустым, если ещё не присвоен.",
    )

    # Постоянные характеристики: идентификация и классификация
    gtin = models.CharField(
        "Штрих-код (GTIN)",
        max_length=14,
        blank=True,
        validators=[validate_gtin],
        help_text="Глобальный номер товара: EAN-8/13, UPC-A (12) или GTIN-14. Только цифры.",
    )
    tnved_code = models.CharField(
        "Код ТН ВЭД",
        max_length=10,
        blank=True,
        help_text="Код товарной номенклатуры ВЭД ЕАЭС (до 10 цифр). Пока вводится вручную.",
    )
    country_of_origin = CountryField(
        verbose_name="Страна производства",
        blank=True,
        help_text="Страна, где произведён товар.",
    )

    # Постоянные характеристики: логистический блок (брутто)
    gross_width_mm = models.DecimalField(
        "Брутто-ширина, мм", max_digits=10, decimal_places=2, blank=True, null=True
    )
    gross_height_mm = models.DecimalField(
        "Брутто-высота, мм", max_digits=10, decimal_places=2, blank=True, null=True
    )
    gross_depth_mm = models.DecimalField(
        "Брутто-глубина, мм", max_digits=10, decimal_places=2, blank=True, null=True
    )
    gross_weight_kg = models.DecimalField(
        "Брутто-масса, кг", max_digits=10, decimal_places=3, blank=True, null=True
    )

    # Документы на товар
    documents = models.ManyToManyField(
        Document,
        verbose_name="Документы",
        related_name="products",
        blank=True,
    )

    # Группировка вариантов (переключатель «соседей» на карточке)
    group = models.ForeignKey(
        ProductGroup,
        verbose_name="Серия (группа вариантов)",
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
    )
    group_order = models.PositiveIntegerField(
        "Порядок в серии",
        default=0,
        help_text="Порядок отображения в переключателе вариантов.",
    )
    variant_label = models.CharField(
        "Подпись варианта",
        max_length=255,
        blank=True,
        help_text="Короткая подпись для переключателя. Пусто — берётся название товара.",
    )

    # Навигационные фасеты: для кого и для какого направления
    audiences = models.ManyToManyField(
        Audience,
        verbose_name="Аудитории",
        related_name="products",
        blank=True,
    )
    directions = models.ManyToManyField(
        Direction,
        verbose_name="Направления",
        related_name="products",
        blank=True,
    )

    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # пустой external_id храним как NULL: иначе несколько "" нарушат unique
        self.external_id = (self.external_id or "").strip() or None
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    """Изображение товара. Порядок задаётся полем order (drag-and-drop в админке)."""
    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField("Изображение", upload_to="products/")
    alt = models.CharField("Alt-текст", max_length=255, blank=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"
        ordering = ["order", "id"]

    def __str__(self):
        return f"Изображение #{self.pk} ({self.product})"

    def save(self, *args, **kwargs):
        # галерейный виджет не редактирует alt — подставляем название товара,
        # чтобы у изображения был осмысленный alt-текст для SEO/доступности
        if not self.alt and self.product_id:
            self.alt = self.product.name
        super().save(*args, **kwargs)


class ProductAttributeValue(models.Model):
    """
    Значение категорийной характеристики у конкретного товара (EAV).
    Используется ровно один из value_* столбцов — в зависимости от типа
    характеристики. Для списков значения лежат в value_options.
    """
    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    characteristic = models.ForeignKey(
        Characteristic,
        verbose_name="Характеристика",
        on_delete=models.CASCADE,
        related_name="values",
    )

    value_text = models.TextField("Текстовое значение", blank=True)
    value_number = models.DecimalField(
        "Числовое значение", max_digits=20, decimal_places=4, blank=True, null=True
    )
    value_boolean = models.BooleanField("Булево значение", blank=True, null=True)
    value_options = models.ManyToManyField(
        CharacteristicOption,
        verbose_name="Выбранные варианты",
        related_name="attribute_values",
        blank=True,
    )

    class Meta:
        verbose_name = "Значение характеристики"
        verbose_name_plural = "Значения характеристик"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "characteristic"],
                name="uniq_product_characteristic",
            )
        ]

    def __str__(self):
        return f"{self.product} — {self.characteristic}"

    @property
    def value(self):
        """Типизированное значение в зависимости от типа характеристики."""
        t = self.characteristic.type
        if t == Characteristic.Type.TEXT:
            return self.value_text
        if t == Characteristic.Type.NUMBER:
            return self.value_number
        if t == Characteristic.Type.BOOLEAN:
            return self.value_boolean
        if t == Characteristic.Type.SINGLE_SELECT:
            opt = self.value_options.first()
            return opt.value if opt else None
        if t == Characteristic.Type.MULTI_SELECT:
            return [o.value for o in self.value_options.all()]
        return None


class ProductGroupValue(models.Model):
    """
    Значение товара на конкретном уровне группировки (однозначное).
    На каждый (товар, уровень) — ровно одна запись (уникальность ниже).
    """
    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        related_name="group_values",
    )
    level = models.ForeignKey(
        GroupLevel,
        verbose_name="Уровень",
        on_delete=models.CASCADE,
        related_name="product_values",
    )
    value = models.ForeignKey(
        GroupLevelValue,
        verbose_name="Значение",
        on_delete=models.CASCADE,
        related_name="product_values",
    )

    class Meta:
        verbose_name = "Значение группировки товара"
        verbose_name_plural = "Значения группировки товара"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "level"],
                name="uniq_product_group_level",
            )
        ]

    def __str__(self):
        return f"{self.product} — {self.level.name}: {self.value.value}"

    def clean(self):
        # значение должно принадлежать выбранному уровню, а уровень — серии товара
        from django.core.exceptions import ValidationError

        errors = {}
        if self.value_id and self.level_id and self.value.level_id != self.level_id:
            errors["value"] = "Значение не относится к выбранному уровню."
        if (
            self.level_id
            and self.product_id
            and self.product.group_id
            and self.level.group_id != self.product.group_id
        ):
            errors["level"] = "Уровень относится к другой серии, не к серии этого товара."
        if errors:
            raise ValidationError(errors)
