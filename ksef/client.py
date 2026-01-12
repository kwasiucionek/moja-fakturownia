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

# Usunięto: from ksiegowosc.models import CompanyInfo

logger = logging.getLogger(__name__)

class KsefClient:
    def __init__(self, user):
        # Import lokalny zapobiega ModuleNotFoundError podczas startu aplikacji
        from ksiegowosc.models import CompanyInfo

        try:
            self.company_info = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            raise Exception("Brak danych firmy (CompanyInfo).")

        if not self.company_info.ksef_token:
            raise Exception("Brak tokena KSeF. Wygeneruj w Aplikacji Podatnika.")

        env = self.company_info.ksef_environment
        if env == "test":
            self.base_url = "https://ksef-test.mf.gov.pl/api/v2"
        else:
            self.base_url = "https://ksef.mf.gov.pl/api/v2"

        self.nip = self._normalize_nip(self.company_info.tax_id)
        self.access_token = None
        self.refresh_token = None
        self.token_encryption_key = None
        self.symmetric_key_encryption_key = None
        self.aes_key = None
        self.aes_iv = None

    # ... (reszta metod pozostaje bez zmian) ...

    def _normalize_nip(self, nip: str) -> str:
        if not nip: raise Exception("Brak numeru NIP")
        normalized = nip.replace("-", "").replace(" ", "").strip()
        if not normalized.isdigit() or len(normalized) != 10:
            raise Exception(f"Nieprawidłowy NIP: {nip}. Wymagane 10 cyfr.")
        return normalized

    def _get_public_keys(self):
        if self.token_encryption_key and self.symmetric_key_encryption_key: return
        try:
            key_url = f"{self.base_url}/security/public-key-certificates"
            response = requests.get(key_url, timeout=10)
            response.raise_for_status()
            certificates = response.json()
            for cert_data in certificates:
                cert_b64 = cert_data.get("certificate")
                usage = cert_data.get("usage", [])
                if not cert_b64: continue
                cert_der = base64.b64decode(cert_b64)
                cert = load_der_x509_certificate(cert_der, default_backend())
                public_key = cert.public_key()
                if "KsefTokenEncryption" in usage: self.token_encryption_key = public_key
                if "SymmetricKeyEncryption" in usage: self.symmetric_key_encryption_key = public_key
        except Exception as e:
            logger.error(f"Błąd kluczy: {e}")
            raise

    def _encrypt_ksef_token(self, ksef_token: str, timestamp: str) -> str:
        if not self.token_encryption_key: self._get_public_keys()
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        timestamp_ms = int(dt.timestamp() * 1000)
        token_string = f"{ksef_token}|{timestamp_ms}"
        encrypted = self.token_encryption_key.encrypt(
            token_string.encode("utf-8"),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        return base64.b64encode(encrypted).decode("utf-8")

    def _generate_aes_key(self):
        self.aes_key = os.urandom(32)
        self.aes_iv = os.urandom(16)

    def _encrypt_aes_key(self) -> dict:
        if not self.symmetric_key_encryption_key: self._get_public_keys()
        encrypted_key = self.symmetric_key_encryption_key.encrypt(
            self.aes_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        return {
            "encryptedSymmetricKey": base64.b64encode(encrypted_key).decode("utf-8"),
            "initializationVector": base64.b64encode(self.aes_iv).decode("utf-8"),
        }

    def _encrypt_invoice(self, invoice_xml: str) -> bytes:
        invoice_bytes = invoice_xml.encode("utf-8")
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(self.aes_iv), backend=default_backend())
        encryptor = cipher.encryptor()
        padding_length = 16 - (len(invoice_bytes) % 16)
        padded_data = invoice_bytes + bytes([padding_length] * padding_length)
        return encryptor.update(padded_data) + encryptor.finalize()

    def _calculate_sha256(self, data: bytes) -> str:
        return base64.b64encode(hashlib.sha256(data).digest()).decode("utf-8")

    def _authenticate(self):
        if self.access_token: return
        challenge_url = f"{self.base_url}/auth/challenge"
        res = requests.post(challenge_url, headers={"Content-Type": "application/json"}, timeout=10)
        res.raise_for_status()
        c_data = res.json()
        encrypted_token = self._encrypt_ksef_token(self.company_info.ksef_token, c_data["timestamp"])
        auth_url = f"{self.base_url}/auth/ksef-token"
        payload = {"challenge": c_data["challenge"], "contextIdentifier": {"type": "Nip", "value": self.nip}, "encryptedToken": encrypted_token}
        auth_res = requests.post(auth_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        auth_res.raise_for_status()
        self.access_token = auth_res.json().get("authenticationToken", {}).get("token")

    def send_invoice(self, invoice_xml: str):
        self._authenticate()
        self._generate_aes_key()
        session_url = f"{self.base_url}/sessions/online"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"}
        session_payload = {"formCode": {"systemCode": "FA (3)", "schemaVersion": "1-0E", "value": "FA"}, "encryption": self._encrypt_aes_key()}
        s_res = requests.post(session_url, json=session_payload, headers=headers, timeout=10)
        s_res.raise_for_status()
        s_ref = s_res.json()["referenceNumber"]

        inv_bytes = invoice_xml.encode("utf-8")
        enc_inv = self._encrypt_invoice(invoice_xml)
        invoice_url = f"{self.base_url}/sessions/online/{s_ref}/invoices"
        invoice_payload = {
            "invoiceHash": self._calculate_sha256(inv_bytes), "invoiceSize": len(inv_bytes),
            "encryptedInvoiceHash": self._calculate_sha256(enc_inv), "encryptedInvoiceSize": len(enc_inv),
            "encryptedInvoiceContent": base64.b64encode(enc_inv).decode("utf-8"), "offlineMode": False
        }
        i_res = requests.post(invoice_url, json=invoice_payload, headers=headers, timeout=15)
        i_res.raise_for_status()
        return {"session_reference": s_ref, "invoice_reference": i_res.json()["referenceNumber"]}
