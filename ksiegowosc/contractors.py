"""Kontrahenci: normalizacja NIP, dopasowanie przy imporcie i scalanie duplikatów."""

from __future__ import annotations

import re

from django.db import transaction
from django.db.models import Count

from .models import Contractor, DutyRate, normalize_tax_id

__all__ = [
    "ContractorMergeError",
    "find_or_create_contractor",
    "merge_contractors",
    "normalize_name",
    "normalize_tax_id",
    "pick_merge_target",
]


class ContractorMergeError(Exception):
    pass


def normalize_name(value: str | None) -> str:
    """Klucz porównania nazw: bez wielkości liter, cudzysłowów i nadmiarowych spacji."""
    if not value:
        return ""
    value = re.sub(r"[\"'„”«»]", "", value)
    return " ".join(value.split()).casefold()


def _match_by_name(queryset, name: str | None) -> Contractor | None:
    key = normalize_name(name)
    if not key:
        return None
    matches = [c for c in queryset if normalize_name(c.name) == key]
    if not matches:
        return None
    # Kontrahent z NIP-em ma pierwszeństwo przed rekordem bez NIP-u
    return sorted(matches, key=lambda c: (not c.tax_id, c.pk))[0]


def find_or_create_contractor(
    user, tax_id: str | None, name: str | None
) -> tuple[Contractor, bool]:
    """Znajduje kontrahenta po NIP-ie (niezależnie od zapisu: myślniki, spacje, prefiks PL)
    albo — gdy NIP-u brak — po nazwie. Rekord bez NIP-u o tej samej nazwie dostaje NIP.

    Zwraca (kontrahent, czy_utworzono).
    """
    nip = normalize_tax_id(tax_id)
    own = Contractor.objects.filter(user=user)

    if nip:
        contractor = own.filter(tax_id=nip).first()
        if contractor:
            if name and contractor.name == contractor.tax_id:
                # Kontrahent powstał wcześniej z samym NIP-em — uzupełnij nazwę
                contractor.name = name
                contractor.save(update_fields=["name"])
            return contractor, False
        contractor = _match_by_name(own.filter(tax_id__isnull=True), name)
        if contractor is None:
            contractor = _match_by_name(own.filter(tax_id=""), name)
        if contractor:
            contractor.tax_id = nip
            contractor.save(update_fields=["tax_id"])
            return contractor, False
        return Contractor.objects.create(user=user, tax_id=nip, name=name or nip), True

    if not normalize_name(name):
        raise ValueError("Brak NIP-u i nazwy kontrahenta.")
    contractor = _match_by_name(own, name)
    if contractor:
        return contractor, False
    return Contractor.objects.create(user=user, tax_id=None, name=name.strip()), True


def pick_merge_target(contractors) -> Contractor:
    """Rekord docelowy scalania: z NIP-em, potem z największą liczbą faktur, potem najstarszy."""
    ids = [c.pk for c in contractors]
    counted = Contractor.objects.filter(pk__in=ids).annotate(
        n=Count("invoice", distinct=True) + Count("purchaseinvoice", distinct=True)
    )
    return sorted(counted, key=lambda c: (not c.tax_id, -c.n, c.pk))[0]


@transaction.atomic
def merge_contractors(target: Contractor, duplicates) -> dict[str, int]:
    """Przepina faktury, zakupy, dyżury i stawki z duplikatów na `target` i usuwa duplikaty.

    Puste pola adresu i NIP celu uzupełnia z duplikatów. Zwraca liczbę przepiętych rekordów
    wg modelu.
    """
    duplicates = [d for d in duplicates if d.pk != target.pk]
    if not duplicates:
        return {}
    if any(d.user_id != target.user_id for d in duplicates):
        raise ContractorMergeError(
            "Można scalać tylko kontrahentów jednego użytkownika."
        )
    nips = {normalize_tax_id(c.tax_id) for c in [target, *duplicates]} - {None}
    if len(nips) > 1:
        raise ContractorMergeError(
            "Zaznaczeni kontrahenci mają różne NIP-y: " + ", ".join(sorted(nips))
        )

    # Stawki dyżurów są unikalne w ramach (kontrahent, obowiązuje od)
    ids = [target.pk, *(d.pk for d in duplicates)]
    clash = (
        DutyRate.objects.filter(contractor_id__in=ids)
        .values("valid_from")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .values_list("valid_from", flat=True)
    )
    if clash:
        dates = ", ".join(d.strftime("%Y-%m-%d") for d in clash)
        raise ContractorMergeError(
            f"Kontrahenci mają stawki dyżurów od tej samej daty ({dates}) — usuń zbędne i spróbuj ponownie."
        )

    moved: dict[str, int] = {}
    for rel in Contractor._meta.related_objects:
        if not rel.one_to_many:
            continue
        n = rel.related_model._base_manager.filter(
            **{f"{rel.field.name}__in": duplicates}
        ).update(**{rel.field.name: target})
        if n:
            moved[rel.related_model._meta.verbose_name_plural] = n

    tax_id = target.tax_id or next((d.tax_id for d in duplicates if d.tax_id), None)
    for field in ("street", "zip_code", "city"):
        if not getattr(target, field):
            value = next(
                (getattr(d, field) for d in duplicates if getattr(d, field)), ""
            )
            setattr(target, field, value)
    for d in duplicates:
        d.delete()
    target.tax_id = tax_id
    target.save()
    return moved
