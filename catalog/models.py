from django.core.validators import FileExtensionValidator
from django.db import models

from .utils import unique_slugify

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

    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
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
