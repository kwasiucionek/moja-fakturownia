# ksiegowosc/management/commands/create_superuser_with_company.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from ksiegowosc.models import CompanyInfo
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = 'Tworzy superusera z podstawowymi danymi firmy'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Nazwa użytkownika')
        parser.add_argument('--email', type=str, help='Email')
        parser.add_argument('--password', type=str, help='Hasło')
        parser.add_argument('--company-name', type=str, help='Nazwa firmy')
        parser.add_argument('--nip', type=str, help='NIP firmy')

    def handle(self, *args, **options):
        username = options.get('username') or input('Nazwa użytkownika: ')
        email = options.get('email') or input('Email: ')
        password = options.get('password') or input('Hasło: ')
        company_name = options.get('company_name') or input('Nazwa firmy: ')
        nip = options.get('nip') or input('NIP firmy: ')

        try:
            # Sprawdź czy użytkownik już istnieje
            if User.objects.filter(username=username).exists():
                self.stdout.write(
                    self.style.ERROR(f'Użytkownik {username} już istnieje!')
                )
                return

            # Utwórz superusera
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )

            # Dodaj do grupy ksiegowosc
            ksiegowosc_group, _ = Group.objects.get_or_create(name='ksiegowosc')
            user.groups.add(ksiegowosc_group)

            self.stdout.write(
                self.style.SUCCESS(f'✓ Utworzono superusera: {username}')
            )

            # Utwórz podstawowe dane firmy
            company_info = CompanyInfo.objects.create(
                user=user,
                company_name=company_name,
                tax_id=nip,
                street='',
                zip_code='',
                city='',
                bank_account_number='',
                business_type='osoba_fizyczna',
                income_tax_type='ryczalt_ewidencjonowany',
                lump_sum_rate='14',
            )

            self.stdout.write(
                self.style.SUCCESS(f'✓ Utworzono dane firmy: {company_name}')
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Superuser {username} z firmą {company_name} został utworzony!'
                )
            )

        except ValidationError as e:
            self.stdout.write(
                self.style.ERROR(f'Błąd walidacji: {e}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Błąd: {e}')
            )

