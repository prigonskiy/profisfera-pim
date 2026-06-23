"""Запуск пересборки витрины через GitHub repository_dispatch.

Витрина (репозиторий profisfera-shop) слушает событие repository_dispatch
с типом «rebuild» и пересобирает статику. Здесь — отправка такого события.

Конфигурация берётся из переменных окружения (.env):
    GITHUB_DISPATCH_TOKEN     — fine-grained PAT с правом Contents: Read and write
                                на репозиторий витрины (и ничего лишнего);
    STOREFRONT_REPO           — репозиторий вида "owner/repo",
                                напр. "prigonskiy/profisfera-shop";
    STOREFRONT_DISPATCH_EVENT — тип события, по умолчанию "rebuild"
                                (должен совпадать с types: в pages.yml витрины).
"""
import json
import os
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"


def _config():
    token = os.getenv("GITHUB_DISPATCH_TOKEN", "").strip()
    repo = os.getenv("STOREFRONT_REPO", "").strip()
    event = (os.getenv("STOREFRONT_DISPATCH_EVENT", "rebuild") or "rebuild").strip()
    return token, repo, event


def trigger_rebuild(timeout=10):
    """Отправляет repository_dispatch в репозиторий витрины.

    Возвращает кортеж (ok: bool, message: str). Никогда не бросает исключений —
    безопасно вызывать из админки, management-команды или крона.
    """
    token, repo, event = _config()
    if not token or not repo:
        return False, (
            "Пересборка не настроена: задайте в .env переменные "
            "GITHUB_DISPATCH_TOKEN и STOREFRONT_REPO (вида owner/repo)."
        )

    url = f"{GITHUB_API}/repos/{repo}/dispatches"
    body = json.dumps({"event_type": event}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "profisfera-pim")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
        # При успехе GitHub отвечает 204 No Content.
        if code == 204:
            return True, f"Пересборка витрины запущена (событие «{event}» → {repo})."
        return True, f"Запрос отправлен, код ответа {code}."
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        hint = ""
        if e.code in (401, 403):
            hint = (" Проверьте токен и его право Contents: Read and write "
                    "на репозиторий витрины.")
        elif e.code == 404:
            hint = (" Проверьте STOREFRONT_REPO (owner/repo) и что токен "
                    "имеет доступ именно к этому репозиторию.")
        return False, f"GitHub вернул ошибку {e.code}.{hint} {detail}".strip()
    except urllib.error.URLError as e:
        return False, f"Не удалось связаться с GitHub: {e.reason}"
    except Exception as e:  # подстраховка: не роняем вызывающий код
        return False, f"Непредвиденная ошибка при запуске пересборки: {e}"
