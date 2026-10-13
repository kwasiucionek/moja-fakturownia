# ksef/services.py
# Integracja z KSeF API 2.0 przez bibliotekę ksef2

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ksef2 import Client, Environment, FormSchema

from ksiegowosc.models import CompanyInfo, Invoice
from .ksef2_import import ENVIRONMENT_MAP
from .xml_generator import generate_invoice_xml

logger = logging.getLogger(__name__)


class KsefService:
    """
    Serwis do obsługi KSeF z wykorzystaniem biblioteki ksef2.
    
    Przykład użycia:
        service = KsefService(user)
        result = service.send_invoice(invoice)
    """
    
    def __init__(self, user):
        self.user = user
        self.company_info = self._get_company_info()
        self.client = self._create_client()
    
    def _get_company_info(self) -> CompanyInfo:
        """Pobiera dane firmy użytkownika."""
        try:
            return CompanyInfo.objects.get(user=self.user)
        except CompanyInfo.DoesNotExist:
            raise KsefServiceError("Użytkownik nie posiada uzupełnionych danych firmy.")
    
    def _create_client(self) -> Client:
        """Tworzy klienta ksef2 dla odpowiedniego środowiska."""
        # Ta sama mapa co przy imporcie — klucze zgodne z choices CompanyInfo.ksef_environment
        # (ksef2 ma Environment.PRODUCTION, nie PROD). Nieznana wartość -> TEST, nigdy produkcja.
        env = ENVIRONMENT_MAP.get(self.company_info.ksef_environment or "test", Environment.TEST)
        return Client(env)
    
    def _normalize_nip(self, nip: str) -> str:
        """Normalizuje NIP do 10 cyfr."""
        return nip.replace("-", "").replace(" ", "").strip()
    
    def _authenticate(self):
        """
        Uwierzytelnia w KSeF tokenem.
        Zwraca AuthenticatedClient do użycia w sesji.
        """
        if not self.company_info.ksef_token:
            raise KsefServiceError("Brak tokena KSeF. Wygeneruj go w Aplikacji Podatnika.")
        
        nip = self._normalize_nip(self.company_info.tax_id)
        
        logger.info(f"Uwierzytelnianie w KSeF dla NIP: {nip}")
        
        try:
            auth = self.client.authentication.with_token(
                ksef_token=self.company_info.ksef_token,
                nip=nip,
            )
            logger.info("✓ Pomyślnie uwierzytelniono w KSeF")
            return auth
        
        except Exception as e:
            logger.error(f"❌ Błąd uwierzytelniania KSeF: {e}")
            raise KsefServiceError(f"Błąd uwierzytelniania: {e}")
    
    def send_invoice(self, invoice: Invoice) -> dict:
        """
        Wysyła fakturę do KSeF.
        
        Args:
            invoice: Obiekt faktury do wysłania
            
        Returns:
            dict z reference_number i statusem
        """
        logger.info(f"Wysyłanie faktury {invoice.invoice_number} do KSeF...")
        
        # 1. Wygeneruj XML faktury
        try:
            invoice_xml = generate_invoice_xml(invoice, self.company_info)
            xml_bytes = invoice_xml.encode('utf-8')
            logger.info(f"✓ Wygenerowano XML ({len(xml_bytes)} bajtów)")
        except Exception as e:
            logger.error(f"❌ Błąd generowania XML: {e}")
            raise KsefServiceError(f"Błąd generowania XML faktury: {e}")
        
        # 2. Uwierzytelnij
        auth = self._authenticate()
        
        # 3. Otwórz sesję i wyślij fakturę
        try:
            with auth.online_session(form_code=FormSchema.FA3) as session:
                logger.info(f"✓ Otwarto sesję KSeF: {session.reference_number}")
                
                # Wyślij fakturę
                result = session.send_invoice(invoice_xml=xml_bytes)
                
                logger.info(f"✓ Faktura wysłana, ref: {result.reference_number}")
                
                # Aktualizuj fakturę w bazie
                self._update_invoice_status(
                    invoice, 
                    ksef_reference=result.reference_number,
                    session_reference=session.reference_number
                )
                
                return {
                    'success': True,
                    'invoice_reference': result.reference_number,
                    'session_reference': session.reference_number,
                }
        
        except Exception as e:
            logger.error(f"❌ Błąd KSeF: {e}")
            self._mark_invoice_error(invoice, str(e))
            raise KsefServiceError(f"Błąd KSeF: {e}")
    
    @transaction.atomic
    def _update_invoice_status(
        self, 
        invoice: Invoice, 
        ksef_reference: str,
        session_reference: str
    ):
        """Aktualizuje status faktury po wysłaniu do KSeF."""
        invoice.ksef_reference_number = ksef_reference
        invoice.ksef_session_id = session_reference
        invoice.ksef_sent_at = timezone.now()
        invoice.ksef_status = 'success'
        invoice.ksef_processing_description = 'Faktura wysłana pomyślnie'
        invoice.save(update_fields=[
            'ksef_reference_number', 
            'ksef_session_id',
            'ksef_sent_at', 
            'ksef_status',
            'ksef_processing_description'
        ])
        logger.info(f"✓ Zaktualizowano status faktury {invoice.invoice_number}")
    
    @transaction.atomic
    def _mark_invoice_error(self, invoice: Invoice, error_message: str):
        """Oznacza fakturę jako błąd."""
        invoice.ksef_status = 'error'
        invoice.ksef_processing_description = error_message[:500]
        invoice.save(update_fields=['ksef_status', 'ksef_processing_description'])
    
    def send_multiple_invoices(self, invoices: list[Invoice]) -> list[dict]:
        """
        Wysyła wiele faktur w jednej sesji KSeF.
        Bardziej efektywne niż wysyłanie pojedynczo.
        
        Args:
            invoices: Lista faktur do wysłania
            
        Returns:
            Lista wyników dla każdej faktury
        """
        if not invoices:
            return []
        
        logger.info(f"Wysyłanie {len(invoices)} faktur do KSeF...")
        
        auth = self._authenticate()
        results = []
        
        try:
            with auth.online_session(form_code=FormSchema.FA3) as session:
                logger.info(f"✓ Otwarto sesję: {session.reference_number}")
                
                for invoice in invoices:
                    try:
                        # Generuj XML
                        invoice_xml = generate_invoice_xml(invoice, self.company_info)
                        xml_bytes = invoice_xml.encode('utf-8')
                        
                        # Wyślij
                        result = session.send_invoice(invoice_xml=xml_bytes)
                        
                        # Aktualizuj status
                        self._update_invoice_status(
                            invoice,
                            ksef_reference=result.reference_number,
                            session_reference=session.reference_number
                        )
                        
                        results.append({
                            'invoice_number': invoice.invoice_number,
                            'success': True,
                            'reference': result.reference_number,
                        })
                        logger.info(f"✓ Wysłano {invoice.invoice_number}")
                        
                    except Exception as e:
                        logger.error(f"❌ Błąd dla {invoice.invoice_number}: {e}")
                        self._mark_invoice_error(invoice, str(e))
                        results.append({
                            'invoice_number': invoice.invoice_number,
                            'success': False,
                            'error': str(e),
                        })
                
                return results
        
        except Exception as e:
            logger.error(f"❌ Błąd sesji: {e}")
            raise KsefServiceError(f"Błąd sesji KSeF: {e}")


class KsefServiceError(Exception):
    """Wyjątek dla błędów serwisu KSeF."""
    pass


# === Funkcje pomocnicze dla widoków Django ===

def send_invoice_to_ksef(user, invoice: Invoice) -> dict:
    """
    Funkcja pomocnicza do wysyłania pojedynczej faktury.
    
    Użycie w widoku:
        from ksef.services import send_invoice_to_ksef
        
        result = send_invoice_to_ksef(request.user, invoice)
    """
    service = KsefService(user)
    return service.send_invoice(invoice)


def send_invoices_batch(user, invoices: list[Invoice]) -> list[dict]:
    """
    Funkcja pomocnicza do wysyłania wielu faktur.
    
    Użycie w widoku:
        from ksef.services import send_invoices_batch
        
        results = send_invoices_batch(request.user, invoices)
    """
    service = KsefService(user)
    return service.send_multiple_invoices(invoices)
