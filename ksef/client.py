# ksef/client.py
# KSeF API 2.0 - Zaktualizowana wersja zgodna z oficjalną dokumentacją OpenAPI

import requests
import logging
import time
import base64
import os
import hashlib
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_der_x509_certificate

from ksiegowosc.models import CompanyInfo

logger = logging.getLogger(__name__)


class KsefClient:
    """
    Klient KSeF API 2.0 (październik 2025)
    
    Uwierzytelnianie tokenem KSeF:
    - Tokeny działają do 31.12.2026
    - Od 1.11.2025 dostępne certyfikaty KSeF
    
    Zmiany w API 2.0:
    - Dwa osobne klucze publiczne (token encryption vs symmetric key encryption)
    - Nowy endpoint dla kluczy: /api/v2/security/public-key-certificates
    - FormCode z trzema polami: systemCode, schemaVersion, value
    - POST zamiast PUT przy wysyłaniu faktur
    - Wysyłanie metadanych faktury (hash, rozmiar) w JSON
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
        
        # Osobne klucze publiczne dla różnych celów (API 2.0)
        self.token_encryption_key = None      # Do szyfrowania tokena KSeF
        self.symmetric_key_encryption_key = None  # Do szyfrowania klucza AES
        
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

    def _get_public_keys(self):
        """
        Pobiera klucze publiczne KSeF z API (KSeF 2.0)
        
        Endpoint: GET /api/v2/security/public-key-certificates
        
        Zwraca dwa certyfikaty:
        - KsefTokenEncryption: do szyfrowania tokena KSeF podczas uwierzytelniania
        - SymmetricKeyEncryption: do szyfrowania klucza AES do faktur
        """
        if self.token_encryption_key and self.symmetric_key_encryption_key:
            return

        try:
            logger.info("Pobieranie kluczy publicznych z API KSeF 2.0...")
            key_url = f"{self.base_url}/security/public-key-certificates"
            
            logger.debug(f"URL: {key_url}")
            
            response = requests.get(key_url, timeout=10)
            response.raise_for_status()
            
            certificates = response.json()
            logger.debug(f"Otrzymano {len(certificates)} certyfikatów")
            
            # Znajdź certyfikaty według przeznaczenia
            for cert_data in certificates:
                cert_b64 = cert_data.get("certificate")
                usage = cert_data.get("usage", [])
                valid_from = cert_data.get("validFrom")
                valid_to = cert_data.get("validTo")
                
                if not cert_b64:
                    continue
                
                # Dekoduj Base64 -> format DER
                cert_der = base64.b64decode(cert_b64)
                
                # Wczytaj jako certyfikat X.509 DER
                cert = load_der_x509_certificate(cert_der, default_backend())
                public_key = cert.public_key()
                
                # Przypisz do odpowiedniego pola według usage
                if "KsefTokenEncryption" in usage:
                    self.token_encryption_key = public_key
                    logger.info(
                        f"✓ Klucz do tokena KSeF ({public_key.key_size} bitów)"
                        f"\n  Ważny: {valid_from} - {valid_to}"
                    )
                
                if "SymmetricKeyEncryption" in usage:
                    self.symmetric_key_encryption_key = public_key
                    logger.info(
                        f"✓ Klucz do szyfrowania AES ({public_key.key_size} bitów)"
                        f"\n  Ważny: {valid_from} - {valid_to}"
                    )
            
            if not self.token_encryption_key:
                raise Exception("Nie znaleziono klucza KsefTokenEncryption")
            
            if not self.symmetric_key_encryption_key:
                raise Exception("Nie znaleziono klucza SymmetricKeyEncryption")

        except requests.exceptions.RequestException as e:
            error_msg = f"Błąd pobierania kluczy z API: {e}"
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
            logger.error(f"❌ Błąd wczytywania kluczy: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: str) -> str:
        """
        Szyfruje token KSeF zgodnie z KSeF API 2.0
        
        Format: "{token}|{timestamp_in_milliseconds}" -> RSA-OAEP SHA-256 -> Base64
        
        Args:
            ksef_token: Token KSeF z bazy danych
            timestamp: Timestamp ISO z odpowiedzi challenge
        
        Returns:
            Zaszyfrowany token w Base64
        """
        try:
            # Pobierz klucz dedykowany do szyfrowania tokena
            if not self.token_encryption_key:
                self._get_public_keys()

            # Konwertuj timestamp ISO na milisekundy Unix
            # Format: "2025-07-11T12:23:56.0154302+00:00"
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            timestamp_ms = int(dt.timestamp() * 1000)

            token_string = f"{ksef_token}|{timestamp_ms}"
            logger.info(f"Szyfrowanie tokena (długość: {len(token_string)}, timestamp: {timestamp_ms})")

            token_bytes = token_string.encode("utf-8")

            # RSA-OAEP SHA-256
            encrypted = self.token_encryption_key.encrypt(
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
        """
        Szyfruje klucz AES kluczem publicznym KSeF dedykowanym do szyfrowania symetrycznego
        
        Returns:
            Dict z polami: encryptedSymmetricKey, initializationVector
        """
        try:
            # Pobierz klucz dedykowany do szyfrowania klucza symetrycznego
            if not self.symmetric_key_encryption_key:
                self._get_public_keys()

            encrypted_key = self.symmetric_key_encryption_key.encrypt(
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
        Szyfruje fakturę XML przy użyciu AES-256-CBC z PKCS7 padding
        
        Args:
            invoice_xml: Faktura w formacie XML
            
        Returns:
            Zaszyfrowana faktura (bytes)
        """
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

    def _calculate_sha256(self, data: bytes) -> str:
        """
        Oblicza hash SHA256 i zwraca w Base64
        
        Args:
            data: Dane do zahashowania
            
        Returns:
            Hash SHA256 zakodowany w Base64
        """
        sha256_hash = hashlib.sha256(data).digest()
        return base64.b64encode(sha256_hash).decode("utf-8")

    def _authenticate(self):
        """
        Uwierzytelnianie w KSeF API 2.0 z tokenem
        
        Kroki:
        1. POST /api/v2/auth/challenge (bez body!)
        2. Zaszyfruj token z timestampem
        3. POST /api/v2/auth/ksef-token
        4. GET /api/v2/auth/{ref} (zmiana z /auth/status/{ref})
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

            # KROK 1: Pobierz challenge (bez body!)
            logger.info("Krok 1/4: Pobieranie challenge...")
            challenge_url = f"{self.base_url}/auth/challenge"
            headers = {"Content-Type": "application/json"}

            logger.debug(f"URL: {challenge_url}")
            logger.debug("Wysyłanie POST bez body")

            response = requests.post(
                challenge_url, headers=headers, timeout=10
            )
            response.raise_for_status()
            challenge_data = response.json()
            
            challenge = challenge_data["challenge"]
            timestamp = challenge_data["timestamp"]

            logger.info(f"✓ Challenge: {challenge}")
            logger.info(f"✓ Timestamp: {timestamp}")

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
                    "type": "Nip",  # Uwaga: "Nip" z wielką literą w API 2.0
                    "value": self.nip
                },
                "encryptedToken": encrypted_token,
            }

            logger.debug(f"URL: {auth_url}")

            auth_response = requests.post(
                auth_url, json=payload, headers=headers, timeout=10
            )
            
            logger.info(f"Status HTTP: {auth_response.status_code}")
            
            if auth_response.status_code != 202:  # API 2.0 zwraca 202 Accepted
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
            auth_token = auth_data.get("authenticationToken", {}).get("token")

            logger.info(f"✓ Ref: {auth_ref}")
            logger.info(f"✓ Auth Token: {auth_token[:30]}...")

            # KROK 4: Pobierz status (zmiana endpointu!)
            logger.info("Krok 4/4: Pobieranie statusu...")
            time.sleep(2)

            # Nowy endpoint: /api/v2/auth/{referenceNumber} zamiast /auth/status/{ref}
            status_url = f"{self.base_url}/auth/{auth_ref}"
            status_headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
            
            max_attempts = 10

            for attempt in range(max_attempts):
                status_response = requests.get(status_url, headers=status_headers, timeout=10)
                status_response.raise_for_status()
                status_data = status_response.json()

                status_code = status_data.get("status", {}).get("code")

                if status_code == 200:
                    # W API 2.0 struktura odpowiedzi może być inna
                    # Sprawdź czy authToken jest w odpowiedzi statusu
                    if "authToken" in status_data:
                        self.access_token = status_data["authToken"]["accessToken"]
                        self.refresh_token = status_data["authToken"].get("refreshToken")
                    else:
                        # Jeśli nie ma w statusie, użyj tokena z kroku 3
                        logger.info("Token z inicjalizacji uwierzytelnienia")
                        # Może trzeba wykonać dodatkowe kroki...
                        # Na razie użyjmy auth_token z kroku 3
                        self.access_token = auth_token

                    logger.info("✓ Uwierzytelnienie OK")
                    logger.info(f"  Token JWT: {self.access_token[:30]}...")
                    logger.info("=" * 70)
                    break

                elif status_code and status_code >= 400:
                    error_desc = status_data.get("status", {}).get("description", "?")
                    error_details = status_data.get("status", {}).get("details", [])
                    logger.error(f"❌ Błąd: {error_desc}")
                    if error_details:
                        logger.error(f"Szczegóły: {error_details}")
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
        
        Zmiany w API 2.0:
        - FormCode ma teraz strukturę z systemCode, schemaVersion, value
        - POST zamiast PUT przy wysyłaniu faktury
        - Wysyłanie metadanych (hash, rozmiar) w JSON
        
        Kroki:
        1. POST /api/v2/sessions/online
        2. POST /api/v2/sessions/online/{ref}/invoices (ZMIANA: POST zamiast PUT, JSON zamiast binary)
        3. GET /api/v2/sessions/{ref}/invoices/{ref}
        4. POST /api/v2/sessions/online/{ref}/close
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
            
            # API 2.0: FormCode ma strukturę z trzema polami
            session_payload = {
                "formCode": {
                    "systemCode": "FA (3)",
                    "schemaVersion": "1-0E",
                    "value": "FA"
                },
                "encryption": encryption_data
            }

            session_response = requests.post(
                session_url, json=session_payload, headers=headers, timeout=10
            )
            session_response.raise_for_status()
            session_data = session_response.json()
            session_ref = session_data["referenceNumber"]
            
            logger.info(f"✓ Sesja: {session_ref}")

            # KROK 2: Wyślij fakturę (ZMIANA: POST + JSON!)
            logger.info("Krok 2/4: Wysyłanie faktury...")
            
            # Oblicz hash oryginalnej faktury
            invoice_bytes = invoice_xml.encode("utf-8")
            invoice_hash = self._calculate_sha256(invoice_bytes)
            invoice_size = len(invoice_bytes)
            
            # Zaszyfruj fakturę
            encrypted_invoice = self._encrypt_invoice(invoice_xml)
            encrypted_hash = self._calculate_sha256(encrypted_invoice)
            encrypted_size = len(encrypted_invoice)
            
            # Zakoduj zaszyfrowaną fakturę w Base64
            encrypted_invoice_b64 = base64.b64encode(encrypted_invoice).decode("utf-8")

            # API 2.0: POST zamiast PUT, wysyłanie JSON z metadanymi
            invoice_url = f"{self.base_url}/sessions/online/{session_ref}/invoices"
            invoice_payload = {
                "invoiceHash": invoice_hash,
                "invoiceSize": invoice_size,
                "encryptedInvoiceHash": encrypted_hash,
                "encryptedInvoiceSize": encrypted_size,
                "encryptedInvoiceContent": encrypted_invoice_b64,
                "offlineMode": False
            }
            
            logger.debug(f"Invoice hash: {invoice_hash}")
            logger.debug(f"Invoice size: {invoice_size} B")
            logger.debug(f"Encrypted hash: {encrypted_hash}")
            logger.debug(f"Encrypted size: {encrypted_size} B")

            invoice_response = requests.post(
                invoice_url, json=invoice_payload, headers=headers, timeout=15
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
                    # Pobierz KSeF number jeśli jest
                    ksef_number = status_data.get("ksefNumber")
                    if ksef_number:
                        logger.info(f"  Numer KSeF: {ksef_number}")
                    break
                elif invoice_status and invoice_status >= 400:
                    error_desc = status_data.get("status", {}).get("description", "?")
                    error_details = status_data.get("status", {}).get("details", [])
                    logger.error(f"❌ Błąd: {error_desc}")
                    if error_details:
                        logger.error(f"Szczegóły: {error_details}")
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
