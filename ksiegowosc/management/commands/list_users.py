# ksiegowosc/management/commands/list_users.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ksiegowosc.models import CompanyInfo


class Command(BaseCommand):
    help = 'Wyświetla listę wszystkich użytkowników z podstawowymi informacjami'

    def handle(self, *args, **options):
        users = User.objects.all().order_by('date_joined')

        self.stdout.write('Lista użytkowników w systemie:')
        self.stdout.write('=' * 60)

        for user in users:
            # Informacje podstawowe
            status = []
            if user.is_superuser:
                status.append('SUPER')
            if user.is_staff:
                status.append('STAFF')
            if not user.is_active:
                status.append('NIEAKTYWNY')

            status_str = f"[{', '.join(status)}]" if status else "[USER]"

            # Grupy
            groups = list(user.groups.values_list('name', flat=True))
            groups_str = ', '.join(groups) if groups else 'brak grup'

            # Dane firmy
            try:
                company_info = CompanyInfo.objects.get(user=user)
                company_str = f"{company_info.company_name} (NIP: {company_info.tax_id})"
            except CompanyInfo.DoesNotExist:
                company_str = "BRAK DANYCH FIRMY"

            self.stdout.write(
                f"{user.username:20} {status_str:15} {user.email:30}"
            )
            self.stdout.write(
                f"{'':20} Grupy: {groups_str}"
            )
            self.stdout.write(
                f"{'':20} Firma: {company_str}"
            )
            self.stdout.write(
                f"{'':20} Dołączył: {user.date_joined.strftime('%d.%m.%Y %H:%M')}"
            )
            self.stdout.write('-' * 60)

        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        users_with_companies = User.objects.filter(companyinfo__isnull=False).count()

        self.stdout.write(f'\nPodsumowanie:')
        self.stdout.write(f'Łączna liczba użytkowników: {total_users}')
        self.stdout.write(f'Aktywni użytkownicy: {active_users}')
        self.stdout.write(f'Użytkownicy z danymi firmy: {users_with_companies}')

