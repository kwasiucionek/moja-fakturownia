# ksiegowosc/management/commands/set_ksef_token.py
"""
Django management command do ustawiania tokena KSeF

Użycie:
    python manage.py set_ksef_token --user=username --token="YOUR_TOKEN_HERE"
    python manage.py set_ksef_token --user=username --token="YOUR_TOKEN_HERE" --environment=prod
    python manage.py set_ksef_token --user=username --show  # Pokaż obecny token
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from ksiegowosc.models import CompanyInfo

User = get_user_model()


class Command(BaseCommand):
    help = 'Zarządzanie tokenem KSeF dla użytkownika'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            required=True,
            help='Username użytkownika',
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Token KSeF do ustawienia',
        )
        parser.add_argument(
            '--environment',
            type=str,
            choices=['test', 'prod'],
            default='test',
            help='Środowisko KSeF (test/prod)',
        )
        parser.add_argument(
            '--show',
            action='store_true',
            help='Pokaż obecny token',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Usuń token',
        )

    def handle(self, *args, **options):
        username = options['user']
        token = options.get('token')
        environment = options['environment']
        show = options['show']
        clear = options['clear']

        # Znajdź użytkownika
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'Użytkownik "{username}" nie istnieje')

        # Znajdź lub utwórz CompanyInfo
        company_info, created = CompanyInfo.objects.get_or_create(user=user)

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Utworzono nowy CompanyInfo dla użytkownika {username}')
            )

        # POKAŻ OBECNY TOKEN
        if show:
            if company_info.ksef_token:
                # Pokaż tylko pierwsze i ostatnie znaki
                token_masked = f"{company_info.ksef_token[:10]}...{company_info.ksef_token[-10:]}"
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Obecny token KSeF: {token_masked}\n'
                        f'Długość: {len(company_info.ksef_token)} znaków\n'
                        f'Środowisko: {company_info.ksef_environment}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Brak tokena KSeF')
                )
            return

        # USUŃ TOKEN
        if clear:
            company_info.ksef_token = None
            company_info.save()
            self.stdout.write(
                self.style.SUCCESS('Token KSeF usunięty')
            )
            return

        # USTAW TOKEN
        if token:
            # Walidacja tokena
            token = token.strip()
            
            if len(token) < 20:
                raise CommandError('Token jest za krótki. Sprawdź czy skopiowałeś cały token.')

            # Zapisz token i środowisko
            company_info.ksef_token = token
            company_info.ksef_environment = environment
            company_info.save()

            token_masked = f"{token[:10]}...{token[-10:]}"
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Token KSeF ustawiony pomyślnie!\n'
                    f'  Token: {token_masked}\n'
                    f'  Długość: {len(token)} znaków\n'
                    f'  Środowisko: {environment}\n'
                    f'  Użytkownik: {username}'
                )
            )

            # Sprawdź czy są inne wymagane dane
            warnings = []
            if not company_info.tax_id:
                warnings.append('⚠ Brak NIP - ustaw w admin panel')
            if not company_info.company_name:
                warnings.append('⚠ Brak nazwy firmy - ustaw w admin panel')

            if warnings:
                self.stdout.write(
                    self.style.WARNING('\nUwagi:')
                )
                for warning in warnings:
                    self.stdout.write(f'  {warning}')

        else:
            raise CommandError(
                'Musisz podać --token lub użyć --show lub --clear\n'
                'Przykład: python manage.py set_ksef_token --user=admin --token="TWOJ_TOKEN"'
            )
