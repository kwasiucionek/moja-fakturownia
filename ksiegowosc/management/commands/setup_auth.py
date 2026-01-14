# ksiegowosc/management/commands/setup_auth.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from ksiegowosc.models import CompanyInfo, Contractor, Invoice, MonthlySettlement, YearlySettlement, ZUSRates, Payment, PurchaseInvoice, ExpenseCategory


class Command(BaseCommand):
    help = 'Tworzy grupę ksiegowosc i przypisuje odpowiednie uprawnienia'

    def handle(self, *args, **options):
        self.stdout.write('Tworzenie grupy ksiegowosc...')

        # Utwórz grupę
        group, created = Group.objects.get_or_create(name='ksiegowosc')

        if created:
            self.stdout.write(
                self.style.SUCCESS('✓ Utworzono grupę "ksiegowosc"')
            )
        else:
            self.stdout.write(
                self.style.WARNING('⚠ Grupa "ksiegowosc" już istnieje')
            )

        # Lista modeli do których przypisać uprawnienia
        models_to_grant = [
            CompanyInfo,
            Contractor,
            Invoice,
            MonthlySettlement,
            YearlySettlement,
            ZUSRates,
            Payment,
            PurchaseInvoice,
            ExpenseCategory,
        ]

        permissions_added = 0

        for model in models_to_grant:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)

            for permission in permissions:
                group.permissions.add(permission)
                permissions_added += 1

            self.stdout.write(f'✓ Dodano uprawnienia dla {model.__name__}')

        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Pomyślnie skonfigurowano grupę "ksiegowosc" z {permissions_added} uprawnieniami'
            )
        )

        # Wyświetl informacje o uprawnieniach
        self.stdout.write('\nUprawnienia w grupie "ksiegowosc":')
        for perm in group.permissions.all():
            self.stdout.write(f'  - {perm.name}')
