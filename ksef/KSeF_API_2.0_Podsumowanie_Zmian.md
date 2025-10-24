# KSeF API 2.0 - Kompletne podsumowanie zmian

## Data aktualizacji: 24 października 2025
## Wersja API: 2.0.0 (build 2.0.0-rc5.4-te-20251023.1)

---

## 🔑 1. KLUCZE PUBLICZNE - NAJWAŻNIEJSZA ZMIANA!

### ❌ STARA WERSJA (nie działa poprawnie):
- **Endpoint**: `/api/v2/common/Encryption/PublicKey`
- **Problem**: Endpoint zwracał nieprawidłowe dane lub nie działał
- **Format**: JSON z polem `publicKey` 
- **Użycie**: Jeden klucz do wszystkiego

### ✅ NOWA WERSJA (obowiązująca):
- **Endpoint**: `/api/v2/security/public-key-certificates`
- **Zwraca**: Array JSON z certyfikatami
- **Format**: DER zakodowany w Base64 (nie PEM!)
- **Użycie**: **Dwa osobne klucze** według pola `usage`:

```json
[
  {
    "certificate": "MIIGWDCCBECgAwIBAgIQGmXqNRg5ye1JMZDOQ7HNCTANBgk...",
    "validFrom": "2025-09-29T06:03:19+00:00",
    "validTo": "2027-09-29T06:03:18+00:00",
    "usage": ["KsefTokenEncryption"]  ← Do szyfrowania tokena KSeF
  },
  {
    "certificate": "MIIGWDCCBECgAwIBAgIQe4NvS/i3yyDCcnaXiiC6BTANBG...",
    "validFrom": "2025-09-29T06:17:45+00:00",
    "validTo": "2027-09-29T06:17:44+00:00",
    "usage": ["SymmetricKeyEncryption"]  ← Do szyfrowania klucza AES
  }
]
```

### Implementacja w kodzie:

```python
# ❌ STARA WERSJA
self.public_key_cert = None  # Jeden klucz

def _get_public_key(self):
    key_url = f"{self.base_url}/common/Encryption/PublicKey"
    # ... wczytywanie jako PEM

# ✅ NOWA WERSJA
self.token_encryption_key = None      # Do tokena KSeF
self.symmetric_key_encryption_key = None  # Do klucza AES

def _get_public_keys(self):
    key_url = f"{self.base_url}/security/public-key-certificates"
    response = requests.get(key_url, timeout=10)
    certificates = response.json()
    
    for cert_data in certificates:
        cert_b64 = cert_data.get("certificate")
        usage = cert_data.get("usage", [])
        
        # WAŻNE: Format DER, nie PEM!
        cert_der = base64.b64decode(cert_b64)
        cert = load_der_x509_certificate(cert_der, default_backend())
        public_key = cert.public_key()
        
        if "KsefTokenEncryption" in usage:
            self.token_encryption_key = public_key
        elif "SymmetricKeyEncryption" in usage:
            self.symmetric_key_encryption_key = public_key
```

**Import wymagany**:
```python
from cryptography.x509 import load_der_x509_certificate  # Nie load_pem!
```

---

## 🔐 2. UWIERZYTELNIANIE

### Krok 1: Challenge

#### ❌ STARA WERSJA:
```python
# Wysyłano body z kontekstem
context = {
    "contextIdentifier": {
        "type": "NIP",
        "value": self.nip
    }
}
response = requests.post(challenge_url, json=context, headers=headers)
```

#### ✅ NOWA WERSJA:
```python
# Challenge BEZ BODY!
response = requests.post(challenge_url, headers=headers, timeout=10)
```

**Odpowiedź**:
```json
{
  "challenge": "20250514-CR-226FB7B000-3ACF9BE4C0-10",
  "timestamp": "2025-07-11T12:23:56.0154302+00:00"
}
```

---

### Krok 2: Szyfrowanie tokena

#### ❌ STARA WERSJA:
```python
# Używano tego samego klucza co do AES
public_key = self._get_public_key()
token_string = f"{ksef_token}|{timestamp}"  # Timestamp jako string?
encrypted = public_key.encrypt(...)
```

#### ✅ NOWA WERSJA:
```python
# Dedykowany klucz do tokena
if not self.token_encryption_key:
    self._get_public_keys()

# Konwersja timestamp ISO → milisekundy Unix
dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
timestamp_ms = int(dt.timestamp() * 1000)

token_string = f"{ksef_token}|{timestamp_ms}"
# Przykład: "abc123token|1720703036015"

encrypted = self.token_encryption_key.encrypt(
    token_string.encode("utf-8"),
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    ),
)
```

**Import wymagany**:
```python
from datetime import datetime
```

---

### Krok 3: Wysyłanie uwierzytelnienia

#### ❌ STARA WERSJA:
```python
payload = {
    "challenge": challenge,
    "contextIdentifier": {
        "type": "NIP",  # Małe litery
        "value": self.nip
    },
    "encryptedToken": encrypted_token,
}

# Oczekiwano 201 Created
if auth_response.status_code != 201:
    raise Exception(...)
```

#### ✅ NOWA WERSJA:
```python
payload = {
    "challenge": challenge,
    "contextIdentifier": {
        "type": "Nip",  # WAŻNE: Wielka litera!
        "value": self.nip
    },
    "encryptedToken": encrypted_token,
}

# API 2.0 zwraca 202 Accepted
if auth_response.status_code != 202:
    raise Exception(...)
```

**Odpowiedź (202 Accepted)**:
```json
{
  "referenceNumber": "20250514-AU-2DFC46C000-3AC6D5877F-D4",
  "authenticationToken": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "validUntil": "2025-07-11T12:23:56.0154302+00:00"
  }
}
```

---

### Krok 4: Pobieranie statusu

#### ❌ STARA WERSJA:
```python
status_url = f"{self.base_url}/auth/status/{auth_ref}"
```

#### ✅ NOWA WERSJA:
```python
# Zmiana endpointu!
status_url = f"{self.base_url}/auth/{auth_ref}"

# Wymagany Bearer token z kroku 3
status_headers = {
    "Authorization": f"Bearer {auth_token}",
    "Content-Type": "application/json"
}
```

---

## 📄 3. WYSYŁANIE FAKTUR

### Krok 1: Otwieranie sesji

#### ❌ STARA WERSJA:
```python
session_payload = {
    "formCode": "FA(3)",  # String
    "encryption": encryption_data
}
```

#### ✅ NOWA WERSJA:
```python
session_payload = {
    "formCode": {  # Obiekt z trzema polami!
        "systemCode": "FA (3)",
        "schemaVersion": "1-0E",
        "value": "FA"
    },
    "encryption": encryption_data
}
```

**Obsługiwane schematy**:
| SystemCode | SchemaVersion | Value |
|------------|---------------|-------|
| FA (2)     | 1-0E         | FA    |
| FA (3)     | 1-0E         | FA    |
| PEF (3)    | 2-1          | PEF   |
| PEF_KOR (3)| 2-1          | PEF   |

---

### Krok 2: Wysyłanie faktury - NAJWIĘKSZA ZMIANA!

#### ❌ STARA WERSJA:
```python
# PUT z surowymi bytes
encrypted_invoice = self._encrypt_invoice(invoice_xml)

invoice_headers = {
    "Content-Type": "application/octet-stream",
    "Authorization": f"Bearer {self.access_token}",
}

invoice_response = requests.put(
    invoice_url, 
    data=encrypted_invoice,  # bytes
    headers=invoice_headers, 
    timeout=15
)
```

#### ✅ NOWA WERSJA:
```python
# POST z JSON zawierającym metadane + fakturę w Base64

# 1. Oblicz hash oryginału
invoice_bytes = invoice_xml.encode("utf-8")
invoice_hash = self._calculate_sha256(invoice_bytes)
invoice_size = len(invoice_bytes)

# 2. Zaszyfruj
encrypted_invoice = self._encrypt_invoice(invoice_xml)

# 3. Oblicz hash zaszyfrowanej
encrypted_hash = self._calculate_sha256(encrypted_invoice)
encrypted_size = len(encrypted_invoice)

# 4. Zakoduj w Base64
encrypted_invoice_b64 = base64.b64encode(encrypted_invoice).decode("utf-8")

# 5. Wyślij jako JSON
invoice_payload = {
    "invoiceHash": invoice_hash,  # SHA256 oryginału w Base64
    "invoiceSize": invoice_size,
    "encryptedInvoiceHash": encrypted_hash,  # SHA256 zaszyfrowanej w Base64
    "encryptedInvoiceSize": encrypted_size,
    "encryptedInvoiceContent": encrypted_invoice_b64,  # Faktura w Base64
    "offlineMode": False
}

invoice_headers = {
    "Content-Type": "application/json",  # JSON, nie octet-stream!
    "Authorization": f"Bearer {self.access_token}",
}

invoice_response = requests.post(  # POST, nie PUT!
    invoice_url, 
    json=invoice_payload,  # json=, nie data=
    headers=invoice_headers, 
    timeout=15
)
```

**Nowa metoda pomocnicza**:
```python
def _calculate_sha256(self, data: bytes) -> str:
    """Oblicza hash SHA256 i zwraca w Base64"""
    sha256_hash = hashlib.sha256(data).digest()
    return base64.b64encode(sha256_hash).decode("utf-8")
```

**Import wymagany**:
```python
import hashlib
```

---

### Krok 3: Sprawdzanie statusu

**Endpoint pozostał bez zmian**:
```python
status_url = f"{self.base_url}/sessions/{session_ref}/invoices/{invoice_ref}"
```

**Odpowiedź może zawierać numer KSeF**:
```json
{
  "status": {
    "code": 200,
    "description": "Faktura przetworzona"
  },
  "ksefNumber": "1234567890-20251024-ABCD1234-EF",
  "invoiceHash": "...",
  "invoiceNumber": "FV/2025/10/001"
}
```

---

### Krok 4: Zamykanie sesji

**Bez zmian**:
```python
close_url = f"{self.base_url}/sessions/online/{session_ref}/close"
close_response = requests.post(close_url, headers=close_headers, timeout=10)
```

---

## 🔄 4. SZYFROWANIE KLUCZA AES

### ❌ STARA WERSJA:
```python
# Ten sam klucz co do tokena
public_key = self._get_public_key()
encrypted_key = public_key.encrypt(self.aes_key, ...)
```

### ✅ NOWA WERSJA:
```python
# Dedykowany klucz do szyfrowania symetrycznego
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
```

---

## 📊 5. PODSUMOWANIE WSZYSTKICH ZMIAN

| Obszar | Stara wersja | Nowa wersja |
|--------|-------------|-------------|
| **Endpoint kluczy** | `/common/Encryption/PublicKey` | `/security/public-key-certificates` |
| **Liczba kluczy** | 1 (do wszystkiego) | 2 (według usage) |
| **Format certyfikatu** | PEM lub undefined | DER w Base64 |
| **Challenge body** | Z contextIdentifier | Bez body |
| **Timestamp** | String lub manual | ISO → ms Unix |
| **contextIdentifier.type** | "NIP" | "Nip" |
| **Auth status code** | 201 | 202 |
| **Auth status endpoint** | `/auth/status/{ref}` | `/auth/{ref}` |
| **FormCode** | String | Obiekt (3 pola) |
| **Faktura metoda** | PUT | POST |
| **Faktura format** | Binary (octet-stream) | JSON |
| **Faktura zawartość** | Surowe bytes | Base64 + metadane |

---

## ⚠️ 6. TYPOWE BŁĘDY DO UNIKNIĘCIA

### ❌ Błąd 1: Używanie jednego klucza
```python
# ŹLE - ten sam klucz do wszystkiego
public_key = self._get_public_key()
encrypted_token = public_key.encrypt(token_bytes, ...)
encrypted_aes = public_key.encrypt(aes_key, ...)
```

### ✅ Poprawnie:
```python
# DOBRZE - osobne klucze
encrypted_token = self.token_encryption_key.encrypt(token_bytes, ...)
encrypted_aes = self.symmetric_key_encryption_key.encrypt(aes_key, ...)
```

---

### ❌ Błąd 2: Body w challenge
```python
# ŹLE
context = {"contextIdentifier": {"type": "NIP", "value": nip}}
requests.post(challenge_url, json=context)  # Zwróci błąd!
```

### ✅ Poprawnie:
```python
# DOBRZE
requests.post(challenge_url, headers=headers)  # Bez body!
```

---

### ❌ Błąd 3: Timestamp jako string
```python
# ŹLE
token_string = f"{token}|{timestamp}"  
# Wynik: "token|2025-07-11T12:23:56.0154302+00:00"
```

### ✅ Poprawnie:
```python
# DOBRZE
dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
timestamp_ms = int(dt.timestamp() * 1000)
token_string = f"{token}|{timestamp_ms}"
# Wynik: "token|1720703036015"
```

---

### ❌ Błąd 4: PUT przy wysyłce faktury
```python
# ŹLE
requests.put(invoice_url, data=encrypted_invoice)
```

### ✅ Poprawnie:
```python
# DOBRZE
requests.post(invoice_url, json=invoice_payload)
```

---

### ❌ Błąd 5: PEM zamiast DER
```python
# ŹLE
from cryptography.x509 import load_pem_x509_certificate
cert = load_pem_x509_certificate(cert_bytes, ...)
```

### ✅ Poprawnie:
```python
# DOBRZE
from cryptography.x509 import load_der_x509_certificate
cert_der = base64.b64decode(cert_b64)
cert = load_der_x509_certificate(cert_der, default_backend())
```

---

## 🎯 7. CHECKLIST MIGRACJI

Przed wdrożeniem sprawdź:

### Klucze publiczne
- [ ] Zmieniono endpoint na `/security/public-key-certificates`
- [ ] Dodano dwa osobne pola: `token_encryption_key`, `symmetric_key_encryption_key`
- [ ] Wczytywanie jako DER (`load_der_x509_certificate`)
- [ ] Sprawdzanie pola `usage` dla każdego certyfikatu

### Uwierzytelnianie
- [ ] Challenge wysyłany BEZ body
- [ ] Timestamp konwertowany na milisekundy Unix
- [ ] `contextIdentifier.type` = `"Nip"` (wielka litera)
- [ ] Obsługa kodu 202 (nie 201)
- [ ] Zmieniono endpoint statusu na `/auth/{ref}`
- [ ] Bearer token z auth response w nagłówkach statusu

### Wysyłanie faktur
- [ ] FormCode jako obiekt z `systemCode`, `schemaVersion`, `value`
- [ ] POST zamiast PUT
- [ ] Content-Type: application/json (nie octet-stream)
- [ ] Dodano metodę `_calculate_sha256()`
- [ ] Obliczanie hash oryginału i zaszyfrowanej
- [ ] Faktura zakodowana w Base64
- [ ] Wszystkie metadane w JSON payload

### Importy
- [ ] `from datetime import datetime`
- [ ] `import hashlib`
- [ ] `from cryptography.x509 import load_der_x509_certificate`

---

## 📝 8. TESTOWANIE

### Test 1: Pobieranie kluczy
```python
client = KsefClient(user)
client._get_public_keys()

assert client.token_encryption_key is not None
assert client.symmetric_key_encryption_key is not None
assert client.token_encryption_key != client.symmetric_key_encryption_key
print("✓ Klucze pobrane poprawnie")
```

### Test 2: Uwierzytelnianie
```python
client._authenticate()
assert client.access_token is not None
print(f"✓ Token: {client.access_token[:30]}...")
```

### Test 3: Wysyłanie faktury
```python
invoice_xml = """<?xml version="1.0"?>..."""
result = client.send_invoice(invoice_xml)

assert "session_reference" in result
assert "invoice_reference" in result
assert result["status"]["status"]["code"] == 200
print(f"✓ Faktura wysłana: {result['invoice_reference']}")
```

---

## 📚 9. ZASOBY

- **Gotowy kod**: `client_ksef_v2.py`
- **Dokumentacja OpenAPI**: `openapi.json`
- **Test endpoint**: `https://ksef-test.mf.gov.pl/api/v2/security/public-key-certificates`
- **Prod endpoint**: `https://ksef.mf.gov.pl/api/v2/security/public-key-certificates`
- **GitHub MF**: https://github.com/CIRFMF/ksef-docs

---

## 🚀 10. SZYBKI START

### 1. Zamień plik
```bash
# Backup starej wersji
mv ksef/client.py ksef/client_old.py

# Wdróż nową wersję
cp client_ksef_v2.py ksef/client.py
```

### 2. Przetestuj
```python
from ksef.client import KsefClient

client = KsefClient(user)

# Test 1: Klucze
client._get_public_keys()
print(f"Token key: {client.token_encryption_key.key_size} bits")
print(f"AES key: {client.symmetric_key_encryption_key.key_size} bits")

# Test 2: Uwierzytelnienie
client._authenticate()
print(f"Access token: {client.access_token[:50]}...")

# Test 3: Faktura (opcjonalnie)
# result = client.send_invoice(invoice_xml)
```

### 3. Monitoruj logi
```python
import logging
logging.basicConfig(level=logging.INFO)
```

---

**✅ Kod został w pełni zaktualizowany zgodnie z oficjalną dokumentacją OpenAPI KSeF API 2.0**

**Data**: 24 października 2025  
**Wersja API**: 2.0.0 (build 2.0.0-rc5.4-te-20251023.1)
