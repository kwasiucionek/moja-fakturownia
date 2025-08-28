# 📊 Moja Fakturownia

Kompleksowy system księgowy dla jednoosobowych działalności gospodarczych. Aplikacja Django z panelem administracyjnym umożliwiającym zarządzanie fakturami, kosztami, płatnościami oraz automatyczne rozliczenia podatkowe i składki ZUS. Aplikacja jest również Progresywną Aplikacją Webową (PWA), co umożliwia jej instalację na urządzeniach i pracę w trybie offline.

Wersja demonstracyjna, w pełni funkcjonalna: https://kwasiucionek.cytr.us/

## ✨ Funkcjonalności

### 📈 Zarządzanie Sprzedażą
- **Wystawianie faktur** z automatyczną numeracją
- **Faktury korygujące** z powiązaniem do oryginalnych dokumentów i automatycznym wykrywaniem stanu "było" / "powinno być"
- **Generowanie PDF** z profesjonalnymi szablonami dla faktur i korekt
- **Import/Export JPK_FA** - automatyczny import faktur sprzedaży z plików XML oraz eksport zaznaczonych dokumentów
- **Zarządzanie pozycjami na fakturach** z automatycznym obliczaniem wartości

### 📉 Zarządzanie Kosztami
- **Rejestracja faktur zakupu** z podziałem na koszty uzyskania przychodu i VAT do odliczenia
- **Kategorie kosztów** dla lepszej analityki i organizacji wydatków
- **Raporty kosztów** - generowanie szczegółowych raportów kosztów w wybranym okresie oraz analiza po kategoriach
- **Śledzenie płatności za koszty** ze statusami (opłacona, przeterminowana, oczekuje)

### 💰 Płatności i Rozliczenia
- **Śledzenie płatności** - dedykowany moduł do rejestrowania wpłat od klientów i powiązania ich z fakturami
- **Automatyczny status płatności** (opłacona, częściowo opłacona, przeterminowana, nieopłacona)
- **Rozliczenia miesięczne** z automatycznym obliczaniem podatku ryczałtowego
- **Import JPK_EWP** do automatycznego uzupełniania przychodów w rozliczeniach miesięcznych
- **Rozliczenia roczne** z automatycznym wykrywaniem dopłat/zwrotów podatku
- **Kalkulator składek ZUS** z aktualnymi stawkami, uwzględniający ulgi (preferencyjny ZUS, Mały ZUS Plus)

### 📊 Dashboard i Raporty
- **Zaawansowany dashboard finansowy** z wykresami przychodów, kosztów, zysku i porównaniem rok do roku
- **Progres roku podatkowego** z prognozami przychodu i podatku na koniec roku
- **Raporty płatności** i faktur przeterminowanych
- **Generowanie PDF** dla faktur oraz rocznych podsumowań podatkowych

### 📱 Progressive Web App (PWA)
- **Możliwość instalacji** na komputerach i urządzeniach mobilnych, działając jak natywna aplikacja
- **Praca w trybie offline** dzięki zaawansowanemu Service Workerowi, który cache'uje zasoby i dane
- **Szybki dostęp** dzięki skrótom do najczęstszych akcji (np. nowa faktura, dashboard)
- **Powiadomienia** o statusie połączenia i dostępnych aktualizacjach

### 🔑 Uwierzytelnianie i Bezpieczeństwo
- **Logowanie i rejestracja przez Google** (OAuth2) dla wygody użytkowników
- **Automatyczne zarządzanie uprawnieniami** i przypisywanie nowych użytkowników do odpowiedniej grupy
- **Zaawansowane ustawienia bezpieczeństwa** dla środowiska produkcyjnego (nagłówki HTTP, ciasteczka, CSRF)
- **Skrypty do wdrożenia i sprawdzania bezpieczeństwa** (deploy.sh, security_check.py)

### 🏢 Dane Firmy
- Kompleksowy profil firmy
- Ustawienia podatku (ryczałt, skala, liniowy)
- Konfiguracja VAT i ZUS
- Dane do faktur i rozliczeń

## 🛠️ Technologie

- **Backend:** Django 5.2.3
- **Frontend:** Bootstrap 5 + Jazzmin Admin
- **Baza danych:** SQLite (domyślnie), PostgreSQL (produkcyjnie)
- **PDF:** WeasyPrint
- **Uwierzytelnianie:** django-social-auth (dla Google OAuth)
- **PWA:** Service Workers, Manifest API
- **Styling:** CSS3, Font Awesome
- **Python:** 3.12+

## 📋 Wymagania

- Python 3.12 lub nowszy
- pip (menedżer pakietów Python)
- Opcjonalnie: virtualenv

## 🚀 Instalacja

1. **Sklonuj repozytorium**
```bash
git clone https://github.com/twoj-username/moja-fakturownia.git
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
2. **Uzupełnij dane firmy** - przejdź do "Dane Firmy" i wprowadź wszystkie wymagane informacje
3. **Zaktualizuj stawki ZUS** - przejdź do "Stawki ZUS" i kliknij "Aktualizuj stawki"

### Konfiguracja Google Login
Aby włączyć logowanie przez Google, dodaj do pliku `.env` swoje klucze API:
```env
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=twoj-klucz-klienta
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET=twoj-sekret-klienta
```

### Struktura bazy danych
- `CompanyInfo` - dane firmy
- `Contractor` - kontrahenci
- `Invoice` + `InvoiceItem` - faktury z pozycjami
- `PurchaseInvoice` - faktury zakupu/koszty
- `Payment` - płatności od klientów
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

### Zarządzanie kosztami
1. Przejdź do "Faktury zakupu" → "Dodaj fakturę zakupu"
2. Wprowadź dane faktury, wybierz kategorię i zaznacz, czy jest to koszt uzyskania przychodu
3. Po zapisaniu, koszt zostanie uwzględniony w raportach i przyszłych rozliczeniach

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

### Praca z PWA
1. Otwórz aplikację w przeglądarce obsługującej PWA (np. Chrome, Edge, Safari)
2. W pasku adresu powinna pojawić się ikona instalacji
3. Kliknij ją, aby zainstalować aplikację na pulpicie lub ekranie głównym
4. Uruchamiaj aplikację za pomocą nowej ikony, aby korzystać z trybu offline

## 📁 Struktura Projektu

```
moja-fakturownia/
├── fakturownia/                 # Główne ustawienia Django
│   ├── settings.py
│   └── urls.py
├── ksiegowosc/                  # Główna aplikacja
│   ├── admin.py                 # Panel administracyjny
│   ├── models.py                # Modele danych
│   ├── views.py                 # Widoki
│   ├── auth_views.py            # Widoki autoryzacji
│   ├── pwa_views.py             # Widoki dla PWA
│   ├── middleware.py            # Middleware
│   ├── auth_pipeline.py         # Pipeline dla social auth
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
│   ├── pwa/                     # Zasoby PWA (ikony, manifest)
│   └── sw.js                    # Service Worker
├── media/                       # Pliki użytkowników
├── requirements.txt             # Zależności Python
├── deploy.sh                    # Skrypt wdrożeniowy
└── manage.py                    # Skrypt zarządzający Django
```

## 🔧 Funkcje zaawansowane

### Automatyzacja składek ZUS
- Pobieranie aktualnych stawek ze strony ZUS.pl
- Obliczanie składek na podstawie ustawień firmy
- Obsługa preferencji i ulg

### JPK
- Import z różnych wersji schematu JPK_FA oraz JPK_EWP
- Eksport JPK_FA zgodny z wymogami MF
- Obsługa faktur korygujących

### Wieloużytkownikowość
- Każdy użytkownik ma swoją niezależną księgowość
- Izolacja danych między firmami
- Automatyczne zarządzanie uprawnieniami

## 🐛 Rozwiązywanie problemów

### Błędy podczas importu PDF
- Sprawdź czy WeasyPrint jest poprawnie zainstalowany
- Upewnij się, że wszystkie czcionki są dostępne

### Problemy z JPK_FA
- Sprawdź czy plik XML jest poprawnie sformatowany
- Upewnij się, że zawiera wymagane pola (NIP, nazwa kontrahenta)

### Błędy składek ZUS
- Zaktualizuj stawki ZUS w panelu administracyjnym
- Sprawdź ustawienia firmy (preferencje, Mały ZUS Plus)

### Problemy z PWA
- Upewnij się, że serwer działa w trybie HTTPS (nawet z certyfikatem self-signed dla developmentu), aby Service Worker działał poprawnie
- Wyczyść dane przeglądarki (cache i Service Workers) w narzędziach deweloperskich, jeśli aplikacja nie aktualizuje się

### Błędy logowania przez Google
- Sprawdź, czy `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY` i `SECRET` w `.env` są poprawne
- Upewnij się, że w konsoli Google Cloud skonfigurowałeś poprawny Redirect URI, który powinien wskazywać na `http://127.0.0.1:8000/auth/social/complete/google-oauth2/`

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
- Email: twoj-email@example.com

## 📚 Dodatkowe zasoby

- [Dokumentacja Django](https://docs.djangoproject.com/)
- [Przepisy o JPK_FA](https://www.gov.pl/web/kas/jednolity-plik-kontrolny-jpk)
- [Aktualne stawki ZUS](https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki)

---

**💡 Wskazówka:** Po pierwszym uruchomieniu nie zapomnij uzupełnić danych firmy i zaktualizować stawek ZUS!

## 🔄 Historia wersji

### v1.0.0 (Aktualna)
- **Pełne zarządzanie fakturami sprzedaży i kosztów**
- **Import/Export JPK_FA** i **import JPK_EWP**
- **Rozliczenia miesięczne i roczne**
- **Kalkulator składek ZUS**
- **Generowanie PDF**
- **🆕 Aplikacja PWA z trybem offline**
- **🆕 Logowanie przez Google**
- **🆕 Zaawansowany dashboard finansowy**
- **🆕 Moduł śledzenia płatności**

### Planowane funkcje
- [ ] Integracja z systemami bankowymi
- [ ] Automatyczne wysyłanie faktur email
- [ ] Eksport do programów księgowych
- [ ] Aplikacja mobilna

## 📝 Licencja

Ten projekt jest udostępniony na licencji Creative Commons (CC BY-NC-SA 4.0).

**Oznacza to, że możesz swobodnie:**
- Kopiować i rozpowszechniać oprogramowanie w dowolnym medium i formacie
- Adaptować, remiksować i tworzyć na podstawie tego oprogramowania

**Pod następującymi warunkami:**
- **Uznanie autorstwa (BY)** — Musisz odpowiednio oznaczyć autorstwo, podać link do licencji i wskazać, czy dokonano zmian
- **Użycie niekomercyjne (NC)** — Nie możesz używać tego oprogramowania do celów komercyjnych
- **Na tych samych warunkach (SA)** — Jeśli remiksujesz, zmieniasz lub tworzysz na podstawie materiału, musisz rozpowszechniać swoje dzieła na tej samej licencji, co oryginał

Pełną treść licencji znajdziesz w pliku LICENSE w tym repozytorium oraz pod adresem:
http://creativecommons.org/licenses/by-nc-sa/4.0/
