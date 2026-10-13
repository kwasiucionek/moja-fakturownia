import secrets

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import TOKEN_PREFIX, ApiToken, AssistantReport, hash_token


class OwnDataMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(user=request.user)


@admin.register(ApiToken)
class ApiTokenAdmin(OwnDataMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "prefix",
        "can_write",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = ("can_write",)
    readonly_fields = ("prefix", "created_at", "last_used_at", "revoked_at")
    actions = ["revoke_tokens"]

    def get_fields(self, request, obj=None):
        fields = ["name", "can_write"]
        if request.user.is_superuser:
            fields.insert(0, "user")
        return fields + (list(self.readonly_fields) if obj else [])

    def get_readonly_fields(self, request, obj=None):
        # Po utworzeniu tokena zmienia się tylko nazwę; uprawnienia = nowy token
        return list(self.readonly_fields) + (["user", "can_write"] if obj else [])

    def save_model(self, request, obj, form, change):
        if not change:
            raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
            obj.token_hash = hash_token(raw)
            obj.prefix = raw[:10]
            if not request.user.is_superuser or not obj.user_id:
                obj.user = request.user
            super().save_model(request, obj, form, change)
            messages.warning(
                request,
                format_html(
                    "Token (skopiuj teraz — nie da się go odczytać później): <code>{}</code>",
                    raw,
                ),
            )
            return
        super().save_model(request, obj, form, change)

    @admin.action(description="Unieważnij zaznaczone tokeny")
    def revoke_tokens(self, request, queryset):
        n = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        messages.success(request, f"Unieważniono tokenów: {n}.")


@admin.register(AssistantReport)
class AssistantReportAdmin(OwnDataMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "kind",
        "period",
        "has_issues",
        "created_at",
        "read_at",
        "user",
    )
    list_filter = ("kind", "has_issues")
    readonly_fields = (
        "user",
        "kind",
        "period",
        "title",
        "rendered",
        "created_at",
        "read_at",
    )
    exclude = ("content", "data")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Treść")
    def rendered(self, obj):
        return format_html(
            '<pre style="white-space: pre-wrap; font-size: 0.95rem">{}</pre>',
            obj.content,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        self.get_queryset(request).filter(pk=object_id, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return super().change_view(request, object_id, form_url, extra_context)
