"""Import faktur zakupowych (otrzymanych) z KSeF przy użyciu SDK ksef2.

Używa metadanych zwracanych przez KSeF (seller/net/vat/gross) — nie trzeba
parsować XML samodzielnie. Surowe XML pobieramy i zapisujemy jako
document_file na PurchaseInvoice, do wglądu/archiwum.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.core.files.base import ContentFile

from ksef2 import Client, Environment
from ksef2.domain.models.invoices import InvoicesFilter

from ksiegowosc.models import CompanyInfo, Contractor, Invoice, InvoiceItem, PurchaseInvoice

ENVIRONMENT_MAP = {
    "test": Environment.TEST,
    "demo": Environment.DEMO,
    "production": Environment.PRODUCTION,
}

# Faktury z KSeF nie niosą informacji o kategorii kosztu w Twojej appce —
# każda zaimportowana faktura ląduje z tą kategorią i wymaga ręcznego
# doprecyzowania (widać to po `notes`, które oznaczamy poniżej).
DEFAULT_IMPORT_CATEGORY = "other" if any(
    c[0] == "other" for c in PurchaseInvoice._meta.get_field("category").choices
) else PurchaseInvoice._meta.get_field("category").choices[0][0]


@dataclass
class KSeFImportResult:
    created: int = 0
    skipped_existing: int = 0
    errors: list[str] = field(default_factory=list)


def _get_or_create_supplier(user, nip: str, name: str | None) -> Contractor:
    contractor, _ = Contractor.objects.get_or_create(
        user=user,
        tax_id=nip,
        defaults={"name": name or nip},
    )
    if name and contractor.name != name and contractor.name == contractor.tax_id:
        # Uzupełnij nazwę, jeśli wcześniej kontrahent powstał tylko z NIP-em.
        contractor.name = name
        contractor.save(update_fields=["name"])
    return contractor


@dataclass
class KSeFSalesImportResult:
    created: int = 0
    synced: int = 0
    errors: list[str] = field(default_factory=list)


def _get_or_create_buyer(user, nip: str | None, name: str | None) -> Contractor | None:
    if not nip:
        return None
    contractor, _ = Contractor.objects.get_or_create(
        user=user,
        tax_id=nip,
        defaults={"name": name or nip},
    )
    if name and contractor.name != name and contractor.name == contractor.tax_id:
        contractor.name = name
        contractor.save(update_fields=["name"])
    return contractor


def import_sales_invoices_from_ksef(
    company_info: CompanyInfo, *, days: int = 30
) -> KSeFSalesImportResult:
    """Importuje/synchronizuje faktury sprzedażowe (jako wystawca) z KSeF.

    Dla faktur już istniejących w bazie (po `invoice_number`) tylko uzupełnia
    status/numer KSeF — nie rusza kwot ani pozycji, bo te są autorytatywne
    lokalnie. Dla faktur, których nie ma w bazie (np. wystawionych poza tą
    appką), tworzy nowy rekord z jedną pozycją zbiorczą — do doprecyzowania
    ręcznie, jeśli potrzeba rozbicia na pozycje.
    """
    result = KSeFSalesImportResult()

    if not company_info.ksef_token:
        result.errors.append("Brak tokenu KSeF w danych firmy (CompanyInfo.ksef_token).")
        return result

    environment = ENVIRONMENT_MAP.get(company_info.ksef_environment or "test", Environment.TEST)
    user = company_info.user

    client = Client(environment)
    auth = client.authentication.with_token(
        ksef_token=company_info.ksef_token,
        nip=company_info.tax_id,
    )

    now = datetime.now(tz=dt_timezone.utc)
    filters = InvoicesFilter(
        role="seller",
        date_type="issue_date",
        date_from=now - timedelta(days=days),
        date_to=now,
        amount_type="brutto",
    )

    try:
        pages = auth.invoices.query_metadata_pages(filters=filters)
        for page in pages:
            for meta in page.invoices:
                try:
                    existing = Invoice.objects.filter(
                        user=user, invoice_number=meta.invoice_number
                    ).first()

                    if existing:
                        existing.ksef_number = meta.ksef_number
                        existing.ksef_status = "success"
                        existing.ksef_processing_description = (
                            "Zsynchronizowano z KSeF (metadane)."
                        )
                        existing.save(
                            update_fields=[
                                "ksef_number",
                                "ksef_status",
                                "ksef_processing_description",
                            ]
                        )
                        result.synced += 1
                        continue

                    buyer_nip = (
                        meta.buyer.identifier.value
                        if meta.buyer and meta.buyer.identifier
                        else None
                    )
                    buyer = _get_or_create_buyer(user, buyer_nip, meta.buyer.name if meta.buyer else None)
                    if buyer is None:
                        result.errors.append(
                            f"Faktura {meta.invoice_number}: brak NIP nabywcy w metadanych — pomiń lub dodaj kontrahenta ręcznie."
                        )
                        continue

                    invoice = Invoice.objects.create(
                        user=user,
                        invoice_number=meta.invoice_number,
                        issue_date=meta.issue_date,
                        sale_date=meta.issue_date,
                        contractor=buyer,
                        ksef_number=meta.ksef_number,
                        ksef_status="success",
                        ksef_processing_description="Zaimportowano z KSeF (nie było w bazie).",
                        notes=(
                            "Zaimportowano automatycznie z KSeF — pozycja zbiorcza, "
                            "sprawdź czy wymaga rozbicia na szczegółowe pozycje."
                        ),
                    )
                    InvoiceItem.objects.create(
                        user=user,
                        invoice=invoice,
                        name="Import z KSeF",
                        quantity=1,
                        unit="usł.",
                        unit_price=Decimal(str(meta.gross_amount)),
                        total_price=Decimal(str(meta.gross_amount)),
                    )
                    invoice.update_total_amount()
                    result.created += 1
                except Exception as row_error:  # noqa: BLE001
                    result.errors.append(
                        f"Faktura {getattr(meta, 'invoice_number', '?')}: {row_error}"
                    )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Błąd zapytania do KSeF: {exc}")

    return result


def import_purchase_invoices_from_ksef(
    company_info: CompanyInfo, *, days: int = 30
) -> KSeFImportResult:
    """Importuje faktury zakupowe (jako nabywca) z KSeF za ostatnie `days` dni.

    Wymaga wypełnionego `company_info.ksef_token` i `company_info.tax_id`.
    Tworzy `PurchaseInvoice` dla każdej faktury, której numer jeszcze nie ma
    w bazie dla danego dostawcy (po `invoice_number` + `supplier`).
    """
    result = KSeFImportResult()

    if not company_info.ksef_token:
        result.errors.append("Brak tokenu KSeF w danych firmy (CompanyInfo.ksef_token).")
        return result

    environment = ENVIRONMENT_MAP.get(company_info.ksef_environment or "test", Environment.TEST)
    user = company_info.user

    client = Client(environment)
    auth = client.authentication.with_token(
        ksef_token=company_info.ksef_token,
        nip=company_info.tax_id,
    )

    now = datetime.now(tz=dt_timezone.utc)
    filters = InvoicesFilter(
        role="buyer",
        date_type="issue_date",
        date_from=now - timedelta(days=days),
        date_to=now,
        amount_type="brutto",
    )

    try:
        pages = auth.invoices.query_metadata_pages(filters=filters)
        for page in pages:
            for meta in page.invoices:
                try:
                    exists = PurchaseInvoice.objects.filter(
                        user=user,
                        invoice_number=meta.invoice_number,
                        supplier__tax_id=meta.seller.nip,
                    ).exists()
                    if exists:
                        result.skipped_existing += 1
                        continue

                    supplier = _get_or_create_supplier(user, meta.seller.nip, meta.seller.name)

                    purchase_invoice = PurchaseInvoice(
                        user=user,
                        invoice_number=meta.invoice_number,
                        supplier=supplier,
                        issue_date=meta.issue_date,
                        receipt_date=now.date(),
                        service_date=meta.issue_date,
                        net_amount=Decimal(str(meta.net_amount)),
                        vat_amount=Decimal(str(meta.vat_amount)),
                        total_amount=Decimal(str(meta.gross_amount)),
                        category=DEFAULT_IMPORT_CATEGORY,
                        is_deductible=False,  # do potwierdzenia ręcznie
                        vat_deductible=False,  # do potwierdzenia ręcznie
                        notes=(
                            f"Zaimportowano automatycznie z KSeF (numer: {meta.ksef_number}). "
                            "Sprawdź kategorię i odliczalność VAT/kosztu przed rozliczeniem."
                        ),
                    )

                    try:
                        xml_bytes = auth.invoices.download_invoice(ksef_number=meta.ksef_number)
                        purchase_invoice.document_file.save(
                            f"ksef_{meta.ksef_number}.xml",
                            ContentFile(xml_bytes),
                            save=False,
                        )
                    except Exception as download_error:  # noqa: BLE001
                        result.errors.append(
                            f"Faktura {meta.invoice_number}: metadane zapisane, "
                            f"ale nie udało się pobrać XML ({download_error})."
                        )

                    purchase_invoice.save()
                    result.created += 1
                except Exception as row_error:  # noqa: BLE001
                    result.errors.append(
                        f"Faktura {getattr(meta, 'invoice_number', '?')}: {row_error}"
                    )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Błąd zapytania do KSeF: {exc}")

    return result
