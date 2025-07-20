# ksiegowosc/models.py

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

class CompanyInfo(models.Model):
    # Podstawowe dane identyfikacyjne
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Użytkownik")
    company_name = models.CharField(max_length=255, verbose_name="Pełna nazwa firmy")
    short_name = models.CharField(max_length=100, blank=True, verbose_name="Nazwa skrócona")
    tax_id = models.CharField(max_length=20, verbose_name="NIP")
    regon = models.CharField(max_length=20, blank=True, verbose_name="REGON")
    krs = models.CharField(max_length=20, blank=True, verbose_name="KRS")
    
    # Typ działalności gospodarczej
    BUSINESS_TYPES = [
        ('osoba_fizyczna', 'Osoba fizyczna prowadząca działalność gospodarczą'),
        ('spolka_cywilna', 'Spółka cywilna'),
        ('spolka_jawna', 'Spółka jawna'),
        ('spolka_partnerska', 'Spółka partnerska'),
        ('spolka_komandytowa', 'Spółka komandytowa'),
        ('spolka_z_ograniczona', 'Spółka z ograniczoną odpowiedzialnością'),
        ('spolka_akcyjna', 'Spółka akcyjna'),
        ('inne', 'Inne'),
    ]
    business_type = models.CharField(
        max_length=50, 
        choices=BUSINESS_TYPES, 
        default='osoba_fizyczna',
        verbose_name="Forma prawna"
    )
    
    # Adres
    street = models.CharField(max_length=255, verbose_name="Ulica i numer")
    zip_code = models.CharField(max_length=10, verbose_name="Kod pocztowy")
    city = models.CharField(max_length=100, verbose_name="Miasto")
    voivodeship = models.CharField(max_length=50, blank=True, verbose_name="Województwo")
    country = models.CharField(max_length=50, default="Polska", verbose_name="Kraj")
    
    # Dane kontaktowe
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    fax = models.CharField(max_length=20, blank=True, verbose_name="Faks")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    website = models.URLField(blank=True, verbose_name="Strona internetowa")
    
    # Rachunek bankowy
    bank_account_number = models.CharField(max_length=34, verbose_name="Numer konta bankowego")
    bank_name = models.CharField(max_length=100, blank=True, verbose_name="Nazwa banku")
    bank_swift = models.CharField(max_length=20, blank=True, verbose_name="SWIFT/BIC")
    
    # Opcje podatku dochodowego
    INCOME_TAX_TYPES = [
        ('skala_podatkowa', 'Skala podatkowa'),
        ('podatek_liniowy', 'Podatek liniowy (19%)'),
        ('ryczalt_ewidencjonowany', 'Ryczałt od przychodów ewidencjonowanych'),
        ('karta_podatkowa', 'Karta podatkowa'),
        ('opodatkowanie_cit', 'Opodatkowanie CIT'),
    ]
    income_tax_type = models.CharField(
        max_length=50,
        choices=INCOME_TAX_TYPES,
        default='ryczalt_ewidencjonowany',
        verbose_name="Forma opodatkowania"
    )
    
    # Stawka ryczałtu
    LUMP_SUM_RATES = [
        ('2', '2%'),
        ('3', '3%'),
        ('5.5', '5,5%'),
        ('8.5', '8,5%'),
        ('10', '10%'),
        ('12', '12%'),
        ('14', '14%'),
        ('15', '15%'),
        ('17', '17%'),
        ('20', '20%'),
    ]
    lump_sum_rate = models.CharField(
        max_length=10,
        choices=LUMP_SUM_RATES,
        default='14',
        verbose_name="Stawka ryczałtu (%)",
        blank=True
    )
    
    # VAT
    VAT_SETTLEMENT_TYPES = [
        ('miesiecznie', 'Miesięcznie'),
        ('kwartalnie', 'Kwartalnie'),
        ('rocznie', 'Rocznie'),
        ('zwolniony', 'Zwolniony z VAT'),
    ]
    vat_settlement = models.CharField(
        max_length=20,
        choices=VAT_SETTLEMENT_TYPES,
        default='miesiecznie',
        verbose_name="Okres rozliczeniowy VAT"
    )
    
    vat_payer = models.BooleanField(default=True, verbose_name="Płatnik VAT")
    vat_id = models.CharField(max_length=20, blank=True, verbose_name="NIP UE")
    
    # Opcje VAT
    vat_cash_method = models.BooleanField(default=False, verbose_name="Metoda kasowa VAT")
    small_taxpayer_vat = models.BooleanField(default=False, verbose_name="Mały podatnik VAT")
    
    # ZUS
    zus_payer = models.BooleanField(default=True, verbose_name="Płatnik składek ZUS")
    zus_number = models.CharField(max_length=20, blank=True, verbose_name="Numer płatnika ZUS")
    
    ZUS_CODES = [
        ('0510', '0510 - Osoba prowadząca pozarolniczą działalność gospodarczą'),
        ('0570', '0570 - Zleceniobiorca'),
        ('0590', '0590 - Osoba współpracująca'),
        ('0610', '0610 - Osoba duchowna'),
    ]
    zus_code = models.CharField(
        max_length=10,
        choices=ZUS_CODES,
        default='0510',
        verbose_name="Kod tytułu ubezpieczenia ZUS",
        blank=True
    )
    
    # Opcje ZUS
    preferential_zus = models.BooleanField(default=False, verbose_name="Preferencyjne składki ZUS")
    small_zus_plus = models.BooleanField(default=False, verbose_name="Mały ZUS Plus")
    zus_health_insurance_only = models.BooleanField(default=False, verbose_name="Tylko składka zdrowotna")
    
    # Dodatkowe opcje
    pkd_code = models.CharField(max_length=10, blank=True, verbose_name="Kod PKD")
    pkd_description = models.CharField(max_length=255, blank=True, verbose_name="Opis działalności PKD")
    
    # Księgowość
    ACCOUNTING_METHODS = [
        ('ksiegi_rachunkowe', 'Księgi rachunkowe'),
        ('podatkowa_ksiega_przychodow', 'Podatkowa księga przychodów i rozchodów'),
        ('ewidencja_ryczaltowa', 'Ewidencja przychodów (ryczałt)'),
        ('karta_podatkowa', 'Karta podatkowa'),
    ]
    accounting_method = models.CharField(
        max_length=50,
        choices=ACCOUNTING_METHODS,
        default='ewidencja_ryczaltowa',
        verbose_name="Forma ewidencji"
    )
    
    # Daty ważne
    business_start_date = models.DateField(null=True, blank=True, verbose_name="Data rozpoczęcia działalności")
    tax_year_start = models.DateField(null=True, blank=True, verbose_name="Początek roku podatkowego")
    
    # Opcje dodatkowe
    electronic_invoices = models.BooleanField(default=True, verbose_name="Faktury elektroniczne")
    jpk_fa_required = models.BooleanField(default=True, verbose_name="Obowiązek JPK_FA")
    
    # Przedstawiciel ustawowy (dla spółek)
    legal_representative_name = models.CharField(max_length=255, blank=True, verbose_name="Przedstawiciel ustawowy - imię i nazwisko")
    legal_representative_position = models.CharField(max_length=100, blank=True, verbose_name="Stanowisko")
    
    class Meta:
        verbose_name = "Dane Firmy"
        verbose_name_plural = "Dane Firmy"

    def __str__(self):
        return self.company_name

    def get_full_address(self):
        """Zwraca pełny adres jako string"""
        return f"{self.street}, {self.zip_code} {self.city}"
    
    def is_vat_exempt(self):
        """Sprawdza czy firma jest zwolniona z VAT"""
        return self.vat_settlement == 'zwolniony' or not self.vat_payer
    
    def get_tax_rate(self):
        """Zwraca stawkę podatku jako decimal"""
        if self.income_tax_type == 'ryczalt_ewidencjonowany':
            return float(self.lump_sum_rate) / 100 if self.lump_sum_rate else 0.14
        elif self.income_tax_type == 'podatek_liniowy':
            return 0.19
        else:
            return 0.14  # domyślnie


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