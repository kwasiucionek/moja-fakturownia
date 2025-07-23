# 📊 Moja Fakturownia

Kompleksowy system księgowy dla jednoosobowych działalności gospodarczych prowadzących ryczałt ewidencjonowany. Aplikacja Django z panelem administracyjnym umożliwiającym zarządzanie fakturami, kontrahentami oraz automatyczne rozliczenia podatkowe i składki ZUS.

## ✨ Funkcjonalności

### 📄 Zarządzanie Fakturami
- **Wystawianie faktur** z automatyczną numeracją
- **Faktury korygujące** z powiązaniem do oryginalnych dokumentów
- **Generowanie PDF** z profesjonalnymi szablonami
- **Import/Export JPK_FA** - automatyczny import z plików XML
- **Pozycje na fakturach** z obliczaniem wartości

### 👥 Kontrahenci
- Zarządzanie bazą kontrahentów
- Automatyczne tworzenie podczas importu JPK
- Walidacja numerów NIP
- Pełne dane adresowe

### 💰 Rozliczenia Podatkowe
- **Rozliczenia miesięczne** z automatycznym obliczaniem podatku
- **Rozliczenia roczne** z wykrywaniem dopłat/zwrotów
- **Kalkulator składek ZUS** z aktualnymi stawkami
- **Składki społeczne, zdrowotne i Fundusz Pracy**
- Obsługa preferencyjnych składek i Małego ZUS Plus

### 🏢 Dane Firmy
- Kompleksowy profil firmy
- Ustawienia podatku (ryczałt, skala, liniowy)
- Konfiguracja VAT i ZUS
- Dane do faktur i rozliczeń

### 📊 Raporty i Eksport
- **PDF faktur** z profesjonalnym layoutem
- **PDF rozliczeń rocznych** ze szczegółami
- **Export JPK_FA** dla urzędu skarbowego
- Zestawienia miesięczne i roczne

## 🛠️ Technologie

- **Backend:** Django 5.2.3
- **Frontend:** Bootstrap 5 + Jazzmin Admin
- **Baza danych:** SQLite (możliwość PostgreSQL/MySQL)
- **PDF:** WeasyPrint
- **Styling:** CSS3, Font Awesome
- **Python:** 3.12+

## 📋 Wymagania

- Python 3.12 lub nowszy
- pip (menedżer pakietów Python)
- Opcjonalnie: virtualenv

## 🚀 Instalacja

1. **Sklonuj repozytorium**
```bash
git clone https://github.com/kwasiucionek/moja-fakturownia.git
cd moja-fakturownia
```

2. **Utwórz środowisko wirtualne**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# lub
venv\Scripts\activate     # Windows
```

3. **Zainstaluj zależności**
```bash
pip install -r requirements.txt
```

4. **Wykonaj migracje bazy danych**
```bash
python manage.py makemigrations
python manage.py migrate
```

5. **Utwórz superużytkownika**
```bash
python manage.py createsuperuser
```

6. **Uruchom serwer deweloperski**
```bash
python manage.py runserver
```

7. **Otwórz w przeglądarce**
```
http://127.0.0.1:8000/admin/
```

## ⚙️ Konfiguracja

### Pierwsze kroki
1. **Zaloguj się do panelu admin**
2. **Uzupełnij dane firmy** - przejdź do "Dane Firmy" i wprowadź:
   - Pełne dane identyfikacyjne (nazwa, NIP, adres)
   - Formę opodatkowania (ryczałt, skala, liniowy)
   - Ustawienia VAT i ZUS
   - Kod urzędu skarbowego

3. **Zaktualizuj stawki ZUS**
   - Przejdź do "Stawki ZUS"
   - Kliknij "Aktualizuj stawki" aby pobrać aktualne dane

### Struktura bazy danych
- `CompanyInfo` - dane firmy
- `Contractor` - kontrahenci
- `Invoice` + `InvoiceItem` - faktury z pozycjami
- `MonthlySettlement` - rozliczenia miesięczne
- `YearlySettlement` - rozliczenia roczne
- `ZUSRates` - stawki składek ZUS

## 📖 Używanie

### Wystawianie faktur
1. Przejdź do "Faktury" → "Dodaj fakturę"
2. Wybierz kontrahenta (lub dodaj nowego)
3. Wprowadź pozycje na fakturze
4. Zapisz - numer zostanie wygenerowany automatycznie
5. Wygeneruj PDF do wysłania klientowi

### Import z JPK_FA
1. "Faktury" → "Importuj z JPK"
2. Wybierz plik XML z JPK_FA
3. System automatycznie:
   - Utworzy kontrahentów
   - Zaimportuje faktury z pozycjami
   - Rozpozna faktury korygujące

### Rozliczenia miesięczne
1. "Rozliczenia miesięczne" → "Oblicz i zapisz nowy miesiąc"
2. Wybierz okres
3. Wprowadź opłacone składki ZUS
4. System obliczy należny podatek automatycznie

### Rozliczenia roczne
1. "Rozliczenia roczne" → "Oblicz rozliczenie roczne"
2. Wybierz rok
3. Ustaw stawkę podatku
4. System pokaże czy jest dopłata czy zwrot

## 📁 Struktura Projektu

```
moja-fakturownia/
├── fakturownia/                 # Główne ustawienia Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── ksiegowosc/                  # Główna aplikacja
│   ├── admin.py                 # Panel administracyjny
│   ├── models.py                # Modele danych
│   ├── views.py                 # Widoki
│   ├── forms.py                 # Formularze
│   ├── templates/               # Szablony HTML
│   │   └── ksiegowosc/
│   │       ├── invoice_pdf_template.html
│   │       ├── settlement_form.html
│   │       └── zus_calculator.html
│   ├── management/commands/     # Komendy Django
│   │   └── update_zus_rates.py
│   └── migrations/              # Migracje bazy
├── static/                      # Pliki statyczne
├── media/                       # Pliki użytkowników
├── requirements.txt             # Zależności Python
└── manage.py                    # Skrypt zarządzający Django
```

## 🔧 Funkcje zaawansowane

### Automatyzacja składek ZUS
- Pobieranie aktualnych stawek ze strony ZUS.pl
- Obliczanie składek na podstawie ustawień firmy
- Obsługa preferencji i ulg

### JPK_FA
- Import z różnych wersji schema JPK
- Export zgodny z wymogami MF
- Obsługa faktur korygujących

### Wieloużytkownikowość
- Każdy użytkownik ma swoją niezależną księgowość
- Izolacja danych między firmami
- Zarządzanie uprawnieniami

## 🐛 Rozwiązywanie problemów

### Błędy podczas importu PDF
- Sprawdź czy WeasyPrint jest poprawnie zainstalowany
- Upewnij się, że wszystkie czcionki są dostępne

### Problemy z JPK_FA
- Sprawdź czy plik XML jest poprawnie sformatowany
- Upewnij się, że zawiera wymagane pola (NIP, nazwa kontrahenta)

### Błędy składek ZUS
- Zaktualizuj stawki ZUS w panelu administracyjnym
- Sprawdź ustawienia firmy (preferencje, Małe ZUS Plus)

## 📝 Licencja

Ten projekt jest udostępniony na licencji MIT. Zobacz plik `LICENSE` dla szczegółów.

## 🤝 Wkład w projekt

Jeśli chcesz przyczynić się do rozwoju projektu:

1. Fork repozytorium
2. Utwórz branch dla swojej funkcji (`git checkout -b feature/AmazingFeature`)
3. Commit zmiany (`git commit -m 'Add some AmazingFeature'`)
4. Push do brancha (`git push origin feature/AmazingFeature`)
5. Otwórz Pull Request

## 📞 Kontakt

W przypadku pytań lub problemów:
- Otwórz issue na GitHubie
- Email: kwasiek@gmail.com

## 📚 Dodatkowe zasoby

- [Dokumentacja Django](https://docs.djangoproject.com/)
- [Przepisy o JPK_FA](https://www.gov.pl/web/kas/jednolity-plik-kontrolny-jpk)
- [Aktualne stawki ZUS](https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki)

---

**💡 Wskazówka:** Po pierwszym uruchomieniu nie zapomnij uzupełnić danych firmy i zaktualizować stawek ZUS!

## 🔄 Historia wersji

### v1.0.0 (Aktualna)
- Podstawowe zarządzanie fakturami
- Import/Export JPK_FA
- Rozliczenia miesięczne i roczne
- Kalkulator składek ZUS
- Generowanie PDF

### Planowane funkcje
- [ ] Integracja z systemami bankowymi
- [ ] Automatyczne wysyłanie faktur email
- [ ] Dashboard z wykresami i statystykami
- [ ] Eksport do programów księgowych
- [ ] Aplikacja mobilna
