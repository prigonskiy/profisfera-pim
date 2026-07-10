"""Генерация уменьшенных копий изображений товара.

Три именованных размера (max-бокс, вписывание по длинной стороне БЕЗ кропа,
апскейл не делаем):
    thumb — 160  (миниатюры карусели/списка)
    card  — 400  (плитка каталога)
    main  — 1200 (главное изображение карточки)

Формат — WebP q≈80. Учитываем EXIF-поворот, сохраняем прозрачность.
Оригинал не трогаем. Вызывается сигналом post_save (см. models.py) и командой
generate_image_derivatives. Служебные поля пишем через .update() — без рекурсии.
"""
import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

SIZES = {"thumb": 160, "card": 400, "main": 1200}
WEBP_QUALITY = 80


def _generate_all(src_path):
    """Собрать байты всех копий из файла-оригинала. Возвращает {name: bytes}."""
    out = {}
    with Image.open(src_path) as im0:
        im0 = ImageOps.exif_transpose(im0)  # применить поворот из EXIF
        # сохраняем альфу, если она есть; иначе плоский RGB
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
    """Привести копии в соответствие с оригиналом.

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

    # сначала собираем всё в память — чтобы ошибка не оставила товар без копий
    try:
        data = _generate_all(instance.image.path)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        logger.warning("Копии для изображения %s не созданы: %s", instance.pk, exc)
        return

    # удаляем прежние копии (перегенерация или замена оригинала)
    for old in (instance.thumb, instance.card, instance.main):
        try:
            if old:
                old.delete(save=False)
        except Exception:  # noqa: BLE001 — очистка не должна ронять сохранение
            logger.warning("Не удалось удалить старую копию для %s", instance.pk)

    base = os.path.splitext(os.path.basename(instance.image.name))[0]
    for name, content in data.items():
        getattr(instance, name).save(f"{base}__{name}.webp", ContentFile(content), save=False)

    ProductImage.objects.filter(pk=instance.pk).update(
        thumb=instance.thumb.name,
        card=instance.card.name,
        main=instance.main.name,
        derived_from=instance.image.name,
    )
