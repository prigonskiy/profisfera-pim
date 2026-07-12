"""Генерация уменьшенных копий изображений товара + безопасная работа с файлами.

Три именованных размера (max-бокс, вписывание по длинной стороне БЕЗ кропа,
апскейл не делаем):
    thumb — 160  (миниатюры карусели/списка)
    card  — 400  (плитка каталога)
    main  — 1200 (главное изображение карточки)

Формат — WebP q≈80. Учитываем EXIF-поворот, сохраняем прозрачность.

Файлы хранятся content-addressed (см. storage.ContentAddressedStorage): имя = хеш
байтов, поэтому одинаковые файлы физически совпадают (дедуп). Удаление любого
файла делаем ТОЛЬКО если на него не ссылается ни одна другая запись — так
дедупнутый файл не пропадёт, пока им кто-то пользуется.
"""
import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile, File
from django.db.models import Q
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

SIZES = {"thumb": 160, "card": 400, "main": 1200}
WEBP_QUALITY = 80
_FILE_FIELDS = ("image", "thumb", "card", "main")


# ---------- подсчёт ссылок и безопасное удаление ----------

def _name_referenced(name, exclude_pk=None):
    """Ссылается ли на файл `name` хоть одна запись ProductImage (любым из 4 полей)?"""
    from .models import ProductImage
    if not name:
        return False
    q = Q(image=name) | Q(thumb=name) | Q(card=name) | Q(main=name)
    qs = ProductImage.objects.filter(q)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def safe_delete_name(storage, name, exclude_pk=None):
    """Удалить физический файл, только если на него больше никто не ссылается."""
    if not name:
        return
    if _name_referenced(name, exclude_pk):
        return  # файл ещё используется другой записью → не трогаем
    try:
        storage.delete(name)
    except Exception:  # noqa: BLE001 — уборка не должна ронять основную операцию
        logger.warning("Не удалось удалить файл %s", name)


# ---------- генерация копий ----------

def _generate_all(src_path):
    """Собрать байты всех копий из файла-оригинала. Возвращает {name: bytes}."""
    out = {}
    with Image.open(src_path) as im0:
        im0 = ImageOps.exif_transpose(im0)  # применить поворот из EXIF
        if im0.mode in ("RGBA", "LA") or (im0.mode == "P" and "transparency" in im0.info):
            base = im0.convert("RGBA")
        else:
            base = im0.convert("RGB")
        for name, box in SIZES.items():
            im = base.copy()
            im.thumbnail((box, box))  # вписать, пропорции сохранить, апскейла нет
            buf = BytesIO()
            im.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
            out[name] = buf.getvalue()
    return out


def sync_derivatives(instance, force=False):
    """Привести копии в соответствие с оригиналом и убрать осиротевшие старые файлы.

    Пропускаем, если оригинал не менялся и все копии на месте (кроме force).
    """
    from .models import ProductImage

    if not instance.image:
        return

    up_to_date = (
        instance.image.name == instance.derived_from
        and bool(instance.thumb) and bool(instance.card) and bool(instance.main)
    )
    if up_to_date and not force:
        return

    old_names = dict(getattr(instance, "_orig_files", {}) or {})  # имена ДО сохранения

    # сначала собираем всё в память — чтобы ошибка не оставила товар без копий
    try:
        data = _generate_all(instance.image.path)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        logger.warning("Копии для изображения %s не созданы: %s", instance.pk, exc)
        return

    # пишем новые копии (storage сам дедупит одинаковые по содержимому)
    base = os.path.splitext(os.path.basename(instance.image.name))[0]
    for name, content in data.items():
        getattr(instance, name).save(f"{base}__{name}.webp", ContentFile(content), save=False)

    ProductImage.objects.filter(pk=instance.pk).update(
        thumb=instance.thumb.name,
        card=instance.card.name,
        main=instance.main.name,
        derived_from=instance.image.name,
    )

    # старые файлы (оригинал/копии), которые сменились, — удалить, если осиротели
    storage = instance.image.storage
    new_names = {getattr(instance, f).name for f in _FILE_FIELDS}
    for old in old_names.values():
        if old and old not in new_names:
            safe_delete_name(storage, old, exclude_pk=instance.pk)

    # обновляем снимок имён
    instance._orig_files = {f: getattr(instance, f).name for f in _FILE_FIELDS}


# ---------- разовый перевод существующих файлов на content-addressed имена ----------

def migrate_to_cas(instance, dry_run=False):
    """Перевести файлы записи на хеш-имена (схлопнув дубли) и убрать осиротевшее.

    Идемпотентно: файлы, уже лежащие под своим content-addressed именем, пропускаются.
    Возвращает число переименованных файлов.
    """
    from .models import ProductImage

    storage = instance.image.storage
    updates = {}
    old_to_clear = []

    for field in _FILE_FIELDS:
        f = getattr(instance, field)
        old = f.name
        if not old or not storage.exists(old):
            continue
        with storage.open(old, "rb") as fh:
            new = storage.hashed_name(old, File(fh))
            if new == old:
                continue  # уже под своим хеш-именем
            if not dry_run and not storage.exists(new):
                fh.seek(0)
                storage.save(old, File(fh))  # запишет под new (или вернёт существующий)
        updates[field] = new
        old_to_clear.append(old)

    if dry_run or not updates:
        return len(updates)

    ProductImage.objects.filter(pk=instance.pk).update(**updates)
    for field, new in updates.items():
        getattr(instance, field).name = new  # синхронизируем объект в памяти

    for old in old_to_clear:
        safe_delete_name(storage, old, exclude_pk=instance.pk)
    return len(updates)
