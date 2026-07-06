"""Синхронизация остатков/цен торговых предложений.

Источник подключаемый: URL (http/https), локальный файл или переданный список
записей. Формат фида — список объектов:
    [{"erp_code": "...", "stock": 42, "price": 1234.56}, ...]
(допускается обёртка {"items": [...]}).

Синк обновляет у предложения только stock_qty и base_price (справочная цена
склада) + synced_at. Цены строк «Условия продажи» и их price_floor НЕ трогаются —
это ручной коммерческий слой, поэтому порог тут нарушить нельзя by design.
"""
import json
import urllib.request
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .offers import Offer


def load_feed(source):
    """source: URL (http/https) или путь к файлу. Возвращает список записей."""
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    else:
        with open(source, "r", encoding="utf-8") as fh:
            raw = fh.read()
    payload = json.loads(raw)
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("offers") or []
    if not isinstance(payload, list):
        raise ValueError("Фид должен быть списком записей или {\"items\": [...]}.")
    return payload


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def apply_records(records, seller=None):
    """Применяет записи к предложениям (по erp_code). Возвращает статистику."""
    qs = Offer.objects.all()
    if seller is not None:
        qs = qs.filter(warehouse__seller=seller)
    now = timezone.now()
    stats = {"records": len(records), "updated": 0, "unknown": []}

    for rec in records:
        code = str(rec.get("erp_code") or "").strip()
        if not code:
            continue
        offers = list(qs.filter(erp_code=code))
        if not offers:
            stats["unknown"].append(code)
            continue
        for offer in offers:
            fields = ["synced_at"]
            if rec.get("stock") is not None:
                try:
                    offer.stock_qty = max(0, int(rec["stock"]))
                    fields.append("stock_qty")
                except (TypeError, ValueError):
                    pass
            if rec.get("price") is not None:
                price = _to_decimal(rec["price"])
                if price is not None:
                    offer.base_price = price  # справочная цена; строки условий не трогаем
                    fields.append("base_price")
            offer.synced_at = now
            offer.save(update_fields=fields)
            stats["updated"] += 1
    return stats


def sync_from_source(source, seller=None):
    return apply_records(load_feed(source), seller=seller)
