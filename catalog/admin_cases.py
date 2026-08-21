"""Админка кейсов (v1). Тело — TinyMCE + медиатека, зубная формула — карта."""
from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.templatetags.static import static
from django.urls import path
from django.utils.html import format_html
from tinymce.widgets import TinyMCE

from .cases import Case, CaseMedia, CaseProduct


CASE_TOOLBAR = ("undo redo | blocks | bold italic underline | "
                "alignleft aligncenter alignright | bullist numlist | "
                "link image table | casemedia caseproduct | code fullscreen | removeformat")


class CaseAdminForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # кнопка «Галерея» — только на форме кейса (в товарах TinyMCE без неё)
        self.fields["body_html"].widget = TinyMCE(mce_attrs={
            "external_plugins": {
                "casemedia": static("catalog/js/tinymce_casemedia.js"),
                "caseproduct": static("catalog/js/tinymce_caseproduct.js"),
            },
            "toolbar": CASE_TOOLBAR,
        })


class CaseMediaInline(admin.TabularInline):
    model = CaseMedia
    extra = 1
    fields = ("preview_tag", "image", "caption", "alt", "order", "show_in_gallery")
    readonly_fields = ("preview_tag",)

    @admin.display(description="")
    def preview_tag(self, obj):
        src = (obj.thumb or obj.image) if obj.pk else None
        if src:
            return format_html('<img src="{}" style="height:48px;border-radius:4px" />', src.url)
        return "—"


class CaseProductInline(admin.TabularInline):
    model = CaseProduct
    extra = 1
    fields = ("product", "note", "order")
    autocomplete_fields = ("product",)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    form = CaseAdminForm
    list_display = ("case_number", "title", "case_profile", "status", "published_at", "is_featured")
    list_filter = ("status", "case_profile", "is_featured", "audiences", "directions")
    search_fields = ("title", "slug", "case_number")
    list_editable = ("is_featured",)
    filter_horizontal = ("audiences", "directions")
    readonly_fields = ("case_number", "slug", "case_profile", "published_at",
                       "slug_locked", "publish_state")
    inlines = [CaseMediaInline, CaseProductInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "slug_locked", "case_number",
                           "status", "publish_state", "is_featured")}),
        ("Содержание", {"fields": ("body_html", "author_line", "cover")}),
        ("Классификация", {"fields": ("audiences", "directions", "case_profile")}),
        ("Зубная формула", {"fields": ("tooth_scope", "teeth", "arches")}),
        ("SEO", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    class Media:
        js = ("catalog/js/tooth_chart.js",)
        css = {"all": ("catalog/css/tooth_chart.css",)}

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path("<int:pk>/media-json/", self.admin_site.admin_view(self.media_json),
                 name="%s_%s_media_json" % info),
            path("<int:pk>/products-json/", self.admin_site.admin_view(self.products_json),
                 name="%s_%s_products_json" % info),
        ]
        return custom + urls

    def media_json(self, request, pk):
        """Список изображений галереи кейса для медиатеки в редакторе тела."""
        case = self.get_object(request, pk)
        results = []
        if case is not None:
            for m in case.media.all():
                src = m.thumb or m.image
                results.append({
                    "id": m.pk,
                    "thumb": request.build_absolute_uri(src.url) if src else "",
                    "caption": m.caption or "",
                })
        return JsonResponse({"results": results})

    def products_json(self, request, pk):
        """Привязанные к кейсу товары — для вставки карточки товара в тело."""
        case = self.get_object(request, pk)
        results = []
        if case is not None:
            for cp in case.products.select_related("product").all():
                p = cp.product
                if not p:
                    continue
                first = p.images.all().first()
                thumb = (first.thumb or first.image) if first else None
                results.append({
                    "slug": p.slug,
                    "name": p.name,
                    "thumb": request.build_absolute_uri(thumb.url) if thumb else "",
                    "active": p.is_active,
                })
        return JsonResponse({"results": results})

    @admin.display(description="Готовность к публикации")
    def publish_state(self, obj):
        if not obj or not obj.pk:
            return "Сохраните черновик, затем добавьте направления и фото."
        blockers = obj.publish_blockers()
        if not blockers:
            return format_html('<b style="color:#1e7e34">Готов к публикации</b>')
        return format_html('<span style="color:#c0392b">Нельзя опубликовать: {}</span>',
                            "; ".join(blockers))

    def save_model(self, request, obj, form, change):
        if obj.status == Case.Status.PUBLISHED:
            blockers = obj.publish_blockers()
            if blockers:
                from django.contrib import messages
                obj.status = Case.Status.DRAFT
                messages.warning(
                    request, "Кейс сохранён как черновик — для публикации: " + "; ".join(blockers))
        super().save_model(request, obj, form, change)
