# ksiegowosc/utils.py
import requests
from bs4 import BeautifulSoup
import re
from decimal import Decimal
from django.utils import timezone


def add_pwa_headers(headers, path, url):
    """
    Dodaje nagłówek Service-Worker-Allowed do pliku sw.js.
    Pozwala to na rejestrację Service Workera w głównym zakresie ('/'),
    nawet jeśli sam plik sw.js jest serwowany z innego katalogu (np. /static/).
    """
    if url == "/static/sw.js":
        headers["Service-Worker-Allowed"] = "/"


def fetch_zus_rates_from_web(year=None):
    """Pobiera aktualne stawki ZUS ze strony ZUS.pl"""
    if year is None:
        year = timezone.now().year

    url = "https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki/skladki/wysokosc-skladek-na-ubezpieczenia-spoleczne"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Szukaj danych w tabelach lub tekście
        rates_data = {
            "year": year,
            "minimum_wage": None,
            "minimum_base": None,
            "source_url": url,
        }

        # Szukaj kwot w złotych (wzorce: 4 300,00 zł, 4300 zł, itp.)
        text_content = soup.get_text()

        # Wzorce do wyszukiwania kwot
        wage_patterns = [
            r"płaca minimalna.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"wynagrodzenie minimalne.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"(\d[\d\s]*[,.]?\d*)\s*zł.*?płaca minimalna",
        ]

        base_patterns = [
            r"podstawa wymiaru.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"minimalna podstawa.*?(\d[\d\s]*[,.]?\d*)\s*zł",
            r"(\d[\d\s]*[,.]?\d*)\s*zł.*?podstawa wymiaru",
        ]

        # Próbuj wyciągnąć płacę minimalną
        for pattern in wage_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE | re.DOTALL)
            if match:
                amount_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    amount = Decimal(amount_str)
                    if 3000 <= amount <= 10000:  # Realistyczny zakres
                        rates_data["minimum_wage"] = amount
                        break
                except:
                    continue

        # Próbuj wyciągnąć podstawę wymiaru
        for pattern in base_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE | re.DOTALL)
            if match:
                amount_str = match.group(1).replace(" ", "").replace(",", ".")
                try:
                    amount = Decimal(amount_str)
                    if 3000 <= amount <= 10000:  # Realistyczny zakres
                        rates_data["minimum_base"] = amount
                        break
                except:
                    continue

        # Wartości domyślne jeśli nie udało się wyciągnąć
        if not rates_data["minimum_wage"]:
            rates_data["minimum_wage"] = Decimal("4300.00")  # Aktualna na 2024

        if not rates_data["minimum_base"]:
            rates_data["minimum_base"] = rates_data["minimum_wage"] * Decimal(
                "1.092"
            )  # Typowo ok. 109.2% płacy minimalnej

        return rates_data

    except requests.RequestException as e:
        print(f"Błąd pobierania danych z ZUS: {e}")
        # Zwrócić wartości domyślne
        return {
            "year": year,
            "minimum_wage": Decimal("4300.00"),
            "minimum_base": Decimal("4694.40"),
            "source_url": url,
        }
    except Exception as e:
        print(f"Błąd parsowania danych ZUS: {e}")
        return {
            "year": year,
            "minimum_wage": Decimal("4300.00"),
            "minimum_base": Decimal("4694.40"),
            "source_url": url,
        }
