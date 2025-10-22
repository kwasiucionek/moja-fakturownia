# kwasiucionek/moja-fakturownia/moja-fakturownia-c860f8aa353586b9765a97279fa06703d6f956c5/ksef/client.py

import requests
from django.conf import settings

# === OSTATECZNA POPRAWKA IMPORTU ===
# Importujemy KSEFService oraz obiekty środowisk z właściwego modułu 'online'
from ksef_utils.online import KSEFService
from ksef_utils.online.environments import test_env, prod_env
from ksiegowosc.models import CompanyInfo


class KsefClient:
    def __init__(self, user):
        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception("User has no companyinfo.")

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF w ustawieniach firmy.")

        # === OSTATECZNY POPRAWIONY BLOK KODU ===
        # Wybieramy odpowiedni obiekt środowiska na podstawie ustawień w modelu
        env_str = self.company_info.ksef_environment
        server_obj = test_env if env_str == "test" else prod_env

        # Przekazujemy ten obiekt do KSEFService
        self.service = KSEFService(server_obj)

        self.session = None

    def _initialize_session(self):
        if not self.session:
            try:
                self.session = self.service.auth_by_token(
                    self.company_info.tax_id, self.company_info.ksef_token
                )
            except Exception as e:
                raise Exception(f"Błąd inicjalizacji sesji KSeF: {e}")

    def send_invoice(self, invoice_xml):
        self._initialize_session()
        try:
            response = self.session.send_invoice(invoice_xml)
            return response
        except Exception as e:
            raise Exception(f"Błąd podczas wysyłki faktury do KSeF: {e}")

    def get_session_status(self):
        if not self.session:
            self._initialize_session()
        try:
            response = self.session.get_session_status()
            return response
        except Exception as e:
            raise Exception(f"Błąd podczas sprawdzania statusu sesji: {e}")
