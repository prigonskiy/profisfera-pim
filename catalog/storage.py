"""Хранилище с адресацией по содержимому (content-addressed) для файлов
изображений товаров — оригиналов и их копий.

Имя файла вычисляется из SHA-256 его байтов, поэтому два одинаковых по
содержимому файла получают ОДИН и тот же путь → это один физический файл, на
который просто ссылаются несколько записей в БД. Так дубли схлопываются сами,
без отдельных указателей и «переадресаций».

Применяется ТОЛЬКО к полям ProductImage (image/thumb/card/main). Документы,
пакеты курсов и логотипы брендов используют обычное хранилище и не затрагиваются.

Имена файлов строятся через posixpath (всегда «/»): в хранилище Django имена —
POSIX-стиля на всех ОС, и os.path (с «\» на Windows) тут использовать нельзя.
"""
import hashlib
import posixpath

from django.core.files.storage import FileSystemStorage
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.deconstruct import deconstructible


@deconstructible
class ContentAddressedStorage(FileSystemStorage):
    def _digest(self, content):
        h = hashlib.sha256()
        for chunk in content.chunks():
            h.update(chunk)
        content.seek(0)  # вернуть указатель, чтобы файл потом записался целиком
        return h.hexdigest()

    def hashed_name(self, name, content):
        # сохраняем исходный «префикс» (products/ или products/derived/) и расширение,
        # раскладывая по подпапкам из первых символов хеша, чтобы не было тысяч файлов в одной папке.
        # Только «/»: имена в хранилище Django POSIX-стиля на любой ОС.
        name = name.replace("\\", "/")
        ext = posixpath.splitext(name)[1].lower()
        digest = self._digest(content)
        cas_suffix = posixpath.join(digest[:2], digest[2:4], digest + ext)
        if name.endswith(cas_suffix):
            return name  # уже под своим content-addressed именем → идемпотентно
        prefix = posixpath.dirname(name)
        return posixpath.join(prefix, cas_suffix)

    def save(self, name, content, max_length=None):
        target = self.hashed_name(name, content)
        if self.exists(target):
            return target  # файл с таким содержимым уже есть → дедуп, ничего не пишем
        return super().save(target, content, max_length=max_length)


# Единственный экземпляр — на него ссылаются поля модели.
product_image_storage = ContentAddressedStorage()


@receiver(setting_changed)
def _reset_storage_location(sender, setting, **kwargs):
    # чтобы override_settings(MEDIA_ROOT=...) в тестах реально переключал папку
    if setting in ("MEDIA_ROOT", "MEDIA_URL"):
        for attr in ("base_location", "location", "base_url"):
            product_image_storage.__dict__.pop(attr, None)
