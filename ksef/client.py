# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksef/client.py

import requests
import pytz
import time
import logging
from datetime import datetime
from ksiegowosc.models import CompanyInfo
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from base64 import b64encode

logger = logging.getLogger(__name__)


class KsefClient:
    def __init__(self, user):
        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception(
                "Użytkownik nie ma przypisanych danych firmy (CompanyInfo)."
            )

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF w ustawieniach firmy.")

        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        self.session_token = None

    def _get_public_key(self):
        """Pobiera klucz publiczny KSeF do szyfrowania."""
        try:
            # Zakładamy, że klucz jest w projekcie - tak jak masz to zrobione
            with open("ksef-pubkey/publicKey.pem", "rb") as f:
                public_key = serialization.load_pem_public_key(f.read())
            return public_key
        except FileNotFoundError:
            # W przyszłości można dodać pobieranie klucza z API
            # GET /api/v2/security/public-key-certificates
            raise Exception(
                "Nie znaleziono pliku klucza publicznego KSeF (ksef-pubkey/publicKey.pem)."
            )

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: str) -> str:
        """Szyfruje token KSeF zgodnie z wymaganiami API 2.0."""
        public_key = self._get_public_key()
        token_string = f"{ksef_token}|{timestamp}"

        encrypted_token_bytes = public_key.encrypt(
            token_string.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return b64encode(encrypted_token_bytes).decode("utf-8")

    def _initialize_session(self):
        """Nowy, wieloetapowy proces uwierzytelniania w API v2.0."""
        if self.session_token:
            return

        headers = {"Content-Type": "application/json"}
        context = {
            "contextIdentifier": {"type": "NIP", "identifier": self.company_info.tax_id}
        }

        try:
            # Krok 1: Pobierz challenge
            challenge_url = f"{self.base_url}/auth/challenge"
            logger.info(f"Pobieranie challenge z API v2.0: {challenge_url}")
            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]
            logger.info("Otrzymano challenge z KSeF API v2.0.")

            # Krok 2: Uwierzytelnienie tokenem KSeF
            auth_url = f"{self.base_url}/auth/ksef-token"
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp
            )

            payload = {
                "challenge": challenge,
                "contextIdentifier": {"type": "NIP", "value": self.company_info.tax_id},
                "encryptedToken": encrypted_token,
            }

            logger.info("Wysyłanie żądania uwierzytelnienia do API v2.0")
            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            auth_response.raise_for_status()
            auth_data = auth_response.json()

            # W API v2.0 InitToken zwraca bezpośrednio token sesji
            self.session_token = auth_data["sessionToken"]["token"]
            logger.info("Pomyślnie zainicjowano sesję z KSeF API v2.0.")

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if e.response is not None:
                try:
                    error_details = e.response.json()
                except ValueError:
                    error_details = e.response.text
            logger.error(f"Błąd inicjalizacji sesji KSeF API v2.0: {error_details}")
            raise Exception(f"Błąd inicjalizacji sesji KSeF API v2.0: {error_details}")

    def send_invoice(self, invoice_xml: str):
        self._initialize_session()

        url = f"{self.base_url}/online/v2/Invoice/Send"
        headers = {
            "Content-Type": "application/octet-stream; charset=utf-8",
            "SessionToken": self.session_token,
        }

        try:
            logger.info(f"Wysyłanie faktury do API v2.0: {url}")
            response = requests.put(
                url, data=invoice_xml.encode("utf-8"), headers=headers, timeout=15
            )
            response.raise_for_status()
            logger.info("Faktura wysłana pomyślnie do API v2.0.")
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if e.response is not None:
                try:
                    error_details = e.response.json()
                except ValueError:
                    error_details = e.response.text
            logger.error(
                f"Błąd podczas wysyłki faktury do KSeF API v2.0: {error_details}"
            )
            raise Exception(
                f"Błąd podczas wysyłki faktury do KSeF API v2.0: {error_details}"
            )
