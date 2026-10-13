# Moja Fakturownia

System księgowy dla jednoosobowej działalności gospodarczej, zbudowany na Django i panelu admina Jazzmin. Obsługuje faktury sprzedaży i zakupu, integrację z **KSeF 2.0** (wysyłka i import faktur), import/eksport **JPK_FA** i import **JPK_EWP**, rozliczenia miesięczne i roczne na ryczałcie, składki ZUS oraz rozliczanie **dyżurów medycznych** na fakturach. Działa jako PWA (instalacja na urządzeniu, tryb offline). Wielu użytkowników — każdy widzi tylko własne dane.

Instancja produkcyjna: <https://moja-fakturownia.cytr.us> (rejestracja formularzem lub kontem Google).

Wersja: 1.4.0 · Python 3.12 · Django 6.1

## Funkcje

### Sprzedaż
- Faktury z pozycjami i automatycznym przeliczaniem wartości; numeracja automatyczna.
- Faktury korygujące powiązane z fakturą pierwotną (pozycje „było” / „powinno być”).
- PDF faktury (WeasyPrint).
- Płatności przypisane do faktur, status płatności (opłacona / częściowo / nieopłacona / przeterminowana), raport płatności i raport faktur przeterminowanych.

### KSeF (API 2.0, biblioteka `ksef2`)
- Konfiguracja w „Dane firmy”: NIP, token KSeF (generowany w Aplikacji Podatnika KSeF) i środowisko — test, demo albo produkcja.
- Wysyłka zaznaczonych faktur sprzedaży: XML w schemacie FA(3), sesja interaktywna, zapis numeru referencyjnego i statusu KSeF na fakturze; akcja „Resetuj status KSeF”.
- Import/synchronizacja faktur sprzedaży (rola sprzedawcy): faktury już istniejące w bazie dostają numer i status KSeF, kwoty i pozycje pozostają bez zmian; brakujące są tworzone z jedną pozycją zbiorczą.
- Import faktur zakupu (rola nabywcy) z metadanych KSeF; oryginalny XML zapisywany jako załącznik, kategoria kosztu ustawiana domyślnie do ręcznego doprecyzowania.
- Log komunikacji z KSeF w `logs/ksef.log`.

### Koszty
- Faktury zakupu z pozycjami, podział na koszty uzyskania przychodu i VAT do odliczenia.
- Kategorie kosztów, raporty kosztów za okres, analiza według kategorii, przeterminowane płatności za zakupy.

### JPK
- Import JPK_FA z pliku XML: tworzy kontrahentów, faktury z pozycjami i rozpoznaje korekty.
- Eksport zaznaczonych faktur do JPK_FA(4).
- Import JPK_EWP (warianty 3 i 4) do rozliczeń miesięcznych.

### Rozliczenia i ZUS
- Rozliczenie miesięczne: przychód z faktur za miesiąc, wpłacone składki, należny ryczałt.
- Rozliczenie roczne: dopłata lub zwrot podatku, podgląd i PDF.
- Kalkulator składek ZUS; stawki ZUS pobierane ze strony ZUS.pl (przycisk w panelu lub komenda `update_zus_rates`).
- Dashboard finansowy: przychody, koszty, zysk, porównanie rok do roku, prognoza na koniec roku podatkowego (`/admin/ksiegowosc/monthlysettlement/dashboard/`).

### Dyżury medyczne
- Cenniki per kontrahent (szpital/placówka) z datą obowiązywania — cztery stawki godzinowe: dzień roboczy lub weekend/święto × dyżur samodzielny lub towarzyszący. Historia stawek jest zachowana, do dyżuru stosowana jest stawka obowiązująca w jego dniu.
- Dyżury z liczbą godzin wyliczaną z godzin od–do (także przez północ), flagą święta i oddziałem (OPK).
- Import grafiku przez wklejenie tekstu, jedna linia na dyżur, pola rozdzielone tabulatorem lub średnikiem:
  ```
  DATA;OD;DO;RODZAJ;OPK;UWAGI
  04.07.2026;20:00;8:00;samodzielny;;
  07.07.2026;18:00;8:00;towarzyszacy;500-00-16;
  ```
- Akcja „Wystaw fakturę z zaznaczonych dyżurów” — grupuje dyżury według rodzaju i typu dnia, zamraża zastosowaną stawkę na dyżurze.
- Załącznik PDF z wykazem dyżurów do faktury.

### Konta i dostęp
- Rejestracja i logowanie formularzem lub przez Google (OAuth2); nowy użytkownik trafia do grupy `ksiegowosc` z uprawnieniami do modułu, po pierwszym logowaniu przez Google — do formularza danych firmy.
- Izolacja danych: listy w panelu filtrowane po użytkowniku (superużytkownik widzi wszystko).
- Endpointy kontrolne: `/health/` (JSON: baza, cache), `/ready/`, `/live/`.

### PWA
- Manifest, service worker (`/sw.js`) z cache zasobów i stroną offline, skróty do najczęstszych akcji.

## Stos

| Warstwa | Technologia |
|---|---|
| Backend | Django 6.1, Python 3.12 |
| Panel | django-jazzmin 3.0.5 (Bootstrap 5) |
| KSeF | ksef2 0.18.1 |
| PDF | WeasyPrint 69 |
| Import/eksport | django-import-export 4.4, lxml, defusedxml |
| Logowanie | social-auth-app-django 6.0 (Google OAuth2) |
| Konfiguracja | django-environ (`.env`) |
| Pliki statyczne | WhiteNoise + `LenientManifestStaticFilesStorage` |
| Baza | SQLite domyślnie; PostgreSQL przez `DATABASE_URL` (psycopg2 w zależnościach) |
| Produkcja | gunicorn + nginx + systemd |

## Uruchomienie lokalne

WeasyPrint wymaga systemowych bibliotek Pango (Debian/Ubuntu: m.in. `libpango-1.0-0 libpangoft2-1.0-0`; szczegóły w dokumentacji WeasyPrint).

```bash
git clone https://github.com/kwasiucionek/moja-fakturownia.git
cd moja-fakturownia
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p logs                     # wymagane — konfiguracja logowania zapisuje do logs/
echo "DEBUG=True" > .env          # reszta ma wartości domyślne (SQLite w db.sqlite3)
python manage.py migrate
python manage.py setup_auth       # grupa "ksiegowosc" i jej uprawnienia
python manage.py createsuperuser  # albo: create_superuser_with_company (niżej)
python manage.py runserver
```

Aplikacja: <http://127.0.0.1:8000/> (przekierowanie na `/auth/login/`), panel: `/admin/`.

Po pierwszym zalogowaniu:
1. „Dane firmy” — uzupełnij dane, formę opodatkowania, ustawienia ZUS; dla KSeF także token i środowisko.
2. „Stawki ZUS” → „Aktualizuj stawki”.

## Konfiguracja (`.env`)

`settings.py` czyta wyłącznie poniższe zmienne:

| Zmienna | Domyślnie | Uwagi |
|---|---|---|
| `SECRET_KEY` | klucz deweloperski | w produkcji obowiązkowo własny |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | lista po przecinku |
| `CSRF_TRUSTED_ORIGINS` | pusta | np. `https://moja-fakturownia.cytr.us` |
| `DATABASE_URL` | `sqlite:///<repo>/db.sqlite3` | np. `postgres://user:pass@host:5432/db` |
| `DB_CONN_MAX_AGE`, `DB_CONN_HEALTH_CHECKS` | `600`, `True` | |
| `GOOGLE_OAUTH2_KEY`, `GOOGLE_OAUTH2_SECRET` | puste | logowanie przez Google |
| `SECURE_SSL_REDIRECT` | `False` | za proxy terminującym TLS (Cloudflare) zostaw `False` |
| `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD` | `0`, `False`, `False` | |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `False` | w produkcji `True` |
| `SESSION_COOKIE_AGE` | `28800` (8 h) | |
| `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_BROWSER_XSS_FILTER` | `True` | |
| `LANGUAGE_CODE`, `TIME_ZONE` | `pl`, `Europe/Warsaw` | |
| `STATIC_ROOT`, `MEDIA_ROOT` | `staticfiles/`, `media/` | |
| `DJANGO_LOG_FILE`, `KSEF_LOG_FILE` | `logs/django.log`, `logs/ksef.log` | katalog musi istnieć |

Inne klucze obecne w starszych przykładach `.env` (`EMAIL_*`, `SENTRY_*`, `REDIS_URL`, `CSP_*` itp.) nie są używane.

### Logowanie przez Google

W Google Cloud Console utwórz klienta OAuth 2.0 (aplikacja internetowa) i dodaj Authorized redirect URI:

```
https://<twoja-domena>/auth/social-auth/complete/google-oauth2/
```

Lokalnie: `http://127.0.0.1:8000/auth/social-auth/complete/google-oauth2/`. Klucze wpisz do `GOOGLE_OAUTH2_KEY` i `GOOGLE_OAUTH2_SECRET`.

## Komendy zarządzania

| Komenda | Działanie |
|---|---|
| `setup_auth` | tworzy grupę `ksiegowosc` i przypisuje jej uprawnienia |
| `create_superuser_with_company --username … --email … --password … --company-name … --nip …` | superużytkownik z podstawowymi danymi firmy |
| `fix_user_permissions` | naprawia uprawnienia istniejących użytkowników |
| `list_users` | lista użytkowników |
| `update_zus_rates [--year RRRR] [--force]` | pobiera stawki ZUS z ZUS.pl |

## Wdrożenie produkcyjne

Wzorzec użyty na instancji produkcyjnej: gunicorn na `127.0.0.1:8500` jako usługa systemd, nginx przed nim, Cloudflare terminuje TLS.

```bash
pip install gunicorn               # nie ma go w requirements.txt
mkdir -p logs
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py setup_auth
```

- `fakturownia.service` — przykładowy unit systemd (`EnvironmentFile=.env`, 3 workery, timeout 120 s, logi gunicorna w `logs/`). Dostosuj `User`, `WorkingDirectory` i ścieżki.
- `fakturownia.conf` — konfiguracja nginx: `/static/` i `/media/` serwowane z dysku, `/sw.js` bez cache, reszta proxy do gunicorna, `client_max_body_size 10M`.
- `deploy.sh` pochodzi z wcześniejszego wariantu opartego na docker-compose i nie odpowiada obecnemu wdrożeniu.

## Struktura projektu

```
fakturownia/            ustawienia Django, urls (w tym /health/, /ready/, /live/), storage.py
ksiegowosc/             główna aplikacja
  models.py             CompanyInfo, Contractor, Invoice(+Item), Payment, PurchaseInvoice(+Item),
                        ExpenseCategory, ExpenseReport, MonthlySettlement, YearlySettlement,
                        ZUSRates, DutyRate, DutyShift
  admin.py              panel: widoki importu/eksportu, rozliczenia, dashboard, dyżury, akcje KSeF
  formats.py            formaty django-import-export dla JPK
  auth_*.py             rejestracja, logowanie, pipeline social-auth
  pwa_views.py          manifest, service worker, API PWA
  management/commands/  komendy z tabeli wyżej
  templates/            szablony panelu, PDF (faktura, rozliczenie roczne, załącznik dyżurów), PWA
ksef/
  services.py           wysyłka faktur do KSeF (ksef2)
  ksef2_import.py       import faktur sprzedaży i zakupu z KSeF
  xml_generator.py      XML faktury FA(3)
static/                 sw.js, manifest i ikony PWA
```

## Znane ograniczenia

- Rozliczenie miesięczne liczy ryczałt stałą stawką 14% (po odjęciu składek społecznych i połowy zdrowotnej); stawka ryczałtu z „Danych firmy” nie jest tu jeszcze używana.
- Reset hasła e-mailem wymaga skonfigurowania backendu poczty — `settings.py` obecnie nie czyta zmiennych `EMAIL_*`.
- Brak testów automatycznych.

## Ostatnie zmiany (VIII–IX 2026)

- Aktualizacja do Django 6.1 i Jazzmin 3.0.5 (Bootstrap 5), porządki w zależnościach (usunięte m.in. `ksef-utils`, `django-health-check`, Sphinx).
- Integracja KSeF przepisana na bibliotekę `ksef2` (API 2.0, schemat FA(3)); nowy import faktur sprzedaży i zakupu z KSeF.
- Moduł dyżurów medycznych: cenniki, import grafiku, faktura z dyżurów, załącznik PDF.
- `LenientManifestStaticFilesStorage` dla zasobów vendor, poprawione ścieżki logów.

## Licencja

[CC BY-NC-SA 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/) — uznanie autorstwa, użycie niekomercyjne, na tych samych warunkach. Pełna treść w pliku `LICENSE`.

Pytania i błędy: [Issues](https://github.com/kwasiucionek/moja-fakturownia/issues).
