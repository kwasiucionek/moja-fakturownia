# Szybki Start - Testowanie Aplikacji KSeF

## 🚀 Opcja 1: Testy bez prawdziwego API (najszybsze)

### Krok 1: Uruchom setup testowy
```bash
# Wygeneruje mock dane (NIP, token, firmę)
python manage.py setup_ksef_test --user=twoja_nazwa_uzytkownika
```

To stworzy:
- ✅ Testową firmę "Testowa Firma Sp. z o.o."
- ✅ Losowy NIP (10 cyfr)
- ✅ Mock token (nie działa z prawdziwym API)
- ✅ Środowisko = test

### Krok 2: Testuj kod lokalnie
Możesz teraz testować logikę bez wysyłania do API:
- Szyfrowanie
- Generowanie XML
- Struktury danych
- Walidację

**⚠️ UWAGA**: Mock token NIE będzie działał z prawdziwym API KSeF!

---

## 🌐 Opcja 2: Testy z prawdziwym API testowym (pełne testy)

### Krok 1: Utwórz podmiot testowy w KSeF

1. **Przejdź do**: https://ksef-test.mf.gov.pl/
2. **Kliknij**: "Dane testowe" → "Utwórz podmiot testowy"
3. **Wypełnij formularz**:
   - Typ podmiotu: np. "Podatnik VAT czynny"
   - NIP: Zostanie wygenerowany automatycznie
   - Nazwa: np. "Moja Testowa Firma"
4. **Kliknij**: "Utwórz"
5. **Skopiuj dane**:
   - NIP: `1234567890`
   - Login: `login@example.com`
   - Hasło: `wygenerowane_haslo`

### Krok 2: Zaloguj się i wygeneruj token

1. **Zaloguj się** na ksef-test.mf.gov.pl używając danych z kroku 1
2. **Przejdź do**: "Zarządzanie tokenami"
3. **Kliknij**: "Wygeneruj nowy token"
4. **Wybierz uprawnienia**: 
   - ✅ InvoiceWrite (wysyłanie faktur)
   - ✅ InvoiceRead (odczyt faktur)
5. **Podaj opis**: "Token dla aplikacji testowej"
6. **Kliknij**: "Generuj"
7. **⚠️ WAŻNE**: Skopiuj token TERAZ - zobaczysz go tylko raz!

Token wygląda podobnie do:
```
A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0...
```

### Krok 3: Skonfiguruj aplikację

```bash
# Uruchom setup z prawdziwym tokenem
python manage.py setup_ksef_test --user=twoja_nazwa_uzytkownika --with-real-token

# Zostaniesz poproszony o wklejenie tokena
# Wklej skopiowany token i naciśnij Enter
```

LUB ręcznie:

```bash
# Ustaw token ręcznie
python manage.py set_ksef_token \
    --user=twoja_nazwa_uzytkownika \
    --token="TUTAJ_WKLEJ_SWOJ_TOKEN" \
    --environment=test
```

### Krok 4: Zaktualizuj NIP

W Django admin lub bezpośrednio w bazie:
```python
from ksiegowosc.models import CompanyInfo
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username='twoja_nazwa_uzytkownika')
company = CompanyInfo.objects.get(user=user)

# Ustaw NIP z KSeF-test
company.tax_id = "1234567890"  # NIP z kroku 1
company.save()
```

### Krok 5: Testuj!

Teraz możesz wysyłać prawdziwe faktury testowe:

```python
from ksef.client import KsefClient
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username='twoja_nazwa_uzytkownika')

client = KsefClient(user)

# Przykładowa faktura XML
invoice_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="http://crd.gov.pl/wzor/2023/06/29/12648/">
    <!-- Twoja faktura XML -->
</Faktura>"""

# Wyślij
result = client.send_invoice(invoice_xml)
print(f"✓ Faktura wysłana: {result['invoice_reference']}")
```

---

## 📋 Sprawdzanie statusu

### Komenda show
```bash
# Pokaż obecne ustawienia
python manage.py set_ksef_token --user=twoja_nazwa_uzytkownika --show
```

Wynik:
```
Obecny token KSeF: A1B2C3D4E5...Q7R8S9T0
Długość: 64 znaków
Środowisko: test
```

---

## 🔧 Troubleshooting

### Problem: "Brak tokena KSeF"
```bash
# Sprawdź czy token jest ustawiony
python manage.py set_ksef_token --user=twoja_nazwa --show

# Jeśli brak, ustaw go
python manage.py setup_ksef_test --user=twoja_nazwa --with-real-token
```

### Problem: "Nieprawidłowy NIP"
```bash
# Sprawdź NIP w bazie
python manage.py shell
>>> from ksiegowosc.models import CompanyInfo
>>> company = CompanyInfo.objects.first()
>>> print(company.tax_id)

# Ustaw poprawny NIP (10 cyfr)
>>> company.tax_id = "1234567890"
>>> company.save()
```

### Problem: "Błąd uwierzytelniania"
- Sprawdź czy token jest poprawny (nie wygasł, nie ma spacji)
- Sprawdź czy środowisko = "test"
- Sprawdź czy NIP zgadza się z kontem w KSeF-test
- Wygeneruj nowy token w KSeF-test

### Problem: "Nie mogę zalogować się do KSeF-test"
- Użyj danych z "Utwórz podmiot testowy"
- Jeśli zapomniałeś hasła, utwórz nowy podmiot testowy

---

## 📊 Weryfikacja wysłanych faktur

Po wysłaniu faktury:

1. **Zaloguj się**: https://ksef-test.mf.gov.pl/
2. **Przejdź do**: "Faktury wysłane"
3. **Sprawdź status**: Powinna być widoczna Twoja faktura

---

## 🎯 Podsumowanie - Co wybrać?

| Opcja | Kiedy używać | Czas setup | Wymaga konta |
|-------|--------------|------------|--------------|
| **Opcja 1: Mock** | Testy jednostkowe, lokalne | 30 sekund | ❌ Nie |
| **Opcja 2: KSeF-test** | Testy integracyjne, pełne | 5 minut | ✅ Tak |

**Rekomendacja**: Zacznij od **Opcji 1** dla szybkich testów, potem przejdź do **Opcji 2** dla pełnej integracji.

---

## 📞 Potrzebujesz pomocy?

```bash
# Pomoc dla setup_ksef_test
python manage.py setup_ksef_test --help

# Pomoc dla set_ksef_token
python manage.py set_ksef_token --help
```
