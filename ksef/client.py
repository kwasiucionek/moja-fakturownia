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
    """
    Klient KSeF API 2.0 z obsługą certyfikatów i tokenów
    
    Uwierzytelnianie:
    - Tokeny KSeF (działają do 31.12.2026)
    - Certyfikaty KSeF (dostępne od 01.11.2025 przez MCU)
    - Środowisko testowe: samodzielnie wygenerowane certyfikaty
    """
    
    def __init__(self, user):
        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception(
                "Użytkownik nie ma przypisanych danych firmy (CompanyInfo)."
            )

        if not self.company_info.ksef_token:
            raise Exception(
                "Brak tokena KSeF w ustawieniach firmy. "
                "Od 01.11.2025 można używać certyfikatów KSeF przez MCU."
            )

        # Ustaw URL dla API 2.0
        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        # Ścieżka do katalogu z kluczami publicznymi
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
        """Usuwa myślniki i spacje z NIP-u, zwraca tylko cyfry"""
        if not nip:
            raise Exception("Brak numeru NIP")

        normalized = nip.replace("-", "").replace(" ", "").strip()

        # Walidacja: musi mieć dokładnie 10 cyfr
        if not normalized.isdigit() or len(normalized) != 10:
            raise Exception(f"Nieprawidłowy format NIP: {nip}. Wymagane 10 cyfr.")

        logger.info(f"NIP znormalizowany: {nip} -> {normalized}")
        return normalized

    def _get_public_key(self):
        """
        Wczytuje klucz publiczny KSeF do szyfrowania
        
        Środowisko testowe:
        - Klucz z https://ksef-test.mf.gov.pl/web/formularze/ksef-test-encryption-public-key.pem
        - Lub endpoint: /api/v2/common/Encryption/PublicKey
        
        Produkcja:
        - Tylko endpoint API
        """
        if self.public_key_cert:
            return self.public_key_cert

        try:
            logger.info("Wczytywanie klucza publicznego KSeF...")

            # Dla środowiska testowego - spróbuj lokalny plik
            if self.company_info.ksef_environment == "test":
                pem_file = self.key_dir / "publicKey.pem"
                
                if pem_file.exists():
                    with open(pem_file, "rb") as f:
                        key_data = f.read()
                    
                    logger.info(f"Wczytywanie lokalnego klucza: {pem_file} ({len(key_data)} bajtów)")
                    
                    # Próbuj jako certyfikat X.509
                    try:
                        cert = load_pem_x509_certificate(key_data, default_backend())
                        self.public_key_cert = cert.public_key()
                        logger.info(
                            f"✓ Klucz testowy (certyfikat X.509, {self.public_key_cert.key_size} bitów)"
                        )
                        return self.public_key_cert
                    except Exception:
                        # Próbuj jako surowy klucz publiczny
                        from cryptography.hazmat.primitives.serialization import load_pem_public_key
                        
                        self.public_key_cert = load_pem_public_key(key_data, default_backend())
                        logger.info(
                            f"✓ Klucz testowy (raw PEM, {self.public_key_cert.key_size} bitów)"
                        )
                        return self.public_key_cert
            
            # Pobierz z API (produkcja lub brak lokalnego pliku)
            logger.info("Pobieranie klucza publicznego z API KSeF...")
            key_url = f"{self.base_url}/common/Encryption/PublicKey"
            
            response = requests.get(key_url, timeout=10)
            response.raise_for_status()
            
            key_data_json = response.json()
            key_pem = key_data_json.get("publicKey")
            
            if not key_pem:
                raise Exception("API nie zwróciło klucza publicznego")
            
            # Konwertuj z Base64 jeśli potrzeba
            if not key_pem.startswith("-----BEGIN"):
                key_pem = base64.b64decode(key_pem).decode('utf-8')
            
            key_bytes = key_pem.encode('utf-8')
            
            # Próbuj wczytać jako certyfikat lub klucz
            try:
                cert = load_pem_x509_certificate(key_bytes, default_backend())
                self.public_key_cert = cert.public_key()
                logger.info(
                    f"✓ Klucz z API (certyfikat X.509, {self.public_key_cert.key_size} bitów)"
                )
            except Exception:
                from cryptography.hazmat.primitives.serialization import load_pem_public_key
                
                self.public_key_cert = load_pem_public_key(key_bytes, default_backend())
                logger.info(
                    f"✓ Klucz z API (raw PEM, {self.public_key_cert.key_size} bitów)"
                )
            
            return self.public_key_cert

        except requests.exceptions.RequestException as e:
            error_msg = f"Błąd pobierania klucza z API: {e}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f"\nStatus: {e.response.status_code}"
                try:
                    error_msg += f"\nOdpowiedź: {e.response.json()}"
                except:
                    error_msg += f"\nOdpowiedź: {e.response.text[:200]}"
            
            logger.error(f"❌ {error_msg}")
            
            # Jeśli to test, pokaż pomocną wskazówkę
            if self.company_info.ksef_environment == "test":
                pem_file = self.key_dir / "publicKey.pem"
                logger.error(
                    f"\n💡 Dla środowiska testowego pobierz klucz:\n"
                    f"   mkdir -p {self.key_dir}\n"
                    f"   curl -o {pem_file} https://ksef-test.mf.gov.pl/web/formularze/ksef-test-encryption-public-key.pem"
                )
            
            raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania klucza publicznego: {e}")
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: int) -> str:
        """
        Szyfruje token KSeF zgodnie z API 2.0
        Format: "{token}|{timestamp}" -> RSA-OAEP SHA-256 -> Base64
        
        UWAGA: Tokeny KSeF działają do 31.12.2026
        Od 01.11.2025 dostępne są certyfikaty KSeF przez MCU
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
            logger.debug(
                f"Zaszyfrowany token (pierwsze 50 znaków): {encrypted_b64[:50]}..."
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
            logger.error(f"❌ Błąd szyfrowania klucza AES: {e}")
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
            logger.error(f"❌ Błąd szyfrowania faktury: {e}")
            raise

    def _authenticate(self):
        """
        Proces uwierzytelniania w KSeF API 2.0 z tokenem
        
        Kroki:
        1. Pobierz challenge
        2. Zaszyfruj token KSeF
        3. Wyślij uwierzytelnienie
        4. Pobierz status i tokeny dostępu
        """
        if self.access_token:
            logger.info("Token dostępowy już istnieje, pomijam uwierzytelnianie")
            return

        try:
            logger.info("=" * 70)
            logger.info("ROZPOCZĘCIE PROCESU UWIERZYTELNIANIA KSEF API 2.0")
            logger.info(f"Środowisko: {self.company_info.ksef_environment}")
            logger.info(f"NIP: {self.nip}")
            logger.info("=" * 70)

            # Krok 1: Pobierz challenge
            logger.info("Krok 1/4: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            context = {"contextIdentifier": {"type": "NIP", "value": self.nip}}

            logger.info(f"URL: {challenge_url}")
            logger.info(f"Context: {context}")

            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]

            logger.info(f"✓ Challenge otrzymany (timestamp: {timestamp})")

            # Krok 2: Zaszyfruj token KSeF
            logger.info("Krok 2/4: Szyfrowanie tokena KSeF...")
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp
            )

            # Krok 3: Wyślij uwierzytelnienie
            logger.info("Krok 3/4: Wysyłanie uwierzytelnienia...")
            auth_url = f"{self.base_url}/auth/ksef-token"

            payload = {
                "challenge": challenge,
                "contextIdentifier": {"type": "NIP", "value": self.nip},
                "encryptedToken": encrypted_token,
            }

            logger.info(f"URL: {auth_url}")

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            
            # Szczegółowe logowanie odpowiedzi
            logger.info(f"Status odpowiedzi: {auth_response.status_code}")
            
            if auth_response.status_code != 201:
                error_detail = "Nieznany błąd"
                try:
                    error_json = auth_response.json()
                    error_detail = error_json
                    logger.error(f"Błąd API (JSON): {error_json}")
                except:
                    error_detail = auth_response.text[:500]
                    logger.error(f"Błąd API (text): {auth_response.text}")
                
                raise Exception(f"Błąd uwierzytelniania (status {auth_response.status_code}): {error_detail}")
            
            auth_response.raise_for_status()
            auth_data = auth_response.json()
            auth_ref = auth_data["referenceNumber"]

            logger.info(f"✓ Uwierzytelnienie wysłane: {auth_ref}")

            # Krok 4: Pobierz status uwierzytelnienia
            logger.info("Krok 4/4: Pobieranie statusu uwierzytelnienia...")
            time.sleep(2)

            status_url = f"{self.base_url}/auth/status/{auth_ref}"
            max_attempts = 10

            for attempt in range(max_attempts):
                status_response = requests.get(status_url, headers=headers, timeout=10)
                status_response.raise_for_status()
                status_data = status_response.json()

                status_code = status_data.get("status", {}).get("code")

                if status_code == 200:
                    self.access_token = status_data["authToken"]["accessToken"]
                    self.refresh_token = status_data["authToken"]["refreshToken"]

                    logger.info("✓ Uwierzytelnienie zakończone sukcesem")
                    logger.info(
                        f"  Access token: {self.access_token[:30]}... (długość: {len(self.access_token)})"
                    )
                    logger.info("=" * 70)
                    break

                elif status_code and status_code >= 400:
                    error_desc = status_data.get("status", {}).get(
                        "description", "Nieznany błąd"
                    )
                    logger.error(f"❌ Błąd uwierzytelniania: {error_desc}")
                    logger.error(f"Pełna odpowiedź: {status_data}")
                    raise Exception(f"Błąd uwierzytelniania: {error_desc}")

                else:
                    logger.info(
                        f"  Status: {status_code} - oczekiwanie... ({attempt + 1}/{max_attempts})"
                    )
                    time.sleep(2)

            if not self.access_token:
                raise Exception(
                    "Nie udało się uzyskać tokena dostępowego po maksymalnej liczbie prób"
                )

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_details = error_json
                    logger.error(f"❌ Błąd HTTP - JSON: {error_json}")
                except ValueError:
                    error_details = e.response.text[:500]
                    logger.error(f"❌ Błąd HTTP - text: {e.response.text}")

                logger.error(f"Status code: {e.response.status_code}")
                logger.error(f"Headers: {dict(e.response.headers)}")

            logger.error(f"❌ Błąd uwierzytelniania: {error_details}")
            raise Exception(f"Błąd uwierzytelniania KSeF API v2.0: {error_details}")

    def send_invoice(self, invoice_xml: str):
        """
        Wysyła fakturę do KSeF w trybie interaktywnym (online)
        
        Proces:
        1. Otwórz sesję online z szyfrowaniem AES
        2. Wyślij zaszyfrowaną fakturę
        3. Sprawdź status przetwarzania
        4. Zamknij sesję
        """
        try:
            # Uwierzytelnienie
            self._authenticate()

            # Generuj klucz AES do szyfrowania faktury
            self._generate_aes_key()

            logger.info("=" * 70)
            logger.info("WYSYŁANIE FAKTURY DO KSEF")
            logger.info("=" * 70)

            # Krok 1: Otwórz sesję online
            logger.info("Krok 1/4: Otwieranie sesji online...")
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
            time.sleep(3)

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
                    logger.info("✓ Faktura przetworzona pomyślnie")
                    break
                elif invoice_status and invoice_status >= 400:
                    error_desc = status_data.get("status", {}).get(
                        "description", "Nieznany błąd"
                    )
                    logger.error(f"❌ Błąd przetwarzania faktury: {error_desc}")
                    logger.error(f"Pełna odpowiedź: {status_data}")
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
                    error_json = e.response.json()
                    error_details = error_json
                    logger.error(f"❌ Błąd wysyłki - JSON: {error_json}")
                except ValueError:
                    error_details = e.response.text[:500]
                    logger.error(f"❌ Błąd wysyłki - text: {e.response.text}")
                
                logger.error(f"Status code: {e.response.status_code}")
            
            logger.error(f"❌ Błąd wysyłki faktury: {error_details}")
            raise Exception(f"Błąd wysyłki faktury do KSeF: {error_details}")
