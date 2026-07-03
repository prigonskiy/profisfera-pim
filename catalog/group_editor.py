"""Редактор группировки вариантов «в одном окне» (Этап 2).

Подключается к ProductGroupAdmin миксином GroupEditorAdminMixin: добавляет
страницу-редактор и набор JSON-эндпоинтов под адресами админки. Всё — только
для staff (обёрнуто в admin_site.admin_view), запись через POST с CSRF.

Никаких правок корневого urls.py не требуется: маршруты живут внутри админки
модели ProductGroup (…/admin/catalog/productgroup/<pk>/editor/…).
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
            path("<int:pk>/editor/rename/", self.admin_site.admin_view(self.editor_rename),
                 name="%s_%s_editor_rename" % info),
            path("<int:pk>/editor/member/", self.admin_site.admin_view(self.editor_member),
                 name="%s_%s_editor_member" % info),
            path("<int:pk>/editor/level/", self.admin_site.admin_view(self.editor_level),
                 name="%s_%s_editor_level" % info),
        ]
        return mine + super().get_urls()

    # ссылка «Открыть редактор» для списка серий
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

    # ---------- поиск товаров для добавления (не состоящих ни в одной серии) ----------
    def editor_search(self, request, pk):
        self._group(pk)
        q = (request.GET.get("q") or "").strip()
        qs = Product.objects.filter(group__isnull=True)
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(manufacturer_sku__icontains=q) | Q(sku__icontains=q))
        qs = qs.order_by("name")[:20]
        return JsonResponse({"results": [
            {"id": p.pk, "name": p.name, "sku": p.manufacturer_sku or ""} for p in qs
        ]})

    # ---------- переименование серии ----------
    def editor_rename(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest("POST only")
        group = self._group(pk)
        name = (_body(request).get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "Имя не может быть пустым."}, status=400)
        group.name = name[:255]
        group.save(update_fields=["name"])
        return JsonResponse({"ok": True, "name": group.name})

    # ---------- участники: add / remove / update ----------
    def editor_member(self, request, pk):
        if request.method != "POST":
            return HttpResponseBadRequest("POST only")
        group = self._group(pk)
        data = _body(request)
        action = data.get("action")

        if action == "add":
            p = get_object_or_404(Product, pk=data.get("product_id"))
            if p.group_id and p.group_id != group.pk:
                return JsonResponse({"error": "Товар уже состоит в другой серии."}, status=400)
            p.group = group
            p.save(update_fields=["group"])
            return JsonResponse({"ok": True, "member": _member_dict(p)})

        if action == "remove":
            p = get_object_or_404(Product, pk=data.get("product_id"), group=group)
            p.group = None
            p.group_level = None
            p.save(update_fields=["group", "group_level"])
            return JsonResponse({"ok": True})

        if action == "update":
            p = get_object_or_404(Product, pk=data.get("product_id"), group=group)
            fields = []
            if "variant_label" in data:
                p.variant_label = (data.get("variant_label") or "")[:255]
                fields.append("variant_label")
            if "group_order" in data:
                try:
                    p.group_order = max(0, int(data.get("group_order") or 0))
                    fields.append("group_order")
                except (TypeError, ValueError):
                    pass
            if "group_level" in data:
                lvl_id = data.get("group_level")
                if lvl_id in (None, "", 0, "0"):
                    p.group_level = None
                else:
                    # уровень обязан принадлежать этой же серии
                    p.group_level = get_object_or_404(GroupLevel, pk=lvl_id, group=group)
                fields.append("group_level")
            if fields:
                p.save(update_fields=fields)
            return JsonResponse({"ok": True, "member": _member_dict(p)})

        return HttpResponseBadRequest("unknown action")

    # ---------- уровни: add / update / delete ----------
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

        if action == "update":
            lvl = get_object_or_404(GroupLevel, pk=data.get("level_id"), group=group)
            fields = []
            if "name" in data:
                name = (data.get("name") or "").strip()
                if name:
                    lvl.name = name[:255]
                    fields.append("name")
            if "order" in data:
                try:
                    lvl.order = max(0, int(data.get("order") or 0))
                    fields.append("order")
                except (TypeError, ValueError):
                    pass
            if fields:
                lvl.save(update_fields=fields)
            return JsonResponse({"ok": True, "level": _level_dict(lvl)})

        if action == "delete":
            lvl = get_object_or_404(GroupLevel, pk=data.get("level_id"), group=group)
            with transaction.atomic():
                Product.objects.filter(group_level=lvl).update(group_level=None)
                lvl.delete()
            return JsonResponse({"ok": True})

        return HttpResponseBadRequest("unknown action")
