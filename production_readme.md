# 🚀 Wdrożenie Produkcyjne - Aplikacja Fakturownia

## 📋 Spis treści
- [Wymagania](#wymagania)
- [Szybkie wdrożenie](#szybkie-wdrożenie)
- [Konfiguracja](#konfiguracja)
- [Bezpieczeństwo](#bezpieczeństwo)
- [Monitoring](#monitoring)
- [Backup](#backup)
- [Troubleshooting](#troubleshooting)

## 🔧 Wymagania

### Minimalne wymagania sprzętowe:
- **CPU:** 2 rdzenie
- **RAM:** 4 GB
- **Dysk:** 20 GB wolnego miejsca
- **OS:** Ubuntu 20.04+ / CentOS 8+ / Debian 11+

### Oprogramowanie:
- Docker 20.10+
- Docker Compose 2.0+
- Git
- Curl (do testów)

### Opcjonalne:
- Nginx (jako load balancer)
- Let's Encrypt (certyfikaty SSL)
- PostgreSQL (zewnętrzna baza)
- Redis (zewnętrzny cache)

## ⚡ Szybkie wdrożenie

### 1. Pobierz kod aplikacji
```bash
git clone https://github.com/your-username/moja-fakturownia.git
cd moja-fakturownia
```

### 2. Uruchom skrypt automatycznego wdrożenia
```bash
chmod +x deploy.sh
./deploy.sh
```

Skrypt automatycznie:
- ✅ Sprawdzi wymagania systemowe
- ✅ Utworzy plik .env z przykładowej konfiguracji
- ✅ Zbuduje i uruchomi kontenery Docker
- ✅ Wykona migracje bazy danych
- ✅ Utworzy superużytkownika
- ✅ Skonfiguruje automatyczne backupy

### 3. Dostęp do aplikacji
Po zakończeniu wdrożenia:
- **HTTP:** http://localhost
- **HTTPS:** https://localhost (self-signed)
- **Admin:** https://localhost/admin/

## ⚙️ Konfiguracja

### Plik .env - Kluczowe ustawienia

```bash
# PODSTAWOWE
DEBUG=False
SECRET_KEY=your-unique-secret-key-here
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# BAZA DANYCH
DATABASE_URL=postgresql://user:password@localhost:5432/fakturownia_db

# SECURITY
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# EMAIL
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### ⚠️ WAŻNE: Zmień przed produkcją!

1. **SECRET_KEY** - wygeneruj nowy:
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

2. **ALLOWED_HOSTS** - ustaw rzeczywistą domenę:
```bash
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

3. **Hasła bazy danych** - zmień domyślne hasła w docker-compose.yml

## 🔒 Bezpieczeństwo

### 1. SSL/TLS
Wdrożenie generuje self-signed certyfikat. W produkcji użyj Let's Encrypt:

```bash
# Zainstaluj certbot
sudo apt install certbot python3-certbot-nginx

# Wygeneruj certyfikat
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Automatyczne odnawianie
sudo crontab -e
# Dodaj: 0 12 * * * /usr/bin/certbot renew --quiet
```

### 2. Firewall
```bash
# Tylko potrzebne porty
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### 3. Aktualizacje
```bash
# Regularne aktualizacje systemu
sudo apt update && sudo apt upgrade

# Aktualizacja aplikacji
git pull origin main
docker-compose build --no-cache
docker-compose up -d
```

### 4. Monitoring logów
```bash
# Sprawdź logi aplikacji
./show_logs.sh

# Logi bezpieczeństwa
sudo tail -f /var/log/auth.log
```

## 📊 Monitoring

### Health Checks
```bash
# Sprawdzenie statusu aplikacji
curl http://localhost/health/

# Status kontenerów
docker-compose ps

# Wykorzystanie zasobów
docker stats
```

### Logi
```bash
# Wszystkie logi
./show_logs.sh

# Tylko błędy
docker-compose logs web | grep ERROR

# Logi w czasie rzeczywistym
docker-compose logs -f web
```

### Metryki
Aplikacja udostępnia endpoint `/health/` z informacjami o:
- Status bazy danych
- Status cache
- Ogólny stan aplikacji

## 💾 Backup

### Automatyczny backup (skonfigurowany przez deploy.sh)
- **Częstotliwość:** Codziennie o 2:00
- **Lokalizacja:** `./backups/`
- **Retencja:** 30 dni

### Ręczny backup
```bash
# Backup bazy danych
./backup_database.sh

# Backup plików media
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/

# Backup całej aplikacji
tar -czf app_backup_$(date +%Y%m%d).tar.gz . --exclude=./backups
```

### Przywracanie z backupu
```bash
# Przywróć bazę danych
docker-compose exec db psql -U fakturownia_user -d fakturownia_db < backup_file.sql

# Zrestartuj aplikację
docker-compose restart web
```

## 🔧 Zarządzanie

### Podstawowe komendy
```bash
# Zatrzymaj aplikację
docker-compose down

# Uruchom aplikację
docker-compose up -d

# Zrestartuj aplikację
docker-compose restart

# Rebuilding (po zmianach w kodzie)
docker-compose build --no-cache
docker-compose up -d
```

### Zarządzanie bazą danych
```bash
# Migracje
docker-compose exec web python manage.py migrate

# Shell Django
docker-compose exec web python manage.py shell

# Dostęp do bazy PostgreSQL
docker-compose exec db psql -U fakturownia_user fakturownia_db
```

### Aktualizacja stawek ZUS
```bash
docker-compose exec web python manage.py update_zus_rates
```

## 🚨 Troubleshooting

### Aplikacja nie uruchamia się

1. **Sprawdź logi:**
```bash
docker-compose logs web
```

2. **Sprawdź konfigurację:**
```bash
docker-compose exec web python manage.py check --deploy
```

3. **Sprawdź porty:**
```bash
netstat -tulpn | grep -E ":(80|443)"
```

### Problemy z bazą danych

1. **Reset bazy danych:**
```bash
docker-compose down
docker volume rm $(docker volume ls -q | grep postgres)
docker-compose up -d
```

2. **Sprawdź połączenie:**
```bash
docker-compose exec web python manage.py dbshell
```

### Problemy z SSL

1. **Sprawdź certyfikaty:**
```bash
openssl x509 -in ssl/cert.pem -text -noout
```

2. **Regeneruj self-signed:**
```bash
rm ssl/cert.pem ssl/key.pem
./deploy.sh  # Wygeneruje nowe
```

### Wysoka pamięć/CPU

1. **Sprawdź użycie zasobów:**
```bash
docker stats --no-stream
```

2. **Zwiększ limity w docker-compose.yml:**
```yaml
services:
  web:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

### Logi błędów

1. **Błędy 500:**
```bash
docker-compose logs web | grep "500"
```

2. **Błędy bazy danych:**
```bash
docker-compose logs db
```

3. **Błędy Nginx:**
```bash
docker-compose logs nginx
```

## 🔄 Aktualizacje

### Aktualizacja aplikacji
```bash
# 1. Backup przed aktualizacją
./backup_database.sh

# 2. Pobierz najnowszą wersję
git pull origin main

# 3. Przebuduj kontenery
docker-compose build --no-cache

# 4. Migracje (jeśli potrzebne)
docker-compose exec web python manage.py migrate

# 5. Zbierz pliki statyczne
docker-compose exec web python manage.py collectstatic --noinput

# 6. Zrestartuj
docker-compose up -d
```

### Rollback
```bash
# Cofnij do poprzedniej wersji
git checkout HEAD~1

# Przebuduj
docker-compose build --no-cache
docker-compose up -d

# Przywróć backup bazy (jeśli potrzebne)
docker-compose exec db psql -U fakturownia_user -d fakturownia_db < backups/latest_backup.sql
```

## 📞 Wsparcie

### Logi do debugging
Zawsze dołącz logi przy zgłaszaniu problemów:

```bash
# Stwórz pakiet z logami
tar -czf debug_logs_$(date +%Y%m%d).tar.gz \
    --exclude=*.pyc \
    --exclude=media/* \
    logs/ \
    docker-compose.yml \
    .env.example

# Wyślij na email support
```

### Przydatne linki
- [Dokumentacja Django](https://docs.djangoproject.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [PostgreSQL](https://www.postgresql.org/docs/)
- [Nginx](https://nginx.org/en/docs/)

---

## ✅ Checklist wdrożenia produkcyjnego

- [ ] **Bezpieczeństwo**
  - [ ] Zmieniono SECRET_KEY
  - [ ] Ustawiono DEBUG=False
  - [ ] Skonfigurowano ALLOWED_HOSTS
  - [ ] Zainstalowano prawdziwy certyfikat SSL
  - [ ] Zmieniono domyślne hasła bazy danych
  - [ ] Skonfigurowano firewall

- [ ] **Konfiguracja**
  - [ ] Wypełniono plik .env
  - [ ] Skonfigurowano email (SMTP)
  - [ ] Ustawiono domenę
  - [ ] Skonfigurowano monitoring

- [ ] **Backup**
  - [ ] Testowano backup i restore
  - [ ] Skonfigurowano automatyczne backupy
  - [ ] Dokumentowano procedury recovery

- [ ] **Monitoring**
  - [ ] Skonfigurowano logi
  - [ ] Sprawdzono health checks
  - [ ] Ustawiono alerty

- [ ] **Testy**
  - [ ] Przetestowano wszystkie funkcje
  - [ ] Sprawdzono wydajność
  - [ ] Przetestowano w przeglądarce

---

**🎉 Gratulacje! Aplikacja Fakturownia jest gotowa do użycia w środowisku produkcyjnym.**