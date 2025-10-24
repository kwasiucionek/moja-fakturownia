# ksiegowosc/management/commands/configure_ksef_test.py
"""
Konfiguracja środowiska testowego KSeF

Użycie:
    python manage.py configure_ksef_test --user=username
    python manage.py configure_ksef_test --user=username --nip=1234567890 --token="TOKEN"
    python manage.py configure_ksef_test --all  # Ustaw test dla wszystkich firm (dev only!)
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from ksiegowosc.models import CompanyInfo

User = get_user_model()


class Command(BaseCommand):
    help = 'Konfiguruje środowisko testowe KSeF dla użytkownika'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username użytkownika',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Ustaw środowisko testowe dla WSZYSTKICH firm (tylko development!)',
        )
        parser.add_argument(
            '--nip',
            type=str,
            help='NIP podmiotu testowego z ksef-test.mf.gov.pl',
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Token KSeF wygenerowany w środowisku testowym',
        )
        parser.add_argument(
            '--company-name',
            type=str,
            help='Nazwa firmy testowej',
        )

    def handle(self, *args, **options):
        username = options.get('user')
        set_all = options['all']
        nip = options.get('nip')
        token = options.get('token')
        company_name = options.get('company_name')

        self.stdout.write(
            self.style.SUCCESS('=' * 70)
        )
        self.stdout.write(
            self.style.SUCCESS('KONFIGURACJA ŚRODOWISKA TESTOWEGO KSEF')
        )
        self.stdout.write(
            self.style.SUCCESS('https://ksef-test.mf.gov.pl/api/v2')
        )
        self.stdout.write(
            self.style.SUCCESS('=' * 70)
        )
        self.stdout.write('')

        if set_all:
            # WSZYSTKIE FIRMY - TYLKO DEV!
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  UWAGA: Ustawiasz środowisko testowe dla WSZYSTKICH firm!'
                )
            )
            confirm = input('Kontynuować? (yes/no): ')
            
            if confirm.lower() != 'yes':
                self.stdout.write('Anulowano.')
                return

            count = CompanyInfo.objects.update(ksef_environment='test')
            self.stdout.write(
                self.style.SUCCESS(f'✓ Zaktualizowano {count} firm na środowisko testowe')
            )
            return

        if not username:
            raise CommandError('Podaj --user=username lub użyj --all')

        # Znajdź użytkownika
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f'✓ Znaleziono użytkownika: {username}')
        except User.DoesNotExist:
            raise CommandError(f'Użytkownik "{username}" nie istnieje')

        # Znajdź lub utwórz CompanyInfo
        company_info, created = CompanyInfo.objects.get_or_create(user=user)
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('✓ Utworzono nowy CompanyInfo')
            )

        # Ustaw środowisko testowe
        company_info.ksef_environment = 'test'
        self.stdout.write('✓ Ustawiono środowisko: TEST')

        # NIP
        if nip:
            # Normalizuj NIP
            nip_normalized = nip.replace('-', '').replace(' ', '').strip()
            if len(nip_normalized) == 10 and nip_normalized.isdigit():
                company_info.tax_id = nip_normalized
                self.stdout.write(f'✓ Ustawiono NIP: {nip_normalized}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Nieprawidłowy NIP: {nip} (pomijam)')
                )
        elif not company_info.tax_id:
            self.stdout.write(
                self.style.WARNING('⚠️  Brak NIP - ustaw później lub podaj --nip')
            )

        # Token
        if token:
            company_info.ksef_token = token.strip()
            token_masked = f"{token[:10]}...{token[-10:]}"
            self.stdout.write(f'✓ Ustawiono token: {token_masked}')
        elif not company_info.ksef_token:
            self.stdout.write(
                self.style.WARNING('⚠️  Brak tokena - ustaw później lub podaj --token')
            )

        # Nazwa firmy
        if company_name:
            company_info.company_name = company_name
            self.stdout.write(f'✓ Ustawiono nazwę: {company_name}')
        elif not company_info.company_name:
            self.stdout.write(
                self.style.WARNING('⚠️  Brak nazwy firmy - ustaw później lub podaj --company-name')
            )

        company_info.save()

        # Podsumowanie
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('✓ KONFIGURACJA ZAKOŃCZONA'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Użytkownik:      {username}')
        self.stdout.write(f'Środowisko:      TEST (https://ksef-test.mf.gov.pl)')
        self.stdout.write(f'Nazwa firmy:     {company_info.company_name or "BRAK"}')
        self.stdout.write(f'NIP:             {company_info.tax_id or "BRAK"}')
        
        if company_info.ksef_token:
            token_masked = f"{company_info.ksef_token[:10]}...{company_info.ksef_token[-10:]}"
            self.stdout.write(f'Token:           {token_masked}')
        else:
            self.stdout.write(
                self.style.WARNING('Token:           BRAK')
            )

        self.stdout.write('')
        self.stdout.write('Następne kroki:')
        
        if not company_info.ksef_token or not company_info.tax_id:
            self.stdout.write('')
            self.stdout.write('1. Przejdź do: https://ksef-test.mf.gov.pl/')
            self.stdout.write('2. "Dane testowe" → "Utwórz podmiot testowy"')
            self.stdout.write('3. Skopiuj wygenerowany NIP')
            self.stdout.write('4. Zaloguj się jako ten podmiot')
            self.stdout.write('5. "Zarządzanie tokenami" → "Wygeneruj token"')
            self.stdout.write('6. Uruchom ponownie z: --nip i --token')
        else:
            self.stdout.write('')
            self.stdout.write('✓ Możesz teraz wysyłać faktury testowe!')
            self.stdout.write('  Faktury nie będą miały skutków podatkowych')
            self.stdout.write('  i zostaną automatycznie usunięte')

        self.stdout.write('')
        self.stdout.write('=' * 70)
