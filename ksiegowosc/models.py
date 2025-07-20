# ksiegowosc/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

class CompanyInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    company_name = models.CharField(max_length=255, verbose_name="Pełna nazwa firmy")
    tax_id = models.CharField(max_length=20, verbose_name="NIP")
    street = models.CharField(max_length=255, verbose_name="Ulica i numer")
    zip_code = models.CharField(max_length=10, verbose_name="Kod pocztowy")
    city = models.CharField(max_length=100, verbose_name="Miasto")
    bank_account_number = models.CharField(max_length=34, verbose_name="Numer konta bankowego")

    class Meta:
        verbose_name = "Dane Firmy"
        verbose_name_plural = "Dane Firmy"

    def __str__(self):
        return self.company_name


class Contractor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    name = models.CharField(max_length=255, verbose_name="Nazwa kontrahenta")
    tax_id = models.CharField(max_length=20, verbose_name="NIP", blank=True, null=True, help_text="Wypełnij, jeśli dotyczy")
    street = models.CharField(max_length=255, verbose_name="Ulica i numer", blank=True, default="")
    zip_code = models.CharField(max_length=10, verbose_name="Kod pocztowy", blank=True, default="")
    city = models.CharField(max_length=100, verbose_name="Miasto", blank=True, default="")

    class Meta:
        verbose_name = "Kontrahent"
        verbose_name_plural = "Kontrahenci"
        ordering = ['name']
        unique_together = ['user', 'tax_id']  # Zapobiega duplikatom NIP per użytkownik

    def __str__(self):
        return self.name

class Invoice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice_number = models.CharField(max_length=50, unique=True, verbose_name="Numer faktury")
    issue_date = models.DateField(default=timezone.now, verbose_name="Data wystawienia")
    sale_date = models.DateField(default=timezone.now, verbose_name="Data sprzedaży")
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, verbose_name="Kontrahent")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Kwota całkowita")
    payment_method = models.CharField(
        max_length=50, 
        choices=[('przelew', 'Przelew'), ('gotówka', 'Gotówka')], 
        default='przelew', 
        verbose_name="Sposób płatności"
    )
    payment_date = models.DateField(verbose_name="Termin płatności", blank=True, null=True)
    notes = models.TextField(blank=True, null=True, verbose_name="Uwagi")
    is_correction = models.BooleanField(default=False, verbose_name="Czy to korekta?")
    correction_reason = models.TextField(blank=True, null=True, verbose_name="Przyczyna korekty")
    corrected_invoice = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='corrections',
        verbose_name="Faktura korygowana"
     )

    class Meta:
        verbose_name = "Faktura"
        verbose_name_plural = "Faktury"
        ordering = ['-issue_date']

    def __str__(self):
        return f"Faktura {self.invoice_number} dla {self.contractor.name}"

    def save(self, *args, **kwargs):
        # Automatycznie ustaw payment_date jeśli nie jest ustawione
        if not self.payment_date:
            self.payment_date = self.issue_date + timedelta(days=14)  # 14 dni termin płatności
        super().save(*args, **kwargs)

    def update_total_amount(self):
        """Metoda do aktualizacji sumy faktury na podstawie jej pozycji."""
        total = self.items.aggregate(total=models.Sum('total_price'))['total'] or 0.00
        self.total_amount = total
        self.save(update_fields=['total_amount'])


class InvoiceItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE, verbose_name="Faktura")
    name = models.CharField(max_length=255, verbose_name="Nazwa usługi")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ilość")
    unit = models.CharField(max_length=10, default='godz.', verbose_name="J.M.")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cena jedn.")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Wartość")
    lump_sum_tax_rate = models.DecimalField(max_digits=4, decimal_places=2, default=14.00, verbose_name="Stawka ryczałtu (%)")

    class Meta:
        verbose_name = "Pozycja na fakturze"
        verbose_name_plural = "Pozycje na fakturze"

    def save(self, *args, **kwargs):
        # Automatyczne obliczanie wartości dla pozycji
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        # Po zapisaniu pozycji, aktualizujemy sumę całej faktury
        self.invoice.update_total_amount()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        # Po usunięciu pozycji, również aktualizujemy sumę
        invoice.update_total_amount()

    def __str__(self):
        return self.name

class MonthlySettlement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    month = models.IntegerField(verbose_name="Miesiąc")
    year = models.IntegerField(verbose_name="Rok")
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Przychód w danym miesiącu")
    health_insurance_paid = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Opłacona składka zdrowotna")
    income_tax_payable = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Należny podatek dochodowy")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rozliczenie miesięczne"
        verbose_name_plural = "Rozliczenia miesięczne"
        unique_together = ('year', 'month', 'user')  # Dodano user do unique_together
        ordering = ['-year', '-month']

    def __str__(self):
        return f"Rozliczenie za {self.month}/{self.year}"