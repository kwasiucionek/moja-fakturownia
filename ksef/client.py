# ksef/client.py
# KSeF API 2.0 - pobieranie klucza tylko z API

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
from cryptography.x509 import load_pem_x509_certificate

from ksiegowosc.models import CompanyInfo

logger = logging.getLogger(__name__)


class KsefClient:
    """
    Klient KSeF API 2.0 (wrzesień 2025)
    
    Uwierzytelnianie tokenem KSeF:
    - Tokeny działają do 31.12.2026
    - Od 1.11.2025 dostępne certyfikaty KSeF
    """
    
    def __init__(self, user):
        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception("Brak danych firmy (CompanyInfo).")

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF. Wygeneruj w Aplikacji Podatnika.")

        # URL dla KSeF 2.0
        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        # Znormalizuj NIP
        self.nip = self._normalize_nip(self.company_info.tax_id)

        # Tokeny
        self.access_token = None
        self.refresh_token = None
        self.public_key_cert = None
        
        # Klucze szyfrowania
        self.aes_key = None
        self.aes_iv = None

    def _normalize_nip(self, nip: str) -> str:
        """Normalizuje NIP do 10 cyfr"""
        if not nip:
            raise Exception("Brak numeru NIP")

        normalized = nip.replace("-", "").replace(" ", "").strip()

        if not normalized.isdigit() or len(normalized) != 10:
            raise Exception(f"Nieprawidłowy NIP: {nip}. Wymagane 10 cyfr.")

        logger.info(f"NIP znormalizowany: {nip} -> {normalized}")
        return normalized

    def _get_public_key(self):
        """
        Pobiera klucz publiczny KSeF z API do szyfrowania
        
        Endpoint: GET /api/v2/common/Encryption/PublicKey
        """
        if self.public_key_cert:
            return self.public_key_cert

        try:
            logger.info("Pobieranie klucza publicznego z API KSeF 2.0...")
            key_url = f"{self.base_url}/common/Encryption/PublicKey"
            
            logger.debug(f"URL: {key_url}")
            
            response = requests.get(key_url, timeout=10)
            response.raise_for_status()
            
            key_data_json = response.json()
            logger.debug(f"Otrzymano odpowiedź z polami: {list(key_data_json.keys())}")
            
            # Pobierz klucz z JSON
            key_pem = key_data_json.get("publicKey")
            
            if not key_pem:
                raise Exception("API nie zwróciło pola 'publicKey'")
            
            logger.debug(f"Klucz (pierwsze 50 znaków): {key_pem[:50]}...")
            
            # Jeśli zakodowany Base64, zdekoduj
            if not key_pem.startswith("-----BEGIN"):
                logger.debug("Dekodowanie z Base64...")
                key_pem = base64.b64decode(key_pem).decode('utf-8')
            
            key_bytes = key_pem.encode('utf-8')
            
            # Wczytaj jako certyfikat X.509
            try:
                cert = load_pem_x509_certificate(key_bytes, default_backend())
                self.public_key_cert = cert.public_key()
                logger.info(
                    f"✓ Klucz z API (certyfikat X.509, {self.public_key_cert.key_size} bitów)"
                )
            except Exception as e:
                # Próbuj jako surowy klucz PEM
                logger.debug(f"Nie jest certyfikatem X.509, próbuję jako klucz PEM...")
                from cryptography.hazmat.primitives.serialization import load_pem_public_key
                
                self.public_key_cert = load_pem_public_key(key_bytes, default_backend())
                logger.info(
                    f"✓ Klucz z API (PEM, {self.public_key_cert.key_size} bitów)"
                )
            
            return self.public_key_cert

        except requests.exceptions.RequestException as e:
            error_msg = f"Błąd pobierania klucza z API: {e}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f"\nStatus HTTP: {e.response.status_code}"
                try:
                    error_json = e.response.json()
                    error_msg += f"\nOdpowiedź JSON: {error_json}"
                except:
                    error_msg += f"\nOdpowiedź text: {e.response.text[:300]}"
            
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania klucza: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: int) -> str:
        """
        Szyfruje token KSeF zgodnie z KSeF API 2.0
        Format: "{token}|{timestamp}" -> RSA-OAEP SHA-256 -> Base64
        """
        try:
            public_key = self._get_public_key()

            token_string = f"{ksef_token}|{timestamp}"
            logger.info(f"Szyfrowanie tokena (długość: {len(token_string)})")

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

            encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")
            logger.info(
                f"✓ Token zaszyfrowany ({len(encrypted)} B → {len(encrypted_b64)} znaków Base64)"
            )

            return encrypted_b64

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania tokena: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _generate_aes_key(self):
        """Generuje klucz AES-256 i IV"""
        self.aes_key = os.urandom(32)  # 256 bitów
        self.aes_iv = os.urandom(16)   # 128 bitów
        logger.info("✓ Wygenerowano klucz AES-256 i IV")

    def _encrypt_aes_key(self) -> dict:
        """Szyfruje klucz AES kluczem publicznym KSeF"""
        try:
            public_key = self._get_public_key()

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
        """Szyfruje fakturę XML przy użyciu AES-256-CBC"""
        try:
            invoice_bytes = invoice_xml.encode("utf-8")

            cipher = Cipher(
                algorithms.AES(self.aes_key),
                modes.CBC(self.aes_iv),
                backend=default_backend(),
            )

            encryptor = cipher.encryptor()

            # PKCS7 padding
            padding_length = 16 - (len(invoice_bytes) % 16)
            padded_data = invoice_bytes + bytes([padding_length] * padding_length)

            encrypted = encryptor.update(padded_data) + encryptor.finalize()

            logger.info(f"✓ Faktura zaszyfrowana AES-256-CBC ({len(encrypted)} B)")
            return encrypted

        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania faktury: {e}")
            raise

    def _authenticate(self):
        """
        Uwierzytelnianie w KSeF API 2.0 z tokenem
        
        4 kroki:
        1. POST /auth/challenge
        2. Zaszyfruj token
        3. POST /auth/ksef-token
        4. GET /auth/status/{ref}
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

            context = {
                "contextIdentifier": {
                    "type": "NIP",
                    "value": self.nip
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

            logger.info(f"✓ Challenge: {timestamp}")

            # KROK 2: Zaszyfruj token
            logger.info("Krok 2/4: Szyfrowanie tokena KSeF...")
            encrypted_token = self._encrypt_ksef_token(
                self.company_info.ksef_token, timestamp
            )

            # KROK 3: Wyślij uwierzytelnienie
            logger.info("Krok 3/4: Wysyłanie uwierzytelnienia...")
            auth_url = f"{self.base_url}/auth/ksef-token"

            payload = {
                "challenge": challenge,
                "contextIdentifier": {
                    "type": "NIP",
                    "value": self.nip
                },
                "encryptedToken": encrypted_token,
            }

            logger.debug(f"URL: {auth_url}")

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            
            logger.info(f"Status HTTP: {auth_response.status_code}")
            
            if auth_response.status_code != 201:
                try:
                    error_json = auth_response.json()
                    logger.error(f"Błąd API: {error_json}")
                    raise Exception(f"Błąd uwierzytelniania: {error_json}")
                except:
                    logger.error(f"Błąd API: {auth_response.text}")
                    raise Exception(f"Błąd uwierzytelniania: {auth_response.text[:300]}")
            
            auth_response.raise_for_status()
            auth_data = auth_response.json()
            auth_ref = auth_data["referenceNumber"]

            logger.info(f"✓ Ref: {auth_ref}")

            # KROK 4: Pobierz status
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
                    self.access_token = status_data["authToken"]["accessToken"]
                    self.refresh_token = status_data["authToken"]["refreshToken"]

                    logger.info("✓ Uwierzytelnienie OK")
                    logger.info(f"  Token JWT: {self.access_token[:30]}...")
                    logger.info("=" * 70)
                    break

                elif status_code and status_code >= 400:
                    error_desc = status_data.get("status", {}).get("description", "?")
                    logger.error(f"❌ Błąd: {error_desc}")
                    logger.error(f"Odpowiedź: {status_data}")
                    raise Exception(f"Błąd uwierzytelniania: {error_desc}")

                else:
                    logger.info(f"  Status: {status_code} ({attempt + 1}/{max_attempts})")
                    time.sleep(2)

            if not self.access_token:
                raise Exception("Nie uzyskano tokena dostępowego")

        except requests.exceptions.RequestException as e:
            error_details = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_details = e.response.json()
                    logger.error(f"❌ Błąd HTTP JSON: {error_details}")
                except ValueError:
                    error_details = e.response.text[:500]
                    logger.error(f"❌ Błąd HTTP text: {error_details}")

                logger.error(f"Status: {e.response.status_code}")

            raise Exception(f"Błąd uwierzytelniania: {error_details}")

    def send_invoice(self, invoice_xml: str):
        """
        Wysyła fakturę do KSeF 2.0 w trybie online
        
        4 kroki:
        1. POST /sessions/online
        2. PUT /sessions/online/{ref}/invoices
        3. GET /sessions/{ref}/invoices/{ref}
        4. POST /sessions/online/{ref}/close
        """
        try:
            self._authenticate()
            self._generate_aes_key()

            logger.info("=" * 70)
            logger.info("WYSYŁANIE FAKTURY DO KSEF 2.0")
            logger.info("=" * 70)

            # KROK 1: Otwórz sesję
            logger.info("Krok 1/4: Otwieranie sesji...")
            session_url = f"{self.base_url}/sessions/online"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }

            encryption_data = self._encrypt_aes_key()
            session_payload = {
                "formCode": "FA(3)",
                "encryption": encryption_data
            }

            session_response = requests.post(
                session_url, json=session_payload, headers=headers, timeout=10
            )
            session_response.raise_for_status()
            session_data = session_response.json()
            session_ref = session_data["referenceNumber"]
            
            logger.info(f"✓ Sesja: {session_ref}")

            # KROK 2: Wyślij fakturę
            logger.info("Krok 2/4: Wysyłanie faktury...")
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
            logger.info(f"✓ Faktura: {invoice_ref}")

            # KROK 3: Sprawdź status
            logger.info("Krok 3/4: Sprawdzanie statusu...")
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
                    logger.info("✓ Faktura przetworzona")
                    break
                elif invoice_status and invoice_status >= 400:
                    error_desc = status_data.get("status", {}).get("description", "?")
                    logger.error(f"❌ Błąd: {error_desc}")
                    logger.error(f"Odpowiedź: {status_data}")
                    break
                else:
                    logger.info(f"  Status: {invoice_status} ({attempt + 1}/{max_attempts})")
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
            logger.info("SUKCES!")
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
                    logger.error(f"❌ JSON: {error_details}")
                except ValueError:
                    error_details = e.response.text[:500]
                    logger.error(f"❌ text: {error_details}")
                
                logger.error(f"Status: {e.response.status_code}")
            
            raise Exception(f"Błąd wysyłki faktury: {error_details}")
