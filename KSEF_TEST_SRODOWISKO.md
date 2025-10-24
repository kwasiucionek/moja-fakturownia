# Środowisko Testowe KSeF - Przewodnik dla Developerów

## 🎯 Oficjalne Środowisko Testowe

**URL**: https://ksef-test.mf.gov.pl/api/v2

### ✅ Zalety:
- **Dane zanonimizowane** - nie musisz mieć prawdziwej firmy
- **Bez skutków podatkowych** - faktury są testowe
- **Auto-usuwanie** - faktury automatycznie usuwane po określonym czasie
- **Prawdziwe API** - pełna integracja z KSeF 2.0
- **Bezpłatne** - dostępne dla wszystkich

---

## 🚀 Krok po Kroku (10 minut)

### Krok 1: Utwórz Podmiot Testowy

1. Przejdź do: **https://ksef-test.mf.gov.pl/**

2. Kliknij: **"Dane testowe"** → **"Utwórz podmiot testowy"**

3. Wypełnij formularz:
   - **Typ podmiotu**: Podatnik VAT czynny
   - **Nazwa**: np. "Moja Testowa Firma Sp. z o.o."
   - System wygeneruje automatycznie:
     - ✅ NIP (10 cyfr)
     - ✅ Login
     - ✅ Hasło

4. **⚠️ ZAPISZ DANE**:
   ```
   NIP: 1234567890
   Login: login@example.com
   Hasło: wygenerowane_haslo_123
   ```

---

### Krok 2: Wygeneruj Token KSeF

1. **Zaloguj się** na https://ksef-test.mf.gov.pl/ używając danych z Kroku 1

2. Przejdź do: **"Zarządzanie tokenami"**

3. Kliknij: **"Wygeneruj nowy token"**

4. Wybierz uprawnienia:
   - ✅ **InvoiceWrite** (wysyłanie faktur)
   - ✅ **InvoiceRead** (odczyt faktur)

5. Podaj opis: **"Token dla aplikacji testowej"**

6. Kliknij: **"Generuj"**

7. **⚠️ SKOPIUJ TOKEN TERAZ** - zobaczysz go tylko raz!
   ```
   Token: A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0...
   ```

---

### Krok 3: Skonfiguruj Aplikację

#### Opcja A: Przez management command (zalecane)

```bash
python manage.py configure_ksef_test \
    --user=nazwa_uzytkownika \
    --nip=1234567890 \
    --token="TUTAJ_WKLEJ_TOKEN" \
    --company-name="Moja Testowa Firma Sp. z o.o."
```

#### Opcja B: Przez Django admin

1. Otwórz **Django Admin**
2. Przejdź do **CompanyInfo**
3. Wybierz/utwórz firmę dla użytkownika
4. Ustaw:
   ```
   ksef_environment: test
   tax_id: 1234567890
   ksef_token: TUTAJ_WKLEJ_TOKEN
   company_name: Moja Testowa Firma Sp. z o.o.
   ```
5. Zapisz

#### Opcja C: Przez Django shell

```python
from django.contrib.auth import get_user_model
from ksiegowosc.models import CompanyInfo

User = get_user_model()
user = User.objects.get(username='nazwa_uzytkownika')

# Utwórz lub zaktualizuj firmę
company, created = CompanyInfo.objects.get_or_create(user=user)
company.ksef_environment = 'test'  # ← Kluczowe!
company.tax_id = '1234567890'
company.ksef_token = 'TUTAJ_WKLEJ_TOKEN'
company.company_name = 'Moja Testowa Firma Sp. z o.o.'
company.save()

print(f"✓ Firma skonfigurowana dla środowiska testowego")
```

---

### Krok 4: Testuj!

```python
from ksef.client import KsefClient
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username='nazwa_uzytkownika')

# Utwórz klienta - automatycznie użyje środowiska testowego
client = KsefClient(user)

# Przykładowa faktura XML
invoice_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Faktura xmlns="http://crd.gov.pl/wzor/2023/06/29/12648/">
    <Naglowek>
        <KodFormularza>FA(3)</KodFormularza>
        <WariantFormularza>3</WariantFormularza>
        <DataWytworzeniaFa>2025-01-15</DataWytworzeniaFa>
    </Naglowek>
    <Podmiot1>
        <DaneIdentyfikacyjne>
            <NIP>1234567890</NIP>
            <Nazwa>Moja Testowa Firma</Nazwa>
        </DaneIdentyfikacyjne>
    </Podmiot1>
    <Fa>
        <P_1>2025-01-15</P_1>
        <P_2_1>FV/2025/01/001</P_2_1>
    </Fa>
</Faktura>"""

# Wyślij fakturę testową
result = client.send_invoice(invoice_xml)

print(f"✓ Faktura wysłana pomyślnie!")
print(f"  Session: {result['session_reference']}")
print(f"  Invoice: {result['invoice_reference']}")
print(f"  KSeF Number: {result['status'].get('ksefNumber')}")
```

---

## 📊 Weryfikacja Faktury

Po wysłaniu faktury możesz ją sprawdzić:

1. Zaloguj się: https://ksef-test.mf.gov.pl/
2. Przejdź do: **"Faktury wysłane"**
3. Powinna być widoczna Twoja faktura testowa

**Pamiętaj**: Faktura testowa:
- ❌ Nie ma skutków podatkowych
- ❌ Zostanie automatycznie usunięta
- ✅ Jest widoczna tylko w środowisku testowym

---

## 🔧 Zarządzanie Środowiskami

### Sprawdzenie aktualnego środowiska:

```python
from ksiegowosc.models import CompanyInfo

company = CompanyInfo.objects.get(user=user)
print(f"Środowisko: {company.ksef_environment}")
print(f"URL: {client.base_url}")
```

### Przełączanie środowisk:

```python
# Środowisko testowe
company.ksef_environment = 'test'
company.save()
# → https://ksef-test.mf.gov.pl/api/v2

# Środowisko produkcyjne
company.ksef_environment = 'prod'
company.save()
# → https://ksef.mf.gov.pl/api/v2
```

---

## 🎓 Najlepsze Praktyki

### ✅ Development (lokalnie):

```python
# settings.py lub .env
DEBUG = True

# W bazie danych:
CompanyInfo.objects.all().update(ksef_environment='test')
```

### ✅ Staging:

```python
# settings.py
DEBUG = False

# Użytkownicy mają tokeny testowe z ksef-test.mf.gov.pl
company.ksef_environment = 'test'
```

### ✅ Production:

```python
# settings.py
DEBUG = False

# Użytkownicy mają prawdziwe tokeny z ksef.mf.gov.pl
company.ksef_environment = 'prod'
```

---

## 🐛 Troubleshooting

### Problem: "Błąd uwierzytelniania"

**Przyczyny**:
1. Token wygasł lub jest nieprawidłowy
2. NIP nie zgadza się z kontem w KSeF-test
3. Środowisko ustawione na 'prod' zamiast 'test'

**Rozwiązanie**:
```python
# Sprawdź konfigurację
company = CompanyInfo.objects.get(user=user)
print(f"Environment: {company.ksef_environment}")  # Powinno być 'test'
print(f"NIP: {company.tax_id}")
print(f"Token: {company.ksef_token[:20]}...")

# Jeśli coś nie tak, wygeneruj nowy token na ksef-test.mf.gov.pl
```

### Problem: "Nieprawidłowy NIP"

**Rozwiązanie**: NIP musi mieć dokładnie 10 cyfr
```python
company.tax_id = '1234567890'  # ✅ OK
company.tax_id = '123-456-78-90'  # ❌ ŹLE (będzie znormalizowany)
company.tax_id = '123'  # ❌ ŹLE (za krótki)
company.save()
```

### Problem: "Brak tokena KSeF"

**Rozwiązanie**: Upewnij się że token jest ustawiony
```python
company = CompanyInfo.objects.get(user=user)
print(f"Token exists: {bool(company.ksef_token)}")

# Jeśli False, ustaw token
company.ksef_token = "TWOJ_TOKEN_Z_KSEF_TEST"
company.save()
```

---

## 📋 Checklist Konfiguracji

Przed wysłaniem pierwszej faktury sprawdź:

- [ ] Utworzony podmiot testowy na ksef-test.mf.gov.pl
- [ ] Wygenerowany token KSeF z uprawnieniem InvoiceWrite
- [ ] W bazie: `ksef_environment = 'test'`
- [ ] W bazie: `tax_id` = NIP z ksef-test (10 cyfr)
- [ ] W bazie: `ksef_token` = skopiowany token
- [ ] W bazie: `company_name` = nazwa testowej firmy
- [ ] Kod używa `client_ksef_v2.py` (najnowsza wersja)

---

## 🎯 Podsumowanie

**Środowisko testowe KSeF to idealne rozwiązanie dla developerów!**

✅ **Bez ryzyka** - żadnych skutków podatkowych  
✅ **Zanonimizowane dane** - nie musisz mieć firmy  
✅ **Prawdziwa integracja** - pełne API KSeF 2.0  
✅ **Bezpłatne** - dostępne dla wszystkich  

**URL**: https://ksef-test.mf.gov.pl/api/v2

---

## 📞 Więcej Informacji

- **Portal KSeF-test**: https://ksef-test.mf.gov.pl/
- **Dokumentacja API**: OpenAPI specification (openapi.json)
- **GitHub MF**: https://github.com/CIRFMF/ksef-docs

---

**Powodzenia z testowaniem! 🚀**
