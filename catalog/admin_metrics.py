"""Лёгкая панель метрик сервера для админки PIM.

Отдаёт staff-only JSON: загрузка CPU, память, диск (раздел с медиа), load average.
Это «панель на один взгляд», а не система мониторинга — без истории и алертов.
Все метрики защищены try/except; если psutil не установлен — отвечаем мягко.
"""
import os

from django.conf import settings
from django.http import JsonResponse


def server_metrics(request):
    try:
        import psutil
    except Exception:
        return JsonResponse({"available": False, "error": "psutil не установлен на сервере"})

    data = {"available": True}

    # процессор: утилизация по load average, нормированному на число ядер.
    # Стабильнее короткого мгновенного замера (тот на VPS шумит/завышен из-за
    # виртуализации и блокирует воркер), системная и одинаковая для всех воркеров.
    cores = psutil.cpu_count() or 1
    data["cpu_count"] = cores
    try:
        la = os.getloadavg()  # средняя нагрузка за 1 / 5 / 15 минут (Unix)
        data["load_avg"] = [round(x, 2) for x in la]
        data["cpu_percent"] = round(min(la[0] / cores * 100, 100), 1)
    except (OSError, AttributeError):
        # getloadavg недоступен (например, Windows) — мгновенный замер как запасной
        try:
            data["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        except Exception:
            pass

    # оперативная память
    try:
        vm = psutil.virtual_memory()
        data["mem"] = {"percent": vm.percent, "used": vm.used, "total": vm.total}
    except Exception:
        pass

    # диск раздела, где лежат медиафайлы (иначе — корень)
    try:
        media_root = str(getattr(settings, "MEDIA_ROOT", "") or "/")
        path = media_root if os.path.isdir(media_root) else "/"
        du = psutil.disk_usage(path)
        data["disk"] = {"percent": du.percent, "used": du.used, "total": du.total, "path": path}
    except Exception:
        pass

    return JsonResponse(data)
