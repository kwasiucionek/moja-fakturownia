# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksef/client.py

import base64
import json
import logging
import os
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone

# Usunięto import CompanyInfo z góry pliku, aby uniknąć cyklicznego importu

logger = logging.getLogger(__name__)

class KsefClient:
    """
    Klient do komunikacji z API KSeF (Krajowy System e-Faktur).
    """

    def __init__(self, user):
        self.user = user
        self.session_token = None
        self.context_identifier = None

        # Import lokalny wewnątrz __init__ lub metod, aby uniknąć ModuleNotFoundError
        from ksiegowosc.models import CompanyInfo

        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise ValueError(f"Użytkownik {user} nie posiada skonfigurowanych danych firmy (CompanyInfo).")

        if not self.company_info.ksef_token:
            raise ValueError("Brak tokenu KSeF w profilu firmy.")

        self.base_url = self._get_base_url()

    def _get_base_url(self):
        """Zwraca adres URL API w zależności od środowiska."""
        if self.company_info.ksef_environment == 'prod':
            return "https://ksef.mf.gov.pl/api/online/"
        return "https://ksef-test.mf.gov.pl/api/online/"

    def _get_headers(self, include_token=True):
        """Generuje nagłówki dla zapytań HTTP."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if include_token and self.session_token:
            headers["SessionToken"] = self.session_token
        return headers

    def authenticate(self):
        """
        Inicjalizuje sesję w KSeF przy użyciu tokenu.
        W uproszczonej wersji testowej symulujemy lub przesyłamy token bezpośrednio.
        """
        # Logika autoryzacji (InitSessionToken)
        # Na potrzeby demo przyjmujemy, że token z CompanyInfo jest naszym kluczem
        self.session_token = self.company_info.ksef_token
        return True

    def send_invoice(self, xml_content):
        """
        Wysyła fakturę XML do KSeF.
        """
        if not self.session_token:
            self.authenticate()

        url = f"{self.base_url}Invoice/Send"

        # KSeF wymaga często skrótu dokumentu i specyficznej struktury
        # Tu następuje uproszczona logika wysyłki
        payload = {
            "invoiceHash": {
                "hashSHA": {
                    "algorithm": "SHA-256",
                    "encoding": "Base64",
                    "value": self._calculate_hash(xml_content)
                },
                "fileSize": len(xml_content)
            },
            "invoicePayload": {
                "type": "plain",
                "invoiceBody": base64.b64encode(xml_content.encode('utf-8')).decode('utf-8')
            }
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd wysyłki do KSeF: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Odpowiedź błędu: {e.response.text}")
                raise Exception(f"KSeF Error: {e.response.text}")
            raise e

    def _calculate_hash(self, content):
        """Oblicza hash SHA-256 dla zawartości."""
        import hashlib
        return hashlib.sha256(content.encode('utf-8')).digest().hex()

    def get_status(self, session_reference):
        """Sprawdza status przetwarzania sesji/faktury."""
        url = f"{self.base_url}Common/Status/{session_reference}"

        try:
            response = requests.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Błąd sprawdzania statusu KSeF: {e}")
            return {"error": str(e)}
