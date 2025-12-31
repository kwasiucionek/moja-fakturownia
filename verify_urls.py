#!/usr/bin/env python3
"""
Weryfikacja wszystkich odniesień {% url %} w szablonach Django
Sprawdza czy wszystkie URL-e używane w szablonach są poprawnie zdefiniowane
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

def extract_url_references(template_path):
    """Wyciąga wszystkie odniesienia {% url %} z szablonu"""
    try:
        content = template_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"❌ Błąd odczytu {template_path}: {e}")
        return []
    
    # Wzorce dla różnych formatów {% url %}
    patterns = [
        r"{%\s*url\s+['\"]([^'\"]+)['\"]\s*%}",  # {% url 'name' %}
        r"{%\s*url\s+['\"]([^'\"]+)['\"]\s+\d+\s*%}",  # {% url 'name' 123 %}
        r"{%\s*url\s+['\"]([^'\"]+)['\"]\s+[a-zA-Z_]+\s*%}",  # {% url 'name' variable %}
    ]
    
    urls = []
    for pattern in patterns:
        urls.extend(re.findall(pattern, content))
    
    return list(set(urls))  # Unikalne wartości

def analyze_url_name(url_name):
    """Analizuje nazwę URL i zwraca informacje o nim"""
    parts = url_name.split(':')
    
    if len(parts) == 2 and parts[0] == 'admin':
        # Format: admin:app_model_action
        admin_url = parts[1]
        url_parts = admin_url.split('_')
        
        return {
            'type': 'admin',
            'full_name': url_name,
            'app': url_parts[0] if len(url_parts) > 0 else None,
            'model': url_parts[1] if len(url_parts) > 1 else None,
            'action': '_'.join(url_parts[2:]) if len(url_parts) > 2 else None,
        }
    else:
        return {
            'type': 'custom',
            'full_name': url_name,
        }

def check_expected_urls():
    """Zwraca listę oczekiwanych URL-i w admin.py"""
    return {
        'InvoiceAdmin': [
            'admin:ksiegowosc_invoice_pdf',
            'admin:ksiegowosc_invoice_import_jpk',
            'admin:ksiegowosc_invoice_export_jpk',
            'admin:ksiegowosc_invoice_send_ksef',
            'admin:ksiegowosc_invoice_payments_report',
            'admin:ksiegowosc_invoice_overdue_report',
        ],
        'PurchaseInvoiceAdmin': [
            'admin:ksiegowosc_purchaseinvoice_expenses_report',
            'admin:ksiegowosc_purchaseinvoice_category_analysis',
            'admin:ksiegowosc_purchaseinvoice_overdue_purchases',
        ],
        'MonthlySettlementAdmin': [
            'admin:ksiegowosc_monthlysettlement_dashboard',
            'admin:ksiegowosc_monthlysettlement_import_jpk_ewp',
        ],
        'YearlySettlementAdmin': [
            'admin:ksiegowosc_yearlysettlement_generate_pdf',
        ],
    }

def main():
    print("=" * 80)
    print("WERYFIKACJA ODNIESIEŃ URL W SZABLONACH")
    print("=" * 80)
    print()
    
    # Znajdź wszystkie szablony
    templates_dir = Path("ksiegowosc/templates")
    
    if not templates_dir.exists():
        print(f"❌ Nie znaleziono katalogu: {templates_dir}")
        print("   Uruchom skrypt z katalogu głównego projektu")
        sys.exit(1)
    
    template_files = list(templates_dir.rglob("*.html"))
    print(f"📁 Znaleziono {len(template_files)} plików HTML")
    print()
    
    # Zbierz wszystkie URL-e z wszystkich szablonów
    all_urls = defaultdict(list)
    
    for template_file in template_files:
        urls = extract_url_references(template_file)
        for url in urls:
            all_urls[url].append(template_file)
    
    # Analiza URL-i
    admin_urls = {}
    custom_urls = {}
    
    for url_name, templates in all_urls.items():
        info = analyze_url_name(url_name)
        if info['type'] == 'admin':
            admin_urls[url_name] = templates
        else:
            custom_urls[url_name] = templates
    
    # Wyświetl URL-e admin
    if admin_urls:
        print("📋 URL-E ADMIN (admin:*)")
        print("-" * 80)
        for url_name in sorted(admin_urls.keys()):
            info = analyze_url_name(url_name)
            print(f"\n   {url_name}")
            if info.get('model'):
                print(f"      Model: {info['model']}")
                print(f"      Action: {info['action']}")
            print(f"      Używany w:")
            for template in admin_urls[url_name][:3]:  # Pokaż max 3 szablony
                rel_path = template.relative_to(Path.cwd())
                print(f"         - {rel_path}")
    
    # Wyświetl URL-e custom
    if custom_urls:
        print("\n\n📋 URL-E NIESTANDARDOWE")
        print("-" * 80)
        for url_name in sorted(custom_urls.keys()):
            print(f"   - {url_name}")
    
    # Sprawdź które URL-e wymagają definicji w get_urls()
    print("\n\n" + "=" * 80)
    print("WYMAGANE DEFINICJE W get_urls()")
    print("=" * 80)
    
    expected = check_expected_urls()
    
    for class_name, expected_urls in expected.items():
        print(f"\n📌 {class_name}:")
        for url in expected_urls:
            if url in admin_urls:
                print(f"   ✓ {url}")
            else:
                print(f"   ? {url} (nie znaleziono w szablonach)")
    
    # Sprawdź URL-e które są w szablonach ale nie są w expected
    print("\n\n" + "=" * 80)
    print("URL-E NIEOCZEKIWANE (mogą wymagać dodania)")
    print("=" * 80)
    
    all_expected = []
    for urls in expected.values():
        all_expected.extend(urls)
    
    unexpected = [url for url in admin_urls.keys() 
                  if url not in all_expected 
                  and url.startswith('admin:ksiegowosc_')]
    
    if unexpected:
        for url in sorted(unexpected):
            print(f"   ⚠️  {url}")
    else:
        print("   ✅ Wszystkie URL-e są oczekiwane")
    
    print("\n")

if __name__ == "__main__":
    main()
