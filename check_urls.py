#!/usr/bin/env python3
"""
Skrypt do sprawdzenia odniesień URL w szablonie enhanced_dashboard.html
"""
import re
import sys

def extract_url_tags(template_path):
    """Wyciąga wszystkie tagi {% url %} z szablonu"""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Wzorzec do wyciągania {% url 'nazwa' %}
        pattern = r"{%\s*url\s+['\"]([^'\"]+)['\"]\s*%}"
        urls = re.findall(pattern, content)
        
        return urls
    except FileNotFoundError:
        print(f"❌ Nie znaleziono pliku: {template_path}")
        return []

def main():
    template_path = "ksiegowosc/templates/admin/enhanced_dashboard.html"
    
    print("=" * 80)
    print("SPRAWDZANIE ODNIESIEŃ URL W SZABLONIE")
    print("=" * 80)
    
    urls = extract_url_tags(template_path)
    
    if not urls:
        print("❌ Nie znaleziono żadnych odniesień URL")
        return
    
    print(f"\n✅ Znaleziono {len(urls)} odniesień URL:\n")
    
    # Grupowanie URL-i po prefiksie
    admin_urls = [u for u in urls if u.startswith('admin:')]
    other_urls = [u for u in urls if not u.startswith('admin:')]
    
    print("📋 URL-e admin:")
    for url in sorted(set(admin_urls)):
        print(f"   - {url}")
    
    if other_urls:
        print("\n📋 Inne URL-e:")
        for url in sorted(set(other_urls)):
            print(f"   - {url}")
    
    # Sprawdzenie które URL-e dotyczą Invoice
    print("\n" + "=" * 80)
    print("URL-E WYMAGAJĄCE DEFINICJI W InvoiceAdmin.get_urls()")
    print("=" * 80)
    
    invoice_patterns = [
        'admin:ksiegowosc_invoice_payments_report',
        'admin:ksiegowosc_invoice_overdue_report',
        'admin:ksiegowosc_invoice_pdf',
        'admin:ksiegowosc_invoice_import_jpk',
        'admin:ksiegowosc_invoice_export_jpk',
        'admin:ksiegowosc_invoice_send_ksef',
    ]
    
    print("\nPowinny być zdefiniowane w get_urls():")
    for pattern in invoice_patterns:
        if pattern in admin_urls:
            print(f"   ✓ {pattern}")
        else:
            print(f"   ? {pattern} (nie znaleziono w szablonie)")
    
    # Sprawdzenie URL-i Payment
    print("\n" + "=" * 80)
    print("URL-E WYMAGAJĄCE DEFINICJI W PaymentAdmin.get_urls()")
    print("=" * 80)
    
    payment_urls = [u for u in admin_urls if 'payment' in u.lower()]
    if payment_urls:
        for url in sorted(set(payment_urls)):
            print(f"   - {url}")
    else:
        print("   Brak specjalnych URL-i dla Payment")
    
    # Sprawdzenie URL-i PurchaseInvoice
    print("\n" + "=" * 80)
    print("URL-E WYMAGAJĄCE DEFINICJI W PurchaseInvoiceAdmin.get_urls()")
    print("=" * 80)
    
    purchase_urls = [u for u in admin_urls if 'purchase' in u.lower()]
    if purchase_urls:
        for url in sorted(set(purchase_urls)):
            print(f"   - {url}")
    else:
        print("   Brak specjalnych URL-i dla PurchaseInvoice")

if __name__ == "__main__":
    main()
