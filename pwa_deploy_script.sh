#!/bin/sh

# Prosty instalator PWA dla Fakturownia
# Kompatybilny z podstawowym sh

echo "🚀 Prosty instalator PWA dla Fakturownia"
echo "========================================"

# Sprawdź podstawy
echo "📋 Sprawdzanie podstawowych wymagań..."

if [ ! -f "manage.py" ]; then
    echo "❌ Nie znaleziono manage.py - uruchom w katalogu projektu Django"
    exit 1
fi
echo "✅ Projekt Django wykryty"

if [ ! -d "ksiegowosc" ]; then
    echo "❌ Nie znaleziono aplikacji ksiegowosc"
    exit 1
fi
echo "✅ Aplikacja ksiegowosc znaleziona"

# Sprawdź Python
if ! which python3 > /dev/null 2>&1; then
    echo "❌ Python3 nie jest zainstalowany"
    exit 1
fi
echo "✅ Python3 dostępny"

# Utwórz strukturę katalogów
echo "📁 Tworzenie struktury katalogów..."
mkdir -p static/pwa/icons
mkdir -p static/pwa/splash  
mkdir -p templates/pwa
echo "✅ Katalogi utworzone"

# Utwórz browserconfig.xml
echo "📄 Tworzenie browserconfig.xml..."
cat > static/browserconfig.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
    <msapplication>
        <tile>
            <square70x70logo src="/static/pwa/icons/mstile-70x70.png"/>
            <square150x150logo src="/static/pwa/icons/mstile-150x150.png"/>
            <square310x310logo src="/static/pwa/icons/mstile-310x310.png"/>
            <wide310x150logo src="/static/pwa/icons/mstile-310x150.png"/>
            <TileColor>#007bff</TileColor>
        </tile>
    </msapplication>
</browserconfig>
EOF
echo "✅ browserconfig.xml utworzony"

# Sprawdź czy są ustawienia PWA
echo "⚙️  Sprawdzanie ustawień..."
if grep -q "PWA_VERSION" settings.py 2>/dev/null; then
    echo "✅ Ustawienia PWA znalezione w settings.py"
else
    echo "⚠️  Brak ustawień PWA w settings.py - dodaj je ręcznie"
fi

if grep -q "pwa_manifest" urls.py 2>/dev/null; then
    echo "✅ URLe PWA znalezione w urls.py"
else
    echo "⚠️  Brak URLi PWA w urls.py - dodaj je ręcznie"
fi

# Sprawdź ikony
echo "🎨 Sprawdzanie ikon..."
icon_count=0
for icon in icon-72x72.png icon-96x96.png icon-128x128.png icon-144x144.png icon-152x152.png icon-192x192.png icon-384x384.png icon-512x512.png favicon-32x32.png favicon-16x16.png apple-touch-icon.png; do
    if [ -f "static/pwa/icons/$icon" ]; then
        icon_count=$((icon_count + 1))
    fi
done

if [ $icon_count -eq 11 ]; then
    echo "✅ Wszystkie ikony PWA są dostępne ($icon_count/11)"
else
    echo "⚠️  Brakuje ikon PWA ($icon_count/11) - użyj generatora ikon"
fi

# Test Django
echo "🧪 Testowanie Django..."
if python manage.py check > /dev/null 2>&1; then
    echo "✅ Django check przeszedł pomyślnie"
else
    echo "⚠️  Django check zgłosił problemy - sprawdź konfigurację"
fi

if python manage.py collectstatic --dry-run --noinput > /dev/null 2>&1; then
    echo "✅ Collectstatic działa poprawnie"
else
    echo "⚠️  Problemy z collectstatic - sprawdź STATIC_URL"
fi

# Podsumowanie
echo ""
echo "🎉 Podstawowa instalacja PWA zakończona!"
echo ""
echo "📋 Co zostało utworzone:"
echo "- static/pwa/icons/ (katalog na ikony)"
echo "- static/pwa/splash/ (katalog na splash screens)"
echo "- templates/pwa/ (katalog na szablony PWA)"
echo "- static/browserconfig.xml (konfiguracja Windows)"
echo ""
echo "📝 Następne kroki:"
echo "1. Wygeneruj ikony PWA używając generatora"
echo "2. Dodaj ustawienia PWA do settings.py (jeśli nie ma)"
echo "3. Dodaj URLe PWA do urls.py (jeśli nie ma)"
echo "4. Skopiuj pliki Service Worker i manifest"
echo "5. Przetestuj: python manage.py runserver"
echo ""
echo "🔗 Sprawdź w przeglądarce:"
echo "- Developer Tools → Application → Manifest" 
echo "- Developer Tools → Application → Service Workers"
echo ""

# Opcjonalnie uruchom serwer
printf "Czy chcesz uruchomić serwer deweloperski? (y/N): "
read answer
case "$answer" in
    [Yy]*)
        echo "🚀 Uruchamianie serwera..."
        echo "➡️  Otwórz http://localhost:8000"
        echo "⏹️  Naciśnij Ctrl+C aby zatrzymać"
        python manage.py runserver
        ;;
    *)
        echo "👍 Możesz uruchomić serwer później: python manage.py runserver"
        ;;
esac

echo "✨ Gotowe!"