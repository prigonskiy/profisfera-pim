"""Распаковка и хостинг пакетов слайдов (экспорт курсов iSpring / xAPI-Tin Can).

Модуль курса вида «Слайды» получает zip-пакет (FileField `package`). При его
появлении/замене мы:
  1) безопасно распаковываем zip в media/course_packages/module_<id>/;
  2) находим точку входа (входной index.html плеера);
  3) записываем относительный путь в `entry_path`.

Витрина затем встраивает этот путь в <iframe src=...>. Плеер и все ассеты
(js/css/шрифты/картинки) внутри пакета ссылаются относительными путями, поэтому
показ возможен ТОЛЬКО как отдача статических файлов + iframe (не через srcdoc).

Триггер — сигнал post_save на CourseModule (см. education.py). Запись служебных
полей идёт через .update() (в обход сигнала), поэтому рекурсии нет.
"""
import logging
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET

from django.conf import settings

logger = logging.getLogger(__name__)

# Предохранители против «zip-бомб» и мусора.
MAX_MEMBERS = 5000              # максимум файлов в архиве
MAX_TOTAL_BYTES = 300 * 1024 * 1024   # максимум распакованного объёма (300 МБ)


def module_dir(module_id):
    """Папка распакованного пакета конкретного модуля (внутри MEDIA_ROOT)."""
    return os.path.join(settings.MEDIA_ROOT, "course_packages", f"module_{module_id}")


def _is_within(base, target):
    """target лежит внутри base? Защита от выхода за папку (zip-slip)."""
    base = os.path.realpath(base)
    target = os.path.realpath(target)
    return target == base or target.startswith(base + os.sep)


def _safe_extract(zf, dest):
    """Распаковать безопасно: запрещаем пути с ../ и абсолютные, лимитируем объём."""
    os.makedirs(dest, exist_ok=True)
    members = zf.infolist()
    if len(members) > MAX_MEMBERS:
        raise ValueError("Слишком много файлов в архиве.")

    total = 0
    for info in members:
        if info.filename.endswith("/"):
            continue
        target = os.path.join(dest, info.filename)
        if not _is_within(dest, target):
            raise ValueError(f"Небезопасный путь в архиве: {info.filename}")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Архив слишком большой после распаковки.")

    # извлекаем поштучно (а не extractall) — полный контроль над путями
    for info in members:
        if info.filename.endswith("/"):
            continue
        target = os.path.join(dest, info.filename)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _read_launch(tincan_path):
    """Достать <launch> из tincan.xml (точка входа относительно папки манифеста)."""
    try:
        tree = ET.parse(tincan_path)
    except Exception:
        return None
    for el in tree.iter():
        if el.tag.split("}")[-1] == "launch" and (el.text or "").strip():
            return el.text.strip()
    return None


def _find_entry(root):
    """Абсолютный путь до входного HTML. Порядок надёжности:
    1) tincan.xml <launch>; 2) index.html рядом с lms.js (плеер iSpring);
    3) самый неглубокий index.html."""
    # 1) манифест xAPI
    for dirpath, _dirs, files in os.walk(root):
        if "tincan.xml" in files:
            launch = _read_launch(os.path.join(dirpath, "tincan.xml"))
            if launch:
                cand = os.path.normpath(os.path.join(dirpath, launch))
                if _is_within(root, cand) and os.path.isfile(cand):
                    return cand
    # 2) плеер iSpring
    for dirpath, _dirs, files in os.walk(root):
        if "index.html" in files and "lms.js" in files:
            return os.path.join(dirpath, "index.html")
    # 3) любой index.html, самый верхний
    best = None
    for dirpath, _dirs, files in os.walk(root):
        if "index.html" in files:
            p = os.path.join(dirpath, "index.html")
            depth = os.path.relpath(p, root).count(os.sep)
            if best is None or depth < best[0]:
                best = (depth, p)
    return best[1] if best else None


def _rel_to_media(path):
    """Путь относительно MEDIA_ROOT в URL-форме (через прямые слэши)."""
    return os.path.relpath(path, settings.MEDIA_ROOT).replace(os.sep, "/")


def _clear_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def sync_module_package(module):
    """Привести распакованный пакет в соответствие с текущим FileField.

    Пишет entry_path/entry_source через .update() (без сигнала → без рекурсии).
    Ошибки логирует и не пробрасывает, чтобы сохранение модуля в админке не падало;
    признак неуспеха — пустой entry_path при загруженном package.
    """
    # локальный импорт, чтобы не создавать цикл на этапе загрузки моделей
    from .education import CourseModule

    # пакет сняли — чистим и обнуляем служебные поля
    if not module.package:
        if module.entry_path or module.entry_source:
            _clear_dir(module_dir(module.pk))
            CourseModule.objects.filter(pk=module.pk).update(entry_path="", entry_source="")
        return

    # этот же zip уже распакован — ничего не делаем
    if module.package.name == module.entry_source:
        return

    dest = module_dir(module.pk)
    _clear_dir(dest)
    try:
        with zipfile.ZipFile(module.package.path) as zf:
            _safe_extract(zf, dest)
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        logger.warning("Пакет модуля %s не распакован: %s", module.pk, exc)
        _clear_dir(dest)
        CourseModule.objects.filter(pk=module.pk).update(
            entry_path="", entry_source=module.package.name
        )
        return

    entry = _find_entry(dest)
    rel = _rel_to_media(entry) if entry else ""
    if not rel:
        logger.warning("В пакете модуля %s не найдена точка входа (index.html).", module.pk)
    CourseModule.objects.filter(pk=module.pk).update(
        entry_path=rel, entry_source=module.package.name
    )
