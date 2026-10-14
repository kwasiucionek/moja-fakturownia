"""Dostęp zwykłych kont (nie-superuserów): grupa „ksiegowosc” i izolacja danych w panelu.

Uprawnienia są nadawane grupie, nie poszczególnym kontom — zapis formularza użytkownika w panelu
nie odbiera więc dostępu. Każdy ekran panelu pokazuje tylko rekordy zalogowanego użytkownika
(`OwnDataAdminMixin`).
"""

from __future__ import annotations

import logging

from django.contrib import admin

logger = logging.getLogger(__name__)

GROUP_NAME = "ksiegowosc"

# (aplikacja, model) -> akcje; modele z polem `user`, ekrany filtrują po właścicielu
GROUP_PERMISSIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("ksiegowosc", "companyinfo"): ("view", "add", "change"),
    ("ksiegowosc", "contractor"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "invoice"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "invoiceitem"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "payment"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "purchaseinvoice"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "purchaseinvoiceitem"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "expensecategory"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "monthlysettlement"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "yearlysettlement"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "businesssuspension"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "dutyrate"): ("view", "add", "change", "delete"),
    ("ksiegowosc", "dutyshift"): ("view", "add", "change", "delete"),
    ("assistant", "apitoken"): ("view", "add", "change"),
    ("assistant", "assistantreport"): ("view", "change", "delete"),
}


def sync_group_permissions(**kwargs) -> None:
    """Ustawia uprawnienia grupy zgodnie z GROUP_PERMISSIONS (post_migrate, idempotentne)."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    wanted = []
    for (app_label, model), actions in GROUP_PERMISSIONS.items():
        for action in actions:
            perm = Permission.objects.filter(
                content_type__app_label=app_label, codename=f"{action}_{model}"
            ).first()
            if perm is None:
                # Na świeżej bazie uprawnienia innej aplikacji mogą jeszcze nie istnieć
                continue
            wanted.append(perm)
    group.permissions.set(wanted)


def grant_default_access(user) -> None:
    """Zwykłe konto: dostęp do panelu i grupa „ksiegowosc”. Superuser bez zmian."""
    from django.contrib.auth.models import Group, User

    if user.is_superuser:
        return
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    user.groups.add(group)
    if not user.is_staff:
        # update() zamiast save() — bez ponownego wywołania sygnałów post_save
        User.objects.filter(pk=user.pk).update(is_staff=True)
        user.is_staff = True


def _has_user_field(model) -> bool:
    return any(f.name == "user" and f.is_relation for f in model._meta.fields)


class OwnDataAdminMixin:
    """Izolacja danych dla zwykłych kont: lista, filtry boczne i pola wyboru tylko z własnych
    rekordów; kolumna i filtr „Użytkownik” widoczne tylko dla superusera."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or not _has_user_field(qs.model):
            return qs
        return qs.filter(user=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser and "queryset" not in kwargs:
            related = db_field.related_model
            if db_field.name == "user":
                kwargs["queryset"] = related.objects.filter(pk=request.user.pk)
            elif _has_user_field(related):
                kwargs["queryset"] = related._default_manager.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_list_display(self, request):
        items = super().get_list_display(request)
        if request.user.is_superuser:
            return items
        return [i for i in items if i != "user"]

    def get_list_filter(self, request):
        items = super().get_list_filter(request)
        if request.user.is_superuser:
            return items
        result = []
        for item in items:
            if item == "user":
                continue
            if isinstance(item, str) and self._is_foreign_key(item):
                # Tylko kontrahenci występujący na liście (czyli własni)
                item = (item, admin.RelatedOnlyFieldListFilter)
            result.append(item)
        return result

    def _is_foreign_key(self, name: str) -> bool:
        try:
            field = self.model._meta.get_field(name)
        except Exception:
            return False
        return field.many_to_one
