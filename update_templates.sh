#!/bin/bash

# --- Konfiguracja ---
# Scieżka do katalogu z szablonami głównej aplikacji, które mają stać się częścią PWA.
TARGET_DIR="ksiegowosc/templates/ksiegowosc"
# Nowy szablon bazowy PWA.
NEW_BASE_TEMPLATE="pwa/base_pwa.html"

# --- Logika skryptu ---

# Sprawdzenie, czy katalog docelowy istnieje
if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Błąd: Katalog docelowy '$TARGET_DIR' nie został znaleziony."
    echo "Upewnij się, że uruchamiasz skrypt z głównego katalogu projektu Django."
    exit 1
fi

echo "🔍 Przeszukuję pliki w katalogu: $TARGET_DIR"
echo "🎯 Zamieniam dziedziczenie na: {% extends \"$NEW_BASE_TEMPLATE\" %}"
echo "---"

# Użyj `find` do znalezienia wszystkich plików .html w katalogu docelowym
# i wykonaj na nich zamianę za pomocą `sed`.
find "$TARGET_DIR" -type f -name "*.html" -print0 | while IFS= read -r -d $'\0' file; do
    # Użyj `grep -q` aby sprawdzić, czy plik zawiera tag `extends`
    if grep -q '{% extends .* %}' "$file"; then
        # `sed -i` modyfikuje plik w miejscu.
        # Wyrażenie regularne `s|...|...|` zamienia całą linię z `extends` na nową.
        sed -i "s|{% extends .* %}|{% extends \"$NEW_BASE_TEMPLATE\" %}|" "$file"
        echo "✅ Zaktualizowano plik: $file"
    else
        echo "⚪️ Pominięto plik (brak tagu 'extends'): $file"
    fi
done

echo "---"
echo "🎉 Gotowe! Wszystkie odpowiednie szablony dziedziczą teraz po '$NEW_BASE_TEMPLATE'."
