# ksef/client.py

import base64
import hashlib
import json
import logging
import os
from datetime import datetime

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509 import load_pem_x509_certificate
from django.utils import timezone

from ksiegowosc.models import CompanyInfo

logger = logging.getLogger(__name__)


class KsefClient:
    def __init__(self, user):
        """
        Inicjalizacja klienta KSeF dla API v2.0.
        """
        self.user = user
        try:
            self.company_info = CompanyInfo.objects.get(user=self.user)
        except CompanyInfo.DoesNotExist:
            logger.error(f"Użytkownik {user.username} nie posiada przypisanych danych firmy.")
            raise Exception("Użytkownik nie posiada uzupełnionych danych firmy.")

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF w danych firmy. Wygeneruj go w Aplikacji Podatnika.")

        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://api-test.ksef.mf.gov.pl/v2"
        elif env == "demo":
            self.base_url = "https://api-demo.ksef.mf.gov.pl/v2"
        else:
            self.base_url = "https://api.ksef.mf.gov.pl/v2"

        self.session = requests.Session()
        self.nip = self._normalize_nip(self.company_info.tax_id)
        self.token = self.company_info.ksef_token

        # Tokeny JWT z API 2.0
        self.access_token = None
        self.refresh_token = None
        self.session_reference = None
        
        # Szyfrowanie - klucz AES i IV generowane przy sesji
        self.aes_key = None
        self.aes_iv = None

    def _normalize_nip(self, nip_str):
        """Usuwa znaki niebędące cyframi z numeru NIP."""
        if not nip_str:
            return ""
        return "".join(filter(str.isdigit, nip_str))

    def _get_public_key(self, usage="KsefTokenEncryption"):
        """
        Pobiera certyfikat klucza publicznego z KSeF API 2.0.
        usage: 'KsefTokenEncryption' lub 'KsefSessionEncryption'
        """
        url = f"{self.base_url}/security/public-key-certificates"

        try:
            logger.debug(f"Pobieranie certyfikatów z: {url}")
            response = self.session.get(url)
            response.raise_for_status()

            certs = response.json()
            if not certs:
                raise Exception("API zwróciło pustą listę certyfikatów.")

            # Wyszukiwanie certyfikatu o odpowiednim przeznaczeniu
            cert_data = next(
                (c for c in certs if usage in c.get("usage", [])),
                certs[0]
            )

            cert_pem = cert_data['certificate']

            if "BEGIN CERTIFICATE" not in cert_pem:
                cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_pem}\n-----END CERTIFICATE-----"

            cert_obj = load_pem_x509_certificate(cert_pem.encode(), default_backend())
            return cert_obj.public_key()

        except Exception as e:
            error_msg = f"Błąd pobierania klucza publicznego: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

    def _encrypt_token(self, challenge_timestamp):
        """
        Szyfruje token KSeF algorytmem RSA-OAEP (SHA-256).
        """
        try:
            public_key = self._get_public_key("KsefTokenEncryption")

            # Format: token|timestamp_ms
            combined = f"{self.token}|{challenge_timestamp}"

            encrypted = public_key.encrypt(
                combined.encode(),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"❌ Błąd szyfrowania tokena: {str(e)}")
            raise

    def _generate_encryption_data(self):
        """
        Generuje klucz symetryczny AES-256 (32 bajty) i IV (16 bajtów).
        Oba są generowane raz przy otwieraniu sesji.
        """
        self.aes_key = os.urandom(32)
        self.aes_iv = os.urandom(16)
        return self.aes_key, self.aes_iv

    def _encrypt_aes_key(self):
        """
        Szyfruje klucz AES algorytmem RSA-OAEP kluczem publicznym KSeF.
        """
        if not self.aes_key:
            self._generate_encryption_data()

        public_key = self._get_public_key("KsefSessionEncryption")

        encrypted = public_key.encrypt(
            self.aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(encrypted).decode()

    def _encrypt_invoice(self, xml_content):
        """
        Szyfruje fakturę algorytmem AES-256-CBC z PKCS#7 padding.
        Używa IV wygenerowanego przy otwieraniu sesji.
        """
        if not self.aes_key or not self.aes_iv:
            raise Exception("Brak klucza AES/IV. Najpierw otwórz sesję.")

        # PKCS#7 padding
        padder = sym_padding.PKCS7(128).padder()
        xml_bytes = xml_content.encode('utf-8')
        padded_data = padder.update(xml_bytes) + padder.finalize()

        # Szyfrowanie AES-256-CBC
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()

        return base64.b64encode(encrypted).decode()

    def _authenticate(self):
        """
        Pełny proces uwierzytelniania API 2.0:
        1. Pobiera challenge
        2. Wysyła zaszyfrowany token
        3. Czeka na zakończenie uwierzytelnienia (polling statusu)
        4. Wymienia authenticationToken na accessToken (redeem)
        """
        import time
        
        # Krok 1: Challenge
        challenge_url = f"{self.base_url}/auth/challenge"
        payload = {
            "contextIdentifier": {
                "type": "Nip",
                "value": self.nip
            }
        }

        logger.info(f"[1/4] Pobieranie challenge dla NIP: {self.nip}")
        resp_challenge = self.session.post(challenge_url, json=payload)
        resp_challenge.raise_for_status()

        challenge_data = resp_challenge.json()
        challenge_token = challenge_data['challenge']
        timestamp_ms = challenge_data['timestampMs']

        # Krok 2: Uwierzytelnienie tokenem KSeF
        encrypted_token = self._encrypt_token(timestamp_ms)

        auth_url = f"{self.base_url}/auth/ksef-token"
        auth_payload = {
            "challenge": challenge_token,
            "contextIdentifier": {
                "type": "Nip",
                "value": self.nip
            },
            "encryptedToken": encrypted_token
        }

        logger.info("[2/4] Wysyłanie zaszyfrowanego tokena (auth/ksef-token)")
        resp_auth = self.session.post(auth_url, json=auth_payload)
        resp_auth.raise_for_status()

        auth_data = resp_auth.json()
        auth_token = auth_data['authenticationToken']['token']
        auth_reference = auth_data.get('referenceNumber')

        logger.info(f"✓ Otrzymano authenticationToken, ref: {auth_reference}")

        # Aktualizacja nagłówka z authenticationToken
        self.session.headers.update({
            'Authorization': f'Bearer {auth_token}'
        })

        # Krok 3: Polling statusu uwierzytelnienia
        status_url = f"{self.base_url}/auth/status/{auth_reference}"
        
        logger.info("[3/4] Oczekiwanie na zatwierdzenie w aplikacji...")
        max_attempts = 60
        for attempt in range(max_attempts):
            resp_status = self.session.get(status_url)
            resp_status.raise_for_status()
            
            status_data = resp_status.json()
            status_code = status_data.get('status', {}).get('code')
            status_desc = status_data.get('status', {}).get('description', '')
            
            logger.debug(f"Status uwierzytelnienia: {status_code} - {status_desc}")
            
            if status_code == 200:
                logger.info("✓ Uwierzytelnianie zakończone sukcesem")
                break
            elif status_code == 100:
                # W toku - czekamy
                time.sleep(1)
                continue
            else:
                # Błąd (np. 400, 415)
                details = status_data.get('status', {}).get('details', [])
                raise Exception(f"Uwierzytelnianie nieudane ({status_code}): {status_desc}. {details}")
        else:
            raise Exception("Przekroczono czas oczekiwania na uwierzytelnienie")

        # Krok 4: Wymiana authenticationToken na accessToken (redeem)
        redeem_url = f"{self.base_url}/auth/token/redeem"

        logger.info("[4/4] Wymiana tokena na accessToken (auth/token/redeem)")
        resp_redeem = self.session.post(redeem_url)
        resp_redeem.raise_for_status()

        redeem_data = resp_redeem.json()
        
        # accessToken jest obiektem z polami 'token' i 'validUntil'
        access_token_obj = redeem_data['accessToken']
        if isinstance(access_token_obj, dict):
            self.access_token = access_token_obj['token']
        else:
            self.access_token = access_token_obj
            
        refresh_token_obj = redeem_data.get('refreshToken')
        if isinstance(refresh_token_obj, dict):
            self.refresh_token = refresh_token_obj.get('token')
        else:
            self.refresh_token = refresh_token_obj

        # Aktualizacja nagłówków z prawidłowym accessToken (sam string JWT)
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}'
        })

        logger.info("✓ Pomyślnie uzyskano accessToken (API 2.0)")
        
        # Sprawdź uprawnienia (dla debugowania)
        self._check_permissions()
        
        return redeem_data

    def _check_permissions(self):
        """Sprawdza i loguje własne uprawnienia w KSeF."""
        try:
            perms_url = f"{self.base_url}/permissions/query/personal/grants"
            resp = self.session.post(perms_url, json={})
            
            if resp.status_code == 200:
                data = resp.json()
                permissions = data.get('permissions', [])
                if permissions:
                    perm_list = [p.get('permissionScope') for p in permissions]
                    logger.info(f"✓ Uprawnienia użytkownika: {perm_list}")
                else:
                    logger.warning("⚠ Brak uprawnień! Token może nie mieć InvoiceWrite.")
            else:
                logger.warning(f"⚠ Nie udało się sprawdzić uprawnień: {resp.status_code}")
        except Exception as e:
            logger.warning(f"⚠ Błąd sprawdzania uprawnień: {e}")

    def _open_session(self):
        """
        Otwiera sesję interaktywną online.
        Wymaga wygenerowania i zaszyfrowania klucza AES oraz IV.
        """
        # Generuj klucz AES i IV
        self._generate_encryption_data()
        encrypted_key = self._encrypt_aes_key()
        iv_base64 = base64.b64encode(self.aes_iv).decode()

        session_url = f"{self.base_url}/sessions/online"

        # Prawidłowa struktura payloadu dla API 2.0 (zgodnie z OpenAPI)
        init_payload = {
            "formCode": {
                "systemCode": "FA (3)",
                "schemaVersion": "1-0E",
                "value": "FA"
            },
            "encryption": {
                "encryptedSymmetricKey": encrypted_key,
                "initializationVector": iv_base64
            }
        }

        logger.info(f"Otwieranie sesji interaktywnej dla NIP: {self.nip}")
        logger.debug(f"Payload: formCode={init_payload['formCode']}, encryption keys present")
        
        # Bezpieczne logowanie tokena
        token_preview = self.access_token[:20] if self.access_token and len(self.access_token) > 20 else str(self.access_token)
        logger.debug(f"AccessToken present: {bool(self.access_token)}, preview: {token_preview}...")
        
        auth_header = self.session.headers.get('Authorization', 'NOT SET')
        auth_preview = auth_header[:50] if len(auth_header) > 50 else auth_header
        logger.debug(f"Authorization header: {auth_preview}...")
        
        resp_session = self.session.post(session_url, json=init_payload)

        if resp_session.status_code == 401:
            error_text = resp_session.text
            logger.error(f"❌ KSeF 401 Unauthorized: {error_text}")
            # Spróbuj wyciągnąć szczegóły z JSON
            try:
                error_json = resp_session.json()
                details = error_json.get('exception', {}).get('exceptionDetailList', [])
                logger.error(f"Szczegóły błędu: {details}")
            except:
                pass
            raise Exception(
                f"Brak autoryzacji (401). Token może być nieważny lub brak uprawnień InvoiceWrite. "
                f"Szczegóły: {error_text}"
            )

        if resp_session.status_code == 403:
            error_text = resp_session.text
            logger.error(f"❌ KSeF 403 Forbidden: {error_text}")
            raise Exception(
                f"Brak uprawnień do otwarcia sesji (403). "
                f"Sprawdź czy token ma uprawnienia InvoiceWrite. "
                f"Szczegóły: {error_text}"
            )

        resp_session.raise_for_status()

        session_result = resp_session.json()
        self.session_reference = session_result.get('referenceNumber')

        logger.info(f"✓ Sesja otwarta. Nr ref: {self.session_reference}")
        return session_result

    def send_invoice(self, xml_content):
        """
        Wysyła fakturę do KSeF:
        1. Uwierzytelnia
        2. Otwiera sesję
        3. Szyfruje i wysyła fakturę
        """
        # 1. Pełne uwierzytelnienie
        self._authenticate()

        # 2. Otwórz sesję
        session_data = self._open_session()

        # 3. Zaszyfruj fakturę (używa IV z sesji)
        encrypted_invoice = self._encrypt_invoice(xml_content)

        # Oblicz hashe w Base64 (nie hex!)
        xml_bytes = xml_content.encode('utf-8')
        invoice_hash = base64.b64encode(hashlib.sha256(xml_bytes).digest()).decode()
        invoice_size = len(xml_bytes)

        encrypted_bytes = base64.b64decode(encrypted_invoice)
        encrypted_hash = base64.b64encode(hashlib.sha256(encrypted_bytes).digest()).decode()
        encrypted_size = len(encrypted_bytes)

        # 4. Wyślij fakturę
        invoice_url = f"{self.base_url}/sessions/online/{self.session_reference}/invoices"

        invoice_payload = {
            "invoiceHash": invoice_hash,
            "invoiceSize": invoice_size,
            "encryptedInvoiceHash": encrypted_hash,
            "encryptedInvoiceSize": encrypted_size,
            "encryptedInvoiceContent": encrypted_invoice,
            "offlineMode": False
        }

        logger.info("Wysyłanie zaszyfrowanej faktury...")
        logger.debug(f"Invoice hash: {invoice_hash[:16]}..., size: {invoice_size}")
        
        resp_invoice = self.session.post(invoice_url, json=invoice_payload)
        
        if resp_invoice.status_code != 202 and resp_invoice.status_code != 200:
            logger.error(f"❌ Błąd wysyłki faktury: {resp_invoice.status_code} - {resp_invoice.text}")
        
        resp_invoice.raise_for_status()

        invoice_result = resp_invoice.json()
        invoice_reference = invoice_result.get('referenceNumber')

        logger.info(f"✓ Faktura wysłana. Nr ref: {invoice_reference}")

        return {
            "invoice_reference": invoice_reference,
            "session_reference": self.session_reference
        }

    def close_session(self):
        """Zamyka sesję interaktywną."""
        if not self.session_reference:
            logger.warning("Brak otwartej sesji do zamknięcia.")
            return

        close_url = f"{self.base_url}/sessions/online/{self.session_reference}/close"

        logger.info(f"Zamykanie sesji: {self.session_reference}")
        resp = self.session.post(close_url)
        resp.raise_for_status()

        logger.info("✓ Sesja zamknięta")
        return resp.json()
