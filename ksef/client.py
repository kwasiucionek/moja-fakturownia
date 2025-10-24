# ksef/client.py

import requests
import logging
import time
import base64
import os
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate

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

        # Ustaw URL dla API 2.0
        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        # Ścieżka do katalogu z kluczem publicznym
        self.key_dir = Path("/home/fakturownia/app/ksef-pubkey")

        # Znormalizuj NIP (usuń myślniki i spacje)
        self.nip = self._normalize_nip(self.company_info.tax_id)

        # Inicjalizuj zmienne
        self.access_token = None
        self.refresh_token = None
        self.public_key_cert = None
        self.aes_key = None
        self.aes_iv = None

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

        logger.info(f"NIP znormalizowany: {nip} -> {normalized}")
        return normalized

    def _get_public_key(self):
        """Wczytuje certyfikat z kluczem publicznym KSeF z lokalnego pliku"""
        if self.public_key_cert:
            return self.public_key_cert

        try:
            # Najpierw spróbuj PEM
            pem_file = self.key_dir / "publicKey.pem"
            der_file = self.key_dir / "publicKey.der"

            if pem_file.exists():
                logger.info(f"Wczytywanie klucza z: {pem_file}")
                with open(pem_file, "rb") as f:
                    key_data = f.read()

                try:
                    cert = load_pem_x509_certificate(key_data, default_backend())
                    self.public_key_cert = cert.public_key()
                    logger.info(
                        f"✓ Wczytano klucz publiczny PEM (rozmiar: {self.public_key_cert.key_size} bitów)"
                    )
                except Exception as e:
                    # Może to być sam klucz publiczny bez certyfikatu
                    from cryptography.hazmat.primitives.serialization import (
                        load_pem_public_key,
                    )

                    self.public_key_cert = load_pem_public_key(
                        key_data, default_backend()
                    )
                    logger.info(
                        f"✓ Wczytano czysty klucz publiczny PEM (rozmiar: {self.public_key_cert.key_size} bitów)"
                    )

            elif der_file.exists():
                logger.info(f"Wczytywanie klucza z: {der_file}")
                with open(der_file, "rb") as f:
                    key_data = f.read()

                try:
                    cert = load_der_x509_certificate(key_data, default_backend())
                    self.public_key_cert = cert.public_key()
                    logger.info(
                        f"✓ Wczytano klucz publiczny DER (rozmiar: {self.public_key_cert.key_size} bitów)"
                    )
                except Exception as e:
                    # Może to być sam klucz publiczny bez certyfikatu
                    from cryptography.hazmat.primitives.serialization import (
                        load_der_public_key,
                    )

                    self.public_key_cert = load_der_public_key(
                        key_data, default_backend()
                    )
                    logger.info(
                        f"✓ Wczytano czysty klucz publiczny DER (rozmiar: {self.public_key_cert.key_size} bitów)"
                    )
            else:
                raise Exception(f"Brak pliku klucza publicznego w {self.key_dir}")

            return self.public_key_cert

        except Exception as e:
            logger.error(f"Błąd wczytywania klucza publicznego: {e}")
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
            logger.info(
                f"String do zaszyfrowania: {token_string[:30]}... (długość: {len(token_string)})"
            )

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
            logger.info(
                f"✓ Token zaszyfrowany (rozmiar: {len(encrypted)} bajtów, Base64: {len(encrypted_b64)} znaków)"
            )
            logger.info(
                f"✓ Zaszyfrowany token (pierwsze 50 znaków): {encrypted_b64[:50]}..."
            )

            return encrypted_b64

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania tokena KSeF: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise

    def _generate_aes_key(self):
        """Generuje klucz AES-256 i IV dla szyfrowania faktur"""
        self.aes_key = os.urandom(32)  # 256 bitów
        self.aes_iv = os.urandom(16)  # 128 bitów
        logger.info("✓ Wygenerowano klucz AES-256 i IV")

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

            result = {
                "encryptedSymmetricKey": base64.b64encode(encrypted_key).decode(
                    "utf-8"
                ),
                "initializationVector": base64.b64encode(self.aes_iv).decode("utf-8"),
            }

            logger.info("✓ Klucz AES zaszyfrowany kluczem publicznym KSeF")
            return result

        except Exception as e:
            logger.error(f"Błąd szyfrowania klucza AES: {e}")
            raise

    def _encrypt_invoice(self, invoice_xml: str) -> bytes:
        """
        Szyfruje fakturę XML przy użyciu AES-256-CBC z paddingiem PKCS7
        """
        try:
            # Konwersja XML do bajtów UTF-8
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

            logger.info(
                f"✓ Faktura zaszyfrowana AES-256-CBC (rozmiar: {len(encrypted)} bajtów)"
            )
            return encrypted

        except Exception as e:
            logger.error(f"Błąd szyfrowania faktury: {e}")
            raise

    def _authenticate(self):
        """
        Proces uwierzytelniania w API 2.0 zgodny z dokumentacją OpenAPI
        """
        if self.access_token:
            logger.info("Token dostępowy już istnieje, pomijam uwierzytelnianie")
            return

        try:
            logger.info("=" * 70)
            logger.info("ROZPOCZĘCIE PROCESU UWIERZYTELNIANIA KSEF API 2.0")
            logger.info("=" * 70)

            # Krok 1: Pobierz challenge
            logger.info("Krok 1/4: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            # Zgodnie z OpenAPI: contextIdentifier z "type" i "identifier"
            context = {
                "contextIdentifier": {
                    "type": "onip",  # Typ dla NIP
                    "identifier": self.nip,
                }
            }

            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()

            challenge = challenge_data["challenge"]
            timestamp_str = challenge_data["timestamp"]

            # Konwertuj timestamp ISO na milisekundy Unix epoch
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            timestamp_ms = int(dt.timestamp() * 1000)

            logger.info(f"✓ Challenge otrzymany: {challenge[:30]}...")
            logger.info(f"✓ Timestamp z API: {timestamp_str}")
            logger.info(f"✓ Timestamp w ms: {timestamp_ms}")

            # Krok 2: Zaszyfruj token i wyślij żądanie uwierzytelnienia
            logger.info("Krok 2/4: Szyfrowanie i wysyłanie tokena KSeF...")
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp_ms
            )

            auth_url = f"{self.base_url}/auth/authorisation-token"

            # Zgodnie z OpenAPI dla authorisation-token
            payload = {
                "contextIdentifier": {"type": "onip", "identifier": self.nip},
                "token": encrypted_token,
            }

            logger.info(f"Wysyłanie do: {auth_url}")
            logger.info(
                f"Payload (bez tokena): {{'contextIdentifier': {payload['contextIdentifier']}, 'token': '***'}}"
            )

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )

            # Loguj szczegóły odpowiedzi
            logger.info(f"Status odpowiedzi: {auth_response.status_code}")

            if auth_response.status_code != 200:
                error_body = auth_response.text
                logger.error(f"❌ Błąd autoryzacji: {error_body}")
                try:
                    error_json = auth_response.json()
                    logger.error(f"❌ Szczegóły błędu: {error_json}")
                except:
                    pass

            auth_response.raise_for_status()
            auth_data = auth_response.json()

            # W odpowiedzi mamy AuthorisationChallengeResponse
            reference_number = auth_data.get("referenceNumber")
            temp_token = auth_data.get("authenticationToken", {}).get("token")

            if not reference_number or not temp_token:
                logger.error(f"Niepełna odpowiedź: {auth_data}")
                raise Exception(
                    "Brak referenceNumber lub authenticationToken w odpowiedzi"
                )

            logger.info(f"✓ Otrzymano tymczasowy token")
            logger.info(f"✓ Reference number: {reference_number}")

            # Krok 3: Sprawdź status uwierzytelniania
            logger.info("Krok 3/4: Sprawdzanie statusu uwierzytelniania...")
            status_url = f"{self.base_url}/auth/{reference_number}"
            status_headers = {
                "SessionToken": temp_token  # Zgodnie z OpenAPI używamy SessionToken w header
            }

            max_attempts = 15
            for attempt in range(max_attempts):
                time.sleep(2)  # Poczekaj przed sprawdzeniem

                status_response = requests.get(
                    status_url, headers=status_headers, timeout=10
                )
                status_response.raise_for_status()
                status_data = status_response.json()

                status_code = status_data.get("processingCode")
                status_desc = status_data.get("processingDescription", "")

                logger.info(
                    f"  Próba {attempt + 1}/{max_attempts}: kod={status_code}, opis={status_desc}"
                )

                if status_code == 200:
                    logger.info(f"✓ Uwierzytelnianie zakończone sukcesem")
                    break
                elif status_code and status_code >= 400:
                    logger.error(
                        f"❌ Błąd uwierzytelniania (kod {status_code}): {status_desc}"
                    )
                    raise Exception(f"Błąd uwierzytelniania: {status_desc}")
                else:
                    # Wciąż w trakcie przetwarzania
                    continue
            else:
                raise Exception(
                    "Przekroczono limit prób sprawdzenia statusu uwierzytelniania"
                )

            # Krok 4: Odbierz tokeny dostępowe (access i refresh)
            logger.info("Krok 4/4: Odbieranie tokenów dostępowych...")

            # Token w odpowiedzi status może już zawierać finalne tokeny
            if "sessionToken" in status_data:
                session_token_data = status_data["sessionToken"]
                self.access_token = session_token_data.get("token")

                # Refresh token może być opcjonalny
                self.refresh_token = status_data.get("refreshToken", {}).get("token")

                logger.info("✓ Pomyślnie uzyskano tokeny dostępowe")
                logger.info(
                    f"✓ Access token (pierwsze 30 znaków): {self.access_token[:30]}..."
                )
            else:
                logger.error("Brak sessionToken w odpowiedzi statusowej")
                raise Exception("Nie otrzymano sessionToken")

            logger.info("=" * 70)
            logger.info("UWIERZYTELNIANIE ZAKOŃCZONE POMYŚLNIE")
            logger.info("=" * 70)

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

        Zwraca dict z:
        - session_reference: Numer referencyjny sesji
        - invoice_reference: Numer referencyjny faktury
        - status: Status przetworzenia faktury
        """
        try:
            logger.info("=" * 70)
            logger.info("ROZPOCZĘCIE WYSYŁKI FAKTURY DO KSEF")
            logger.info("=" * 70)

            # Uwierzytelnij się
            self._authenticate()

            # Generuj klucz AES dla tej sesji
            self._generate_aes_key()

            # Krok 1: Otwórz sesję interaktywną
            logger.info("Krok 1/4: Otwieranie sesji interaktywnej...")
            session_url = f"{self.base_url}/sessions/online"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }

            encryption_data = self._encrypt_aes_key()
            session_payload = {"formCode": "FA(3)", "encryption": encryption_data}

            session_response = requests.post(
                session_url, json=session_payload, headers=headers, timeout=10
            )
            session_response.raise_for_status()
            session_data = session_response.json()
            session_ref = session_data["referenceNumber"]
            logger.info(f"✓ Sesja otwarta: {session_ref}")

            # Krok 2: Zaszyfruj i wyślij fakturę
            logger.info("Krok 2/4: Szyfrowanie i wysyłanie faktury...")
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
            logger.info("Krok 3/4: Sprawdzanie statusu faktury...")
            time.sleep(3)  # Poczekaj na przetworzenie

            status_url = (
                f"{self.base_url}/sessions/{session_ref}/invoices/{invoice_ref}"
            )
            status_headers = {"Authorization": f"Bearer {self.access_token}"}

            max_attempts = 10
            status_data = None

            for attempt in range(max_attempts):
                status_response = requests.get(
                    status_url, headers=status_headers, timeout=10
                )
                status_response.raise_for_status()
                status_data = status_response.json()

                invoice_status = status_data.get("status", {}).get("code")

                if invoice_status == 200:
                    logger.info(f"✓ Faktura przetworzona pomyślnie")
                    break
                elif invoice_status and invoice_status >= 400:
                    error_desc = status_data.get("status", {}).get(
                        "description", "Nieznany błąd"
                    )
                    logger.error(f"❌ Błąd przetwarzania faktury: {error_desc}")
                    break
                else:
                    logger.info(
                        f"  Status faktury: {invoice_status} - oczekiwanie... ({attempt + 1}/{max_attempts})"
                    )
                    time.sleep(2)

            # Krok 4: Zamknij sesję
            logger.info("Krok 4/4: Zamykanie sesji...")
            close_url = f"{self.base_url}/sessions/online/{session_ref}/close"
            close_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }

            close_response = requests.post(close_url, headers=close_headers, timeout=10)
            close_response.raise_for_status()
            logger.info("✓ Sesja zamknięta")

            logger.info("=" * 70)
            logger.info("FAKTURA WYSŁANA POMYŚLNIE")
            logger.info("=" * 70)

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

    def _get_public_key(self):
        """Pobiera aktualny klucz publiczny KSeF z API"""
        if self.public_key_cert:
            return self.public_key_cert

        try:
            # Endpoint zgodny z KSeF API 2.0
            public_key_url = f"{self.base_url}/common/Credentials/Identifier/{self.nip}/Type/onip/RequestPublicKey"

            logger.info(f"Pobieranie klucza publicznego z API KSeF...")
            logger.info(f"URL: {public_key_url}")

            headers = {"Accept": "application/json"}
            response = requests.get(public_key_url, headers=headers, timeout=10)
            response.raise_for_status()

            # API zwraca JSON z kluczem
            key_response = response.json()
            logger.info(f"Odpowiedź API: {list(key_response.keys())}")

            # Klucz może być w różnych polach - sprawdźmy dokumentację
            public_key_pem = key_response.get("publicKey") or key_response.get("key")

            if not public_key_pem:
                logger.error(f"Struktura odpowiedzi: {key_response}")
                raise Exception("Brak klucza publicznego w odpowiedzi API")

            # Klucz jest w formacie PEM (string z -----BEGIN PUBLIC KEY-----)
            public_key_bytes = public_key_pem.encode("utf-8")

            # Załaduj klucz PEM
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            self.public_key_cert = load_pem_public_key(
                public_key_bytes, default_backend()
            )

            logger.info(f"✓ Pomyślnie wczytano klucz publiczny z API KSeF")
            logger.info(f"✓ Typ klucza: {type(self.public_key_cert).__name__}")
            logger.info(f"✓ Rozmiar klucza: {self.public_key_cert.key_size} bitów")

            return self.public_key_cert

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Błąd HTTP podczas pobierania klucza: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Szczegóły błędu API: {error_detail}")
                except:
                    logger.error(f"Odpowiedź API: {e.response.text[:500]}")
            raise Exception(f"Nie można pobrać klucza publicznego z API: {e}")

        except Exception as e:
            logger.error(f"❌ Błąd przetwarzania klucza publicznego: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise
