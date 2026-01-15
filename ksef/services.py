# ksef/services.py

import logging

import requests
from django.utils import timezone

from .client import KsefClient
from .xml_generator import generate_invoice_xml

logger = logging.getLogger(__name__)


def send_invoice_to_ksef(invoice_id: int):
    """
    Orkiestrator procesu wysyłki faktury do KSeF z obsługą szczegółowych błędów API.
    """
    from ksiegowosc.models import Invoice

    try:
        invoice = Invoice.objects.get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return {"success": False, "message": "Faktura nie istnieje."}

    # Sprawdzenie czy już nie wysłano (zgodnie z wyborem statusu w modelu)
    if invoice.ksef_status == "success" and invoice.ksef_number:
        return {"success": False, "message": "Ta faktura została już wysłana do KSeF."}

    try:
        client = KsefClient(user=invoice.user)
        xml_content = generate_invoice_xml(invoice)
        result = client.send_invoice(xml_content)

        invoice.ksef_reference_number = result.get("invoice_reference")
        invoice.ksef_session_id = result.get("session_reference")
        invoice.ksef_status = "success"
        invoice.ksef_sent_at = timezone.now()
        invoice.ksef_processing_description = (
            "Wysłano pomyślnie. Dokument przyjęty do przetwarzania."
        )
        invoice.save()

        return {
            "success": True,
            "message": f"Wysłano pomyślnie. Nr Ref: {invoice.ksef_reference_number}",
        }

    except requests.exceptions.HTTPError as e:
        # Próba wyciągnięcia szczegółów błędu z odpowiedzi API KSeF
        try:
            error_data = e.response.json()
            # Wyciągamy opis z pól 'exception' i 'message' zwracanych przez KSeF
            details = (
                error_data.get("exception", {})
                .get("exceptionDetailList", [{}])[0]
                .get("description", "")
            )
            error_message = (
                f"Błąd API ({e.response.status_code}): {details or e.response.text}"
            )
        except:
            error_message = f"Błąd HTTP {e.response.status_code}: {str(e)}"

        invoice.ksef_status = "error"
        invoice.ksef_processing_description = error_message[:500]
        invoice.save()
        return {"success": False, "message": error_message}

    except Exception as e:
        error_message = str(e)
        logger.error(f"Błąd systemowy KSeF: {error_message}")
        invoice.ksef_status = "error"
        invoice.ksef_processing_description = error_message[:500]
        invoice.save()
        return {"success": False, "message": error_message}
