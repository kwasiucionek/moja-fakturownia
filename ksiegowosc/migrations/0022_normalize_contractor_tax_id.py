"""Normalizacja NIP-ów kontrahentów i scalenie duplikatów.

Duplikaty powstawały przy imporcie: ten sam NIP zapisany z myślnikami i bez, a faktury z JPK
bez NIP-u tworzyły osobnego kontrahenta po nazwie. Scalane są:
- kontrahenci z tym samym NIP-em po normalizacji,
- kontrahent bez NIP-u, którego nazwa pasuje do dokładnie jednego kontrahenta z NIP-em.
Grupy, w których kolidują stawki dyżurów (ta sama data „obowiązuje od”), zostają bez zmian —
można je scalić akcją w panelu po usunięciu zbędnej stawki.
"""

import re
from collections import Counter, defaultdict

from django.db import migrations


def _nip(value):
    # Kopia ksiegowosc.models.normalize_tax_id — migracja nie zależy od bieżącego kodu
    if value is None:
        return None
    value = re.sub(r"[\s\-.]", "", str(value)).upper()
    if re.fullmatch(r"PL\d{10}", value):
        value = value[2:]
    return value or None


def _name(value):
    value = re.sub(r"[\"'„”«»]", "", value or "")
    return " ".join(value.split()).casefold()


def merge_duplicates(apps, schema_editor):
    Contractor = apps.get_model("ksiegowosc", "Contractor")
    Invoice = apps.get_model("ksiegowosc", "Invoice")
    PurchaseInvoice = apps.get_model("ksiegowosc", "PurchaseInvoice")
    DutyRate = apps.get_model("ksiegowosc", "DutyRate")
    DutyShift = apps.get_model("ksiegowosc", "DutyShift")
    relations = [
        (Invoice, "contractor"),
        (PurchaseInvoice, "supplier"),
        (DutyRate, "contractor"),
        (DutyShift, "contractor"),
    ]

    def usage(c):
        return (
            Invoice.objects.filter(contractor=c).count()
            + PurchaseInvoice.objects.filter(supplier=c).count()
        )

    def merge(group):
        group = sorted(group, key=lambda c: (not _nip(c.tax_id), -usage(c), c.pk))
        target, duplicates = group[0], group[1:]
        dates = Counter(
            DutyRate.objects.filter(contractor__in=group).values_list(
                "valid_from", flat=True
            )
        )
        if any(n > 1 for n in dates.values()):
            return None  # kolizja stawek dyżurów — do ręcznego scalenia
        for model, field in relations:
            model.objects.filter(**{f"{field}__in": duplicates}).update(
                **{field: target}
            )
        tax_id = _nip(target.tax_id) or next(
            (_nip(d.tax_id) for d in duplicates if _nip(d.tax_id)), None
        )
        for attr in ("street", "zip_code", "city"):
            if not getattr(target, attr):
                setattr(
                    target,
                    attr,
                    next(
                        (getattr(d, attr) for d in duplicates if getattr(d, attr)), ""
                    ),
                )
        Contractor.objects.filter(pk__in=[d.pk for d in duplicates]).delete()
        target.tax_id = tax_id
        target.save()
        return target

    for user_id in Contractor.objects.values_list("user_id", flat=True).distinct():
        contractors = list(Contractor.objects.filter(user_id=user_id))
        skipped = set()

        # 1. Ten sam NIP w różnym zapisie
        by_nip = defaultdict(list)
        for c in contractors:
            if _nip(c.tax_id):
                by_nip[_nip(c.tax_id)].append(c)
        for nip, group in by_nip.items():
            if len(group) > 1 and merge(group) is None:
                skipped.add(nip)

        # 2. Normalizacja zapisu pozostałych NIP-ów (poza grupami z kolizją)
        for c in Contractor.objects.filter(user_id=user_id):
            nip = _nip(c.tax_id)
            if nip not in skipped and c.tax_id != nip:
                c.tax_id = nip
                c.save(update_fields=["tax_id"])

        # 3. Kontrahent bez NIP-u o nazwie jednoznacznie pasującej do kontrahenta z NIP-em
        current = list(Contractor.objects.filter(user_id=user_id))
        with_nip = defaultdict(list)
        for c in current:
            if c.tax_id:
                with_nip[_name(c.name)].append(c)
        for c in current:
            if not c.tax_id and len(with_nip.get(_name(c.name), [])) == 1:
                merge([with_nip[_name(c.name)][0], c])


class Migration(migrations.Migration):
    dependencies = [
        ("ksiegowosc", "0021_business_suspension"),
    ]

    operations = [
        migrations.RunPython(merge_duplicates, migrations.RunPython.noop),
    ]
