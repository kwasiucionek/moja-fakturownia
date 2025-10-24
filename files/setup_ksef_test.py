# ksiegowosc/management/commands/setup_ksef_test.py
"""
Automatyczne ustawienie testowego środowiska KSeF

Użycie:
    python manage.py setup_ksef_test --user=username
    python manage.py setup_ksef_test --user=username --with-real-token  # Jeśli masz prawdziwy token testowy
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from ksiegowosc.models import CompanyInfo
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Konfiguruje testowe środowisko KSeF z przykładowymi danymi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            required=True,
            help='Username użytkownika',
        )
        parser.add_argument(
            '--with-real-token',
            action='store_true',
            help='Użyj prawdziwego tokena testowego (musisz go podać gdy zostaniesz zapytany)',
        )

    def generate_test_nip(self):
        """Generuje losowy NIP do testów"""
        # Losowy NIP (10 cyfr)
        nip = ''.join([str(random.randint(0, 9)) for _ in range(10)])
        return nip

    def generate_mock_token(self):
        """Generuje mock token dla testów bez faktycznego API"""
        # Mock token - do testów jednostkowych bez rzeczywistego API
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        token = ''.join(random.choice(chars) for _ in range(64))
        return f"TEST_MOCK_{token}"

    def handle(self, *args, **options):
        username = options['user']
        with_real_token = options['with_real_token']

        self.stdout.write(
            self.style.SUCCESS('=' * 70)
        )
        self.stdout.write(
            self.style.SUCCESS('SETUP TESTOWEGO ŚRODOWISKA KSEF')
        )
        self.stdout.write(
            self.style.SUCCESS('=' * 70)
        )

        # Znajdź użytkownika
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f'✓ Znaleziono użytkownika: {username}')
        except User.DoesNotExist:
            raise CommandError(f'Użytkownik "{username}" nie istnieje')

        # Znajdź lub utwórz CompanyInfo
        company_info, created = CompanyInfo.objects.get_or_create(user=user)
        
        if created:
            self.stdout.write('✓ Utworzono nowy CompanyInfo')

        # Setup danych firmy
        if not company_info.company_name:
            company_info.company_name = "Testowa Firma Sp. z o.o."
            self.stdout.write('✓ Ustawiono nazwę firmy: Testowa Firma Sp. z o.o.')

        if not company_info.tax_id:
            test_nip = self.generate_test_nip()
            company_info.tax_id = test_nip
            self.stdout.write(f'✓ Wygenerowano testowy NIP: {test_nip}')

        # Ustaw środowisko testowe
        company_info.ksef_environment = 'test'
        self.stdout.write('✓ Ustawiono środowisko: TEST')

        # Token KSeF
        if with_real_token:
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(
                self.style.WARNING(
                    'UWAGA: Potrzebujesz prawdziwego tokena testowego z ksef-test.mf.gov.pl'
                )
            )
            self.stdout.write('=' * 70)
            self.stdout.write('')
            self.stdout.write('Jak wygenerować token testowy:')
            self.stdout.write('1. Przejdź do: https://ksef-test.mf.gov.pl/')
            self.stdout.write('2. Kliknij "Dane testowe" → "Utwórz podmiot testowy"')
            self.stdout.write('3. Wybierz typ podmiotu i wygeneruj')
            self.stdout.write('4. Zaloguj się jako ten podmiot')
            self.stdout.write('5. Przejdź do "Zarządzanie tokenami"')
            self.stdout.write('6. Wygeneruj token z uprawnieniem "InvoiceWrite"')
            self.stdout.write('7. Skopiuj token')
            self.stdout.write('')
            
            token = input('Wklej token testowy (lub Enter aby pominąć): ').strip()
            
            if token:
                company_info.ksef_token = token
                token_masked = f"{token[:10]}...{token[-10:]}"
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Ustawiono token: {token_masked}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Pominięto token - ustaw później ręcznie')
                )
        else:
            # Mock token dla testów bez API
            mock_token = self.generate_mock_token()
            company_info.ksef_token = mock_token
            self.stdout.write(
                self.style.WARNING(
                    f'✓ Wygenerowano MOCK token: {mock_token[:20]}...\n'
                    f'  ⚠ To jest token testowy - NIE będzie działał z prawdziwym API!\n'
                    f'  ⚠ Użyj --with-real-token aby podać prawdziwy token testowy'
                )
            )

        company_info.save()

        # Podsumowanie
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('KONFIGURACJA ZAKOŃCZONA'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Użytkownik:     {username}')
        self.stdout.write(f'Firma:          {company_info.company_name}')
        self.stdout.write(f'NIP:            {company_info.tax_id}')
        self.stdout.write(f'Środowisko:     {company_info.ksef_environment}')
        
        if company_info.ksef_token:
            if company_info.ksef_token.startswith('TEST_MOCK_'):
                self.stdout.write(
                    self.style.WARNING(
                        f'Token:          MOCK (nie działa z API)'
                    )
                )
            else:
                token_masked = f"{company_info.ksef_token[:10]}...{company_info.ksef_token[-10:]}"
                self.stdout.write(
                    self.style.SUCCESS(f'Token:          {token_masked}')
                )
        else:
            self.stdout.write(
                self.style.WARNING('Token:          BRAK')
            )

        self.stdout.write('')
        self.stdout.write('Następne kroki:')
        
        if not company_info.ksef_token or company_info.ksef_token.startswith('TEST_MOCK_'):
            self.stdout.write('1. Wygeneruj prawdziwy token testowy na: https://ksef-test.mf.gov.pl/')
            self.stdout.write('2. Uruchom ponownie z: python manage.py setup_ksef_test --user={} --with-real-token'.format(username))
        else:
            self.stdout.write('1. Testuj wysyłkę faktur!')
            self.stdout.write('2. Sprawdź w panelu: https://ksef-test.mf.gov.pl/')

        self.stdout.write('=' * 70)
