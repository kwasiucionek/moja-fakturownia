# ksiegowosc/migrations/0003_extend_companyinfo.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ksiegowosc', '0002_alter_contractor_city_alter_contractor_street_and_more'),
    ]

    operations = [
        # Dodaj nowe pola do CompanyInfo
        migrations.AddField(
            model_name='companyinfo',
            name='short_name',
            field=models.CharField(blank=True, max_length=100, verbose_name='Nazwa skrócona'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='regon',
            field=models.CharField(blank=True, max_length=20, verbose_name='REGON'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='krs',
            field=models.CharField(blank=True, max_length=20, verbose_name='KRS'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='business_type',
            field=models.CharField(choices=[('osoba_fizyczna', 'Osoba fizyczna prowadząca działalność gospodarczą'), ('spolka_cywilna', 'Spółka cywilna'), ('spolka_jawna', 'Spółka jawna'), ('spolka_partnerska', 'Spółka partnerska'), ('spolka_komandytowa', 'Spółka komandytowa'), ('spolka_z_ograniczona', 'Spółka z ograniczoną odpowiedzialnością'), ('spolka_akcyjna', 'Spółka akcyjna'), ('inne', 'Inne')], default='osoba_fizyczna', max_length=50, verbose_name='Forma prawna'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='voivodeship',
            field=models.CharField(blank=True, max_length=50, verbose_name='Województwo'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='country',
            field=models.CharField(default='Polska', max_length=50, verbose_name='Kraj'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='Telefon'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='fax',
            field=models.CharField(blank=True, max_length=20, verbose_name='Faks'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='E-mail'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='website',
            field=models.URLField(blank=True, verbose_name='Strona internetowa'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='bank_name',
            field=models.CharField(blank=True, max_length=100, verbose_name='Nazwa banku'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='bank_swift',
            field=models.CharField(blank=True, max_length=20, verbose_name='SWIFT/BIC'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='income_tax_type',
            field=models.CharField(choices=[('skala_podatkowa', 'Skala podatkowa'), ('podatek_liniowy', 'Podatek liniowy (19%)'), ('ryczalt_ewidencjonowany', 'Ryczałt od przychodów ewidencjonowanych'), ('karta_podatkowa', 'Karta podatkowa'), ('opodatkowanie_cit', 'Opodatkowanie CIT')], default='ryczalt_ewidencjonowany', max_length=50, verbose_name='Forma opodatkowania'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='lump_sum_rate',
            field=models.CharField(blank=True, choices=[('2', '2%'), ('3', '3%'), ('5.5', '5,5%'), ('8.5', '8,5%'), ('10', '10%'), ('12', '12%'), ('14', '14%'), ('15', '15%'), ('17', '17%'), ('20', '20%')], default='14', max_length=10, verbose_name='Stawka ryczałtu (%)'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='vat_settlement',
            field=models.CharField(choices=[('miesiecznie', 'Miesięcznie'), ('kwartalnie', 'Kwartalnie'), ('rocznie', 'Rocznie'), ('zwolniony', 'Zwolniony z VAT')], default='miesiecznie', max_length=20, verbose_name='Okres rozliczeniowy VAT'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='vat_payer',
            field=models.BooleanField(default=True, verbose_name='Płatnik VAT'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='vat_id',
            field=models.CharField(blank=True, max_length=20, verbose_name='NIP UE'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='vat_cash_method',
            field=models.BooleanField(default=False, verbose_name='Metoda kasowa VAT'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='small_taxpayer_vat',
            field=models.BooleanField(default=False, verbose_name='Mały podatnik VAT'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='zus_payer',
            field=models.BooleanField(default=True, verbose_name='Płatnik składek ZUS'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='zus_number',
            field=models.CharField(blank=True, max_length=20, verbose_name='Numer płatnika ZUS'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='zus_code',
            field=models.CharField(blank=True, choices=[('0510', '0510 - Osoba prowadząca pozarolniczą działalność gospodarczą'), ('0570', '0570 - Zleceniobiorca'), ('0590', '0590 - Osoba współpracująca'), ('0610', '0610 - Osoba duchowna')], default='0510', max_length=10, verbose_name='Kod tytułu ubezpieczenia ZUS'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='preferential_zus',
            field=models.BooleanField(default=False, verbose_name='Preferencyjne składki ZUS'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='small_zus_plus',
            field=models.BooleanField(default=False, verbose_name='Mały ZUS Plus'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='zus_health_insurance_only',
            field=models.BooleanField(default=False, verbose_name='Tylko składka zdrowotna'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='pkd_code',
            field=models.CharField(blank=True, max_length=10, verbose_name='Kod PKD'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='pkd_description',
            field=models.CharField(blank=True, max_length=255, verbose_name='Opis działalności PKD'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='accounting_method',
            field=models.CharField(choices=[('ksiegi_rachunkowe', 'Księgi rachunkowe'), ('podatkowa_ksiega_przychodow', 'Podatkowa księga przychodów i rozchodów'), ('ewidencja_ryczaltowa', 'Ewidencja przychodów (ryczałt)'), ('karta_podatkowa', 'Karta podatkowa')], default='ewidencja_ryczaltowa', max_length=50, verbose_name='Forma ewidencji'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='business_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='Data rozpoczęcia działalności'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='tax_year_start',
            field=models.DateField(blank=True, null=True, verbose_name='Początek roku podatkowego'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='electronic_invoices',
            field=models.BooleanField(default=True, verbose_name='Faktury elektroniczne'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='jpk_fa_required',
            field=models.BooleanField(default=True, verbose_name='Obowiązek JPK_FA'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='legal_representative_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Przedstawiciel ustawowy - imię i nazwisko'),
        ),
        migrations.AddField(
            model_name='companyinfo',
            name='legal_representative_position',
            field=models.CharField(blank=True, max_length=100, verbose_name='Stanowisko'),
        ),
    ]