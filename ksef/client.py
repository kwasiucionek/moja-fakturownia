# kwasiucionek/moja-fakturownia/moja-fakturownia-a0f550ee045da0fa60a613fb7a8884b3052e00a0/ksef/client.py

import os
from ksef_utils.server import KSEFServer, KSEFService
from ksef_utils.config import TestConfig, ProdConfig
from ksiegowosc.models import CompanyInfo


class KsefClient:
    """
    Klient API KSeF wykorzystujący bibliotekę ksef-utils.
    """

    def __init__(self, user):
        self.user = user
        try:
            self.company_info = CompanyInfo.objects.get(user=self.user)
            self.token = self.company_info.ksef_token
            self.nip = self.company_info.tax_id.replace("-", "")
            self.environment = self.company_info.ksef_environment
        except CompanyInfo.DoesNotExist:
            raise Exception("Brak danych firmy. Uzupełnij je, aby korzystać z KSeF.")

        if not self.token:
            raise Exception("Brak tokena KSeF w ustawieniach firmy.")

        # Wybór konfiguracji środowiska
        config_class = TestConfig if self.environment == "test" else ProdConfig

        # Inicjalizacja serwera i serwisu z ksef-utils
        self.server = KSEFServer(config_class())
        self.service = KSEFService(self.server)

    def init_session(self):
        """
        Inicjalizuje sesję za pomocą tokena.
        Zwraca token sesji lub rzuca wyjątek w przypadku błędu.
        """
        try:
            session_token = self.service.init_token(self.token, self.nip)
            return session_token
        except Exception as e:
            # Przechwyć błędy z biblioteki i przekaż dalej jako bardziej zrozumiały komunikat
            raise Exception(f"Błąd inicjalizacji sesji KSeF: {e}")

    def send_invoice(self, invoice_xml: str):
        """
        Wysyła fakturę XML do KSeF.
        Zwraca odpowiedź z KSeF.
        """
        try:
            # Inicjalizacja sesji przed każdą wysyłką jest dobrą praktyką
            self.init_session()

            # Biblioteka ksef-utils sama obsługuje opakowanie XML w odpowiednią strukturę
            response = self.service.send_invoice(invoice_xml)
            return response
        except Exception as e:
            raise Exception(f"Błąd podczas wysyłki faktury do KSeF: {e}")

    def get_session_status(self, session_id: str):
        """
        Sprawdza status sesji (np. po wysłaniu faktury).
        """
        try:
            status = self.service.get_session_status(session_id)
            return status
        except Exception as e:
            raise Exception(f"Błąd podczas sprawdzania statusu sesji: {e}")

    def terminate_session(self):
        """Zamyka aktywną sesję."""
        try:
            self.service.terminate_session()
        except Exception as e:
            # Błąd zamknięcia sesji nie jest krytyczny, więc tylko go logujemy
            print(f"Błąd podczas zamykania sesji KSeF: {e}")

    def get_invoice_ksef_reference(self, session_id: str) -> str | None:
        """
        Po pomyślnym przetworzeniu faktury, pobiera jej numer referencyjny KSeF.
        """
        try:
            # Sesja musi być aktywna, aby pobrać status
            if not self.service.is_session_active():
                self.init_session()

            status = self.service.get_session_status(session_id)

            # Kod 315 oznacza, że przetwarzanie zakończyło się sukcesem
            if status.get("processingCode") == 315:
                # W odpowiedzi na status powinniśmy dostać numer KSeF
                ksef_ref_number = status.get("elementReferenceNumber")
                return ksef_ref_number
            return None
        except Exception as e:
            raise Exception(f"Błąd podczas pobierania numeru referencyjnego KSeF: {e}")

    def get_invoice_ksef_reference(self, session_id: str) -> str | None:
        """
        Po pomyślnym przetworzeniu faktury, pobiera jej numer referencyjny KSeF.
        """
        try:
            # Sesja musi być aktywna, aby pobrać status
            if not self.service.is_session_active():
                self.init_session()

            status = self.service.get_session_status(session_id)

            # Kod 315 oznacza, że przetwarzanie zakończyło się sukcesem
            if status.get("processingCode") == 315:
                # W odpowiedzi na status powinniśmy dostać numer KSeF
                ksef_ref_number = status.get("elementReferenceNumber")
                return ksef_ref_number
            return None
        except Exception as e:
            raise Exception(f"Błąd podczas pobierania numeru referencyjnego KSeF: {e}")
