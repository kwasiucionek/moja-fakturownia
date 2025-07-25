#!/usr/bin/env python3
"""
Narzędzia bezpieczeństwa dla aplikacji Fakturownia
- Generowanie SECRET_KEY
- Sprawdzanie konfiguracji bezpieczeństwa
- Walidacja pliku .env
"""

import os
import re
import sys
import secrets
import string
from pathlib import Path

def generate_secret_key(length=50):
    """Generuje bezpieczny SECRET_KEY dla Django"""
    characters = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    return ''.join(secrets.choice(characters) for _ in range(length))

def check_env_file():
    """Sprawdza plik .env pod kątem bezpieczeństwa"""
    env_path = Path('.env')
    
    if not env_path.exists():
        print("❌ Plik .env nie istnieje!")
        return False
    
    print("🔍 Sprawdzanie pliku .env...")
    
    with open(env_path, 'r') as f:
        content = f.read()
    
    issues = []
    warnings = []
    
    # Sprawdź SECRET_KEY
    secret_pattern = r'SECRET_KEY\s*=\s*(.+)'
    secret_match = re.search(secret_pattern, content)
    
    if not secret_match:
        issues.append("SECRET_KEY nie jest ustawiony")
    else:
        secret_key = secret_match.group(1).strip('\'"')
        if 'django-insecure' in secret_key or 'your-super-secret-key' in secret_key:
            issues.append("SECRET_KEY używa domyślnej/przykładowej wartości")
        elif len(secret_key) < 40:
            warnings.append("SECRET_KEY może być za krótki (< 40 znaków)")
    
    # Sprawdź DEBUG
    debug_pattern = r'DEBUG\s*=\s*(.+)'
    debug_match = re.search(debug_pattern, content)
    
    if debug_match:
        debug_value = debug_match.group(1).strip().lower()
        if debug_value in ['true', '1', 'yes']:
            issues.append("DEBUG=True w produkcji jest niebezpieczne!")
    
    # Sprawdź ALLOWED_HOSTS
    hosts_pattern = r'ALLOWED_HOSTS\s*=\s*(.+)'
    hosts_match = re.search(hosts_pattern, content)
    
    if not hosts_match:
        issues.append("ALLOWED_HOSTS nie jest ustawiony")
    else:
        hosts_value = hosts_match.group(1).strip()
        if 'your-domain.com' in hosts_value:
            warnings.append("ALLOWED_HOSTS zawiera przykładową domenę")
    
    # Sprawdź hasła bazy danych
    if 'password@localhost' in content or 'fakturownia_password' in content:
        warnings.append("Używane są domyślne hasła bazy danych")
    
    # Sprawdź SSL
    ssl_redirect = re.search(r'SECURE_SSL_REDIRECT\s*=\s*(.+)', content)
    if ssl_redirect and ssl_redirect.group(1).strip().lower() in ['false', '0', 'no']:
        warnings.append("SECURE_SSL_REDIRECT=False może być niebezpieczne w produkcji")
    
    # Wyniki
    if issues:
        print("\n❌ Krytyczne problemy bezpieczeństwa:")
        for issue in issues:
            print(f"  - {issue}")
    
    if warnings:
        print("\n⚠️ Ostrzeżenia:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if not issues and not warnings:
        print("✅ Konfiguracja .env wygląda dobrze!")
        return True
    
    return len(issues) == 0

def check_file_permissions():
    """Sprawdza uprawnienia krytycznych plików"""
    print("\n🔒 Sprawdzanie uprawnień plików...")
    
    critical_files = ['.env', 'db.sqlite3', 'ssl/key.pem']
    
    for file_path in critical_files:
        if os.path.exists(file_path):
            stat = os.stat(file_path)
            perms = oct(stat.st_mode)[-3:]
            
            if file_path == '.env' and perms != '600':
                print(f"⚠️ {file_path}: uprawnienia {perms} (powinno być 600)")
            elif file_path.endswith('.pem') and perms not in ['600', '400']:
                print(f"⚠️ {file_path}: uprawnienia {perms} (powinno być 600 lub 400)")
            else:
                print(f"✅ {file_path}: uprawnienia {perms}")

def check_dependencies():
    """Sprawdza czy są zainstalowane najnowsze wersje bezpieczeństwa"""
    print("\n📦 Sprawdzanie zależności...")
    
    try:
        import subprocess
        result = subprocess.run(['pip', 'list', '--outdated'], 
                              capture_output=True, text=True)
        
        if result.stdout:
            outdated = result.stdout.split('\n')[2:]  # Pomijaj header
            security_packages = ['django', 'pillow', 'requests', 'cryptography']
            
            for line in outdated:
                if line:
                    package = line.split()[0].lower()
                    if package in security_packages:
                        print(f"⚠️ {package} ma dostępną aktualizację")
        else:
            print("✅ Wszystkie pakiety są aktualne")
            
    except Exception as e:
        print(f"❓ Nie można sprawdzić zależności: {e}")

def generate_env_template():
    """Generuje szablon .env z bezpiecznymi wartościami"""
    template = f"""# =============================================================================
# KONFIGURACJA APLIKACJI FAKTUROWNIA - WYGENEROWANO AUTOMATYCZNIE
# =============================================================================

# PODSTAWOWE USTAWIENIA
DEBUG=False
SECRET_KEY={generate_secret_key()}
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# BAZA DANYCH
DATABASE_URL=sqlite:///db.sqlite3

# SECURITY SETTINGS
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SECURE_CONTENT_TYPE_NOSNIFF=True
SECURE_BROWSER_XSS_FILTER=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# EMAIL SETTINGS
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Fakturownia <your-email@gmail.com>

# TIMEZONE & LANGUAGE
TIME_ZONE=Europe/Warsaw
LANGUAGE_CODE=pl

# LOGGING
LOG_LEVEL=INFO
"""
    
    return template

def main():
    """Główna funkcja programu"""
    print("🔐 Narzędzia bezpieczeństwa Fakturownia")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'generate-key':
            print("🔑 Nowy SECRET_KEY:")
            print(generate_secret_key())
            return
        
        elif command == 'generate-env':
            env_content = generate_env_template()
            
            if os.path.exists('.env'):
                backup_name = '.env.backup'
                os.rename('.env', backup_name)
                print(f"📁 Istniejący .env zapisany jako {backup_name}")
            
            with open('.env', 'w') as f:
                f.write(env_content)
            
            # Ustaw bezpieczne uprawnienia
            os.chmod('.env', 0o600)
            
            print("✅ Nowy plik .env został wygenerowany z bezpiecznymi ustawieniami")
            print("⚠️ WAŻNE: Uzupełnij rzeczywiste wartości przed uruchomieniem!")
            return
        
        elif command == 'check':
            pass  # Wykonaj pełne sprawdzenie
        
        else:
            print(f"❌ Nieznana komenda: {command}")
            print("Dostępne komendy: generate-key, generate-env, check")
            return
    
    # Pełne sprawdzenie bezpieczeństwa
    print("🔍 Przeprowadzam sprawdzenie bezpieczeństwa...\n")
    
    env_ok = check_env_file()
    check_file_permissions()
    check_dependencies()
    
    print("\n" + "=" * 50)
    
    if env_ok:
        print("✅ Sprawdzenie zakończone. Konfiguracja wygląda bezpiecznie!")
    else:
        print("❌ Znaleziono problemy bezpieczeństwa. Popraw je przed wdrożeniem!")
        sys.exit(1)
    
    print("\n💡 Dodatkowe zalecenia:")
    print("  - Regularnie aktualizuj zależności: pip install -r requirements.txt --upgrade")
    print("  - Użyj prawdziwego certyfikatu SSL w produkcji")
    print("  - Skonfiguruj firewall")
    print("  - Włącz automatyczne backupy")

if __name__ == '__main__':
    main()
