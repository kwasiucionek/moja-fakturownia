#!/usr/bin/env python
"""
Skrypt walidacji bezpieczeństwa dla aplikacji Fakturownia
Uruchom przed wdrożeniem w produkcji: python security_check.py
"""

import os
import sys
import subprocess
import re
from pathlib import Path
from decouple import config, UndefinedValueError
import secrets
import string

# Kolory dla terminala
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.CYAN}ℹ {text}{Colors.END}")

class SecurityValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []
        
    def check_environment_variables(self):
        """Sprawdzenie kluczowych zmiennych środowiskowych"""
        print_header("SPRAWDZANIE ZMIENNYCH ŚRODOWISKOWYCH")
        
        required_vars = [
            'SECRET_KEY',
            'DATABASE_URL',
            'ALLOWED_HOSTS'
        ]
        
        critical_vars = {
            'DEBUG': 'False',
            'SECURE_SSL_REDIRECT': 'True',
            'SESSION_COOKIE_SECURE': 'True',
            'CSRF_COOKIE_SECURE': 'True'
        }
        
        # Sprawdź wymagane zmienne
        for var in required_vars:
            try:
                value = config(var)
                if value:
                    print_success(f"{var} jest ustawiony")
                    self.passed.append(f"{var} configured")
                else:
                    print_error(f"{var} jest pusty!")
                    self.errors.append(f"{var} is empty")
            except UndefinedValueError:
                print_error(f"{var} nie jest ustawiony!")
                self.errors.append(f"{var} is not set")
        
        # Sprawdź krytyczne ustawienia bezpieczeństwa
        for var, expected in critical_vars.items():
            try:
                value = config(var, default=None)
                if value == expected:
                    print_success(f"{var} = {expected}")
                    self.passed.append(f"{var} correctly set")
                else:
                    print_warning(f"{var} = {value} (zalecane: {expected})")
                    self.warnings.append(f"{var} should be {expected}")
            except UndefinedValueError:
                print_warning(f"{var} nie jest ustawiony (zalecane: {expected})")
                self.warnings.append(f"{var} should be set to {expected}")
    
    def check_secret_key(self):
        """Sprawdzenie jakości SECRET_KEY"""
        print_header("SPRAWDZANIE SECRET_KEY")
        
        try:
            secret_key = config('SECRET_KEY')
            
            # Sprawdź długość
            if len(secret_key) < 50:
                print_error("SECRET_KEY jest za krótki (minimum 50 znaków)")
                self.errors.append("SECRET_KEY too short")
            else:
                print_success(f"SECRET_KEY ma odpowiednią długość ({len(secret_key)} znaków)")
                self.passed.append("SECRET_KEY length OK")
            
            # Sprawdź czy nie jest domyślny
            if 'django-insecure' in secret_key:
                print_error("Używasz domyślnego SECRET_KEY z Django!")
                self.errors.append("Using default Django SECRET_KEY")
            else:
                print_success("SECRET_KEY nie jest domyślny")
                self.passed.append("SECRET_KEY is custom")
            
            # Sprawdź złożoność
            has_upper = any(c.isupper() for c in secret_key)
            has_lower = any(c.islower() for c in secret_key)
            has_digit = any(c.isdigit() for c in secret_key)
            has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in secret_key)
            
            complexity_score = sum([has_upper, has_lower, has_digit, has_special])
            
            if complexity_score >= 3:
                print_success(f"SECRET_KEY ma dobrą złożoność (score: {complexity_score}/4)")
                self.passed.append("SECRET_KEY complexity good")
            else:
                print_warning(f"SECRET_KEY ma niską złożoność (score: {complexity_score}/4)")
                self.warnings.append("SECRET_KEY complexity low")
                
        except UndefinedValueError:
            print_error("SECRET_KEY nie jest ustawiony!")
            self.errors.append("SECRET_KEY not set")
    
    def check_database_config(self):
        """Sprawdzenie konfiguracji bazy danych"""
        print_header("SPRAWDZANIE KONFIGURACJI BAZY DANYCH")
        
        try:
            db_url = config('DATABASE_URL')
            
            if db_url.startswith('sqlite'):
                print_warning("Używasz SQLite - zalecane PostgreSQL w produkcji")
                self.warnings.append("Using SQLite instead of PostgreSQL")
            elif db_url.startswith('postgresql'):
                print_success("Używasz PostgreSQL")
                self.passed.append("Using PostgreSQL")
                
                # Sprawdź SSL
                if 'sslmode=require' in db_url or config('DB_SSLMODE', default='') == 'require':
                    print_success("SSL jest wymagane dla połączenia z bazą danych")
                    self.passed.append("Database SSL enabled")
                else:
                    print_warning("SSL nie jest wymagane dla bazy danych")
                    self.warnings.append("Database SSL not required")
            else:
                print_info(f"Nieznany typ bazy danych: {db_url.split(':')[0]}")
                
        except UndefinedValueError:
            print_error("DATABASE_URL nie jest ustawiony!")
            self.errors.append("DATABASE_URL not set")
    
    def check_admin_security(self):
        """Sprawdzenie bezpieczeństwa panelu admin"""
        print_header("SPRAWDZANIE BEZPIECZEŃSTWA ADMIN")
        
        try:
            admin_url = config('ADMIN_URL', default='admin/')
            
            if admin_url == 'admin/':
                print_error("Używasz domyślnego URL admin - zmień na coś losowego!")
                self.errors.append("Using default admin URL")
            else:
                print_success(f"Admin URL jest niestandardowy: {admin_url}")
                self.passed.append("Custom admin URL")
                
            # Sprawdź czy URL jest wystarczająco losowy
            if len(admin_url.replace('/', '')) < 20:
                print_warning("Admin URL może być za krótki")
                self.warnings.append("Admin URL might be too short")
            else:
                print_success("Admin URL ma odpowiednią długość")
                self.passed.append("Admin URL length OK")
                
        except UndefinedValueError:
            print_warning("ADMIN_URL nie jest ustawiony (użyje domyślnego 'admin/')")
            self.warnings.append("ADMIN_URL not customized")
    
    def check_file_permissions(self):
        """Sprawdzenie uprawnień plików"""
        print_header("SPRAWDZANIE UPRAWNIEŃ PLIKÓW")
        
        sensitive_files = ['.env', 'db.sqlite3', 'manage.py']
        
        for filename in sensitive_files:
            if os.path.exists(filename):
                stat = os.stat(filename)
                perms = oct(stat.st_mode)[-3:]
                
                if filename == '.env':
                    if perms in ['600', '640']:
                        print_success(f"{filename}: {perms} (bezpieczne)")
                        self.passed.append(f"{filename} permissions OK")
                    else:
                        print_warning(f"{filename}: {perms} (zalecane: 600 lub 640)")
                        self.warnings.append(f"{filename} permissions too open")
                else:
                    print_info(f"{filename}: {perms}")
    
    def check_dependencies(self):
        """Sprawdzenie bezpieczeństwa zależności"""
        print_header("SPRAWDZANIE BEZPIECZEŃSTWA ZALEŻNOŚCI")
        
        try:
            # Sprawdź czy safety jest zainstalowany
            result = subprocess.run(['safety', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print_success("Safety jest zainstalowany")
                
                # Uruchom safety check
                result = subprocess.run(['safety', 'check'], 
                                      capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    print_success("Brak znanych luk bezpieczeństwa w zależnościach")
                    self.passed.append("No known vulnerabilities")
                else:
                    print_error("Znaleziono luki bezpieczeństwa w zależnościach!")
                    print_error(result.stdout)
                    self.errors.append("Vulnerabilities found in dependencies")
            else:
                print_warning("Safety nie jest zainstalowany - uruchom: pip install safety")
                self.warnings.append("Safety not installed")
                
        except FileNotFoundError:
            print_warning("Safety nie jest zainstalowany")
            self.warnings.append("Safety not installed")
        except subprocess.TimeoutExpired:
            print_warning("Safety check przekroczył limit czasu")
            self.warnings.append("Safety check timeout")
    
    def check_debug_mode(self):
        """Sprawdzenie czy debug jest wyłączony"""
        print_header("SPRAWDZANIE TRYBU DEBUG")
        
        debug = config('DEBUG', default=True, cast=bool)
        
        if debug:
            print_error("DEBUG=True - WYŁĄCZ w produkcji!")
            self.errors.append("DEBUG mode enabled")
        else:
            print_success("DEBUG=False")
            self.passed.append("DEBUG mode disabled")
    
    def generate_recommendations(self):
        """Generuj rekomendacje bezpieczeństwa"""
        print_header("REKOMENDACJE BEZPIECZEŃSTWA")
        
        recommendations = [
            "Regularnie aktualizuj wszystkie zależności",
            "Używaj silnych haseł dla wszystkich kont",
            "Skonfiguruj automatyczne backupy",
            "Włącz monitoring i alerty",
            "Przeprowadzaj regularne testy penetracyjne",
            "Implementuj WAF (Web Application Firewall)",
            "Używaj fail2ban do blokowania ataków brute force",
            "Skonfiguruj HTTPS z certyfikatem SSL",
            "Włącz logowanie zdarzeń bezpieczeństwa",
            "Ograniczaj dostęp do serwera przez firewall"
        ]
        
        for i, rec in enumerate(recommendations, 1):
            print(f"{Colors.CYAN}{i:2d}.{Colors.END} {rec}")
    
    def generate_secure_secret_key(self):
        """Wygeneruj bezpieczny SECRET_KEY"""
        alphabet = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
        secret_key = ''.join(secrets.choice(alphabet) for _ in range(64))
        
        print_header("NOWY BEZPIECZNY SECRET_KEY")
        print(f"{Colors.GREEN}SECRET_KEY={secret_key}{Colors.END}")
        print(f"\n{Colors.YELLOW}Skopiuj powyższy klucz do pliku .env{Colors.END}")
    
    def run_all_checks(self):
        """Uruchom wszystkie sprawdzenia"""
        print(f"{Colors.BOLD}{Colors.PURPLE}")
        print("🔒 WALIDATOR BEZPIECZEŃSTWA FAKTUROWNI 🔒")
        print(f"{Colors.END}")
        
        self.check_environment_variables()
        self.check_secret_key()
        self.check_database_config()
        self.check_admin_security()
        self.check_file_permissions()
        self.check_dependencies()
        self.check_debug_mode()
        
        # Podsumowanie
        print_header("PODSUMOWANIE")
        
        print(f"{Colors.GREEN}✓ Testy zaliczone: {len(self.passed)}{Colors.END}")
        for test in self.passed:
            print(f"  • {test}")
        
        if self.warnings:
            print(f"\n{Colors.YELLOW}⚠ Ostrzeżenia: {len(self.warnings)}{Colors.END}")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        if self.errors:
            print(f"\n{Colors.RED}✗ Błędy: {len(self.errors)}{Colors.END}")
            for error in self.errors:
                print(f"  • {error}")
        
        # Ocena ogólna
        total_issues = len(self.errors) + len(self.warnings)
        
        if len(self.errors) == 0:
            if len(self.warnings) == 0:
                print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 DOSKONALE! Aplikacja jest gotowa do wdrożenia.{Colors.END}")
                exit_code = 0
            else:
                print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ UWAGA! Popraw ostrzeżenia przed wdrożeniem.{Colors.END}")
                exit_code = 1
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ KRYTYCZNE! Napraw błędy przed wdrożeniem!{Colors.END}")
            exit_code = 2
        
        self.generate_recommendations()
        
        # Zaproponuj nowy SECRET_KEY jeśli potrzebny
        if any('SECRET_KEY' in error for error in self.errors):
            self.generate_secure_secret_key()
        
        return exit_code

def main():
    validator = SecurityValidator()
    exit_code = validator.run_all_checks()
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
