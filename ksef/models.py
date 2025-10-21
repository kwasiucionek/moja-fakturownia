from django.db import models

# kwasiucionek/moja-fakturownia/moja-fakturownia-a0f550ee045da0fa60a613fb7a8884b3052e00a0/ksiegowosc/models.py


class Invoice(models.Model):
    # ... (istniejące pola)

    # === POLA DLA INTEGRACJI Z KSeF ===
    ksef_reference_number = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Numer referencyjny KSeF",
    )
    ksef_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Status w KSeF",
        help_text="Status przetwarzania faktury w KSeF (np. Wysłano, Przetworzono, Błąd)",
    )
    ksef_sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Data wysłania do KSeF"
    )
    ksef_session_id = models.CharField(
        max_length=40,
        blank=True,
        null=True,
        verbose_name="ID sesji KSeF",
        help_text="Numer referencyjny sesji po wysłaniu faktury",
    )
    ksef_processing_description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Opis przetwarzania KSeF",
        help_text="Zawiera komunikaty o błędach lub sukcesie z KSeF",
    )
