#!/bin/bash

# ==============================================================================
# SKRYPT WDROŻENIA APLIKACJI FAKTUROWNIA - WERSJA PRODUKCYJNA
# ==============================================================================

set -e  # Zatrzymaj przy błędzie

# Kolory dla output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funkcje pomocnicze
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Sprawdź czy jesteśmy w katalogu projektu
if [ ! -f "manage.py" ]; then
    log_error "Nie znaleziono pliku manage.py. Upewnij się, że jesteś w katalogu projektu."
    exit 1
fi

log_info "🚀 Rozpoczynam wdrożenie aplikacji Fakturownia..."

# ==============================================================================
# 1. SPRAWDZENIE WYMAGAŃ
# ==============================================================================

log_info "Sprawdzanie wymagań systemowych..."

# Sprawdź czy Docker jest zainstalowany
if ! command -v docker &> /dev/null; then
    log_error "Docker nie jest zainstalowany. Zainstaluj Docker i spróbuj ponownie."
    exit 1
fi

# Sprawdź czy Docker Compose jest zainstalowany
if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose nie jest zainstalowany. Zainstaluj Docker Compose i spróbuj ponownie."
    exit 1
fi

log_success "Docker i Docker Compose są dostępne"

# ==============================================================================
# 2. SPRAWDZENIE KONFIGURACJI
# ==============================================================================

log_info "Sprawdzanie konfiguracji..."

# Sprawdź czy plik .env istnieje
if [ ! -f ".env" ]; then
    log_warning "Plik .env nie istnieje. Kopiuję przykładowy plik..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_warning "Skopiowano .env.example do .env. WAŻNE: Uzupełnij rzeczywiste wartości przed uruchomieniem!"
    else
        log_error "Nie znaleziono pliku .env.example. Utwórz plik .env z konfiguracją."
        exit 1
    fi
fi

# Sprawdź kluczowe zmienne w .env
if ! grep -q "SECRET_KEY=" .env || grep -q "your-super-secret-key-here" .env; then
    log_error "SECRET_KEY nie jest ustawiony lub używa domyślnej wartości. Wygeneruj nowy klucz!"
    log_info "Możesz wygenerować nowy klucz używając: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    exit 1
fi

if ! grep -q "ALLOWED_HOSTS=" .env || grep -q "your-domain.com" .env; then
    log_warning "ALLOWED_HOSTS może wymagać aktualizacji z Twoją domeną"
fi

log_success "Konfiguracja podstawowa wygląda poprawnie"

# ==============================================================================
# 3. UTWORZENIE KATALOGÓW
# ==============================================================================

log_info "Tworzenie wymaganych katalogów..."

mkdir -p logs backups ssl staticfiles media

log_success "Katalogi utworzone"

# ==============================================================================
# 4. GENEROWANIE CERTYFIKATU SSL (SELF-SIGNED)
# ==============================================================================

if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
    log_info "Generowanie self-signed certyfikatu SSL..."
    
    openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem \
        -days 365 -nodes -subj "/C=PL/ST=Poland/L=Warsaw/O=Fakturownia/CN=localhost"
    
    log_warning "Wygenerowano self-signed certyfikat. W produkcji użyj prawdziwego certyfikatu (Let's Encrypt)!"
fi

# ==============================================================================
# 5. SPRAWDZENIE DJANGO
# ==============================================================================

log_info "Sprawdzanie konfiguracji Django..."

# Sprawdź składnię Python
python -m py_compile manage.py fakturownia/settings.py

# Sprawdź konfigurację Django (w trybie development)
python manage.py check --settings=fakturownia.settings

log_success "Django skonfigurowane poprawnie"

# ==============================================================================
# 6. BUDOWANIE I URUCHAMIANIE KONTENERÓW
# ==============================================================================

log_info "Budowanie kontenerów Docker..."

# Zatrzymaj istniejące kontenery
docker-compose down

# Zbuduj obrazy
docker-compose build --no-cache

log_success "Kontenery zbudowane"

log_info "Uruchamianie aplikacji..."

# Uruchom kontenery
docker-compose up -d

# Sprawdź status
sleep 10
if docker-compose ps | grep -q "Up"; then
    log_success "Kontenery uruchomione pomyślnie"
else
    log_error "Problemy z uruchomieniem kontenerów"
    docker-compose logs
    exit 1
fi

# ==============================================================================
# 7. INICJALIZACJA BAZY DANYCH
# ==============================================================================

log_info "Inicjalizacja bazy danych..."

# Migracje
docker-compose exec web python manage.py migrate --noinput

# Kolekcja plików statycznych
docker-compose exec web python manage.py collectstatic --noinput

log_success "Baza danych zainicjalizowana"

# ==============================================================================
# 8. TWORZENIE SUPERUŻYTKOWNIKA
# ==============================================================================

log_info "Sprawdzanie superużytkownika..."

# Sprawdź czy superużytkownik istnieje
if docker-compose exec web python manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.filter(is_superuser=True).exists())" | grep -q "True"; then
    log_info "Superużytkownik już istnieje"
else
    log_warning "Brak superużytkownika. Zostaniesz poproszony o utworzenie konta administratora..."
    docker-compose exec web python manage.py createsuperuser
fi

# ==============================================================================
# 9. INICJALIZACJA DANYCH
# ==============================================================================

log_info "Inicjalizacja stawek ZUS..."

# Aktualizuj stawki ZUS
docker-compose exec web python manage.py update_zus_rates || log_warning "Nie udało się pobrać stawek ZUS"

# ==============================================================================
# 10. TESTY PODSTAWOWE
# ==============================================================================

log_info "Wykonywanie testów podstawowych..."

# Test health check
if curl -f http://localhost/health/ > /dev/null 2>&1; then
    log_success "Health check - OK"
else
    log_warning "Health check nie odpowiada. Sprawdź logi: docker-compose logs nginx"
fi

# Test dostępu do aplikacji
if curl -f http://localhost > /dev/null 2>&1; then
    log_success "Aplikacja odpowiada na HTTP"
else
    log_warning "Aplikacja nie odpowiada na HTTP"
fi

# Test HTTPS (jeśli mamy certyfikat)
if curl -k -f https://localhost > /dev/null 2>&1; then
    log_success "Aplikacja odpowiada na HTTPS"
else
    log_warning "Aplikacja nie odpowiada na HTTPS"
fi

# ==============================================================================
# 11. KONFIGURACJA BACKUPU
# ==============================================================================

log_info "Konfiguracja systemu backupu..."

# Utwórz skrypt backupu
cat > backup_database.sh << 'EOF'
#!/bin/bash
# Backup bazy danych Fakturownia
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/app/backups"
BACKUP_FILE="$BACKUP_DIR/fakturownia_backup_$DATE.sql"

docker-compose exec db pg_dump -U fakturownia_user fakturownia_db > $BACKUP_FILE
gzip $BACKUP_FILE

echo "Backup utworzony: ${BACKUP_FILE}.gz"

# Usuń backupy starsze niż 30 dni
find $BACKUP_DIR -name "fakturownia_backup_*.sql.gz" -mtime +30 -delete
EOF

chmod +x backup_database.sh

log_success "Skrypt backupu utworzony: ./backup_database.sh"

# ==============================================================================
# 12. MONITORING I LOGI
# ==============================================================================

log_info "Konfiguracja monitoringu..."

# Utwórz skrypt do sprawdzania logów
cat > show_logs.sh << 'EOF'
#!/bin/bash
# Pokazuj logi aplikacji Fakturownia

echo "=== LOGI APLIKACJI DJANGO ==="
docker-compose logs --tail=50 web

echo "=== LOGI NGINX ==="
docker-compose logs --tail=20 nginx

echo "=== LOGI BAZY DANYCH ==="
docker-compose logs --tail=20 db

echo "=== STATUS KONTENERÓW ==="
docker-compose ps
EOF

chmod +x show_logs.sh

log_success "Skrypt logów utworzony: ./show_logs.sh"

# ==============================================================================
# 13. USTAWIENIE CRON (BACKUP)
# ==============================================================================

log_info "Konfiguracja automatycznego backupu..."

# Dodaj wpis do crontab (backup codziennie o 2:00)
CRON_ENTRY="0 2 * * * /$(pwd)/backup_database.sh >> /var/log/fakturownia_backup.log 2>&1"

# Sprawdź czy wpis już istnieje
if ! crontab -l 2>/dev/null | grep -q "backup_database.sh"; then
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    log_success "Automatyczny backup skonfigurowany (codziennie o 2:00)"
else
    log_info "Automatyczny backup już skonfigurowany"
fi

# ==============================================================================
# 14. PODSUMOWANIE
# ==============================================================================

echo
echo "=============================================================================="
echo -e "${GREEN}✅ WDROŻENIE ZAKOŃCZONE POMYŚLNIE!${NC}"
echo "=============================================================================="
echo
echo -e "${BLUE}📍 URL aplikacji:${NC}"
echo "   HTTP:  http://localhost"
echo "   HTTPS: https://localhost (self-signed cert)"
echo "   Admin: https://localhost/admin/"
echo
echo -e "${BLUE}📊 Monitoring:${NC}"
echo "   Status kontenerów: docker-compose ps"
echo "   Logi aplikacji:    ./show_logs.sh"
echo "   Health check:      curl http://localhost/health/"
echo
echo -e "${BLUE}🔧 Zarządzanie:${NC}"
echo "   Zatrzymaj:         docker-compose down"
echo "   Uruchom ponownie:  docker-compose up -d"
echo "   Backup bazy:       ./backup_database.sh"
echo "   Logi:              ./show_logs.sh"
echo
echo -e "${BLUE}📚 Następne kroki:${NC}"
echo "   1. Zaloguj się do panelu admin i uzupełnij dane firmy"
echo "   2. Skonfiguruj prawdziwy certyfikat SSL (Let's Encrypt)"
echo "   3. Ustaw rzeczywistą domenę w ALLOWED_HOSTS (.env)"
echo "   4. Skonfiguruj email (SMTP) dla powiadomień"
echo "   5. Sprawdź logi: ./show_logs.sh"
echo
echo -e "${YELLOW}⚠️  WAŻNE PRZYPOMNIENIA:${NC}"
echo "   - Zmień domyślne hasła bazy danych w .env"
echo "   - Skonfiguruj SSL certyfikat dla produkcji"
echo "   - Regularnie wykonuj backupy: ./backup_database.sh"
echo "   - Monitoruj logi aplikacji"
echo
log_success "Aplikacja Fakturownia jest gotowa do użycia!"

# ==============================================================================
# 15. SPRAWDZENIE KOŃCOWE
# ==============================================================================

echo
log_info "Sprawdzenie końcowe - podsumowanie statusu:"

# Status kontenerów
echo "Status kontenerów:"
docker-compose ps

# Wykorzystanie zasobów
echo
echo "Wykorzystanie zasobów:"
docker stats --no-stream

# Porty
echo
echo "Otwarte porty:"
netstat -tulpn | grep -E ":(80|443|5432|6379) " || echo "Brak informacji o portach"

log_success "Wdrożenie zakończone! 🎉"