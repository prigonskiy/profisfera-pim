"""Админка клиентов и юрлиц. Пароль задаётся отдельным полем (хешируется)."""
from django import forms
from django.contrib import admin

from .clients import Client, ClientMembership, ClientToken, LegalEntity


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ("name", "inn", "segment", "is_active")
    list_filter = ("segment", "is_active")
    search_fields = ("name", "inn")


class ClientMembershipInline(admin.TabularInline):
    model = ClientMembership
    extra = 0
    autocomplete_fields = ("legal_entity",)
    fields = ("legal_entity", "status", "created_at")
    readonly_fields = ("created_at",)


class ClientAdminForm(forms.ModelForm):
    new_password = forms.CharField(
        label="Задать пароль", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Введите, чтобы задать или сменить пароль. Пусто — не менять.",
    )

    class Meta:
        model = Client
        fields = ("email", "phone", "name", "is_active")

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = self.cleaned_data.get("new_password")
        if raw:
            obj.set_password(raw)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    form = ClientAdminForm
    list_display = ("email", "name", "phone", "is_active", "has_password", "entities_col")
    list_filter = ("is_active",)
    search_fields = ("email", "phone", "name")
    inlines = [ClientMembershipInline]
    fields = ("email", "phone", "name", "new_password", "is_active")

    @admin.display(boolean=True, description="Пароль задан")
    def has_password(self, obj):
        return bool(obj.password)

    @admin.display(description="Юрлица")
    def entities_col(self, obj):
        rows = obj.memberships.select_related("legal_entity").all()
        return ", ".join(f"{m.legal_entity.name} [{m.get_status_display()}]" for m in rows) or "—"


@admin.register(ClientToken)
class ClientTokenAdmin(admin.ModelAdmin):
    list_display = ("client", "key_short", "created_at")
    search_fields = ("client__email", "key")
    readonly_fields = ("key", "created_at")

    @admin.display(description="Ключ")
    def key_short(self, obj):
        return (obj.key[:12] + "…") if obj.key else ""
