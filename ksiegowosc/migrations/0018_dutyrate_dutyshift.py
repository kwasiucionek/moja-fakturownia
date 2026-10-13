# Generated for the duty-shift (dyżury) module
# Zależność dopasowana do Twojej realnej numeracji migracji na serwerze
# (ostatnia zaaplikowana: 0017_alter_companyinfo_ksef_environment_and_more)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ksiegowosc', '0017_alter_companyinfo_ksef_environment_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DutyShift',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Data dyżuru')),
                ('start_time', models.TimeField(verbose_name='Od godziny')),
                ('end_time', models.TimeField(verbose_name='Do godziny')),
                ('hours', models.DecimalField(blank=True, decimal_places=2, help_text='Liczone automatycznie z Od/Do (dyżur przechodzący przez północ liczony poprawnie). Można nadpisać ręcznie.', max_digits=5, verbose_name='Suma godzin')),
                ('shift_type', models.CharField(choices=[('samodzielny', 'Samodzielny'), ('towarzyszacy', 'Towarzyszący')], default='towarzyszacy', max_length=20, verbose_name='Rodzaj dyżuru')),
                ('is_holiday', models.BooleanField(default=False, help_text='Zaznacz dla świąt wypadających w dzień roboczy — dyżur zostanie rozliczony jak weekendowy.', verbose_name='Święto')),
                ('department', models.CharField(blank=True, default='', max_length=100, verbose_name='Oddział (OPK)')),
                ('rate_applied', models.DecimalField(blank=True, decimal_places=2, help_text='Uzupełniane automatycznie przy wystawianiu faktury — wartość historyczna, nie zmienia się przy późniejszej zmianie cennika.', max_digits=8, null=True, verbose_name='Zastosowana stawka')),
                ('notes', models.CharField(blank=True, default='', max_length=255, verbose_name='Uwagi')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('contractor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='ksiegowosc.contractor', verbose_name='Kontrahent (szpital/placówka)')),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='duty_shifts', to='ksiegowosc.invoice', verbose_name='Rozliczono na fakturze')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Użytkownik')),
            ],
            options={
                'verbose_name': 'Dyżur',
                'verbose_name_plural': 'Dyżury',
                'ordering': ['date', 'start_time'],
            },
        ),
        migrations.CreateModel(
            name='DutyRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valid_from', models.DateField(verbose_name='Obowiązuje od')),
                ('rate_weekday_towarzyszacy', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Stawka godz. — dzień roboczy, towarzyszący')),
                ('rate_weekday_samodzielny', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Stawka godz. — dzień roboczy, samodzielny')),
                ('rate_weekend_towarzyszacy', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Stawka godz. — weekend/święto, towarzyszący')),
                ('rate_weekend_samodzielny', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Stawka godz. — weekend/święto, samodzielny')),
                ('contractor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ksiegowosc.contractor', verbose_name='Kontrahent (szpital/placówka)')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Użytkownik')),
            ],
            options={
                'verbose_name': 'Stawka za dyżur',
                'verbose_name_plural': 'Stawki za dyżury',
                'ordering': ['-valid_from'],
                'unique_together': {('user', 'contractor', 'valid_from')},
            },
        ),
    ]
