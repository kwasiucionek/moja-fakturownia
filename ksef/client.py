# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksef/client.py

import requests
import pytz
from datetime import datetime
from ksiegowosc.models import CompanyInfo
import logging

# Konfiguracja loggera do debugowania
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
            self.base_url = "https://ksef-test.mf.gov.pl/api"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api"

        self.session_token = None

    def _initialize_session(self):
        if self.session_token:
            return

        # === KOD ZAKTUALIZOWANY DLA API v2.0 ===
        challenge_url = f"{self.base_url}/online/v2/Session/AuthorisationChallenge"

        headers = {"Content-Type": "application/json"}
        context = {
            "contextIdentifier": {"type": "NIP", "identifier": self.company_info.tax_id}
        }

        try:
            logger.info(
                f"Wysyłanie prośby o challenge do nowego API v2.0: {challenge_url}"
            )
            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]  # Pobieramy timestamp z odpowiedzi
            logger.info("Otrzymano challenge z KSeF API v2.0.")

            auth_url = f"{self.base_url}/online/v2/Session/InitToken"

            payload = {
                "authorisationChallengeRequest": {
                    "contextIdentifier": {
                        "type": "NIP",
                        "identifier": self.company_info.tax_id,
                    }
                },
                "challenge": challenge,
                "token": self.company_info.ksef_token,
            }

            logger.info(f"Wysyłanie prośby o token sesji do API v2.0: {auth_url}")
            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            auth_response.raise_for_status()
            self.session_token = auth_response.json()["sessionToken"]["token"]
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
