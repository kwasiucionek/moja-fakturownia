import secrets

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from ksiegowosc.settlements import SettlementError
from ksiegowosc.tax_engine import MissingYearParams
from ksiegowosc.tax_engine.calendar import previous_month

from .agents import close_month
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

    change_list_template = "admin/assistant/assistantreport/change_list.html"

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        custom = [
            path(
                "uruchom-zamkniecie/",
                self.admin_site.admin_view(self.run_month_close_view),
                name="assistant_run_month_close",
            )
        ]
        return custom + super().get_urls()

    def run_month_close_view(self, request):
        today = timezone.localdate()
        year, month = previous_month(today.year, today.month)
        if request.method == "POST":
            try:
                year, month = int(request.POST["year"]), int(request.POST["month"])
                report = close_month(
                    request.user,
                    year,
                    month,
                    save_draft=bool(request.POST.get("save_draft")),
                )
            except (KeyError, ValueError, SettlementError, MissingYearParams) as exc:
                messages.error(request, f"Nie udało się zamknąć miesiąca: {exc}")
            else:
                messages.success(request, report.title)
                return redirect(
                    reverse("admin:assistant_assistantreport_change", args=[report.pk])
                )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Zamknięcie miesiąca",
            "year": year,
            "month": month,
            "years": list(range(today.year - 3, today.year + 1)),
            "months": list(range(1, 13)),
        }
        return render(request, "admin/assistant/run_month_close.html", context)

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
