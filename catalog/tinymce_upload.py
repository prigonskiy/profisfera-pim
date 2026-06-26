"""Загрузка изображений из TinyMCE прямо в media PIM.

Эндпоинт принимает файл (поле `file`, как его шлёт TinyMCE), проверяет, что это
картинка, сохраняет в media/uploads/tinymce/ и возвращает {"location": "<абс. URL>"},
как ожидает редактор.

Доступ — только для персонала. CSRF снят намеренно: штатный загрузчик TinyMCE не
передаёт CSRF-токен, а доступ и без того ограничен сессией сотрудника
(`staff_member_required`) плюс проверкой типа и содержимого файла.
"""
import os
import re

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError
from slugify import slugify

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_BYTES = 10 * 1024 * 1024  # 10 МБ


def _svg_is_safe(raw):
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
    low = text.lower()
    return not (
        "<script" in low
        or "javascript:" in low
        or "<foreignobject" in low
        or re.search(r"\son\w+\s*=", low)
    )


@csrf_exempt
@staff_member_required
@require_POST
def tinymce_upload(request):
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"message": "Файл не передан"}, status=400)
    if f.size > MAX_BYTES:
        return JsonResponse({"message": "Файл слишком большой (макс. 10 МБ)"}, status=400)

    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        return JsonResponse({"message": "Недопустимый тип файла"}, status=400)

    # проверка содержимого
    if ext == ".svg":
        raw = f.read()
        f.seek(0)
        if not _svg_is_safe(raw):
            return JsonResponse(
                {"message": "SVG содержит потенциально небезопасное содержимое"}, status=400
            )
    else:
        try:
            Image.open(f).verify()
        except Exception:
            return JsonResponse(
                {"message": "Файл не является корректным изображением"}, status=400
            )
        finally:
            f.seek(0)

    # имя: читаемая транслитерация + случайный суффикс от коллизий
    base = slugify(os.path.splitext(os.path.basename(f.name or "image"))[0]) or "image"
    name = f"{base[:60]}-{get_random_string(8)}{ext}"
    saved = default_storage.save("uploads/tinymce/" + name, ContentFile(f.read()))

    url = settings.MEDIA_URL + saved
    if not url.startswith(("http://", "https://", "/")):
        url = "/" + url
    return JsonResponse({"location": request.build_absolute_uri(url)})
