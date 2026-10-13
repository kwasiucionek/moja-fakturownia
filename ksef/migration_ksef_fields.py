# ksiegowosc/migrations/XXXX_add_ksef_fields.py
# Uruchom: python manage.py makemigrations --name add_ksef_fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ksiegowosc', 'POPRZEDNIA_MIGRACJA'),  # Zmień na ostatnią migrację
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='ksef_reference',
            field=models.CharField(
                max_length=100, 
                blank=True, 
                null=True,
                verbose_name='Numer referencyjny KSeF',
                help_text='Numer nadany przez KSeF po wysłaniu faktury'
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='ksef_session_reference',
            field=models.CharField(
                max_length=100, 
                blank=True, 
                null=True,
                verbose_name='Nr sesji KSeF'
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='ksef_sent_at',
            field=models.DateTimeField(
                blank=True, 
                null=True,
                verbose_name='Data wysłania do KSeF'
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='ksef_status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('draft', 'Szkic'),
                    ('pending', 'Oczekuje'),
                    ('sent', 'Wysłana'),
                    ('confirmed', 'Potwierdzona'),
                    ('error', 'Błąd'),
                ],
                default='draft',
                verbose_name='Status KSeF'
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='ksef_number',
            field=models.CharField(
                max_length=100, 
                blank=True, 
                null=True,
                verbose_name='Numer KSeF',
                help_text='Oficjalny numer faktury w KSeF'
            ),
        ),
    ]
