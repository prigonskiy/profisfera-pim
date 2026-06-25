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

    # процессор: короткий блокирующий замер — стабильнее на multi-worker gunicorn
    try:
        data["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        data["cpu_count"] = psutil.cpu_count()
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

    # load average (системный, не зависит от воркеров) — только Unix
    try:
        data["load_avg"] = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        pass

    return JsonResponse(data)
