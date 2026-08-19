"""Конвейер изображений кейса (стадия B).

Обложка (Case.cover): cover_thumb (вписать в 800) + cover_og (кроп 1200×630 для OG).
Галерея (CaseMedia.image): thumb (вписать в 400) + preview (вписать в 1600) + width/height.

Формат копий — WebP, метаданные при этом не переносятся (приватность «бесплатно»).
Content-addressed хранилище переиспользуется — одинаковые копии дедупятся сами.
Служебные поля пишем через .update() — без рекурсии post_save. Копии генерятся
только при изменении/отсутствии (снимок исходного имени берётся в from_db).
"""
import logging
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

COVER_THUMB = 800
COVER_OG = (1200, 630)
MEDIA_THUMB = 400
MEDIA_PREVIEW = 1600
WEBP_QUALITY = 82


def _prepared(src_path):
    """Открыть, применить EXIF-поворот, привести к RGB/RGBA. Метаданные далее не переносятся."""
    im = Image.open(src_path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA")
    return im.convert("RGB")


def _fit_webp(base_img, box):
    im = base_img.copy()
    im.thumbnail((box, box))  # вписать по длинной стороне, без апскейла
    buf = BytesIO()
    im.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def _crop_webp(base_img, target_w, target_h):
    """Cover-fit + центральный кроп ровно в target_w×target_h (для OG-карточки)."""
    im = base_img.copy()
    src_w, src_h = im.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    im = im.crop((left, top, left + target_w, top + target_h))
    buf = BytesIO()
    im.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
    return buf.getvalue()


def sync_case_media(instance, force=False):
    """thumb/preview/width/height для изображения галереи кейса."""
    from .cases import CaseMedia
    if not instance.image:
        return
    src = getattr(instance, "_img_src", None)
    up_to_date = (instance.thumb and instance.preview and instance.width
                  and src == instance.image.name)
    if up_to_date and not force:
        return
    try:
        img = _prepared(instance.image.path)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        logger.warning("Копии для изображения кейса %s не созданы: %s", instance.pk, exc)
        return
    width, height = img.size
    base = os.path.splitext(os.path.basename(instance.image.name))[0]
    instance.thumb.save(f"{base}__thumb.webp", ContentFile(_fit_webp(img, MEDIA_THUMB)), save=False)
    instance.preview.save(f"{base}__preview.webp", ContentFile(_fit_webp(img, MEDIA_PREVIEW)), save=False)
    CaseMedia.objects.filter(pk=instance.pk).update(
        thumb=instance.thumb.name, preview=instance.preview.name, width=width, height=height)
    instance._img_src = instance.image.name


def sync_case_cover(instance, force=False):
    """cover_thumb + cover_og для обложки кейса. Обложку убрали — деривативы чистим."""
    from .cases import Case
    if not instance.cover:
        if instance.cover_thumb or instance.cover_og:
            Case.objects.filter(pk=instance.pk).update(cover_thumb="", cover_og="")
        return
    src = getattr(instance, "_cover_src", None)
    up_to_date = (instance.cover_thumb and instance.cover_og and src == instance.cover.name)
    if up_to_date and not force:
        return
    try:
        img = _prepared(instance.cover.path)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
        logger.warning("Копии обложки кейса %s не созданы: %s", instance.pk, exc)
        return
    base = os.path.splitext(os.path.basename(instance.cover.name))[0]
    instance.cover_thumb.save(f"{base}__thumb.webp", ContentFile(_fit_webp(img, COVER_THUMB)), save=False)
    instance.cover_og.save(f"{base}__og.webp", ContentFile(_crop_webp(img, *COVER_OG)), save=False)
    Case.objects.filter(pk=instance.pk).update(
        cover_thumb=instance.cover_thumb.name, cover_og=instance.cover_og.name)
    instance._cover_src = instance.cover.name
