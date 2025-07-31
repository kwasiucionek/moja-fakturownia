# ksiegowosc/management/commands/fix_user_permissions.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from ksiegowosc.models import CompanyInfo, Contractor, Invoice, MonthlySettlement


class Command(BaseCommand):
    help = 'Naprawia uprawnienia dla istniejących użytkowników'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Nazwa konkretnego użytkownika (opcjonalnie)'
        )

    def handle(self, *args, **options):
        username = options.get('username')

        if username:
            try:
                users = [User.objects.get(username=username)]
                self.stdout.write(f'Naprawiam uprawnienia dla użytkownika: {username}')
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Użytkownik {username} nie istnieje!')
                )
                return
        else:
            users = User.objects.filter(is_active=True)
            self.stdout.write('Naprawiam uprawnienia dla wszystkich aktywnych użytkowników...')

        # Upewnij się, że grupa istnieje
        ksiegowosc_group, created = Group.objects.get_or_create(name='ksiegowosc')

        if created:
            self.stdout.write('✓ Utworzono grupę "ksiegowosc"')

        fixed_users = 0

        for user in users:
            try:
                # Przypisz do grupy ksiegowosc
                user.groups.add(ksiegowosc_group)

                # Ustaw is_staff jeśli nie jest superuserem
                if not user.is_superuser and not user.is_staff:
                    user.is_staff = True
                    user.save()

                # Dodaj uprawnienia do modeli księgowości
                models_to_grant = [CompanyInfo, Contractor, Invoice, MonthlySettlement]
                permissions_to_grant = []

                for model in models_to_grant:
                    content_type = ContentType.objects.get_for_model(model)
                    permissions = Permission.objects.filter(content_type=content_type)
                    permissions_to_grant.extend(permissions)

                user.user_permissions.set(permissions_to_grant)

                fixed_users += 1
                self.stdout.write(f'✓ Naprawiono uprawnienia dla: {user.username}')

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Błąd dla użytkownika {user.username}: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'✓ Naprawiono uprawnienia dla {fixed_users} użytkowników')
        )

