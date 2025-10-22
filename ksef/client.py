# ksef/client.py

import requests
import logging
import time
import base64
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
import os

from ksiegowosc.models import CompanyInfo

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
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"  # POPRAWIONY URL
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        self.access_token = None
        self.refresh_token = None
        self.public_key_cert = None
        self.aes_key = None
        self.aes_iv = None

    def _get_public_key(self):
        """Pobiera certyfikat z kluczem publicznym KSeF do szyfrowania"""
        if self.public_key_cert:
            return self.public_key_cert

        try:
            url = f"{self.base_url}/security/public-key-certificates"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # API zwraca listę certyfikatów w Base64 (DER)
            certs_data = response.json()

            # Wybierz certyfikat do szyfrowania tokenów (pierwszy z listy)
            if certs_data and len(certs_data) > 0:
                cert_b64 = certs_data[0]["certificate"]
                cert_der = base64.b64decode(cert_b64)

                # Załaduj certyfikat
                cert = load_pem_x509_certificate(
                    b"-----BEGIN CERTIFICATE-----\n"
                    + base64.b64encode(cert_der)
                    + b"\n-----END CERTIFICATE-----",
                    default_backend(),
                )

                self.public_key_cert = cert.public_key()
                logger.info("Pobrano klucz publiczny KSeF")
                return self.public_key_cert
            else:
                raise Exception("Brak dostępnych certyfikatów")

        except Exception as e:
            logger.error(f"Błąd pobierania klucza publicznego: {e}")
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: int) -> str:
        """
        Szyfruje token KSeF zgodnie z API 2.0
        Format: "{token}|{timestamp}" -> RSA-OAEP SHA-256 -> Base64
        """
        try:
            public_key = self._get_public_key()

            # Przygotuj string do zaszyfrowania
            token_string = f"{ksef_token}|{timestamp}"
            token_bytes = token_string.encode("utf-8")

            # Szyfrowanie RSA-OAEP z SHA-256
            encrypted = public_key.encrypt(
                token_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            # Kodowanie do Base64
            encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
            logger.info("Token KSeF zaszyfrowany pomyślnie")
            return encrypted_b64

        except Exception as e:
            logger.error(f"Błąd szyfrowania tokena KSeF: {e}")
            raise

    def _generate_aes_key(self):
        """Generuje klucz AES-256 i IV dla szyfrowania faktur"""
        self.aes_key = os.urandom(32)  # 256 bitów
        self.aes_iv = os.urandom(16)  # 128 bitów
        logger.info("Wygenerowano klucz AES-256")

    def _encrypt_aes_key(self) -> dict:
        """
        Szyfruje klucz AES kluczem publicznym KSeF
        Zwraca dict z zaszyfrowanym kluczem i IV w Base64
        """
        try:
            public_key = self._get_public_key()

            # Szyfrowanie klucza AES
            encrypted_key = public_key.encrypt(
                self.aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            return {
                "encryptedSymmetricKey": base64.b64encode(encrypted_key).decode(
                    "utf-8"
                ),
                "initializationVector": base64.b64encode(self.aes_iv).decode("utf-8"),
            }

        except Exception as e:
            logger.error(f"Błąd szyfrowania klucza AES: {e}")
            raise

    def _encrypt_invoice(self, invoice_xml: str) -> bytes:
        """
        Szyfruje fakturę XML przy użyciu AES-256-CBC
        """
        try:
            # Konwersja XML do bajtów
            invoice_bytes = invoice_xml.encode("utf-8")

            # Tworzenie szyfru AES-256-CBC
            cipher = Cipher(
                algorithms.AES(self.aes_key),
                modes.CBC(self.aes_iv),
                backend=default_backend(),
            )

            encryptor = cipher.encryptor()

            # Dodanie paddingu PKCS7
            padding_length = 16 - (len(invoice_bytes) % 16)
            padded_data = invoice_bytes + bytes([padding_length] * padding_length)

            # Szyfrowanie
            encrypted = encryptor.update(padded_data) + encryptor.finalize()

            logger.info(f"Faktura zaszyfrowana (rozmiar: {len(encrypted)} bajtów)")
            return encrypted

        except Exception as e:
            logger.error(f"Błąd szyfrowania faktury: {e}")
            raise

    def _authenticate(self):
        """
        Nowy proces uwierzytelniania w API 2.0
        """
        if self.access_token:
            return

        try:
            # Krok 1: Pobierz challenge
            logger.info("Krok 1/4: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            context = {
                "contextIdentifier": {
                    "type": "NIP",
                    "identifier": self.nip,
                }
            }

            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()

            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]
            logger.info(f"✓ Otrzymano challenge: {challenge[:20]}...")

            # Krok 2: Zaszyfruj token i wyślij żądanie uwierzytelnienia
            logger.info("Krok 2/4: Szyfrowanie i wysyłanie tokena KSeF...")
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp
            )

            auth_url = f"{self.base_url}/auth/ksef-token"
            payload = {
                "challenge": challenge,
                "contextIdentifier": {"type": "NIP", "value": self.nip},
                "encryptedToken": encrypted_token,
            }

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            auth_response.raise_for_status()
            auth_data = auth_response.json()

            reference_number = auth_data["referenceNumber"]
            temp_token = auth_data["authenticationToken"]["token"]
            logger.info(f"✓ Otrzymano tymczasowy token, ref: {reference_number}")

            # Krok 3: Sprawdź status uwierzytelniania
            logger.info("Krok 3/4: Sprawdzanie statusu uwierzytelniania...")
            status_url = f"{self.base_url}/auth/{reference_number}"
            status_headers = {"Authorization": f"Bearer {temp_token}"}

            max_attempts = 10
            for attempt in range(max_attempts):
                status_response = requests.get(
                    status_url, headers=status_headers, timeout=10
                )
                status_response.raise_for_status()
                status_data = status_response.json()

                status_code = status_data["status"]["code"]

                if status_code == 200:
                    logger.info("✓ Uwierzytelnianie zakończone sukcesem")
                    break
                elif status_code >= 400:
                    error_msg = status_data["status"].get(
                        "description", "Nieznany błąd"
                    )
                    raise Exception(f"Błąd uwierzytelniania: {error_msg}")
                else:
                    logger.info(
                        f"  Status: {status_code} - oczekiwanie... ({attempt + 1}/{max_attempts})"
                    )
                    time.sleep(2)

            # Krok 4: Odbierz tokeny dostępowe (access i refresh)
            logger.info("Krok 4/4: Odbieranie tokenów dostępowych...")
            redeem_url = f"{self.base_url}/auth/token/redeem"
            redeem_response = requests.post(
                redeem_url, headers=status_headers, timeout=10
            )
            redeem_response.raise_for_status()
            tokens = redeem_response.json()

            self.access_token = tokens["accessToken"]["token"]
            self.refresh_token = tokens["refreshToken"]["token"]

            logger.info("✓ Pomyślnie uzyskano tokeny dostępowe (JWT)")

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_details = e.response.json()
                except ValueError:
                    error_details = e.response.text
            logger.error(f"❌ Błąd uwierzytelniania: {error_details}")
            raise Exception(f"Błąd uwierzytelniania KSeF API v2.0: {error_details}")

    def send_invoice(self, invoice_xml: str) -> dict:
        """
        Wysyła fakturę do KSeF przez sesję interaktywną (API 2.0)
        """
        try:
            # Uwierzytelnij się
            self._authenticate()

            # Generuj klucz AES dla tej sesji
            self._generate_aes_key()

            # Krok 1: Otwórz sesję interaktywną
            logger.info("Otwieranie sesji interaktywnej...")
            session_url = f"{self.base_url}/sessions/online"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }

            encryption_data = self._encrypt_aes_key()
            session_payload = {
                "formCode": "FA(3)",  # Schema FA(3)
                "encryption": encryption_data,
            }

            session_response = requests.post(
                session_url, json=session_payload, headers=headers, timeout=10
            )
            session_response.raise_for_status()
            session_data = session_response.json()
            session_ref = session_data["referenceNumber"]
            logger.info(f"✓ Sesja otwarta: {session_ref}")

            # Krok 2: Zaszyfruj i wyślij fakturę
            logger.info("Szyfrowanie i wysyłanie faktury...")
            encrypted_invoice = self._encrypt_invoice(invoice_xml)

            invoice_url = f"{self.base_url}/sessions/online/{session_ref}/invoices"
            invoice_headers = {
                "Content-Type": "application/octet-stream",
                "Authorization": f"Bearer {self.access_token}",
            }

            invoice_response = requests.put(
                invoice_url, data=encrypted_invoice, headers=invoice_headers, timeout=15
            )
            invoice_response.raise_for_status()
            invoice_data = invoice_response.json()

            invoice_ref = invoice_data["referenceNumber"]
            logger.info(f"✓ Faktura wysłana: {invoice_ref}")

            # Krok 3: Sprawdź status faktury
            logger.info("Sprawdzanie statusu faktury...")
            time.sleep(2)  # Poczekaj chwilę na przetworzenie

            status_url = (
                f"{self.base_url}/sessions/{session_ref}/invoices/{invoice_ref}"
            )
            status_response = requests.get(
                status_url, headers=invoice_headers, timeout=10
            )
            status_response.raise_for_status()
            status_data = status_response.json()

            logger.info(
                f"✓ Status faktury: {status_data.get('status', {}).get('code')}"
            )

            # Krok 4: Zamknij sesję
            logger.info("Zamykanie sesji...")
            close_url = f"{self.base_url}/sessions/online/{session_ref}/close"
            close_response = requests.post(close_url, headers=headers, timeout=10)
            close_response.raise_for_status()
            logger.info("✓ Sesja zamknięta")

            return {
                "session_reference": session_ref,
                "invoice_reference": invoice_ref,
                "status": status_data,
            }

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_details = e.response.json()
                except ValueError:
                    error_details = e.response.text
            logger.error(f"❌ Błąd wysyłki faktury: {error_details}")
            raise Exception(f"Błąd wysyłki faktury do KSeF: {error_details}")

        # Przechowuj NIP bez myślników
        self.nip = self._normalize_nip(self.nip)

    def _normalize_nip(self, nip: str) -> str:
        """
        Usuwa myślniki i spacje z NIP-u, zwraca tylko cyfry
        """
        if not nip:
            raise Exception("Brak numeru NIP")

        normalized = nip.replace("-", "").replace(" ", "").strip()

        # Walidacja: musi mieć dokładnie 10 cyfr
        if not normalized.isdigit() or len(normalized) != 10:
            raise Exception(f"Nieprawidłowy format NIP: {nip}. Wymagane 10 cyfr.")

        return normalized
