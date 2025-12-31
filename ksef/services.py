# ksef/services.py

import logging

from django.utils import timezone
from ksiegowosc.models import Invoice

from .client import KsefClient
from .xml_generator import generate_invoice_xml

logger = logging.getLogger(__name__)


def send_invoice_to_ksef(invoice_id: int):
    """
    Orkiestrator procesu wysyłki faktury do KSeF:
    1. Pobiera fakturę z bazy.
    2. Generuje XML.
    3. Inicjuje sesję i wysyła do KSeF.
    4. Aktualizuje statusy w bazie danych.
    """
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return {"success": False, "message": "Faktura nie istnieje."}

    # Sprawdzenie czy już nie wysłano
    if invoice.ksef_status == "Success" and invoice.ksef_reference_number:
        return {"success": False, "message": "Ta faktura została już wysłana do KSeF."}

    try:
        # 1. Inicjalizacja klienta (korzysta z tokena z CompanyInfo powiązanego z userem faktury)
        client = KsefClient(user=invoice.user)

        # 2. Generowanie XML
        xml_content = generate_invoice_xml(invoice)

        # Opcjonalnie: Tutaj można dodać walidację XSD przed wysyłką

        # 3. Wysyłka (logika jest w client.py)
        result = client.send_invoice(xml_content)

        # 4. Aktualizacja modelu faktury po sukcesie
        invoice.ksef_reference_number = result.get("invoice_reference")
        invoice.ksef_session_id = result.get("session_reference")
        invoice.ksef_status = "Success"  # Możesz użyć statusu z API (np. 100/200)
        invoice.ksef_sent_at = timezone.now()
        invoice.ksef_processing_description = "Wysłano pomyślnie. Czekaj na UPO."
        invoice.save()

        logger.info(
            f"Faktura {invoice.invoice_number} wysłana do KSeF. Ref: {invoice.ksef_reference_number}"
        )

        return {
            "success": True,
            "message": f"Wysłano pomyślnie. Nr Ref: {invoice.ksef_reference_number}",
        }

    except Exception as e:
        # Obsługa błędów - zapisz w modelu, że coś poszło nie tak
        error_message = str(e)
        logger.error(f"Błąd wysyłki do KSeF dla faktury {invoice.id}: {error_message}")

        invoice.ksef_status = "Error"
        invoice.ksef_processing_description = error_message[:500]  # Utnij jak za długie
        invoice.save()

        return {"success": False, "message": f"Błąd: {error_message}"}
