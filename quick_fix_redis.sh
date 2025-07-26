# =============================================================================
# SZYBKA POPRAWKA PROBLEMU Z REDIS
# =============================================================================

# KROK 1: Sprawdź swój plik .env
cat .env | grep REDIS

# KROK 2: Usuń lub skomentuj linię REDIS_URL w .env
# Otwórz plik .env i usuń/skomentuj tę linię:
# REDIS_URL=

# Lub wykonaj automatycznie:
sed -i 's/^REDIS_URL=.*$/# REDIS_URL=/' .env

# KROK 3: Dodaj pustą wartość dla REDIS_URL (opcjonalne)
echo "REDIS_URL=" >> .env

# KROK 4: Zrestartuj serwer Django
python manage.py runserver

# =============================================================================
# ALTERNATYWNE ROZWIĄZANIE - WYŁĄCZENIE REDIS CAŁKOWICIE
# =============================================================================

# Jeśli nadal masz problemy, możesz tymczasowo wyłączyć Redis
# dodając do .env:
echo "REDIS_URL=" > temp_env_addition.txt
echo "# Redis wyłączony dla development" >> temp_env_addition.txt
cat temp_env_addition.txt >> .env

# =============================================================================
# SPRAWDZENIE KONFIGURACJI CACHE
# =============================================================================

# Sprawdź jaką konfigurację cache używa Django:
python manage.py shell -c "
from django.conf import settings
import pprint
print('Cache configuration:')
pprint.pprint(settings.CACHES)
"

# =============================================================================
# INSTALACJA I URUCHOMIENIE REDIS (jeśli chcesz go używać)
# =============================================================================

# Ubuntu/Debian:
# sudo apt-get install redis-server
# sudo systemctl start redis-server

# macOS:
# brew install redis
# brew services start redis

# Sprawdź czy Redis działa:
# redis-cli ping

# Jeśli Redis działa, ustaw w .env:
# REDIS_URL=redis://localhost:6379/1