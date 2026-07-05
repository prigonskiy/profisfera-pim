from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from mptt.models import MPTTModel, TreeForeignKey
from django.utils import timezone
from django_countries.fields import CountryField

from .utils import unique_slugify, validate_gtin
from .offers import Seller, Region, Warehouse, Offer, OfferTerm  # noqa: F401

SLUG_HELP = "Оставьте пустым — сгенерируется автоматически из названия (транслитерацией)."


class Brand(models.Model):
    """Бренд (производитель)."""
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    logo = models.FileField(
        "Логотип", upload_to="brands/", blank=True, null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=["svg", "png", "jpg", "jpeg", "webp", "gif"]
        )],
        help_text="Растровое изображение или SVG. Для логотипов предпочтителен SVG — он чёткий на любом размере.",
    )
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


class Category(MPTTModel):
    """Категория каталога. Дерево через ссылку на себя (parent); порядок хранит MPTT."""
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", unique=True, max_length=255, blank=True, help_text=SLUG_HELP)
    parent = TreeForeignKey(
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
        # ordering не задаём: порядок узлов хранит дерево MPTT (перетаскивание в админке)

    def __str__(self):
        if self.parent_id:
            return f"{self.parent} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)

    def ancestors_chain(self):
        """Категории от себя вверх к корню (себя включая). Защита от циклов."""
        chain, node, seen = [], self, set()
        while node and node.pk not in seen:
            seen.add(node.pk)
            chain.append(node)
            node = node.parent
        return chain

    def effective_filters(self):
        """Эффективные фильтры категории: свои + унаследованные от родителей.

        Потомок переопределяет предка по одной и той же характеристике
        (берётся настройка ближайшей к потомку категории). Результат
        упорядочен по (order, id).
        """
        by_char = {}
        for cat in self.ancestors_chain():  # сначала сама категория, потом предки
            for f in cat.filters.select_related("characteristic").all():
                by_char.setdefault(f.characteristic_id, f)
        chosen = list(by_char.values())
        chosen.sort(key=lambda f: (f.order, f.id))
        return chosen


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
    admin_label = models.CharField(
        "Внутреннее пояснение",
        max_length=255,
        blank=True,
        help_text="Служебная пометка, видна только в админке (покупатель её не видит). "
                  "Различать одноимённые характеристики, напр. «Серия» для хирургии "
                  "и «Серия» для терапии.",
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
    show_to_customer = models.BooleanField(
        "Показывать покупателю",
        default=True,
        help_text="Снимите галочку для служебных характеристик (например, код 1С): "
                  "они останутся в PIM, но не будут видны в витрине.",
    )
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} · {self.admin_label}" if self.admin_label else self.name

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


class CategoryFilter(models.Model):
    """Настройка фильтра витрины: какую характеристику и как показывать в категории.

    Наследуется вниз по дереву: эффективные фильтры категории = свои + от родителей
    (потомок переопределяет предка по одной и той же характеристике). Текстовые
    характеристики как фильтры не используются.
    """

    class Display(models.TextChoices):
        BOOL_CHECKBOX = "bool_checkbox", "Булева: один чекбокс (= «Да»)"
        BOOL_YESNO = "bool_yesno", "Булева: Да / Нет"
        NUMBER_RANGE = "number_range", "Число: диапазон «от–до»"
        NUMBER_BUCKETS = "number_buckets", "Число: корзины-чекбоксы"
        SELECT_CHECKBOX = "select_checkbox", "Список: чекбоксы значений"

    # Допустимые виды отображения для каждого типа характеристики.
    DISPLAY_BY_TYPE = {
        Characteristic.Type.BOOLEAN: {Display.BOOL_CHECKBOX, Display.BOOL_YESNO},
        Characteristic.Type.NUMBER: {Display.NUMBER_RANGE, Display.NUMBER_BUCKETS},
        Characteristic.Type.SINGLE_SELECT: {Display.SELECT_CHECKBOX},
        Characteristic.Type.MULTI_SELECT: {Display.SELECT_CHECKBOX},
    }

    category = models.ForeignKey(
        Category, verbose_name="Категория",
        on_delete=models.CASCADE, related_name="filters",
    )
    characteristic = models.ForeignKey(
        Characteristic, verbose_name="Характеристика",
        on_delete=models.CASCADE, related_name="filter_configs",
    )
    display = models.CharField("Вид фильтра", max_length=32, choices=Display.choices)
    order = models.PositiveIntegerField("Порядок", default=0)
    config = models.JSONField(
        "Доп. настройки", default=dict, blank=True,
        help_text='Необязательно. Подпись: {"label": "Объём"}. '
                  'Корзины для числа: {"buckets": [{"max": 20}, {"min": 20, "max": 40}, {"min": 40}]}.',
    )

    class Meta:
        verbose_name = "Фильтр категории"
        verbose_name_plural = "Фильтры категории"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "characteristic"],
                name="uniq_category_characteristic_filter",
            )
        ]

    def __str__(self):
        return f"{self.category}: {self.characteristic} ({self.get_display_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.characteristic_id:
            return
        allowed = self.DISPLAY_BY_TYPE.get(self.characteristic.type)
        if not allowed:
            raise ValidationError({
                "characteristic": "Этот тип характеристики нельзя использовать как фильтр "
                                  "(например, текстовый)."
            })
        if self.display and self.display not in allowed:
            raise ValidationError({
                "display": "Этот вид отображения недоступен для выбранного типа характеристики."
            })

    def to_config(self):
        """Сериализация фильтра для витрины/API."""
        ch = self.characteristic
        data = {
            "code": ch.code,
            "name": self.config.get("label") or ch.name,
            "type": ch.type,
            "display": self.display,
            "unit": ch.unit,
        }
        if ch.type in (Characteristic.Type.SINGLE_SELECT, Characteristic.Type.MULTI_SELECT):
            data["options"] = list(ch.options.values_list("value", flat=True))
        if self.display == self.Display.NUMBER_BUCKETS:
            data["buckets"] = self.config.get("buckets", [])
        return data


class Document(models.Model):
    """Документ на товар: PDF-файл с метаданными. Связь с товарами — многие-ко-многим."""

    class DocType(models.TextChoices):
        REGISTRATION = "registration", "Регистрационное удостоверение (РУ)"
        DECLARATION = "declaration", "Декларация о соответствии"
        CERTIFICATE = "certificate", "Сертификат соответствия"
        STATE_REGISTRATION = "state_registration", "Свидетельство о госрегистрации (СГР)"
        EXEMPTION = "exemption", "Отказное письмо"
        IFU = "ifu", "Инструкция по применению"
        MANUAL = "manual", "Руководство по эксплуатации"
        PASSPORT = "passport", "Паспорт изделия"
        QUALITY = "quality", "Сертификат качества / анализа"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        PERPETUAL = "perpetual", "Бессрочный"
        VALID = "valid", "Действует"
        EXPIRING = "expiring", "Скоро истекает"
        EXPIRED = "expired", "Просрочен"
        UNKNOWN = "unknown", "Срок не указан"

    EXPIRY_SOON_DAYS = 30  # за сколько дней до конца считать «скоро истекает»

    name = models.CharField(
        "Название (внутреннее)", max_length=255, blank=True,
        help_text="Для внутреннего поиска и идентификации в PIM. Покупателю не показывается.",
    )
    doc_type = models.CharField(
        "Тип документа", max_length=32, choices=DocType.choices, default=DocType.OTHER
    )
    number = models.CharField("Номер", max_length=128, blank=True)
    issuing_authority = models.CharField(
        "Кем выдан", max_length=255, blank=True,
        help_text="Орган или организация, выдавшая документ (например, Росздравнадзор).",
    )
    issued_date = models.DateField("Дата выдачи", null=True, blank=True)
    valid_until = models.DateField(
        "Действует до", null=True, blank=True,
        help_text="Оставьте пустым, если срок не указан. Для бессрочных отметьте «Бессрочный».",
    )
    is_perpetual = models.BooleanField("Бессрочный", default=False)
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

    @property
    def days_left(self):
        """Дней до окончания срока (отрицательное — просрочен). None — нет срока."""
        if self.is_perpetual or not self.valid_until:
            return None
        return (self.valid_until - timezone.localdate()).days

    @property
    def status(self):
        if self.is_perpetual:
            return self.Status.PERPETUAL
        if not self.valid_until:
            return self.Status.UNKNOWN
        days = self.days_left
        if days < 0:
            return self.Status.EXPIRED
        if days <= self.EXPIRY_SOON_DAYS:
            return self.Status.EXPIRING
        return self.Status.VALID


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
        ordering = ["order", "name"]

    def __str__(self):
        if self.audience_id:
            return f"{self.audience.name}: {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class SkuCounter(models.Model):
    """
    Счётчик внутренних артикулов PIM (sku). Ровно одна строка (pk=1).
    Отдельный счётчик, а не max(sku)+1 — это безопасно при гонках и не зависит
    от удалённых товаров (номер не переиспользуется).
    """
    SKU_START = 1000000000  # первый выданный артикул будет 1000000001

    current = models.BigIntegerField("Текущее значение", default=SKU_START)

    class Meta:
        verbose_name = "Счётчик артикулов PIM"
        verbose_name_plural = "Счётчик артикулов PIM"

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
    sku = models.CharField(
        "Артикул PIM",
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        db_index=True,
        help_text="Внутренний идентификатор товара в PIM. Присваивается автоматически и не меняется.",
    )
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
    group_level = models.ForeignKey(
        GroupLevel,
        verbose_name="Уровень в серии",
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
        help_text="Раздел переключателя, в котором показывается этот вариант. Должен принадлежать выбранной серии.",
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
        if not self.sku:
            self.sku = str(SkuCounter.next_value())
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
