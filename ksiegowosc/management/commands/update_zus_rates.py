from django.core.management.base import BaseCommand
from django.utils import timezone
from ksiegowosc.models import ZUSRates
from ksiegowosc.utils import fetch_zus_rates_from_web
from decimal import Decimal

class Command(BaseCommand):
    help = 'Aktualizuje stawki ZUS z oficjalnej strony ZUS.pl'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Rok dla którego pobrać stawki (domyślnie bieżący rok)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Wymuś aktualizację nawet jeśli stawki już istnieją',
        )

    def handle(self, *args, **options):
        year = options['year'] or timezone.now().year
        force = options['force']

        self.stdout.write(
            self.style.SUCCESS(f'Pobieranie stawek ZUS dla roku {year}...')
        )

        # Sprawdź czy stawki już istnieją
        existing_rates = ZUSRates.objects.filter(year=year).first()
        if existing_rates and not force:
            self.stdout.write(
                self.style.WARNING(f'Stawki ZUS dla roku {year} już istnieją. Użyj --force aby je zaktualizować.')
            )
            return

        try:
            # Pobierz dane ze strony ZUS
            rates_data = fetch_zus_rates_from_web(year)
            
            self.stdout.write(f"Pobrane dane:")
            self.stdout.write(f"  - Płaca minimalna: {rates_data['minimum_wage']} PLN")
            self.stdout.write(f"  - Podstawa wymiaru: {rates_data['minimum_base']} PLN")

            # Utwórz lub zaktualizuj stawki
            rates, created = ZUSRates.objects.update_or_create(
                year=year,
                defaults={
                    'minimum_wage': rates_data['minimum_wage'],
                    'minimum_base': rates_data['minimum_base'],
                    'source_url': rates_data['source_url'],
                    'is_current': (year == timezone.now().year),
                    
                    # Standardowe stawki (aktualne na 2024)
                    'pension_rate': Decimal('0.1976'),  # 19.52% + 2.45% = 21.97% ale dzielimy
                    'disability_rate': Decimal('0.015'),   # 1.5%
                    'accident_rate': Decimal('0.0167'),    # 1.67%
                    'labor_fund_rate': Decimal('0.0245'),  # 2.45%
                    'health_insurance_rate': Decimal('0.09'),  # 9%
                    'health_insurance_deductible_rate': Decimal('0.0775'),  # 7.75%
                    'small_zus_plus_threshold': Decimal('120000.00'),  # 120k PLN
                }
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Utworzono nowe stawki ZUS dla roku {year}')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Zaktualizowano stawki ZUS dla roku {year}')
                )

            # Sprawdź czy to bieżący rok i oznacz jako aktualne
            if year == timezone.now().year:
                ZUSRates.objects.exclude(year=year).update(is_current=False)  # POPRAWKA: exclude zamiast year__ne
                rates.is_current = True
                rates.save()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Oznaczono stawki {year} jako aktualne')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Błąd podczas aktualizacji stawek ZUS: {str(e)}')
            )
            raise e
