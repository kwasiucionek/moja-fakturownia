# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksef/client.py

import requests
import pytz
from datetime import datetime
from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from ksiegowosc.models import CompanyInfo


class KsefClient:
    def __init__(self, user):
        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception("User has no companyinfo.")

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF w ustawieniach firmy.")

        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api"

        self.session_token = None

    def _get_public_key(self):
        # Klucz publiczny jest potrzebny do podpisania challenge'u
        # W tej wersji zakładamy, że jest on w zdefiniowanej ścieżce
        # W przyszłości można go pobierać dynamicznie
        try:
            with open("ksef-pubkey/publicKey.pem", "rb") as f:
                return serialization.load_pem_public_key(f.read())
        except FileNotFoundError:
            raise Exception(
                "Nie znaleziono pliku klucza publicznego KSeF (publicKey.pem)."
            )

    def _initialize_session(self):
        if self.session_token:
            return

        challenge_url = f"{self.base_url}/online/Session/Challenge"
        warsaw_tz = pytz.timezone("Europe/Warsaw")
        timestamp = datetime.now(warsaw_tz).isoformat(timespec="milliseconds")

        headers = {"Content-Type": "application/json"}
        context = {
            "contextIdentifier": {"type": "NIP", "identifier": self.company_info.tax_id}
        }

        try:
            response = requests.post(challenge_url, json=context, headers=headers)
            response.raise_for_status()
            challenge_data = response.json()
            challenge = challenge_data["challenge"]

            # Autoryzacja tokenem
            auth_url = f"{self.base_url}/online/Session/InitSessionToken"
            payload = {
                "initSessionTokenRequest": {
                    "challenge": challenge,
                    "identifier": self.company_info.tax_id,
                    "token": self.company_info.ksef_token,
                    "type": "NIP",
                }
            }

            auth_response = requests.post(auth_url, json=payload)
            auth_response.raise_for_status()
            self.session_token = auth_response.json()["sessionToken"]["token"]

        except requests.exceptions.RequestException as e:
            error_details = e.response.json() if e.response else str(e)
            raise Exception(f"Błąd inicjalizacji sesji KSeF: {error_details}")

    def send_invoice(self, invoice_xml: str):
        self._initialize_session()

        url = f"{self.base_url}/online/Invoice/Send"
        headers = {
            "Content-Type": "application/octet-stream",
            "SessionToken": self.session_token,
        }

        try:
            response = requests.put(
                url, data=invoice_xml.encode("utf-8"), headers=headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_details = e.response.json() if e.response else str(e)
            raise Exception(f"Błąd podczas wysyłki faktury do KSeF: {error_details}")
