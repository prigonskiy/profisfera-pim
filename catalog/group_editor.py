"""Редактор группировки вариантов «в одном окне» (Этап 2).

Подключается к ProductGroupAdmin миксином GroupEditorAdminMixin: добавляет
страницу-редактор и JSON-эндпоинты под адресами админки. Всё — только для staff
(admin_view), запись через POST с CSRF. Корневой urls.py не трогаем.

Модель сохранения: параметры (имя серии, имена/порядок уровней, подпись/уровень/
порядок участников) сохраняются одним запросом save/ по кнопке. Структурные
действия (добавить/убрать товар, добавить/удалить уровень) — отдельные запросы.
"""
import json

from django.contrib import admin
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import GroupLevel, Product, ProductGroup


def _member_dict(p):
    return {
        "id": p.pk,
        "name": p.name,
        "sku": p.manufacturer_sku or "",
        "variant_label": p.variant_label or "",
        "group_order": p.group_order,
        "group_level": p.group_level_id,
    }


def _level_dict(lvl):
    return {"id": lvl.pk, "name": lvl.name, "order": lvl.order}


def _body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _to_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


class GroupEditorAdminMixin:
    """Добавляет ProductGroupAdmin страницу-редактор группировки (одно окно, AJAX)."""

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        mine = [
            path("<int:pk>/editor/", self.admin_site.admin_view(self.editor_page),
                 name="%s_%s_editor" % info),
            path("<int:pk>/editor/state/", self.admin_site.admin_view(self.editor_state),
                 name="%s_%s_editor_state" % info),
            path("<int:pk>/editor/search/", self.admin_site.admin_view(self.editor_search),
                 name="%s_%s_editor_search" % info),
            path("<int:pk>/editor/save/", self.admin_site.admin_view(self.editor_save),
                 name="%s_%s_editor_save" % info),
            path("<int:pk>/editor/member/", self.admin_site.admin_view(self.editor_member),
                 name="%s_%s_editor_member" % info),
            path("<int:pk>/editor/level/", self.admin_site.admin_view(self.editor_level),
                 name="%s_%s_editor_level" % info),
        ]
        return mine + super().get_urls()

    @admin.display(description="Редактор")
    def editor_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:%s_%s_editor" % (obj._meta.app_label, obj._meta.model_name),
                      args=[obj.pk])
        return format_html('<a class="button" href="{}">Открыть редактор</a>', url)

    # ---------- вспомогательное ----------
    def _group(self, pk):
        try:
            return ProductGroup.objects.get(pk=pk)
        except ProductGroup.DoesNotExist:
            raise Http404("Серия не найдена")

    # ---------- страница ----------
    def editor_page(self, request, pk):
        group = self._group(pk)
        ctx = {
            **self.admin_site.each_context(request),
            "title": "Редактор группировки: %s" % group.name,
            "opts": self.model._meta,
            "group": group,
        }
        return render(request, "admin/catalog/productgroup/editor.html", ctx)

    # ---------- чтение состояния ----------
    def editor_state(self, request, pk):
        group = self._group(pk)
        levels = [_level_dict(l) for l in group.levels.all()]
        members = [
            _member_dict(p)
            for p in group.products.select_related("group_level").order_by("group_order", "name")
        ]
        return JsonResponse({
            "group": {"id": group.pk, "name": group.name},
            "levels": levels,
            "members": members,
        })

    # ---------- поиск товаров для добавления (не в одной серии) ----------
    def editor_search(self, request, pk):
        self._group(pk)
        q = (request.GET.get("q") or "").strip()
        qs = Product.objects.filter(group__isnull=True)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(manufacturer_sku__icontains=q) | Q(sku__icontains=q))
        qs = qs.order_by("name")[:50]
        return JsonResponse({"results": [
            {"id": p.pk, "name": p.name, "sku": p.manufacturer_sku or ""} for p in qs
        ]})

    # ---------- сохранение всех параметров разом (по кнопке) ----------
    def editor_save(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest("POST only")
        group = self._group(pk)
        data = _body(request)
        with transaction.atomic():
            name = (data.get("name") or "").strip()
            if name:
                group.name = name[:255]
                group.save(update_fields=["name"])

            for lv in data.get("levels", []):
                try:
                    obj = group.levels.get(pk=lv.get("id"))
                except GroupLevel.DoesNotExist:
                    continue
                nm = (lv.get("name") or "").strip()
                if nm:
                    obj.name = nm[:255]
                obj.order = _to_int(lv.get("order"), obj.order)
                obj.save(update_fields=["name", "order"])

            level_ids = set(group.levels.values_list("id", flat=True))
            for mm in data.get("members", []):
                try:
                    p = group.products.get(pk=mm.get("id"))
                except Product.DoesNotExist:
                    continue
                p.variant_label = (mm.get("variant_label") or "")[:255]
                p.group_order = _to_int(mm.get("group_order"), p.group_order)
                gl = mm.get("group_level")
                p.group_level_id = gl if gl in level_ids else None
                p.save(update_fields=["variant_label", "group_order", "group_level"])
        return JsonResponse({"ok": True})

    # ---------- участники: add / remove (структурные) ----------
    def editor_member(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest("POST only")
        group = self._group(pk)
        data = _body(request)
        action = data.get("action")

        if action == "add":
            ids = data.get("product_ids")
            if ids is None and data.get("product_id") is not None:
                ids = [data.get("product_id")]
            ids = [i for i in (ids or []) if i]
            added, skipped = 0, 0
            with transaction.atomic():
                for pid in ids:
                    try:
                        p = Product.objects.get(pk=pid)
                    except Product.DoesNotExist:
                        continue
                    if p.group_id == group.pk:
                        continue  # уже в этой серии
                    if p.group_id:
                        skipped += 1  # в другой серии — не трогаем
                        continue
                    p.group = group
                    p.save(update_fields=["group"])
                    added += 1
            return JsonResponse({"ok": True, "added": added, "skipped": skipped})

        if action == "remove":
            p = get_object_or_404(Product, pk=data.get("product_id"), group=group)
            p.group = None
            p.group_level = None
            p.save(update_fields=["group", "group_level"])
            return JsonResponse({"ok": True})

        return HttpResponseBadRequest("unknown action")

    # ---------- уровни: add / delete (структурные) ----------
    def editor_level(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest("POST only")
        group = self._group(pk)
        data = _body(request)
        action = data.get("action")

        if action == "add":
            name = (data.get("name") or "").strip() or "Новый уровень"
            last = group.levels.order_by("-order").first()
            order = (last.order + 1) if last else 0
            lvl = GroupLevel.objects.create(group=group, name=name[:255], order=order)
            return JsonResponse({"ok": True, "level": _level_dict(lvl)})

        if action == "delete":
            lvl = get_object_or_404(GroupLevel, pk=data.get("level_id"), group=group)
            with transaction.atomic():
                Product.objects.filter(group_level=lvl).update(group_level=None)
                lvl.delete()
            return JsonResponse({"ok": True})

        return HttpResponseBadRequest("unknown action")
