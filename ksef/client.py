# ksef/client.py
# KSeF API 2.0 - aktualny stan na październik 2025

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
    Klient KSeF API 2.0 (wrzesień 2025)
    
    Uwierzytelnianie tokenem KSeF:
    - Tokeny działają do 31.12.2026
    - Od 1.11.2025 dostępne certyfikaty KSeF (MCU)
    - Od 1.01.2027 tylko certyfikaty
    
    Środowisko testowe uruchomione: 30.09.2025
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
                "Brak tokena KSeF. Wygeneruj token w Aplikacji Podatnika KSeF.\n"
                "Od 1 listopada 2025 będziesz mógł użyć certyfikatu KSeF przez MCU."
            )

        # URL dla KSeF 2.0 (od 30.09.2025)
        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        # Ścieżka do kluczy publicznych
        self.key_dir = Path("/home/fakturownia/app/ksef-pubkey")

        # Znormalizuj NIP
        self.nip = self._normalize_nip(self.company_info.tax_id)

        # Tokeny uwierzytelniania
        self.access_token = None
        self.refresh_token = None
        self.public_key_cert = None
        
        # Klucze szyfrowania
        self.aes_key = None
        self.aes_iv = None

    def _normalize_nip(self, nip: str) -> str:
        """Normalizuje NIP do formatu 10 cyfr"""
        if not nip:
            raise Exception("Brak numeru NIP")

        normalized = nip.replace("-", "").replace(" ", "").strip()

        if not normalized.isdigit() or len(normalized) != 10:
            raise Exception(f"Nieprawidłowy format NIP: {nip}. Wymagane 10 cyfr.")

        logger.info(f"NIP znormalizowany: {nip} -> {normalized}")
        return normalized

    def _get_public_key(self):
        """
        Pobiera klucz publiczny KSeF do szyfrowania
        
        Środowisko testowe:
        - Lokalny plik: publicKey.pem
        - Lub endpoint: /api/v2/common/Encryption/PublicKey
        
        Klucz testowy: https://ksef-test.mf.gov.pl/web/formularze/ksef-test-encryption-public-key.pem
        """
        if self.public_key_cert:
            return self.public_key_cert

        try:
            logger.info("Pobieranie klucza publicznego KSeF...")

            # 1. Spróbuj lokalny plik (szybsze dla środowiska testowego)
            pem_file = self.key_dir / "publicKey.pem"
            
            if pem_file.exists():
                with open(pem_file, "rb") as f:
                    key_data = f.read()
                
                logger.info(f"Wczytywanie lokalnego klucza: {pem_file}")
                
                # Próbuj jako certyfikat X.509
                try:
                    cert = load_pem_x509_certificate(key_data, default_backend())
                    self.public_key_cert = cert.public_key()
                    logger.info(
                        f"✓ Klucz lokalny (certyfikat X.509, {self.public_key_cert.key_size} bitów)"
                    )
                    return self.public_key_cert
                except Exception:
                    # Próbuj jako surowy klucz publiczny
                    from cryptography.hazmat.primitives.serialization import load_pem_public_key
                    
                    self.public_key_cert = load_pem_public_key(key_data, default_backend())
                    logger.info(
                        f"✓ Klucz lokalny (PEM, {self.public_key_cert.key_size} bitów)"
                    )
                    return self.public_key_cert
            
            # 2. Pobierz z API KSeF 2.0
            logger.info("Pobieranie klucza z API KSeF 2.0...")
            key_url = f"{self.base_url}/common/Encryption/PublicKey"
            
            response = requests.get(key_url, timeout=10)
            response.raise_for_status()
            
            key_data_json = response.json()
            key_pem = key_data_json.get("publicKey")
            
            if not key_pem:
                raise Exception("API nie zwróciło klucza publicznego")
            
            # Może być zakodowany Base64
            if not key_pem.startswith("-----BEGIN"):
                key_pem = base64.b64decode(key_pem).decode('utf-8')
            
            key_bytes = key_pem.encode('utf-8')
            
            # Wczytaj klucz
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
                    f"✓ Klucz z API (PEM, {self.public_key_cert.key_size} bitów)"
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
            
            # Wskazówka dla środowiska testowego
            if self.company_info.ksef_environment == "test":
                pem_file = self.key_dir / "publicKey.pem"
                logger.error(
                    f"\n💡 Dla środowiska testowego pobierz klucz:\n"
                    f"   mkdir -p {self.key_dir}\n"
                    f"   curl -o {pem_file} https://ksef-test.mf.gov.pl/web/formularze/ksef-test-encryption-public-key.pem"
                )
            
            raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania klucza: {e}")
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: int) -> str:
        """
        Szyfruje token KSeF zgodnie z KSeF API 2.0
        
        Format: "{token}|{timestamp}"
        Algorytm: RSA-OAEP SHA-256
        Kodowanie: Base64
        
        Tokeny działają do 31.12.2026
        """
        try:
            public_key = self._get_public_key()

            # String do zaszyfrowania
            token_string = f"{ksef_token}|{timestamp}"
            logger.info(
                f"Szyfrowanie tokena (długość: {len(token_string)} znaków)"
            )

            token_bytes = token_string.encode("utf-8")

            # RSA-OAEP SHA-256
            encrypted = public_key.encrypt(
                token_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            # Base64
            encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
            logger.info(
                f"✓ Token zaszyfrowany ({len(encrypted)} bajtów → {len(encrypted_b64)} znaków Base64)"
            )

            return encrypted_b64

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania tokena: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _generate_aes_key(self):
        """Generuje klucz AES-256 i IV dla szyfrowania faktur"""
        self.aes_key = os.urandom(32)  # 256 bitów
        self.aes_iv = os.urandom(16)   # 128 bitów
        logger.info("✓ Wygenerowano klucz AES-256 i IV")

    def _encrypt_aes_key(self) -> dict:
        """
        Szyfruje klucz AES kluczem publicznym KSeF
        Zwraca zaszyfrowany klucz i IV w Base64
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
                "encryptedSymmetricKey": base64.b64encode(encrypted_key).decode("utf-8"),
                "initializationVector": base64.b64encode(self.aes_iv).decode("utf-8"),
            }

            logger.info("✓ Klucz AES zaszyfrowany")
            return result

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania klucza AES: {e}")
            raise

    def _encrypt_invoice(self, invoice_xml: str) -> bytes:
        """
        Szyfruje fakturę XML przy użyciu AES-256-CBC z PKCS7
        
        W KSeF 2.0 wszystkie faktury muszą być zaszyfrowane lokalnie
        """
        try:
            # XML do bajtów UTF-8
            invoice_bytes = invoice_xml.encode("utf-8")

            # Szyfr AES-256-CBC
            cipher = Cipher(
                algorithms.AES(self.aes_key),
                modes.CBC(self.aes_iv),
                backend=default_backend(),
            )

            encryptor = cipher.encryptor()

            # Padding PKCS7
            padding_length = 16 - (len(invoice_bytes) % 16)
            padded_data = invoice_bytes + bytes([padding_length] * padding_length)

            # Szyfrowanie
            encrypted = encryptor.update(padded_data) + encryptor.finalize()

            logger.info(
                f"✓ Faktura zaszyfrowana AES-256-CBC ({len(encrypted)} bajtów)"
            )
            return encrypted

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania faktury: {e}")
            raise

    def _authenticate(self):
        """
        Uwierzytelnianie w KSeF API 2.0 z tokenem
        
        Proces (4 kroki):
        1. POST /auth/challenge - pobierz challenge
        2. Zaszyfruj token RSA-OAEP SHA-256
        3. POST /auth/ksef-token - wyślij uwierzytelnienie
        4. GET /auth/status/{ref} - pobierz access token (JWT)
        """
        if self.access_token:
            logger.info("Token dostępowy już istnieje")
            return

        try:
            logger.info("=" * 70)
            logger.info("UWIERZYTELNIANIE W KSEF API 2.0")
            logger.info(f"Środowisko: {self.company_info.ksef_environment}")
            logger.info(f"NIP: {self.nip}")
            logger.info("=" * 70)

            # KROK 1: Pobierz challenge
            logger.info("Krok 1/4: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            # WAŻNE: W API 2.0 używamy "value" nie "identifier"
            context = {
                "contextIdentifier": {
                    "type": "NIP",
                    "value": self.nip  # <-- POPRAWNE dla API 2.0
                }
            }

            logger.debug(f"URL: {challenge_url}")
            logger.debug(f"Payload: {context}")

            response = requests.post(
                challenge_url, json=context, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()
            
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]

            logger.info(f"✓ Challenge otrzymany (timestamp: {timestamp})")

            # KROK 2: Zaszyfruj token KSeF
            logger.info("Krok 2/4: Szyfrowanie tokena KSeF...")
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp
            )

            # KROK 3: Wyślij uwierzytelnienie
            logger.info("Krok 3/4: Wysyłanie uwierzytelnienia...")
            auth_url = f"{self.base_url}/auth/ksef-token"

            # WAŻNE: Wszystkie pola są wymagane
            payload = {
                "challenge": challenge,
                "contextIdentifier": {
                    "type": "NIP",
                    "value": self.nip  # <-- POPRAWNE dla API 2.0
                },
                "encryptedToken": encrypted_token,
            }

            logger.debug(f"URL: {auth_url}")

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            
            # Szczegółowe logowanie
            logger.info(f"Status HTTP: {auth_response.status_code}")
            
            if auth_response.status_code != 201:
                error_detail = "Nieznany błąd"
                try:
                    error_json = auth_response.json()
                    error_detail = error_json
                    logger.error(f"Błąd API: {error_json}")
                except:
                    error_detail = auth_response.text
                    logger.error(f"Błąd API (text): {auth_response.text}")
                
                raise Exception(
                    f"Błąd uwierzytelniania (HTTP {auth_response.status_code}): {error_detail}"
                )
            
            auth_response.raise_for_status()
            auth_data = auth_response.json()
            auth_ref = auth_data["referenceNumber"]

            logger.info(f"✓ Uwierzytelnienie wysłane: {auth_ref}")

            # KROK 4: Pobierz status i tokeny
            logger.info("Krok 4/4: Pobieranie statusu...")
            time.sleep(2)

            status_url = f"{self.base_url}/auth/status/{auth_ref}"
            max_attempts = 10

            for attempt in range(max_attempts):
                status_response = requests.get(status_url, headers=headers, timeout=10)
                status_response.raise_for_status()
                status_data = status_response.json()

                status_code = status_data.get("status", {}).get("code")

                if status_code == 200:
                    # Sukces!
                    self.access_token = status_data["authToken"]["accessToken"]
                    self.refresh_token = status_data["authToken"]["refreshToken"]

                    logger.info("✓ Uwierzytelnienie zakończone sukcesem")
                    logger.info(
                        f"  Access token (JWT): {self.access_token[:30]}... "
                        f"(długość: {len(self.access_token)})"
                    )
                    logger.info("=" * 70)
                    break

                elif status_code and status_code >= 400:
                    # Błąd
                    error_desc = status_data.get("status", {}).get(
                        "description", "Nieznany błąd"
                    )
                    logger.error(f"❌ Błąd uwierzytelniania: {error_desc}")
                    logger.error(f"Pełna odpowiedź: {status_data}")
                    raise Exception(f"Błąd uwierzytelniania: {error_desc}")

                else:
                    # Oczekiwanie
                    logger.info(
                        f"  Status: {status_code} - oczekiwanie... "
                        f"({attempt + 1}/{max_attempts})"
                    )
                    time.sleep(2)

            if not self.access_token:
                raise Exception(
                    "Nie udało się uzyskać tokena dostępowego"
                )

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_details = error_json
                    logger.error(f"❌ Błąd HTTP - JSON: {error_json}")
                except ValueError:
                    error_details = e.response.text
                    logger.error(f"❌ Błąd HTTP - text: {e.response.text[:500]}")

                logger.error(f"Status HTTP: {e.response.status_code}")

            logger.error(f"❌ Błąd uwierzytelniania: {error_details}")
            raise Exception(f"Błąd uwierzytelniania KSeF API 2.0: {error_details}")

    def send_invoice(self, invoice_xml: str):
        """
        Wysyła fakturę do KSeF 2.0 w trybie online
        
        Proces:
        1. Otwórz sesję online (POST /sessions/online)
        2. Wyślij zaszyfrowaną fakturę (PUT /sessions/online/{ref}/invoices)
        3. Sprawdź status (GET /sessions/{ref}/invoices/{ref})
        4. Zamknij sesję (POST /sessions/online/{ref}/close)
        """
        try:
            # Uwierzytelnienie
            self._authenticate()

            # Generuj klucz AES
            self._generate_aes_key()

            logger.info("=" * 70)
            logger.info("WYSYŁANIE FAKTURY DO KSEF 2.0")
            logger.info("=" * 70)

            # KROK 1: Otwórz sesję
            logger.info("Krok 1/4: Otwieranie sesji online...")
            session_url = f"{self.base_url}/sessions/online"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }

            encryption_data = self._encrypt_aes_key()
            session_payload = {
                "formCode": "FA(3)",  # Schemat FA(3) dla KSeF 2.0
                "encryption": encryption_data
            }

            session_response = requests.post(
                session_url, json=session_payload, headers=headers, timeout=10
            )
            session_response.raise_for_status()
            session_data = session_response.json()
            session_ref = session_data["referenceNumber"]
            
            logger.info(f"✓ Sesja otwarta: {session_ref}")

            # KROK 2: Wyślij fakturę
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

            # KROK 3: Sprawdź status
            logger.info("Krok 3/4: Sprawdzanie statusu faktury...")
            time.sleep(3)

            status_url = f"{self.base_url}/sessions/{session_ref}/invoices/{invoice_ref}"
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
                    logger.error(f"❌ Błąd przetwarzania: {error_desc}")
                    logger.error(f"Pełna odpowiedź: {status_data}")
                    break
                else:
                    logger.info(
                        f"  Status: {invoice_status} - oczekiwanie... "
                        f"({attempt + 1}/{max_attempts})"
                    )
                    time.sleep(2)

            # KROK 4: Zamknij sesję
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
                    logger.error(f"❌ Błąd - JSON: {error_json}")
                except ValueError:
                    error_details = e.response.text
                    logger.error(f"❌ Błąd - text: {e.response.text[:500]}")
                
                logger.error(f"Status HTTP: {e.response.status_code}")
            
            logger.error(f"❌ Błąd wysyłki faktury: {error_details}")
            raise Exception(f"Błąd wysyłki faktury do KSeF 2.0: {error_details}")
