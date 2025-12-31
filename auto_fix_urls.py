#!/usr/bin/env python3
"""
Automatyczna naprawa metod get_urls() w ksiegowosc/admin.py
Ten skrypt znajdzie i naprawi wszystkie błędne definicje get_urls()
"""

import re
import sys
from pathlib import Path

def fix_get_urls_method(content, class_name, model_name, urls_config):
    """
    Naprawia metodę get_urls() dla danej klasy Admin
    
    Args:
        content: Zawartość pliku admin.py
        class_name: Nazwa klasy Admin (np. 'InvoiceAdmin')
        model_name: Nazwa modelu (np. 'invoice')
        urls_config: Lista krotek (url_path, view_method, url_name_suffix)
    """
    
    # Wzorzec do znalezienia klasy
    class_pattern = rf'class {class_name}\([^)]+\):'
    class_match = re.search(class_pattern, content)
    
    if not class_match:
        print(f"⚠️  Nie znaleziono klasy {class_name}")
        return content
    
    # Generuj nową metodę get_urls()
    new_method = generate_get_urls_method(urls_config)
    
    # Wzorzec do znalezienia starej metody get_urls w tej klasie
    # Znajdujemy początek metody i wszystko aż do następnej metody na tym samym poziomie wcięcia
    method_pattern = rf'(class {class_name}\([^)]+\):.*?)(    def get_urls\(self\):.*?)(\n    def [^g]|\nclass )'
    
    # Najpierw sprawdź czy metoda istnieje
    if re.search(rf'class {class_name}\([^)]+\):.*?def get_urls\(self\):', content, re.DOTALL):
        # Zamień istniejącą metodę
        content = re.sub(
            method_pattern,
            rf'\1{new_method}\3',
            content,
            flags=re.DOTALL
        )
        print(f"✅ Naprawiono get_urls() w {class_name}")
    else:
        # Dodaj metodę na końcu klasy (przed następną klasą lub końcem pliku)
        insert_pattern = rf'(class {class_name}\([^)]+\):.*?)(\nclass |\Z)'
        content = re.sub(
            insert_pattern,
            rf'\1\n{new_method}\2',
            content,
            flags=re.DOTALL
        )
        print(f"✅ Dodano get_urls() do {class_name}")
    
    return content

def generate_get_urls_method(urls_config):
    """Generuje kod metody get_urls() na podstawie konfiguracji"""
    
    method_lines = [
        "    def get_urls(self):",
        "        \"\"\"Dodaje niestandardowe URL-e\"\"\"",
        "        from django.urls import path",
        "        urls = super().get_urls()",
        "        ",
        "        # Poprawna definicja info tuple",
        "        info = self.model._meta.app_label, self.model._meta.model_name",
        "",
        "        my_urls = ["
    ]
    
    for url_path, view_method, url_suffix in urls_config:
        method_lines.extend([
            f"            # {url_suffix.replace('_', ' ').title()}",
            "            path(",
            f"                \"{url_path}\",",
            f"                self.admin_site.admin_view(self.{view_method}),",
            f"                name=\"%s_%s_{url_suffix}\" % info,",
            "            ),",
        ])
    
    method_lines.extend([
        "        ]",
        "        return my_urls + urls",
        ""
    ])
    
    return "\n".join(method_lines)

def main():
    admin_file = Path("ksiegowosc/admin.py")
    
    if not admin_file.exists():
        print(f"❌ Nie znaleziono pliku: {admin_file}")
        print("   Uruchom skrypt z katalogu głównego projektu (tam gdzie manage.py)")
        sys.exit(1)
    
    print("=" * 80)
    print("AUTOMATYCZNA NAPRAWA get_urls() W admin.py")
    print("=" * 80)
    print()
    
    # Wczytaj zawartość
    content = admin_file.read_text(encoding='utf-8')
    backup_file = admin_file.with_suffix('.py.backup')
    
    # Utwórz backup
    backup_file.write_text(content, encoding='utf-8')
    print(f"📦 Utworzono backup: {backup_file}")
    print()
    
    # Konfiguracja URL-i dla każdej klasy Admin
    configs = {
        'InvoiceAdmin': [
            ("<int:object_id>/change/generate-pdf/", "generate_pdf_view", "pdf"),
            ("import-jpk/", "import_jpk_view", "import_jpk"),
            ("export-jpk/", "export_jpk_view", "export_jpk"),
            ("send-ksef/", "send_to_ksef_view", "send_ksef"),
            ("payments-report/", "payments_report_view", "payments_report"),
            ("overdue-report/", "overdue_report_view", "overdue_report"),
        ],
        'PurchaseInvoiceAdmin': [
            ("expenses-report/", "expenses_report_view", "expenses_report"),
            ("category-analysis/", "category_analysis_view", "category_analysis"),
            ("overdue-purchases/", "overdue_purchases_view", "overdue_purchases"),
        ],
        'MonthlySettlementAdmin': [
            ("dashboard/", "dashboard_view", "dashboard"),
            ("import-jpk-ewp/", "import_jpk_ewp_view", "import_jpk_ewp"),
        ],
        'YearlySettlementAdmin': [
            ("<int:object_id>/generate-pdf/", "generate_pdf_view", "generate_pdf"),
        ],
    }
    
    # Napraw każdą klasę
    for class_name, urls_config in configs.items():
        # Wyciągnij nazwę modelu z klasy (np. InvoiceAdmin -> invoice)
        model_name = class_name.replace('Admin', '').lower()
        content = fix_get_urls_method(content, class_name, model_name, urls_config)
    
    # Zapisz naprawiony plik
    admin_file.write_text(content, encoding='utf-8')
    
    print()
    print("=" * 80)
    print("✅ ZAKOŃCZONO NAPRAWĘ")
    print("=" * 80)
    print(f"✓ Plik admin.py został zaktualizowany")
    print(f"✓ Backup zapisany jako: {backup_file}")
    print()
    print("🔄 Następne kroki:")
    print("   1. python manage.py check")
    print("   2. python manage.py runserver")
    print()

if __name__ == "__main__":
    main()
