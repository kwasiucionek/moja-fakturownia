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
        Proces uwierzytelniania w API 2.0 zgodny z dokumentacją GitHub
        https://github.com/CIRFMF/ksef-docs/tree/main/auth
        """
        if self.access_token:
            logger.info("Token dostępowy już istnieje, pomijam uwierzytelnianie")
            return

        try:
            logger.info("=" * 70)
            logger.info("ROZPOCZĘCIE PROCESU UWIERZYTELNIANIA KSEF API 2.0")
            logger.info(f"Środowisko: {self.company_info.ksef_environment}")
            logger.info(f"Base URL: {self.base_url}")
            logger.info(f"NIP: {self.nip}")
            logger.info("=" * 70)

            # KROK 1: Pobierz Challenge
            logger.info("Krok 1/5: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            challenge_request = {
                "contextIdentifier": {"type": "onip", "identifier": self.nip}
            }

            logger.info(f"POST {challenge_url}")
            logger.debug(f"Request: {challenge_request}")

            response = requests.post(
                challenge_url, json=challenge_request, headers=headers, timeout=10
            )

            logger.info(f"Response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Response: {response.text}")

            response.raise_for_status()
            challenge_data = response.json()

            logger.debug(f"Challenge response: {challenge_data}")

            challenge = challenge_data["challenge"]
            timestamp_str = challenge_data["timestamp"]

            # Konwertuj timestamp na milisekundy
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            timestamp_ms = int(dt.timestamp() * 1000)

            logger.info(f"✓ Challenge: {challenge[:30]}...")
            logger.info(f"✓ Timestamp: {timestamp_str} -> {timestamp_ms} ms")

            # KROK 2: Zaszyfruj token
            logger.info("Krok 2/5: Szyfrowanie tokena...")

            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp_ms
            )

            logger.info(f"✓ Token zaszyfrowany ({len(encrypted_token)} znaków)")

            # KROK 3: InitToken - wyślij zaszyfrowany token
            logger.info("Krok 3/5: Wysyłanie zaszyfrowanego tokena (InitToken)...")

            init_url = f"{self.base_url}/auth/authorisation-token"

            init_request = {
                "contextIdentifier": {"type": "onip", "identifier": self.nip},
                "token": encrypted_token,
            }

            logger.info(f"POST {init_url}")

            init_response = requests.post(
                init_url, json=init_request, headers=headers, timeout=10
            )

            logger.info(f"Response status: {init_response.status_code}")

            if init_response.status_code != 200:
                logger.error(f"Response: {init_response.text}")
                try:
                    error_json = init_response.json()
                    logger.error(
                        f"Error JSON: {json.dumps(error_json, indent=2, ensure_ascii=False)}"
                    )
                except:
                    pass

            init_response.raise_for_status()
            init_data = init_response.json()

            logger.debug(f"Init response: {init_data}")

            reference_number = init_data.get("referenceNumber")
            session_token = init_data.get("sessionToken", {}).get("token")

            if not reference_number or not session_token:
                logger.error(f"Niepełna odpowiedź InitToken: {init_data}")
                raise Exception(
                    "Brak referenceNumber lub sessionToken w odpowiedzi InitToken"
                )

            logger.info(f"✓ Reference number: {reference_number}")
            logger.info(f"✓ Session token otrzymany: {session_token[:30]}...")

            # KROK 4: Sprawdź status autoryzacji
            logger.info("Krok 4/5: Sprawdzanie statusu autoryzacji...")

            status_url = f"{self.base_url}/auth/authorisation/{reference_number}/Status"
            status_headers = {"SessionToken": session_token}

            max_attempts = 20

            for attempt in range(max_attempts):
                time.sleep(2)

                logger.info(f"Próba {attempt + 1}/{max_attempts}: GET {status_url}")

                status_response = requests.get(
                    status_url, headers=status_headers, timeout=10
                )

                logger.info(f"Status code: {status_response.status_code}")

                if status_response.status_code != 200:
                    logger.error(f"Response: {status_response.text}")

                status_response.raise_for_status()
                status_data = status_response.json()

                logger.debug(f"Status: {status_data}")

                processing_code = status_data.get("processingCode")
                processing_desc = status_data.get("processingDescription", "")

                logger.info(
                    f"  Processing: code={processing_code}, desc={processing_desc}"
                )

                if processing_code == 200:
                    logger.info(f"✓ Autoryzacja potwierdzona")
                    break
                elif processing_code and processing_code >= 400:
                    error_msg = (
                        f"Błąd autoryzacji (kod {processing_code}): {processing_desc}"
                    )
                    logger.error(f"❌ {error_msg}")
                    raise Exception(error_msg)
                else:
                    logger.info(f"  Czekam na potwierdzenie...")
                    continue
            else:
                raise Exception("Przekroczono limit prób sprawdzenia statusu")

            # KROK 5: GenerateToken - wygeneruj finalne tokeny JWT
            logger.info(
                "Krok 5/5: Generowanie finalnych tokenów JWT (GenerateToken)..."
            )

            generate_url = (
                f"{self.base_url}/auth/authorisation/{reference_number}/GenerateToken"
            )
            generate_headers = {"SessionToken": session_token}

            logger.info(f"POST {generate_url}")

            generate_response = requests.post(
                generate_url, headers=generate_headers, timeout=10
            )

            logger.info(f"Response status: {generate_response.status_code}")

            if generate_response.status_code != 200:
                logger.error(f"Response: {generate_response.text}")

            generate_response.raise_for_status()
            token_data = generate_response.json()

            logger.debug(f"Token response: {token_data}")

            # Pobierz tokeny JWT
            self.access_token = token_data.get("sessionToken", {}).get("token")
            self.refresh_token = token_data.get("refreshToken", {}).get("token")

            if not self.access_token:
                logger.error(f"Brak sessionToken w odpowiedzi: {token_data}")
                raise Exception("Nie otrzymano sessionToken (JWT)")

            logger.info(f"✓ Access token (JWT) otrzymany: {self.access_token[:30]}...")
            if self.refresh_token:
                logger.info(f"✓ Refresh token otrzymany: {self.refresh_token[:30]}...")

            logger.info("=" * 70)
            logger.info("✅ UWIERZYTELNIANIE ZAKOŃCZONE POMYŚLNIE")
            logger.info("=" * 70)

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_details = json.dumps(error_json, indent=2, ensure_ascii=False)
                    logger.error(f"❌ JSON error:\n{error_details}")
                except ValueError:
                    error_details = e.response.text
                    logger.error(f"❌ Text error:\n{error_details}")

                logger.error(f"Status: {e.response.status_code}")

            logger.error(f"❌ Błąd uwierzytelniania KSeF API v2.0: {error_details}")

            import traceback

            logger.error(f"Traceback:\n{traceback.format_exc()}")

            raise Exception(f"Błąd uwierzytelniania KSeF API v2.0: {error_details}")

        except Exception as e:
            logger.error(f"❌ Nieoczekiwany błąd: {type(e).__name__}: {str(e)}")

            import traceback

            logger.error(f"Traceback:\n{traceback.format_exc()}")

            raise

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
        """Wczytuje klucz publiczny KSeF (tylko lokalny plik)"""
        if self.public_key_cert:
            return self.public_key_cert

        try:
            logger.info("Wczytywanie klucza publicznego KSeF...")

            pem_file = self.key_dir / "publicKey.pem"

            if not pem_file.exists():
                raise Exception(
                    f"Brak pliku klucza publicznego: {pem_file}\n"
                    f"Pobierz klucz komendą:\n"
                    f"curl -o {pem_file} https://ksef-test.mf.gov.pl/web/formularze/ksef-test-encryption-public-key.pem"
                )

            with open(pem_file, "rb") as f:
                key_data = f.read()

            logger.info(f"Plik klucza: {pem_file} ({len(key_data)} bajtów)")

            # Próbuj jako certyfikat X.509
            try:
                cert = load_pem_x509_certificate(key_data, default_backend())
                self.public_key_cert = cert.public_key()
                logger.info(
                    f"✓ Klucz publiczny (certyfikat X.509, {self.public_key_cert.key_size} bitów)"
                )
            except Exception:
                # Próbuj jako surowy klucz publiczny
                from cryptography.hazmat.primitives.serialization import (
                    load_pem_public_key,
                )

                self.public_key_cert = load_pem_public_key(key_data, default_backend())
                logger.info(
                    f"✓ Klucz publiczny (raw PEM, {self.public_key_cert.key_size} bitów)"
                )

            return self.public_key_cert

        except Exception as e:
            logger.error(f"❌ Błąd wczytywania klucza publicznego: {e}")
            raise

    def _load_local_public_key(self):
        """Ładuje lokalny klucz publiczny jako fallback"""
        try:
            pem_file = self.key_dir / "publicKey.pem"
            der_file = self.key_dir / "publicKey.der"

            if pem_file.exists():
                logger.info(f"Wczytywanie lokalnego klucza z: {pem_file}")
                with open(pem_file, "rb") as f:
                    key_data = f.read()

                try:
                    cert = load_pem_x509_certificate(key_data, default_backend())
                    self.public_key_cert = cert.public_key()
                    logger.warning(
                        f"⚠️  Wczytano lokalny klucz PEM (certyfikat, {self.public_key_cert.key_size} bitów)"
                    )
                except Exception:
                    from cryptography.hazmat.primitives.serialization import (
                        load_pem_public_key,
                    )

                    self.public_key_cert = load_pem_public_key(
                        key_data, default_backend()
                    )
                    logger.warning(
                        f"⚠️  Wczytano lokalny klucz PEM (raw, {self.public_key_cert.key_size} bitów)"
                    )

            elif der_file.exists():
                logger.info(f"Wczytywanie lokalnego klucza z: {der_file}")
                with open(der_file, "rb") as f:
                    key_data = f.read()

                try:
                    cert = load_der_x509_certificate(key_data, default_backend())
                    self.public_key_cert = cert.public_key()
                    logger.warning(
                        f"⚠️  Wczytano lokalny klucz DER (certyfikat, {self.public_key_cert.key_size} bitów)"
                    )
                except Exception:
                    from cryptography.hazmat.primitives.serialization import (
                        load_der_public_key,
                    )

                    self.public_key_cert = load_der_public_key(
                        key_data, default_backend()
                    )
                    logger.warning(
                        f"⚠️  Wczytano lokalny klucz DER (raw, {self.public_key_cert.key_size} bitów)"
                    )
            else:
                raise Exception(f"Brak lokalnego pliku klucza w {self.key_dir}")

            return self.public_key_cert

        except Exception as e:
            logger.error(f"❌ Nie można załadować lokalnego klucza: {e}")
            raise Exception(
                f"Nie można pobrać klucza publicznego ani z API ani z lokalnego pliku: {e}"
            )
