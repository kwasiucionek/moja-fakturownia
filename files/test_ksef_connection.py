#!/usr/bin/env python
"""
Test połączenia z KSeF API (bez uwierzytelniania)

Ten skrypt testuje czy:
1. API KSeF jest dostępne
2. Klucze publiczne można pobrać
3. Certyfikaty mają poprawny format

Użycie:
    python test_ksef_connection.py
    python test_ksef_connection.py --prod  # Test środowiska produkcyjnego
"""

import requests
import base64
import sys
from cryptography.x509 import load_der_x509_certificate
from cryptography.hazmat.backends import default_backend


def test_ksef_connection(environment='test'):
    """
    Testuje połączenie z KSeF API bez potrzeby tokena
    
    Args:
        environment: 'test' lub 'prod'
    """
    # Wybierz URL
    if environment == 'test':
        base_url = "https://ksef-test.mf.gov.pl/api/v2"
        env_name = "TESTOWE"
    else:
        base_url = "https://ksef.mf.gov.pl/api/v2"
        env_name = "PRODUKCYJNE"
    
    print("=" * 70)
    print(f"TEST POŁĄCZENIA Z KSEF API - ŚRODOWISKO {env_name}")
    print("=" * 70)
    print()
    
    # Test 1: Połączenie z API
    print("Test 1/3: Połączenie z API...")
    print(f"URL: {base_url}")
    
    try:
        response = requests.get(base_url, timeout=5)
        print(f"✓ API odpowiada (status: {response.status_code})")
    except requests.exceptions.RequestException as e:
        print(f"❌ Błąd połączenia: {e}")
        return False
    
    print()
    
    # Test 2: Pobranie kluczy publicznych
    print("Test 2/3: Pobieranie kluczy publicznych...")
    key_url = f"{base_url}/security/public-key-certificates"
    print(f"URL: {key_url}")
    
    try:
        response = requests.get(key_url, timeout=10)
        response.raise_for_status()
        certificates = response.json()
        
        print(f"✓ Pobrano {len(certificates)} certyfikatów")
        
        # Sprawdź każdy certyfikat
        for i, cert_data in enumerate(certificates, 1):
            usage = cert_data.get("usage", [])
            valid_from = cert_data.get("validFrom", "?")
            valid_to = cert_data.get("validTo", "?")
            
            print(f"\n  Certyfikat #{i}:")
            print(f"    Przeznaczenie: {', '.join(usage)}")
            print(f"    Ważny od:      {valid_from}")
            print(f"    Ważny do:      {valid_to}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Błąd pobierania kluczy: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status: {e.response.status_code}")
            print(f"   Odpowiedź: {e.response.text[:200]}")
        return False
    except Exception as e:
        print(f"❌ Błąd przetwarzania: {e}")
        return False
    
    print()
    
    # Test 3: Walidacja certyfikatów
    print("Test 3/3: Walidacja certyfikatów...")
    
    try:
        token_key_found = False
        symmetric_key_found = False
        
        for cert_data in certificates:
            cert_b64 = cert_data.get("certificate")
            usage = cert_data.get("usage", [])
            
            if not cert_b64:
                print("❌ Brak pola 'certificate' w odpowiedzi")
                continue
            
            # Dekoduj DER
            cert_der = base64.b64decode(cert_b64)
            
            # Wczytaj jako X.509
            cert = load_der_x509_certificate(cert_der, default_backend())
            public_key = cert.public_key()
            
            # Sprawdź typ
            if "KsefTokenEncryption" in usage:
                token_key_found = True
                print(f"  ✓ Klucz do tokena KSeF: {public_key.key_size} bitów")
            
            if "SymmetricKeyEncryption" in usage:
                symmetric_key_found = True
                print(f"  ✓ Klucz do szyfrowania AES: {public_key.key_size} bitów")
        
        if not token_key_found:
            print("  ❌ Brak klucza KsefTokenEncryption")
            return False
        
        if not symmetric_key_found:
            print("  ❌ Brak klucza SymmetricKeyEncryption")
            return False
        
        print("\n✓ Wszystkie certyfikaty są poprawne")
        
    except Exception as e:
        print(f"❌ Błąd walidacji: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    print("=" * 70)
    print("✓ WSZYSTKIE TESTY PRZESZŁY POMYŚLNIE")
    print("=" * 70)
    print()
    print("Możesz teraz używać KSeF API w środowisku:", env_name)
    print()
    print("Następne kroki:")
    if environment == 'test':
        print("1. Utwórz podmiot testowy na: https://ksef-test.mf.gov.pl/")
        print("2. Wygeneruj token KSeF")
        print("3. Uruchom: python manage.py setup_ksef_test --user=<username> --with-real-token")
    else:
        print("1. Zaloguj się do: https://ksef.mf.gov.pl/")
        print("2. Wygeneruj token KSeF produkcyjny")
        print("3. Uruchom: python manage.py set_ksef_token --user=<username> --token=<token> --environment=prod")
    
    return True


if __name__ == "__main__":
    # Sprawdź argumenty
    environment = 'test'
    if len(sys.argv) > 1:
        if sys.argv[1] in ['--prod', '-p', 'prod']:
            environment = 'prod'
        elif sys.argv[1] in ['--help', '-h']:
            print(__doc__)
            sys.exit(0)
    
    # Uruchom test
    success = test_ksef_connection(environment)
    
    sys.exit(0 if success else 1)
