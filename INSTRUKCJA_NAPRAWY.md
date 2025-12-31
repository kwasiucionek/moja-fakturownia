# NAPRAWA BŁĘDÓW NoReverseMatch W DJANGO ADMIN

## Problem
Błąd: `Reverse for 'ksiegowosc_invoice_payments_report' not found`

Przyczyną jest nieprawidłowa definicja URL-i w metodach `get_urls()` w pliku `ksiegowosc/admin.py`.

## Rozwiązanie - KROK PO KROKU

### OPCJA 1: Automatyczna naprawa (ZALECANA) ⚡

```bash
# 1. Przejdź do katalogu projektu
cd ~/Documents/DANE/rozliczanie/moja-fakturownia

# 2. Uruchom skrypt automatycznej naprawy
python3 auto_fix_urls.py

# 3. Sprawdź czy nie ma błędów składniowych
python manage.py check

# 4. Uruchom serwer
python manage.py runserver
```

### OPCJA 2: Manualna naprawa

#### 1. Znajdź i napraw InvoiceAdmin.get_urls()

Otwórz `ksiegowosc/admin.py` i znajdź klasę `InvoiceAdmin`.

Znajdź metodę `get_urls()` (około linii 615-660) i **zamień ją** na:

```python
def get_urls(self):
    """Dodaje niestandardowe URL-e dla Invoice"""
    from django.urls import path
    urls = super().get_urls()
    
    # Poprawna definicja info tuple
    info = self.model._meta.app_label, self.model._meta.model_name

    my_urls = [
        # PDF generation
        path(
            "<int:object_id>/change/generate-pdf/",
            self.admin_site.admin_view(self.generate_pdf_view),
            name="%s_%s_pdf" % info,
        ),
        # JPK import
        path(
            "import-jpk/",
            self.admin_site.admin_view(self.import_jpk_view),
            name="%s_%s_import_jpk" % info,
        ),
        # JPK export
        path(
            "export-jpk/",
            self.admin_site.admin_view(self.export_jpk_view),
            name="%s_%s_export_jpk" % info,
        ),
        # KSeF send
        path(
            "send-ksef/",
            self.admin_site.admin_view(self.send_to_ksef_view),
            name="%s_%s_send_ksef" % info,
        ),
        # Payments report
        path(
            "payments-report/",
            self.admin_site.admin_view(self.payments_report_view),
            name="%s_%s_payments_report" % info,
        ),
        # Overdue report
        path(
            "overdue-report/",
            self.admin_site.admin_view(self.overdue_report_view),
            name="%s_%s_overdue_report" % info,
        ),
    ]
    return my_urls + urls
```

#### 2. Napraw PurchaseInvoiceAdmin.get_urls()

Znajdź klasę `PurchaseInvoiceAdmin` i zamień jej metodę `get_urls()`:

```python
def get_urls(self):
    """Dodaje niestandardowe URL-e dla PurchaseInvoice"""
    from django.urls import path
    urls = super().get_urls()
    
    info = self.model._meta.app_label, self.model._meta.model_name

    my_urls = [
        # Expenses report
        path(
            "expenses-report/",
            self.admin_site.admin_view(self.expenses_report_view),
            name="%s_%s_expenses_report" % info,
        ),
        # Category analysis
        path(
            "category-analysis/",
            self.admin_site.admin_view(self.category_analysis_view),
            name="%s_%s_category_analysis" % info,
        ),
        # Overdue purchases
        path(
            "overdue-purchases/",
            self.admin_site.admin_view(self.overdue_purchases_view),
            name="%s_%s_overdue_purchases" % info,
        ),
    ]
    return my_urls + urls
```

#### 3. Napraw MonthlySettlementAdmin.get_urls()

```python
def get_urls(self):
    """Dodaje niestandardowe URL-e dla MonthlySettlement"""
    from django.urls import path
    urls = super().get_urls()
    
    info = self.model._meta.app_label, self.model._meta.model_name

    my_urls = [
        # Dashboard
        path(
            "dashboard/",
            self.admin_site.admin_view(self.dashboard_view),
            name="%s_%s_dashboard" % info,
        ),
        # JPK import
        path(
            "import-jpk-ewp/",
            self.admin_site.admin_view(self.import_jpk_ewp_view),
            name="%s_%s_import_jpk_ewp" % info,
        ),
    ]
    return my_urls + urls
```

#### 4. Napraw YearlySettlementAdmin.get_urls()

```python
def get_urls(self):
    """Dodaje niestandardowe URL-e dla YearlySettlement"""
    from django.urls import path
    urls = super().get_urls()
    
    info = self.model._meta.app_label, self.model._meta.model_name

    my_urls = [
        # Generate PDF
        path(
            "<int:object_id>/generate-pdf/",
            self.admin_site.admin_view(self.generate_pdf_view),
            name="%s_%s_generate_pdf" % info,
        ),
    ]
    return my_urls + urls
```

## Weryfikacja

Po dokonaniu zmian:

```bash
# Sprawdź składnię
python manage.py check

# Sprawdź URL-e
python manage.py show_urls | grep ksiegowosc

# Uruchom serwer
python manage.py runserver

# Otwórz dashboard
# http://localhost:8000/admin/ksiegowosc/monthlysettlement/dashboard/
```

## Pomocnicze skrypty

### verify_urls.py
Sprawdza wszystkie odniesienia URL w szablonach:
```bash
python3 verify_urls.py
```

### check_urls.py
Wyciąga wszystkie użycia {% url %} z szablonów:
```bash
python3 check_urls.py
```

## Co zostało naprawione?

1. ✅ Usunięto błędną funkcję `info(model_name)` która była źle zdefiniowana
2. ✅ Zastąpiono ją prostym przypisaniem `info = self.model._meta.app_label, self.model._meta.model_name`
3. ✅ Zaktualizowano wszystkie odniesienia do `info` (usunięto wywołanie funkcji)
4. ✅ Dodano wszystkie wymagane URL-e dla raportów i akcji

## Główne błędy które były w oryginalnym kodzie:

```python
# BŁĘDNY KOD (NIE UŻYWAJ!)
def info(model_name):  # <- Funkcja przyjmuje parametr ale go nie używa!
    return (self.model._meta.app_label, model_name)

# Później wywołanie:
name="%s_%s_pdf" % info(self.model)  # <- Wywołanie z parametrem

# PROBLEM: info() zwraca (app_label, model_name) ale parametr jest ignorowany!
```

```python
# POPRAWNY KOD
info = self.model._meta.app_label, self.model._meta.model_name

# Później użycie:
name="%s_%s_pdf" % info  # <- Proste użycie tupli
```

## Backup

Skrypt `auto_fix_urls.py` automatycznie tworzy backup jako `admin.py.backup` przed dokonaniem zmian.

---

**Autor naprawy:** Claude (Anthropic)  
**Data:** 31 grudnia 2024  
**Wersja:** 1.0
